from django.conf import settings
from django.db import models
from apps.common.choices import (
    ExchangePostStatus,
    ExchangeMatchStatus,
    ExchangeSessionStatus,
    SkillStatus,
    UserSkillStatus,
)

from django.core.validators import MinValueValidator, MaxValueValidator


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=20, choices=SkillStatus.choices, default=SkillStatus.PENDING
    )
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class UserSkill(models.Model):
    proficiency_level = models.PositiveSmallIntegerField(default=1)
    proficiency_method = models.CharField(max_length=100, null=True, blank=True)
    proficiency_notes = models.TextField(null=True, blank=True)
    years_experience = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_skills",
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)

    status = models.CharField(
        max_length=20, choices=UserSkillStatus.choices, default=UserSkillStatus.PENDING
    )

    def __str__(self):
        return f"{self.user.email} - {self.skill.name}"


class ExchangePost(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exchange_posts",
    )
    description = models.TextField(null=True, blank=True)
    skills_offered = models.ManyToManyField(
        Skill,
        related_name="offered_in_posts",
    )
    skills_needed = models.ManyToManyField(
        Skill,
        related_name="requested_in_posts",
    )
    status = models.CharField(
        max_length=20,
        choices=ExchangePostStatus.choices,
        default=ExchangePostStatus.MATCHING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Post {self.id} by {self.author.email}"


class ExchangeMatch(models.Model):
    matched_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=ExchangeMatchStatus.choices,
        default=ExchangeMatchStatus.PENDING,
    )
    ex_p_a = models.ForeignKey(
        ExchangePost, related_name="matches_a", on_delete=models.CASCADE
    )
    ex_p_b = models.ForeignKey(
        ExchangePost, related_name="matches_b", on_delete=models.CASCADE
    )

    # Required to fulfill Rule 2: unique skill pairings
    skill_a_offers = models.ForeignKey(
        Skill,
        related_name="matches_offered_a",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    skill_b_offers = models.ForeignKey(
        Skill,
        related_name="matches_offered_b",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    user_a_accepted = models.BooleanField(default=False)
    user_b_accepted = models.BooleanField(default=False)

    def get_context_for_user(self, user):
        """
        Returns a dictionary identifying which post/skills belong to 'user'
        versus the 'partner' in this match.
        """
        if self.ex_p_a.author == user:
            return {
                "my_post": self.ex_p_a,
                "my_skill": self.skill_a_offers,
                "partner_post": self.ex_p_b,
                "partner_skill": self.skill_b_offers,
                "partner_user": self.ex_p_b.author,
            }
        else:
            return {
                "my_post": self.ex_p_b,
                "my_skill": self.skill_b_offers,
                "partner_post": self.ex_p_a,
                "partner_skill": self.skill_a_offers,
                "partner_user": self.ex_p_a.author,
            }

    def __str__(self):
        return (
            f"Match {self.id} between Post {self.ex_p_a.id} and Post {self.ex_p_b.id} -"
            f" {self.skill_a_offers.name} ↔ {self.skill_b_offers.name}"
        )

    class Meta:
        # This allows multiple matches between the same posts, but only for different skill pairs
        unique_together = ("ex_p_a", "ex_p_b", "skill_a_offers", "skill_b_offers")

        constraints = [
            # Ensures ex_p_a ID is always less than ex_p_b ID to prevent duplicate flipped records
            models.CheckConstraint(
                condition=models.Q(ex_p_a__lt=models.F("ex_p_b")),
                name="exchange_match_post_order",
            )
        ]


class ExchangeSession(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    match = models.OneToOneField(
        ExchangeMatch, on_delete=models.CASCADE, related_name="exchange_session"
    )
    thread = models.OneToOneField(
        "threads.Thread", on_delete=models.CASCADE, related_name="exchange_session"
    )

    user_a_completed = models.BooleanField(default=False)
    user_b_completed = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=ExchangeSessionStatus.choices,
        default=ExchangeSessionStatus.ACTIVE,
    )

    # def is_user_a(self, user):
    #     return user == self.match.ex_p_a.author

    # def is_user_b(self, user):
    #     return user == self.match.ex_p_b.author

    # def user_has_confirmed(self, user):
    #     if self.is_user_a(user):
    #         return self.user_a_completed
    #     if self.is_user_b(user):
    #         return self.user_b_completed
    #     return False

    def __str__(self):
        return f"Session {self.id} for Match {self.match.id}"

    class Meta:
        unique_together = ("match", "thread")


class SessionFeedback(models.Model):
    rated_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feedback_given",
    )
    rated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feedback_received",
    )
    exchange_session = models.ForeignKey(
        ExchangeSession, on_delete=models.CASCADE, related_name="feedbacks"
    )

    # 1 to 10 rating
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    notes = models.TextField(null=True, blank=True)  # Optional private feedback

    # status = models.CharField(
    #     max_length=20,
    #     choices=SessionFeedbackStatus.choices,
    #     default=SessionFeedbackStatus.PENDING,
    # )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A user can only leave ONE feedback per session (but they can update it)
        unique_together = ("rated_by_user", "exchange_session")

    def __str__(self):
        return f"{self.rating}/10 for {self.rated_user.email}"
