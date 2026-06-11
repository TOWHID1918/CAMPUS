from django.conf import settings
from django.db import models
from apps.common.choices import (
    ThreadStatus,
    ThreadMessageStatus,
    VoteStatus,
    ThreadVisibility,
    ThreadParticipantRole,
    VoteType,
)


class Thread(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    visibility = models.CharField(
        max_length=20,
        choices=ThreadVisibility.choices,
        default="PUBLIC",
    )

    status = models.CharField(
        max_length=20,
        choices=ThreadStatus.choices,
        default=ThreadStatus.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    tags = models.ManyToManyField("Tag", blank=True, related_name="threads")

    def __str__(self):
        return self.title


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class ThreadMessage(models.Model):
    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="messages"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )

    content = models.TextField()

    reply_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )

    status = models.CharField(
        max_length=20,
        choices=ThreadMessageStatus.choices,
        default=ThreadMessageStatus.SENT,
    )

    upvote_count = models.PositiveIntegerField(default=0)
    downvote_count = models.PositiveIntegerField(default=0)

    is_pinned = models.BooleanField(default=False)

    sent_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    @property
    def net_score(self):
        """Calculates the total score for template rendering."""
        return self.upvote_count - self.downvote_count

    def __str__(self):
        return f"Message {self.id} in Thread {self.thread.id} by {self.sender.email}"


class MessageVote(models.Model):
    message = models.ForeignKey(
        ThreadMessage, on_delete=models.CASCADE, related_name="votes"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="message_votes"
    )

    vote_type = models.CharField(max_length=10, choices=VoteType.choices)

    status = models.CharField(
        max_length=20,
        choices=VoteStatus.choices,
        default=VoteStatus.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("message", "user")  # one vote per user

    def __str__(self):
        return f"{self.user} → {self.vote_type}"


class ThreadParticipant(models.Model):
    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="participants"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="thread_participations",
    )

    role = models.CharField(
        max_length=50,
        choices=ThreadParticipantRole.choices,
        default=ThreadParticipantRole.MEMBER,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("thread", "user")


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        ThreadMessage, on_delete=models.CASCADE, related_name="attachments"
    )

    photo = models.ForeignKey(
        "media.Photo", on_delete=models.CASCADE, related_name="message_attachments"
    )

    order = models.PositiveIntegerField(default=0)
