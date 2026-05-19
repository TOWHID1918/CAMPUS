from django.urls import path
from . import views

app_name = "marketplace"

urlpatterns = [
    path("", views.listing_list, name="listing_list"),
    path("new/", views.create_listing, name="create_listing"),
    path("my/", views.my_listings, name="my_listings"),
    path("negotiations/buying/", views.my_negotiations_buyer, name="negotiations_buyer"),

    path("<int:listing_id>/inquiries/", views.review_inquiries, name="review_inquiries"),

    path("<int:listing_id>/", views.listing_detail, name="listing_detail"),
    path("<int:listing_id>/edit/", views.edit_listing, name="edit_listing"),
    path("<int:listing_id>/contact/", views.contact_seller, name="contact_seller"),
    path("request-chat/<int:listing_id>/",views.request_chat,name="request_chat"),
    path("negotiation/<int:negotiation_id>/accept/",views.accept_negotiation,name="accept_negotiation"),
    path("negotiation/<int:negotiation_id>/reject/",views.reject_negotiation,name="reject_negotiation"),
    path("negotiation/<int:negotiation_id>/open/",views.open_negotiation_conversation,name="open_negotiation"),


]