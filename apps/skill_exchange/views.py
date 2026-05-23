from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import SkillExchangePostForm
from .models import ExchangeMatch, ExchangePost, ExchangeSession
from .services import (
    create_exchange_post,
    delete_exchange_post,
    process_match_decision,
    process_session_completion,
    save_session_feedback,
)
from apps.common.choices import (
    ExchangeMatchStatus,
    ExchangePostStatus,
    ExchangeSessionStatus,
)

# --- POST MANAGEMENT ---


@login_required
def post_list(request):
    """View your own posts and their status."""
    posts = ExchangePost.objects.filter(
        author=request.user,
        status=ExchangePostStatus.MATCHING,
    ).order_by("-created_at")
    return render(request, "skill_exchange/post_list.html", {"posts": posts})


@login_required
def post_create(request):
    """Create a new post and trigger the matching engine."""
    if request.method == "POST":
        form = SkillExchangePostForm(request.POST, user=request.user)
        if form.is_valid():
            create_exchange_post(request.user, form)
            messages.success(request, "Exchange post created successfully!")
            return redirect("skill_exchange:post_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.error(request, error)
    else:
        form = SkillExchangePostForm(user=request.user)

    return render(request, "skill_exchange/post_create.html", {"form": form})


@login_required
@require_POST
def post_delete(request, post_id):
    """
    Rule 1: Posts are immutable. To change skills, the user must delete and
    recreate. This also cleans up any pending matches.
    """
    post = get_object_or_404(ExchangePost, pk=post_id, author=request.user)
    delete_exchange_post(post)
    messages.info(request, "Post deleted and pending matches removed.")
    return redirect("skill_exchange:post_list")


# --- MATCHING & HANDSHAKE ---


@login_required
def match_list(request):
    pending_matches = ExchangeMatch.objects.filter(
        Q(ex_p_a__author=request.user) | Q(ex_p_b__author=request.user),
        status=ExchangeMatchStatus.PENDING,
    ).select_related(
        "ex_p_a__author", "ex_p_b__author", "skill_a_offers", "skill_b_offers"
    )

    for match in pending_matches:
        match.user_context = match.get_context_for_user(request.user)

    return render(
        request,
        "skill_exchange/match_list.html",
        {"pending_matches": pending_matches},
    )


@login_required
def session_list(request):
    active_sessions = ExchangeSession.objects.filter(
        Q(match__ex_p_a__author=request.user) | Q(match__ex_p_b__author=request.user),
        status=ExchangeSessionStatus.ACTIVE,
    )

    for session in active_sessions:
        session.user_context = session.match.get_context_for_user(request.user)

    return render(
        request,
        "skill_exchange/session_list.html",
        {"active_sessions": active_sessions},
    )


@login_required
@require_POST
def match_confirm_decision(request, match_id):
    """The Two-Way Handshake: delegate the decision logic to the service layer."""
    match = get_object_or_404(ExchangeMatch, pk=match_id)
    action = request.POST.get("action")  # 'accepted' or 'rejected'

    result = process_match_decision(match, request.user, action)

    if result["outcome"] == "rejected":
        messages.info(request, "Match declined.")
        return redirect("skill_exchange:match_list")

    if result["outcome"] == "pending":
        messages.success(
            request, "You accepted the match! Waiting for the other user to respond."
        )
        return redirect("skill_exchange:match_list")

    if result["outcome"] == "confirmed":
        messages.success(request, "Match confirmed! A new session has started.")
        return redirect("threads:thread_detail", thread_id=result["thread_id"])

    # outcome == "pending" (waiting for the other user to accept)
    return redirect("skill_exchange:match_list")


# --- SESSION MANAGEMENT ---


@login_required
@require_POST
def session_complete_decision(request, session_id):
    session = get_object_or_404(
        ExchangeSession, pk=session_id, status=ExchangeSessionStatus.ACTIVE
    )

    result = process_session_completion(session, request.user)

    if result["fully_completed"]:
        messages.success(request, "Exchange successfully completed!")
    else:
        messages.info(request, "Completion status recorded.")

    return redirect("threads:thread_detail", thread_id=session.thread.id)


# --- FEEDBACK MANAGEMENT ---


@login_required
@require_POST
def submit_session_feedback(request, session_id):
    session = get_object_or_404(ExchangeSession, pk=session_id)

    # Authorization: ensure the requester is a participant
    is_participant = (
        session.match.ex_p_a.author == request.user
        or session.match.ex_p_b.author == request.user
    )
    if not is_participant:
        messages.error(request, "You are not a participant in this session.")
        return redirect("skill_exchange:session_list")

    # Input validation
    try:
        rating = int(request.POST.get("rating"))
        if not (1 <= rating <= 10):
            raise ValueError
    except (TypeError, ValueError):
        messages.error(
            request, "Invalid rating. Must be a whole number between 1 and 10."
        )
        return redirect("threads:thread_detail", thread_id=session.thread.id)

    notes = request.POST.get("notes", "")

    save_session_feedback(session, request.user, rating, notes)

    messages.success(request, "Your feedback has been saved securely!")
    return redirect("threads:thread_detail", thread_id=session.thread.id)
