from django.urls import path

from . import views
path("skills/add/",                       views.add_skill,    name="add_skill"),
path("skills/remove/<int:userskill_id>/", views.remove_skill, name="remove_skill"),
app_name = "skill_exchange"

urlpatterns = [
    path("posts/", views.post_list, name="post_list"),
    path("posts/new/", views.post_create, name="post_create"),
    path("posts/<int:post_id>/delete/", views.post_delete, name="post_delete"),
    path("matches/", views.match_list, name="match_list"),
    path("sessions/", views.session_list, name="session_list"),
    path(
        "matches/<int:match_id>/confirm/",
        views.match_confirm_decision,
        name="match_confirm_decision",
    ),
    path(
        "sessions/<int:session_id>/complete/",
        views.session_complete_decision,
        name="session_complete_decision",
    ),
    path(
        "sessions/<int:session_id>/feedback/",
        views.submit_session_feedback,
        name="submit_session_feedback",
    ),
    path("skills/add/", views.add_skill, name="add_skill"),                          
    path("skills/remove/<int:userskill_id>/", views.remove_skill, name="remove_skill"),  
]
