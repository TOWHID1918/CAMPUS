# apps/ride_share/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from apps.common.choices import (
    RideGroupMemberStatus,
)
from apps.notifications.signals import notify

from .models import RideMonitorMatch


def _display_name(user):
    return getattr(user, "handle", None) or getattr(user, "email", str(user))


def notify_join_request(member):
    """Notify the ride organizer that a user wants to join."""
    if member.status != RideGroupMemberStatus.PENDING:
        return

    ride_post = member.group.ride_post
    organizer = ride_post.user

    if getattr(organizer, "id", None) == member.user_id:
        return

    def _send():
        notify(
            recipient=organizer,
            verb=f"{_display_name(member.user)} requested to join your ride.",
            target=member,
            data={
                "url": reverse("ride_share:ride_detail", args=[ride_post.pk]),
                "ride_post_id": ride_post.pk,
                "member_id": member.pk,
                "requester": _display_name(member.user),
            },
        )

    transaction.on_commit(_send)


def notify_join_approved(member):
    """Notify the requester that their join request was approved."""
    if member.status != RideGroupMemberStatus.CONFIRMED or member.is_initiator:
        return

    ride_post = member.group.ride_post

    def _send():
        notify(
                recipient=member.user,
            verb=f"Your request to join the ride by {_display_name(ride_post.user)} was approved.",
            target=member,
            data={
                "url": reverse("ride_share:ride_detail", args=[ride_post.pk]),
                "ride_post_id": ride_post.pk,
                "member_id": member.pk,
                "organizer": _display_name(ride_post.user),
            },
        )

    transaction.on_commit(_send)


@receiver(post_save, sender=RideMonitorMatch)
def notify_monitor_match(sender, instance, created, **kwargs):
    """Notify the monitor owner when a new matching ride appears."""
    if not created or instance.notified_at:
        return

    if instance.monitor_request.deleted_at or instance.ride_post.deleted_at:
        return

    def _send():
        notify(
            recipient=instance.monitor_request.user,
            verb=(
                f"A matching ride was found for your monitor request: "
                f"{_display_name(instance.ride_post.user)} posted a ride."
            ),
            target=instance,
            data={
                "url": reverse("ride_share:ride_detail", args=[instance.ride_post.pk]),
                "ride_post_id": instance.ride_post_id,
                "monitor_request_id": instance.monitor_request_id,
                "match_id": instance.pk,
            },
        )
        RideMonitorMatch.objects.filter(pk=instance.pk, notified_at__isnull=True).update(
            notified_at=timezone.now()
        )

    from django.db import transaction

    transaction.on_commit(_send)
