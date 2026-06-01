from django.urls import path
from . import views

app_name = 'ride_share'

urlpatterns = [
    # Browse rides from others
    path('', views.all_rides, name='all_rides'),
    path('rides/<int:pk>/', views.ride_detail, name='ride_detail'),
    
    # User's posts and matches
    path('my-posts/', views.my_posts, name='my_posts'),
    path('my-matches/', views.my_matches, name='my_matches'),
    path('request/', views.request_ride, name='request_ride'),
    
    # Create and join rides
    path('create/', views.create_ride, name='create_ride'),
    path('rides/<int:pk>/approach/', views.approach_ride, name='approach_ride'),
    path('rides/<int:ride_pk>/requests/<int:member_pk>/approve/', views.approve_request, name='approve_request'),
    path('rides/<int:ride_pk>/requests/<int:member_pk>/reject/', views.reject_request, name='reject_request'),
    
    # Chat and management
    path('rides/<int:pk>/chat/', views.ride_chat, name='ride_chat'),
    path('rides/<int:pk>/leave/', views.leave_ride, name='leave_ride'),
    path('rides/<int:pk>/start/', views.start_ride, name='start_ride'),
]
