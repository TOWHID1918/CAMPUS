from django.db import models
from django.conf import settings
from apps.academics.models import Course, Department, Trimester
from apps.common.choices import ForumThreadStatus


# Create your models here.
class ForumThread(models.Model):
    status = models.CharField(
        max_length=20,
        choices=ForumThreadStatus.choices,
        default=ForumThreadStatus.ACTIVE,
    )
    is_announcement = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)

    title = models.CharField(max_length=255)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_threads",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        related_name="forum_threads",
        null=True,
        blank=True,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        related_name="forum_threads",
        null=True,
        blank=True,
    )
    trimester = models.ForeignKey(
        Trimester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forum_threads",
    )
    thread = models.OneToOneField("threads.Thread", on_delete=models.CASCADE)

    def __str__(self):
        return (
            f"ForumThread(id={self.id}, title={self.title}, author={self.author.email})"
        )

    class Meta:
        indexes = [
            models.Index(fields=["department", "course"]),
            models.Index(fields=["author"]),
        ]


class ForumThreadFollower(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followed_threads",
    )
    forum_thread = models.ForeignKey(
        ForumThread,
        on_delete=models.CASCADE,
        related_name="followers",
    )
    followed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "forum_thread")
