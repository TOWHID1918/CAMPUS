from django.db import models
from django.conf import settings


class ListingStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SOLD = "SOLD", "Sold"
    ARCHIVED = "ARCHIVED", "Archived"


class PurchaseRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class Category(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

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

    title = models.CharField(
        max_length=255
    )

    description = models.TextField(
        blank=True
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listings",
    )

    status = models.CharField(
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.ACTIVE,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.title} by {self.seller.email}"


class ListingPhoto(models.Model):

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="photos"
    )

    photo = models.ForeignKey(
        "media.Photo",
        on_delete=models.CASCADE,
        related_name="listing_photos"
    )

    order = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        ordering = ["order"]


class NegotiationThread(models.Model):

    STATUS_PENDING = "PENDING"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="negotiation_threads"
    )

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="buyer_negotiations"
    )

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_negotiations"
    )

    thread = models.OneToOneField(
        "threads.Thread",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="marketplace_negotiation"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = ("listing", "buyer")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.buyer} → {self.listing}"


class PurchaseRequest(models.Model):

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="purchase_requests",
    )

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="purchase_requests",
    )

    message = models.TextField(
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=PurchaseRequestStatus.choices,
        default=PurchaseRequestStatus.PENDING,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        unique_together = ("buyer", "listing")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.buyer.email} → {self.listing.title}"