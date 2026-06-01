from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from apps.common.choices import RideMonitorRequestStatus, RidePostStatus
from apps.notifications.signals import notify
from .models import RideDirection, RideMonitorMatch, RideMonitorRequest, RidePost


def _display_name(user):
    return getattr(user, 'handle', None) or getattr(user, 'email', str(user))


def route_matches(monitor_request, ride_post):
    if monitor_request.direction == RideDirection.TO_UNIVERSITY:
        return ride_post.starting_location_id == monitor_request.starting_location_id
    return ride_post.destination_location_id == monitor_request.destination_location_id


def departure_time_matches(monitor_request, ride_post):
    if not monitor_request.departure_time:
        return True

    window_start = monitor_request.departure_time - timedelta(minutes=30)
    window_end = monitor_request.departure_time + timedelta(minutes=30)
    return window_start <= ride_post.departure_time <= window_end


def matches_ride_post(monitor_request, ride_post):
    if ride_post.user_id == monitor_request.user_id:
        return False

    if ride_post.status != RidePostStatus.OPEN or ride_post.deleted_at:
        return False

    if ride_post.direction != monitor_request.direction:
        return False

    if not route_matches(monitor_request, ride_post):
        return False

    if monitor_request.transport_method and ride_post.transport_method != monitor_request.transport_method:
        return False

    if not departure_time_matches(monitor_request, ride_post):
        return False

    return True


def matching_posts_queryset(monitor_request):
    qs = RidePost.objects.filter(
        status=RidePostStatus.OPEN,
        deleted_at__isnull=True,
        direction=monitor_request.direction,
    ).exclude(user=monitor_request.user)

    if monitor_request.direction == RideDirection.TO_UNIVERSITY:
        qs = qs.filter(starting_location=monitor_request.starting_location)
    else:
        qs = qs.filter(destination_location=monitor_request.destination_location)

    if monitor_request.transport_method:
        qs = qs.filter(transport_method=monitor_request.transport_method)

    if monitor_request.departure_time:
        window_start = monitor_request.departure_time - timedelta(minutes=30)
        window_end = monitor_request.departure_time + timedelta(minutes=30)
        qs = qs.filter(departure_time__gte=window_start, departure_time__lte=window_end)

    return qs


def sync_matches(monitor_request):
    created_matches = []
    for ride_post in matching_posts_queryset(monitor_request):
        if not matches_ride_post(monitor_request, ride_post):
            continue

        match, created = RideMonitorMatch.objects.get_or_create(
            monitor_request=monitor_request,
            ride_post=ride_post,
        )
        if created:
            created_matches.append(match)

    monitor_request.last_matched_at = timezone.now()
    monitor_request.save(update_fields=['last_matched_at', 'updated_at'])
    return created_matches


def match_post(monitor_request, ride_post):
    if ride_post.user_id == monitor_request.user_id:
        return None

    if not matches_ride_post(monitor_request, ride_post):
        return None

    match, _ = RideMonitorMatch.objects.get_or_create(
        monitor_request=monitor_request,
        ride_post=ride_post,
    )
    return match


def similar_monitor_requests_queryset(monitor_request):
    qs = RideMonitorRequest.objects.filter(
        status=RideMonitorRequestStatus.PENDING,
        deleted_at__isnull=True,
        direction=monitor_request.direction,
        transport_method=monitor_request.transport_method,
    )

    if monitor_request.direction == RideDirection.TO_UNIVERSITY:
        qs = qs.filter(starting_location=monitor_request.starting_location)
    else:
        qs = qs.filter(destination_location=monitor_request.destination_location)

    if monitor_request.departure_time:
        window_start = monitor_request.departure_time - timedelta(minutes=30)
        window_end = monitor_request.departure_time + timedelta(minutes=30)
        qs = qs.filter(departure_time__gte=window_start, departure_time__lte=window_end)
    else:
        qs = qs.filter(departure_time__isnull=True)

    return qs


def matching_ride_posts_exist(monitor_request):
    return matching_posts_queryset(monitor_request).exists()


def notify_similar_monitors_to_create_post(monitor_request):
    similar_requests = similar_monitor_requests_queryset(monitor_request).select_related('user')
    if similar_requests.count() < 2:
        return

    if matching_ride_posts_exist(monitor_request):
        return

    create_url = reverse('ride_share:create_ride')
    for req in similar_requests:
        notify(
            recipient=req.user,
            verb=(
                'Multiple students are looking for the same ride within 30 minutes. '
                'Create a ride post so everyone can join.'
            ),
            target=req,
            data={
                'url': create_url,
                'monitor_request_id': req.pk,
            },
        )


def process_new_ride_post(ride_post):
    for monitor_request in RideMonitorRequest.objects.filter(
        status=RideMonitorRequestStatus.PENDING,
        deleted_at__isnull=True,
        direction=ride_post.direction,
    ).exclude(user=ride_post.user):
        match_post(monitor_request, ride_post)


def process_new_monitor_request(monitor_request):
    sync_matches(monitor_request)
    notify_similar_monitors_to_create_post(monitor_request)