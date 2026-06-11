from django.urls import path
from . import views

app_name = "marketplace"

urlpatterns = [
    path("", views.listing_list, name="listing_list"),
    path("new/", views.create_listing, name="create_listing"),
    path("my/", views.my_listings, name="my_listings"),
    path("orders/buying/", views.my_orders_buyer, name="orders_buyer"),
    path(
        "<int:listing_id>/inquiries/", views.review_inquiries, name="review_inquiries"
    ),
    path(
        "<int:listing_id>/orders/",
        views.review_orders,
        name="review_orders",
    ),
    path(
        "<int:listing_id>/orders/<int:request_id>/approve/",
        views.approve_purchase_request,
        name="approve_purchase_request",
    ),
    path(
        "<int:listing_id>/orders/<int:request_id>/reject/",
        views.reject_purchase_request,
        name="reject_purchase_request",
    ),
    path("<int:listing_id>/", views.listing_detail, name="listing_detail"),
    path("<int:listing_id>/edit/", views.edit_listing, name="edit_listing"),
    path("<int:listing_id>/contact/", views.contact_seller, name="contact_seller"),
    path("request-chat/<int:listing_id>/", views.request_chat, name="request_chat"),
    path(
        "order/<int:order_id>/complete/",
        views.complete_order,
        name="complete_order",
    ),
    path(
        "order/<int:order_id>/confirm-received/",
        views.confirm_order_received,
        name="confirm_order_received",
    ),
    path(
        "order/<int:order_id>/accept/",
        views.accept_order,
        name="accept_order",
    ),
    path(
        "order/<int:order_id>/confirm/",
        views.confirm_order,
        name="confirm_order",
    ),
    path(
        "order/<int:order_id>/reject/",
        views.reject_order,
        name="reject_order",
    ),
    path(
        "order/<int:order_id>/open/",
        views.open_order,
        name="open_order",
    ),
]
