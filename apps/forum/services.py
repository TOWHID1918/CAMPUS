from django.db import transaction
from django.urls import reverse
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.http import QueryDict

from apps.academics.models import Trimester
from apps.academics.models import Department, Course
from apps.common.choices import ThreadVisibility, ThreadParticipantRole, VoteType
from apps.threads.models import Thread, ThreadMessage, MessageAttachment, MessageVote
from apps.forum.models import ForumThread, ForumThreadFollower
from apps.media.models import Photo
from apps.notifications.signals import notify

from .filters import ForumThreadFilter


def get_current_trimester():
    """Helper to fetch the current active trimester."""
    return Trimester.objects.order_by("-code").first()


def create_forum_thread(
    user,
    title,
    description,
    department,
    course,
    current_trimester,
    participants_list,
    is_announcement=False,
):
    """
    Creates a base Thread, a linked ForumThread, and populates participants.
    Notifications fire after the atomic block commits so they never dispatch
    on a rolled-back transaction.
    """
    visibility = (
        ThreadVisibility.PUBLIC if not participants_list else ThreadVisibility.PRIVATE
    )

    with transaction.atomic():
        base_thread = Thread.objects.create(
            title=f"Forum Thread: {title}",
            description=description,
            visibility=visibility,
        )
        base_thread.participants.create(user=user, role=ThreadParticipantRole.AUTHOR)

        forum_thread = ForumThread.objects.create(
            author=user,
            title=title,
            course=course,
            department=department,
            trimester=current_trimester,
            thread=base_thread,
            is_announcement=is_announcement,
        )

        if visibility == ThreadVisibility.PRIVATE:
            for p_user in participants_list:
                if p_user != user:
                    base_thread.participants.create(
                        user=p_user, role=ThreadParticipantRole.MEMBER
                    )

        ForumThreadFollower.objects.get_or_create(user=user, forum_thread=forum_thread)

    # Notify outside the atomic block — guaranteed to run only on successful commit
    if visibility == ThreadVisibility.PRIVATE:
        for p_user in participants_list:
            if p_user != user:
                notify(
                    recipient=p_user,
                    verb=(
                        f"You were added to a new private forum base_thread: "
                        f"'{forum_thread.title}' by {user.handle}"
                    ),
                    target=forum_thread,
                    data={
                        "url": reverse("forum:thread_detail", args=[forum_thread.id])
                    },
                )

    return forum_thread


def create_thread_message(
    sender, forum_thread, content, uploaded_photos=None, reply_to_id=None
):
    base_thread = forum_thread.thread

    with transaction.atomic():
        reply_to = None
        if reply_to_id:
            reply_to = get_object_or_404(
                ThreadMessage, pk=reply_to_id, thread=base_thread
            )

        message = ThreadMessage.objects.create(
            thread=base_thread, sender=sender, reply_to=reply_to, content=content
        )

        for order, f in enumerate(uploaded_photos or []):
            photo_obj = Photo.objects.create(file=f, uploaded_by=sender)
            MessageAttachment.objects.create(
                message=message, photo=photo_obj, order=order
            )

        # Auto-follow on reply
        # ForumThreadFollower.objects.get_or_create(
        #     user=sender, forum_thread=forum_thread
        # )

    # Resolve primary recipient (existing logic, unchanged)
    primary_recipient = None
    verb = ""

    if reply_to:
        if reply_to.sender != sender:
            primary_recipient = reply_to.sender
            verb = f"{sender.handle} replied to your message in '{forum_thread.title}'"
    else:
        if forum_thread.author != sender:
            primary_recipient = forum_thread.author
            verb = f"{sender.handle} replied to your thread '{forum_thread.title}'"

    if primary_recipient and verb:
        notify(
            recipient=primary_recipient,
            verb=verb,
            target=message,
            data={
                "url": (
                    reverse("forum:thread_detail", args=[forum_thread.pk])
                    + f"#message-{message.id}"
                ),
                "thread_id": forum_thread.pk,
                "message_id": message.id,
                "sender": sender.handle,
            },
        )

    # Notify followers, excluding the sender and the primary recipient
    # (primary recipient already received a more specific notification above)
    excluded = {sender}
    if primary_recipient:
        excluded.add(primary_recipient)

    followers = (
        ForumThreadFollower.objects.filter(forum_thread=forum_thread)
        .exclude(user__in=excluded)
        .select_related("user")
    )

    follower_url = (
        reverse("forum:thread_detail", args=[forum_thread.pk])
        + f"#message-{message.id}"
    )

    for follower in followers:
        notify(
            recipient=follower.user,
            verb=f"{sender.handle} posted a new reply in '{forum_thread.title}'",
            target=message,
            data={
                "url": follower_url,
                "thread_id": forum_thread.pk,
                "message_id": message.id,
                "sender": sender.handle,
            },
        )

    return message


def toggle_exclusive_message_pin(user, message_id):
    """
    Toggles the is_pinned status of a ThreadMessage with exclusive enforcement:
    at most one message may be pinned per thread at any time.

    The ForumThread row is locked with select_for_update() to serialize
    concurrent pin operations on the same thread. Without the lock, two
    simultaneous requests targeting different messages could both pass the
    exclusivity check and leave two messages pinned.

    The target message is re-fetched after the lock is acquired so the
    is_pinned check reflects committed state, not a stale pre-lock snapshot.

    Notification fires outside the atomic block.
    """
    # Identify the thread before acquiring any lock
    thread_message = get_object_or_404(
        ThreadMessage.objects.select_related("thread", "sender"), pk=message_id
    )

    action = None
    should_notify = False

    with transaction.atomic():
        # Lock the ForumThread row — acts as a per-thread mutex for pin operations
        try:
            forum_thread = ForumThread.objects.select_for_update().get(
                thread=thread_message.thread
            )
        except ForumThread.DoesNotExist:
            raise ValueError("Forum thread not found")

        if forum_thread.author != user:
            raise PermissionDenied("Only the author can mark an answer.")

        # Re-fetch the message now that we hold the lock for a fresh is_pinned state
        thread_message = ThreadMessage.objects.select_related("thread", "sender").get(
            pk=message_id
        )

        if thread_message.is_pinned:
            thread_message.is_pinned = False
            thread_message.save(update_fields=["is_pinned"])
            action = "unpinned"
        else:
            ThreadMessage.objects.filter(
                thread=thread_message.thread, is_pinned=True
            ).update(is_pinned=False)

            thread_message.is_pinned = True
            thread_message.save(update_fields=["is_pinned"])
            action = "pinned"
            should_notify = thread_message.sender != user

    if should_notify:
        notify(
            recipient=thread_message.sender,
            verb=(
                f"Your reply in '{forum_thread.title}' "
                "was marked as the accepted answer!"
            ),
            target=thread_message,
            data={
                "url": (
                    reverse("forum:thread_detail", args=[forum_thread.pk])
                    + f"#message-{thread_message.id}"
                ),
                "thread_id": forum_thread.id,
                "message_id": thread_message.id,
            },
        )

    return thread_message, action


def toggle_message_vote(user, message_id, vote_type_str):
    """
    Handles upvoting/downvoting a message and recalculates denormalized counts.

    SELECT FOR UPDATE on the ThreadMessage row serializes concurrent votes on
    the same message, preventing a lost-update race on the count columns:
    without it two simultaneous requests could both read the same stale count,
    compute the same wrong value, and one write would silently overwrite the
    other.
    """
    if vote_type_str not in ["upvote", "downvote"]:
        raise ValueError("Invalid vote type.")

    target_vote_type = (
        VoteType.UPVOTE if vote_type_str == "upvote" else VoteType.DOWNVOTE
    )

    with transaction.atomic():
        thread_message = get_object_or_404(
            ThreadMessage.objects.select_for_update(), pk=message_id
        )

        vote, created = MessageVote.objects.get_or_create(
            message=thread_message,
            user=user,
            defaults={"vote_type": target_vote_type},
        )

        if not created:
            if vote.vote_type == target_vote_type:
                vote.delete()
            else:
                vote.vote_type = target_vote_type
                vote.save()

        # Recalculate from source of truth rather than increments
        upvotes = thread_message.votes.filter(vote_type=VoteType.UPVOTE).count()
        downvotes = thread_message.votes.filter(vote_type=VoteType.DOWNVOTE).count()

        thread_message.upvote_count = upvotes
        thread_message.downvote_count = downvotes
        thread_message.save(update_fields=["upvote_count", "downvote_count"])

    return upvotes, downvotes


def toggle_thread_follow(user, forum_thread_id):
    """
    Toggles follow status for a user on a given ForumThread.
    Returns a tuple of (is_now_following: bool).
    """
    forum_thread = get_object_or_404(ForumThread, pk=forum_thread_id)

    with transaction.atomic():
        follower, created = ForumThreadFollower.objects.get_or_create(
            user=user,
            forum_thread=forum_thread,
        )
        if not created:
            follower.delete()
            return False

    return True


def build_active_filters(filterset):
    """
    Converts a bound ForumThreadFilter into a list of chip dicts,
    each carrying the label to display and the URL that removes just that chip.
    """
    active_filters = []
    data = filterset.data  # the raw GET data

    if not isinstance(data, QueryDict):
        querydict = QueryDict(mutable=True)
        for key, value in data.items():
            if isinstance(value, list):
                for item in value:
                    querydict.appendlist(key, item)
            else:
                querydict.appendlist(key, value)
    else:
        querydict = data.copy()

    type_map = {
        "department": "dept",
        "course": "course",
        "user": "user",
    }

    for field_name, chip_type in type_map.items():
        # filterset.form.cleaned_data is only available if is_valid() was called;
        # fall back to raw values from data for label resolution
        selected_objects = (
            filterset.form.cleaned_data.get(field_name, [])
            if filterset.form.is_valid()
            else []
        )

        for obj in selected_objects:
            # Build a remove URL: all current params except this one value
            remaining = querydict.copy()
            current_values = remaining.getlist(field_name)
            current_values = [
                v for v in current_values if v != getattr(obj, _to_field(field_name))
            ]
            if current_values:
                remaining.setlist(field_name, current_values)
            else:
                remaining.pop(field_name, None)

            active_filters.append(
                {
                    "type": chip_type,
                    "label": _label_for(chip_type, obj),
                    "remove_url": f"?{remaining.urlencode()}" if remaining else "?",
                }
            )

    return active_filters


def apply_forum_thread_filters(
    queryset, department_code=None, course_code=None, user_handle=None
):
    """Apply forum thread filters for various forum views and build active filter chips."""
    filter_data = {}
    if department_code:
        filter_data["department"] = (
            department_code.split(",")
            if isinstance(department_code, str)
            else department_code
        )
    if course_code:
        filter_data["course"] = (
            course_code.split(",") if isinstance(course_code, str) else course_code
        )
    if user_handle:
        filter_data["user"] = (
            user_handle.split(",") if isinstance(user_handle, str) else user_handle
        )

    filterset = ForumThreadFilter(filter_data, queryset=queryset)
    active_filters = build_active_filters(filterset)
    return filterset.qs, active_filters


def _to_field(field_name):
    return {"department": "short_code", "course": "code", "user": "handle"}[field_name]


def _label_for(chip_type, obj):
    if chip_type == "dept":
        return f"{obj.short_code}: {obj.name}"
    if chip_type == "course":
        return f"{obj.code}: {obj.name}"
    return obj.handle  # user
