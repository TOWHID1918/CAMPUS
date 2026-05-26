# apps/ride_share/models.py
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone

from apps.common.choices import (
    TransportMethod, TRANSPORT_CAPACITY, RidePostStatus,
    RideGroupStatus, RideGroupMemberStatus,
    RideMonitorRequestStatus, RideMonitorMatchStatus,
)

UIU_LOCATION = "United International University"


class Location(models.Model):
    name = models.CharField(max_length=255, primary_key=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @classmethod
    def ensure_predefined_locations(cls):
        cls.objects.get_or_create(name=UIU_LOCATION, defaults={'is_active': True})
    

class RideDirection(models.TextChoices):
    TO_UNIVERSITY = "to_university", "Going to University"
    TO_HOME = "to_home", "Going Home"

# ─────────────────────────────────────────────
# Ride Post
# ─────────────────────────────────────────────
class RidePost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ride_posts')
    starting_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='ride_posts_as_start',
        db_column='starting_location',
        help_text="Your pickup area or landmark",
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='ride_posts_as_destination',
        db_column='destination_location',
        default=UIU_LOCATION,
    )
    direction = models.CharField(max_length=20, choices=RideDirection.choices, default=RideDirection.TO_UNIVERSITY)
    departure_time = models.DateTimeField()
    expires_at = models.DateTimeField()
    transport_method = models.CharField(max_length=20, choices=TransportMethod.choices)
    max_capacity = models.PositiveIntegerField(editable=False)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RidePostStatus.choices, default=RidePostStatus.OPEN)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.max_capacity = TRANSPORT_CAPACITY.get(self.transport_method, 1)
            if self.departure_time and not self.expires_at:
                self.expires_at = self.departure_time + timedelta(hours=2)
        
        if self.expires_at and self.departure_time and self.expires_at < self.departure_time:
            raise ValueError("expires_at cannot be before departure_time.")
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.status = RidePostStatus.CANCELLED
        self.save(update_fields=['deleted_at', 'status', 'updated_at'])

# ─────────────────────────────────────────────
# Ride Group
# ─────────────────────────────────────────────
class RideGroup(models.Model):
    ride_post = models.OneToOneField(RidePost, on_delete=models.CASCADE, related_name='ride_group')
    thread = models.OneToOneField('threads.Thread', on_delete=models.PROTECT, null=True, blank=True, related_name='ride_group')
    status = models.CharField(max_length=20, choices=RideGroupStatus.choices, default=RideGroupStatus.FORMING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def max_capacity(self):
        return self.ride_post.max_capacity

    @property
    def current_occupancy(self):
        # Flattened calculation based directly on members
        from django.db.models import Sum, Value
        from django.db.models.functions import Coalesce

        result = self.members.filter(
            status=RideGroupMemberStatus.CONFIRMED
        ).aggregate(total=Sum(Coalesce('party_size', Value(1))))
        return result['total'] or 0

    @property
    def is_full(self):
        return self.current_occupancy >= self.max_capacity

# ─────────────────────────────────────────────
# Ride Group Member
# ─────────────────────────────────────────────
class RideGroupMember(models.Model):
    group = models.ForeignKey(RideGroup, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ride_group_memberships')
    
    party_size = models.PositiveIntegerField(
        default=1, 
        validators=[MinValueValidator(1)],
        help_text="How many people including the requester"
    )
    is_initiator = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=RideGroupMemberStatus.choices, default=RideGroupMemberStatus.CONFIRMED)
    
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'user')


class RideMonitorRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ride_monitor_requests')
    starting_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='ride_monitor_requests_as_start',
        db_column='starting_location',
        help_text='Your pickup area or landmark',
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='ride_monitor_requests_as_destination',
        db_column='destination_location',
        default=UIU_LOCATION,
    )
    direction = models.CharField(max_length=20, choices=RideDirection.choices, default=RideDirection.TO_UNIVERSITY)
    departure_time = models.DateTimeField(null=True, blank=True, help_text='When you want to travel')
    # allow unspecified transport_method to match any category
    transport_method = models.CharField(max_length=20, choices=TransportMethod.choices, null=True, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RideMonitorRequestStatus.choices, default=RideMonitorRequestStatus.PENDING)
    last_matched_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        if self.departure_time:
            return f'{self.user} - {self.get_direction_display()} - {self.departure_time:%Y-%m-%d %I:%M %p}'
        return f'{self.user} - {self.get_direction_display()} - any time'

    def route_matches(self, ride_post):
        from . import matching

        return matching.route_matches(self, ride_post)

    def departure_time_matches(self, ride_post):
        from . import matching

        return matching.departure_time_matches(self, ride_post)

    def matches_ride_post(self, ride_post):
        from . import matching

        return matching.matches_ride_post(self, ride_post)

    def matching_posts_queryset(self):
        from . import matching

        return matching.matching_posts_queryset(self)

    def sync_matches(self):
        from . import matching

        return matching.sync_matches(self)

    def match_post(self, ride_post):
        from . import matching

        return matching.match_post(self, ride_post)


class RideMonitorMatch(models.Model):
    monitor_request = models.ForeignKey(RideMonitorRequest, on_delete=models.CASCADE, related_name='matches')
    ride_post = models.ForeignKey(RidePost, on_delete=models.CASCADE, related_name='monitor_matches')
    status = models.CharField(max_length=20, choices=RideMonitorMatchStatus.choices, default=RideMonitorMatchStatus.NEW)
    notified_at = models.DateTimeField(null=True, blank=True)

    matched_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-matched_at']
        unique_together = ('monitor_request', 'ride_post')

    def __str__(self):
        return f'{self.monitor_request_id} -> {self.ride_post_id}'
