from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Prefetch

from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.urls import reverse
from .models import Thread, ThreadMessage, MessageAttachment, ThreadParticipant
from apps.common.choices import ThreadStatus, ThreadParticipantRole
from apps.media.models import Photo


@login_required
def thread_detail(request, thread_id):
    thread = get_object_or_404(
        Thread.objects.prefetch_related(
            "marketplace_negotiation__listing",
            "marketplace_negotiation__buyer",
            "marketplace_negotiation__seller"
        ),
        pk=thread_id
    )
    if not ThreadParticipant.objects.filter(thread=thread, user=request.user).exists():
        messages.error(request, "You are not a participant in this thread.")
        return redirect("home")

    base_template = "base.html"
    lost_found_context = None
    skill_exchange_context = None
    marketplace_context = None
    ride_group_context = None

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        files = request.FILES.getlist("photos")

        if content:
            with transaction.atomic():
                msg = ThreadMessage.objects.create(
                    thread=thread,
                    sender=request.user,
                    content=content,
                )

                for idx, f in enumerate(files):
                    photo = Photo.objects.create(file=f, uploaded_by=request.user)
                    MessageAttachment.objects.create(
                        message=msg, photo=photo, order=idx
                    )

            return HttpResponseRedirect(
                reverse("threads:thread_detail", args=[thread.id])
            )

    if hasattr(thread, "claim_thread"):
        lost_found_context = getattr(thread, "claim_thread")
        base_template = "lost_found/base.html"
    elif hasattr(thread, "exchange_session"):
        skill_exchange_context = getattr(thread, "exchange_session")
        base_template = "skill_exchange/base.html"
    elif hasattr(thread, "negotiation_thread"):
        marketplace_context = getattr(thread, "negotiation_thread")
        base_template = "marketplace/base.html"
    elif hasattr(thread, "ride_group"):
        ride_group_context = getattr(thread, "ride_group")
        base_template = "ride_share/base.html"

    context = {
        "thread": thread,
        "thread_messages": thread.messages.select_related("sender")
        .prefetch_related("attachments__photo")
        .order_by("sent_at"),
        "lost_found_context": lost_found_context,
        "skill_exchange_context": skill_exchange_context,
        "marketplace_context": marketplace_context,
        "ride_group_context": ride_group_context,
        "base_template": base_template,
    }

    return render(request, "threads/thread_detail.html", context)


@login_required
def archive_thread(request, thread_id):
    thread = get_object_or_404(Thread, pk=thread_id)
    if not ThreadParticipant.objects.filter(thread=thread, user=request.user).exists():
        return HttpResponseForbidden("You are not a participant of this thread!")
    user_role = ThreadParticipant.objects.get(thread=thread, user=request.user).role
    if user_role not in [ThreadParticipantRole.AUTHOR, ThreadParticipantRole.MODERATOR]:
        return HttpResponseForbidden("Only authors and moderators can archive threads!")

    if request.method == "POST":
        with transaction.atomic():
            thread.status = ThreadStatus.ARCHIVED
            thread.save(update_fields=["status", "updated_at"])
    return redirect("threads:thread_detail", thread_id=thread.id)