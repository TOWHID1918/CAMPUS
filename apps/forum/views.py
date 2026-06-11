from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import JsonResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.academics.models import Department, Course
from apps.common.choices import ForumThreadStatus, ThreadVisibility

from .forms import ForumThreadCreateForm, ForumThreadEditForm, ThreadMessageForm
from .filters import ForumThreadFilter
from .models import ForumThread, ForumThreadFollower
from .services import (
    get_current_trimester,
    create_forum_thread,
    create_thread_message,
    update_forum_thread,
    soft_delete_forum_thread,
    toggle_exclusive_message_pin,
    toggle_message_vote,
    toggle_thread_follow,
    build_active_filters,
    apply_forum_thread_filters,
)


@login_required
def public_threads(request):
    """List and filter forum threads with active filter context."""
    threads_qs = (
        ForumThread.objects.select_related(
            "thread", "author", "course", "department", "trimester"
        )
        .filter(
            Q(thread__visibility=ThreadVisibility.PUBLIC),
            status=ForumThreadStatus.ACTIVE,
            is_announcement=False,
        )
        .distinct()
        .order_by("-thread__created_at")
    )

    filterset = ForumThreadFilter(request.GET, queryset=threads_qs)

    # Build active_filters for the chip UI from the validated filterset data
    active_filters = build_active_filters(filterset)

    paginator = Paginator(filterset.qs, 20)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "threads": page,
        "active_filters": active_filters,
        "filterset": filterset,
    }
    return render(request, "forum/public_threads.html", context)


@login_required
def announcement_threads(request):
    """List all announcement threads."""
    threads = (
        ForumThread.objects.select_related(
            "thread", "author", "course", "department", "trimester"
        )
        .filter(
            thread__visibility=ThreadVisibility.PUBLIC,
            is_announcement=True,
            status=ForumThreadStatus.ACTIVE,
        )
        .order_by("-thread__created_at")
    )
    return render(request, "forum/announcement_threads.html", {"threads": threads})


@login_required
def my_threads(request):
    """List threads created by the current user."""
    threads = (
        ForumThread.objects.select_related(
            "thread", "author", "course", "department", "trimester"
        )
        .filter(author=request.user, status=ForumThreadStatus.ACTIVE)
        .order_by("-thread__created_at")
    )

    filter_dept_code = request.GET.get("department")
    filter_course_code = request.GET.get("course")

    threads, active_filters = apply_forum_thread_filters(
        threads,
        department_code=filter_dept_code,
        course_code=filter_course_code,
    )

    return render(
        request,
        "forum/my_threads.html",
        {"threads": threads, "active_filters": active_filters},
    )


@login_required
def my_participating_threads(request):
    """List threads where the user is a participant (but not the author)."""
    threads = (
        ForumThread.objects.select_related(
            "thread", "author", "course", "department", "trimester"
        )
        .filter(
            thread__participants__user=request.user, status=ForumThreadStatus.ACTIVE
        )
        .exclude(author=request.user)
        .distinct()
        .order_by("-thread__created_at")
    )
    return render(request, "forum/my_participating_threads.html", {"threads": threads})


@login_required
def my_following_threads(request):
    followed = (
        ForumThreadFollower.objects.filter(user=request.user)
        .select_related(
            "forum_thread__thread",
            "forum_thread__author",
            "forum_thread__course",
            "forum_thread__department",
        )
        .filter(forum_thread__status=ForumThreadStatus.ACTIVE)
        .order_by("-followed_at")
    )
    return render(
        request,
        "forum/my_following_threads.html",
        {"followed_threads": followed},
    )


@login_required
def search_suggestions(request):
    """API endpoint for fuzzy searching departments and courses."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"departments": [], "courses": [], "users": []})

    result_depts = Department.objects.filter(
        Q(short_code__icontains=q) | Q(name__icontains=q)
    ).distinct()[:5]

    result_courses = Course.objects.filter(
        Q(code__icontains=q) | Q(name__icontains=q)
    ).distinct()[:5]

    result_users = User.objects.filter(
        Q(handle__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
    ).distinct()[:5]

    return JsonResponse(
        {
            "departments": [
                {"id": d.id, "label": f"{d.short_code}: {d.name}", "code": d.short_code}
                for d in result_depts
            ],
            "courses": [
                {"id": c.id, "label": f"{c.code}: {c.name}", "code": c.code}
                for c in result_courses
            ],
            "users": [
                {
                    "id": u.id,
                    "label": f"{u.get_full_name()} ({u.handle})",
                    "handle": u.handle,
                }
                for u in result_users
            ],
        }
    )


@login_required
def thread_create(request):
    """Create a new forum thread."""
    current_trimester = get_current_trimester()

    if request.method == "POST":
        form = ForumThreadCreateForm(request.POST, user=request.user)
        if form.is_valid():
            # Delegate creation and notifications directly to the service layer
            forum_thread = create_forum_thread(
                user=request.user,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                department=form.cleaned_data["department"],
                course=form.cleaned_data["course"],
                current_trimester=current_trimester,
                participants_list=form.cleaned_data["participants"],
                is_announcement=form.cleaned_data["is_announcement"],
            )
            messages.success(request, "Thread created successfully.")
            return redirect("forum:thread_detail", pk=forum_thread.pk)
        for _, errors in form.errors.items():
            for error in errors:
                messages.error(request, str(error))
    else:
        form = ForumThreadCreateForm(user=request.user)
    context = {"form": form}
    return render(request, "forum/thread_create.html", context)


@login_required
def thread_detail(request, pk):
    """Display a thread, its nested messages, and handle new replies."""
    forum_thread = get_object_or_404(
        ForumThread.objects.select_related(
            "thread", "author", "course", "department", "trimester"
        ).filter(status=ForumThreadStatus.ACTIVE),
        pk=pk,
    )
    base_thread = forum_thread.thread

    # Enforce private thread authorization
    if base_thread.visibility == ThreadVisibility.PRIVATE:
        is_participant = base_thread.participants.filter(user=request.user).exists()
        if not is_participant:
            messages.error(request, "You are not a participant in this thread.")
            return redirect("forum:public_threads")

    # Process new reply submission
    if request.method == "POST":
        form = ThreadMessageForm(request.POST, request.FILES)
        if form.is_valid():
            # Delegate all validation lookup, file saving, and side-effects to service layer
            thread_message = create_thread_message(
                sender=request.user,
                forum_thread=forum_thread,
                content=form.cleaned_data["content"],
                uploaded_photos=form.cleaned_data.get("uploaded_photos"),
                reply_to_id=request.POST.get("reply_to"),
            )
            messages.success(request, "Your reply has been posted successfully.")
            redirect_url = (
                reverse("forum:thread_detail", args=[pk])
                + f"#message-{thread_message.id}"
            )
            return redirect(redirect_url)
    else:
        form = ThreadMessageForm()

    # 1. Base queryset for messages
    thread_messages_qs = base_thread.messages.select_related(
        "sender", "reply_to"
    ).prefetch_related("attachments__photo")

    # 2. Identify the Pinned/Accepted Answer
    # We fetch this to display it in a special "Hero" slot at the top of the page.
    pinned_answer = thread_messages_qs.filter(is_pinned=True).first()

    # 3. Get sort parameter from URL
    sort_option = request.GET.get("sort", "oldest")

    if sort_option == "top":
        thread_messages = thread_messages_qs.annotate(
            db_net_score=F("upvote_count") - F("downvote_count")
        ).order_by("-db_net_score", "sent_at")
    elif sort_option == "latest":
        thread_messages = thread_messages_qs.order_by("-sent_at")
    else:  # "oldest"
        thread_messages = thread_messages_qs.order_by("sent_at")

    # 4. Build Reddit-style nested tree hierarchy
    thread_message_dict = {}
    root_thread_messages = []

    # First pass: load all instances into dictionary
    for msg in thread_messages:
        msg.replies_list = []
        thread_message_dict[msg.id] = msg

    # Second pass: group into parents/roots
    for msg in thread_messages:
        if msg.reply_to_id and msg.reply_to_id in thread_message_dict:
            thread_message_dict[msg.reply_to_id].replies_list.append(msg)
        else:
            root_thread_messages.append(msg)

    is_following = ForumThreadFollower.objects.filter(
        user=request.user, forum_thread=forum_thread
    ).exists()

    context = {
        "forum_thread": forum_thread,
        "base_thread": base_thread,
        "root_thread_messages": root_thread_messages,
        "pinned_answer": pinned_answer,
        "form": form,
        "current_sort": sort_option,
        "is_following": is_following,
    }
    return render(request, "forum/thread_detail.html", context)


@login_required
def thread_edit(request, pk):
    forum_thread = get_object_or_404(
        ForumThread.objects.select_related("thread").filter(
            status=ForumThreadStatus.ACTIVE
        ),
        pk=pk,
    )

    if forum_thread.author != request.user:
        raise PermissionDenied("You do not have permission to edit this thread.")

    if request.method == "POST":
        form = ForumThreadEditForm(
            request.POST, instance=forum_thread, user=request.user
        )
        if form.is_valid():
            update_forum_thread(
                user=request.user,
                forum_thread=forum_thread,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                department=form.cleaned_data["department"],
                course=form.cleaned_data["course"],
                participants_list=form.cleaned_data["participants"],
            )
            messages.success(request, "Thread updated successfully.")
            return redirect("forum:thread_detail", pk=forum_thread.pk)
    else:
        form = ForumThreadEditForm(instance=forum_thread, user=request.user)

    return render(
        request, "forum/thread_edit.html", {"form": form, "forum_thread": forum_thread}
    )


@login_required
@require_POST
def thread_delete(request, pk):
    forum_thread = get_object_or_404(
        ForumThread.objects.select_related("thread").filter(
            status=ForumThreadStatus.ACTIVE
        ),
        pk=pk,
    )

    if forum_thread.author != request.user:
        raise PermissionDenied("You do not have permission to delete this thread.")

    soft_delete_forum_thread(user=request.user, forum_thread_id=pk)
    messages.success(request, "Thread deleted successfully.")
    return redirect("forum:my_threads")


@login_required
@require_POST
def pin_message(request, message_id):
    try:
        # Delegate data fetching, uniqueness validation, and notifications to the service
        _, action = toggle_exclusive_message_pin(
            user=request.user, message_id=message_id
        )
        messages.success(request, f"Message has been {action} successfully.")
        return JsonResponse({"status": "success", "action": action})

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)

    except PermissionDenied as e:
        return JsonResponse({"error": str(e)}, status=403)


@login_required
@require_POST
def vote_message(request, message_id):
    """API endpoint to handle upvoting and downvoting on a thread message."""
    vote_type_param = request.POST.get("vote_type")

    try:
        # Delegate the locking, logic, and math to the service
        upvotes, downvotes = toggle_message_vote(
            user=request.user, message_id=message_id, vote_type_str=vote_type_param
        )

        return JsonResponse(
            {
                "upvote_count": upvotes,
                "downvote_count": downvotes,
            }
        )

    except ValueError as e:
        # Catch our validation error and return a 400 Bad Request
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def follow_thread(request, pk):
    is_following = toggle_thread_follow(user=request.user, forum_thread_id=pk)
    messages.success(
        request,
        (
            "You are now following this thread."
            if is_following
            else "You have unfollowed this thread."
        ),
    )
    return JsonResponse({"is_following": is_following})
