from django.urls import path
from . import views

app_name = "forum"

urlpatterns = [
    path("", views.public_threads, name="public_threads"),
    path("announcements/", views.announcement_threads, name="announcement_threads"),
    path("my/", views.my_threads, name="my_threads"),
    path(
        "participating/",
        views.my_participating_threads,
        name="my_participating_threads",
    ),
    path("following/", views.my_following_threads, name="my_following_threads"),
    path("create/", views.thread_create, name="thread_create"),
    path("<int:pk>/", views.thread_detail, name="thread_detail"),
    path("messages/<int:message_id>/vote/", views.vote_message, name="vote_message"),
    path(
        "messages/<int:message_id>/pin/",
        views.pin_message,
        name="pin_message",
    ),
    path("search-suggestions/", views.search_suggestions, name="search_suggestions"),
    path("<int:pk>/follow/", views.follow_thread, name="toggle_follow"),
]
