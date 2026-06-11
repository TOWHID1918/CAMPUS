from django.db import models
from django.conf import settings
from apps.common.choices import ListingStatus, OrderStatus


class Category(models.Model):

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Listing(models.Model):

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
    )

    title = models.CharField(max_length=255)

    description = models.TextField(blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listings",
    )

    stock = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} by {self.seller.email}"


class ListingPhoto(models.Model):

    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name="photos"
    )

    photo = models.ForeignKey(
        "media.Photo", on_delete=models.CASCADE, related_name="listing_photos"
    )

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class PurchaseOrder(models.Model):
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name="purchase_orders"
    )

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="buyer_orders",
    )

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_orders",
    )

    thread = models.OneToOneField(
        "threads.Thread",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="marketplace_order",
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )

    quantity = models.PositiveIntegerField(default=1)
    message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.buyer} → {self.listing} ({self.quantity})"
