from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ExchangeMatch, SessionFeedback
from .services import notify_match_created, update_user_sx_rating


@receiver(post_save, sender=ExchangeMatch)
def notify_on_skill_exchange_match(sender, instance, created, **kwargs):
    """Notify both users when a new skill exchange match is found."""
    if not created:
        return
    notify_match_created(instance)


@receiver([post_save, post_delete], sender=SessionFeedback)
def update_user_sx_rating_avg(sender, instance, **kwargs):
    """Recalculate the rated user's Bayesian average after any feedback change."""
    update_user_sx_rating(instance.rated_user)
