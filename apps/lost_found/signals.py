"""
Lost & Found — Signal registration
====================================
Register this module in your app config:

    # apps/lost_found/apps.py
    class LostFoundConfig(AppConfig):
        name = "apps.lost_found"

        def ready(self):
            import apps.lost_found.signals  # noqa: F401

The signal below is intentionally lightweight: it only handles the edge case
where a post transitions to ACTIVE status outside of the normal create-view
flow (e.g., admin approval, a moderation action).

For posts created through post_create or post_edit views, run_auto_match()
is called directly in the view *after* form.save_m2m() so that tag data is
already available — signals fire before M2M is committed.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from .models import LostAndFoundPost, SuggestedMatch
from .matching import run_auto_match
from apps.common.choices import LostAndFoundStatus
from apps.notifications.signals import notify


@receiver(post_save, sender=LostAndFoundPost)
def auto_match_on_approval(sender, instance, created, update_fields, **kwargs):
    """
    Trigger auto-matching when a post reaches ACTIVE status.

    Skipped when update_fields is specified and 'status' is not in it,
    to avoid running unnecessarily on every field-level save (e.g., soft deletes).

    Note: tags are a M2M relation and may not be populated yet if this signal
    fires during the initial create-view flow.  The view handles that case
    directly; this signal covers admin/moderation approvals.
    """
    if update_fields and "status" not in update_fields:
        return

    if instance.status == LostAndFoundStatus.ACTIVE and not instance.deleted_at:
        suggestions = run_auto_match(instance)


@receiver(post_save, sender=SuggestedMatch)
def notify_on_suggested_match(sender, instance, created, **kwargs):
    """Notify the lost post owner when a new suggested match is found."""
    if not created:
        return

    # Notify the owner of the lost post
    notify(
        recipient=instance.lost_post.user,
        verb=f"Potential match for '{instance.lost_post.title}'",
        target=instance,
        data={
            "url": reverse("lost_found:my_suggested_matches"),
            "lost_post_id": instance.lost_post.id,
            "found_post_id": instance.found_post.id,
            "match_score": instance.score,
        },
    )
