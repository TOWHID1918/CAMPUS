from django.contrib import admin

from .models import ForumThread, ForumThreadFollower


@admin.register(ForumThread)
class ForumThreadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "author",
        "course",
        "department",
        "trimester",
        "is_announcement",
        "is_pinned",
    )
    search_fields = ("title", "author__email", "course__name", "department__name")
    list_filter = ("is_announcement", "is_pinned", "course", "department", "trimester")


@admin.register(ForumThreadFollower)
class ForumThreadFollowerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "forum_thread", "followed_at")
    search_fields = ("user__email", "forum_thread__thread__title")
    list_filter = ("followed_at",)
