# apps/ride_share/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib import messages
from django.db.models import Prefetch

from .models import RidePost, RideGroup, RideGroupMember, RideDirection, Location, UIU_LOCATION, RideMonitorRequest, RideMonitorMatch
from .forms import RidePostForm, ApproachRideForm, RideMonitorRequestForm
from . import matching
from .signals import notify_join_request, notify_join_approved
from apps.threads.models import Thread, ThreadParticipant
from apps.common.choices import (
    RidePostStatus, RideGroupStatus, RideGroupMemberStatus,
    ThreadParticipantRole, ThreadVisibility, TransportMethod
)


def _expire_past_date_ride_posts():
    """Soft-delete rides whose departure calendar date is already past and remove chat thread."""
    today = timezone.localdate()
    expired_posts = RidePost.objects.filter(
        deleted_at__isnull=True,
        departure_time__date__lt=today,
    ).select_related('ride_group', 'ride_group__thread')

    for post in expired_posts:
        with transaction.atomic():
            ride_group = getattr(post, 'ride_group', None)
            if ride_group:
                thread = ride_group.thread
                if thread:
                    ride_group.thread = None
                    ride_group.save(update_fields=['thread', 'updated_at'])
                    thread.delete()

                if ride_group.status != RideGroupStatus.CANCELLED:
                    ride_group.status = RideGroupStatus.CANCELLED
                    ride_group.save(update_fields=['status', 'updated_at'])

            post.soft_delete()


def _is_past_date_ride(ride_post):
    return ride_post.departure_time.date() < timezone.localdate()

@login_required
def all_rides(request):
    """Browse all active ride posts with N+1 query optimization"""
    _expire_past_date_ride_posts()
    now = timezone.now()
    Location.ensure_predefined_locations()
    
    # Using annotate to calculate occupancy in a single DB trip
    posts = RidePost.objects.filter(
        status=RidePostStatus.OPEN,
        deleted_at__isnull=True,
        expires_at__gt=now,
        ride_group__status=RideGroupStatus.FORMING,
    ).select_related('user', 'user__profile', 'starting_location', 'destination_location').order_by('-created_at')
    
    # Filter by direction if provided
    direction = request.GET.get('direction')
    if direction:
        posts = posts.filter(direction=direction)
    
    # Filter by transport method if provided
    transport = request.GET.get('transport')
    if transport:
        posts = posts.filter(transport_method=transport)
    
    # Filter by starting location if provided
    location = request.GET.get('location')
    if location:
        posts = posts.filter(
            Q(starting_location_id=location) | Q(destination_location_id=location)
        )

    locations = Location.objects.filter(is_active=True).order_by('name')

    context = {
        'posts': posts,
        'tab': 'all',
        'directions': RideDirection.choices,
        'transports': TransportMethod.choices,
        'locations': locations,
        'selected_direction': direction,
        'selected_transport': transport,
        'selected_location': location,
    }
    return render(request, 'ride_share/all_rides.html', context)


@login_required
def approach_ride(request, pk):
    """User joins a ride post - Protected against Race Conditions"""
    _expire_past_date_ride_posts()
    ride_post = get_object_or_404(
        RidePost.objects.select_related('starting_location', 'destination_location'),
        pk=pk,
    )

    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has expired and is no longer available.')
        return redirect('ride_share:all_rides')
    
    # GET: Display the form to join the ride
    if request.method == 'GET':
        form = ApproachRideForm()
        context = {
            'ride_post': ride_post,
            'form': form,
        }
        return render(request, 'ride_share/approach_ride.html', context)
    
    # POST: Process the join request (create a pending request; organizer must approve)
    if request.method == 'POST':
        form = ApproachRideForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Invalid form data.')
            return redirect('ride_share:ride_detail', pk=pk)

        party_size = form.cleaned_data['party_size']

        if ride_post.user == request.user:
            messages.error(request, 'You cannot join your own ride!')
            return redirect('ride_share:ride_detail', pk=pk)

        with transaction.atomic():
            ride_group, _ = RideGroup.objects.select_for_update().get_or_create(
                ride_post=ride_post,
                defaults={'status': RideGroupStatus.FORMING}
            )

            existing = RideGroupMember.objects.filter(group=ride_group, user=request.user).first()
            if existing:
                if existing.status == RideGroupMemberStatus.PENDING:
                    messages.warning(request, 'Your join request is already pending approval.')
                elif existing.status == RideGroupMemberStatus.CONFIRMED:
                    messages.warning(request, 'You are already in this ride!')
                elif existing.status == RideGroupMemberStatus.LEFT:
                    remaining_seats = ride_group.max_capacity - ride_group.current_occupancy
                    if party_size > remaining_seats:
                        messages.error(request, f'Only {remaining_seats} seat(s) available. You requested {party_size}.')
                        return redirect('ride_share:ride_detail', pk=pk)

                    existing.party_size = party_size
                    existing.status = RideGroupMemberStatus.PENDING
                    existing.save(update_fields=['party_size', 'status', 'updated_at'])
                    notify_join_request(existing)
                    messages.success(request, 'Your rejoin request has been submitted. The organizer will review it.')
                    return redirect('ride_share:ride_detail', pk=pk)
                else:
                    messages.warning(request, 'You have an existing request for this ride.')
                return redirect('ride_share:ride_detail', pk=pk)

            remaining_seats = ride_group.max_capacity - ride_group.current_occupancy
            if party_size > remaining_seats:
                messages.error(request, f'Only {remaining_seats} seat(s) available. You requested {party_size}.')
                return redirect('ride_share:ride_detail', pk=pk)

            # Create a pending membership; organizer must approve to confirm and add to chat
            member = RideGroupMember.objects.create(
                group=ride_group,
                user=request.user,
                party_size=party_size,
                status=RideGroupMemberStatus.PENDING
            )
            notify_join_request(member)

        messages.success(request, 'Join request submitted. The organizer will review and approve your request.')
        return redirect('ride_share:ride_detail', pk=pk)


@login_required
@require_POST
def leave_ride(request, pk):
    """User leaves a ride and is safely removed from threads"""
    _expire_past_date_ride_posts()
    ride_post = get_object_or_404(RidePost, pk=pk)
    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has already expired.')
        return redirect('ride_share:my_matches')

    with transaction.atomic():
        ride_post = RidePost.objects.select_for_update().get(pk=ride_post.pk)
        ride_group = RideGroup.objects.select_for_update().get(ride_post=ride_post)
        member = get_object_or_404(RideGroupMember, group=ride_group, user=request.user)

        if member.is_initiator and ride_group.status == RideGroupStatus.FORMING:
            messages.error(request, "Ride organizer cannot leave a ride that hasn't started!")
            return redirect('ride_share:ride_detail', pk=pk)

        # Remove from group
        member.status = RideGroupMemberStatus.LEFT
        member.save(update_fields=['status', 'updated_at'])

        # If a once-full, forming ride now has seats, make it discoverable again
        if (
            ride_group.status == RideGroupStatus.FORMING
            and ride_post.status == RidePostStatus.CLOSED
            and not ride_group.is_full
        ):
            ride_post.status = RidePostStatus.OPEN
            ride_post.save(update_fields=['status', 'updated_at'])

        # Remove from chat thread to secure privacy
        if ride_group.thread:
            ThreadParticipant.objects.filter(thread=ride_group.thread, user=request.user).delete()
    
    messages.success(request, 'You have left the ride.')
    return redirect('ride_share:my_matches')


@login_required
def ride_detail(request, pk):
    """View details of a specific ride post"""
    _expire_past_date_ride_posts()
    ride_post = (
        RidePost.objects.select_related(
            'starting_location',
            'destination_location',
            'user',
            'user__profile',
        ).filter(pk=pk).first()
    )

    if not ride_post:
        messages.error(request, 'This ride post has been deleted.')
        return redirect('ride_share:all_rides')

    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has expired and was removed.')
        return redirect('ride_share:all_rides')
    
    context = {
        'ride_post': ride_post,
        'ride_group': None,
        'members': [],
        'user_is_member': False,
        'is_initiator': False,
        'is_full': False,
    }
    
    # Get the ride group if it exists
    if hasattr(ride_post, 'ride_group'):
        group = ride_post.ride_group
        context['ride_group'] = group
        context['members'] = list(group.members.filter(status=RideGroupMemberStatus.CONFIRMED).select_related('user'))
        # Pending join requests for organizer review
        pending_qs = group.members.filter(status=RideGroupMemberStatus.PENDING).select_related('user')
        context['pending_requests'] = list(pending_qs)
        context['occupancy'] = group.current_occupancy
        context['max_capacity'] = group.max_capacity
        context['available_seats'] = group.max_capacity - group.current_occupancy
        context['is_full'] = group.is_full
        # Calculate capacity percentage for progress bar
        context['capacity_percent'] = int((group.current_occupancy / group.max_capacity) * 100) if group.max_capacity > 0 else 0
        # Determine capacity bar color
        if group.current_occupancy == group.max_capacity:
            context['capacity_color'] = '#dc3545'  # Red - Full
        elif group.current_occupancy >= group.max_capacity * 0.75:
            context['capacity_color'] = '#ffc107'  # Yellow - Almost full
        else:
            context['capacity_color'] = '#28a745'  # Green - Plenty of seats
        
        # Check if user is a member
        try:
            member = group.members.get(user=request.user)
            context['user_is_member'] = True
            context['is_initiator'] = member.is_initiator
        except RideGroupMember.DoesNotExist:
            pass
    
    return render(request, 'ride_share/ride_detail.html', context)


@login_required
def my_posts(request):
    """View user's own ride posts"""
    _expire_past_date_ride_posts()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete':
            post_id = request.POST.get('post_id')
            try:
                post = RidePost.objects.get(pk=post_id, user=request.user)
            except RidePost.DoesNotExist:
                messages.error(request, 'Ride not found or you are not the owner.')
                return redirect('ride_share:my_posts')

            has_other_confirmed_members = RideGroupMember.objects.filter(
                group__ride_post=post,
                status=RideGroupMemberStatus.CONFIRMED,
            ).exclude(user=request.user).exists()

            if has_other_confirmed_members:
                messages.error(request, 'You cannot delete this ride because other members have already joined.')
                return redirect('ride_share:my_posts')

            # Permanently remove associated thread (if any), then delete the post
            try:
                if hasattr(post, 'ride_group') and post.ride_group is not None:
                    rg = post.ride_group
                    thread = rg.thread
                    if thread:
                        # break the PROTECT relation then delete the thread
                        rg.thread = None
                        rg.save(update_fields=['thread'])
                        thread.delete()

                post.delete()
                messages.success(request, 'Ride removed permanently.')
            except Exception as e:
                # If permanent removal fails, fall back to soft delete and inform the user
                try:
                    post.soft_delete()
                except Exception:
                    pass
                messages.error(request, f'Failed to permanently delete ride: {e}. Post marked cancelled instead.')
            return redirect('ride_share:my_posts')

    posts = RidePost.objects.filter(user=request.user).select_related(
        'starting_location',
        'destination_location',
    ).annotate(
        other_confirmed_member_count=Count(
            'ride_group__members',
            filter=Q(ride_group__members__status=RideGroupMemberStatus.CONFIRMED) & ~Q(ride_group__members__user=request.user),
        )
    ).order_by('-created_at')
    
    context = {
        'posts': posts,
        'tab': 'my_posts',
    }
    return render(request, 'ride_share/my_posts.html', context)


@login_required
def my_matches(request):
    """View user's joined/matched rides"""
    _expire_past_date_ride_posts()
    memberships = RideGroupMember.objects.filter(user=request.user).select_related(
        'group',
        'group__ride_post',
        'group__ride_post__starting_location',
        'group__ride_post__destination_location',
    ).order_by('-joined_at')
    
    confirmed_rides = []
    for m in memberships:
        if m.status != RideGroupMemberStatus.CONFIRMED:
            continue
        group = m.group
        # Include only if there are other confirmed members besides the current user
        other_confirmed = group.members.filter(status=RideGroupMemberStatus.CONFIRMED).exclude(user=request.user)
        if other_confirmed.exists():
            confirmed_rides.append(group)

    pending_matches = [m for m in memberships if m.status == RideGroupMemberStatus.PENDING]
    left_rides = [m for m in memberships if m.status == RideGroupMemberStatus.LEFT]

    monitor_matches = RideMonitorMatch.objects.select_related(
        'monitor_request',
        'ride_post',
        'ride_post__user',
        'ride_post__user__profile',
        'ride_post__starting_location',
        'ride_post__destination_location',
    ).filter(monitor_request__user=request.user).order_by('-matched_at')

    monitor_requests = RideMonitorRequest.objects.filter(
        user=request.user,
        deleted_at__isnull=True,
    ).prefetch_related(
        Prefetch('matches', queryset=monitor_matches)
    ).select_related(
        'starting_location',
        'destination_location',
    ).order_by('-created_at')
    
    context = {
        'confirmed_rides': confirmed_rides,
        'pending_matches': pending_matches,
        'left_rides': left_rides,
        'monitor_requests': monitor_requests,
        'tab': 'my_matches',
    }
    return render(request, 'ride_share/my_matches.html', context)


@login_required
def request_ride(request):
    """Create a ride monitor request instead of posting a ride directly."""
    _expire_past_date_ride_posts()
    Location.ensure_predefined_locations()

    if request.method == 'POST':
        form = RideMonitorRequestForm(request.POST)
        if form.is_valid():
            monitor_request = form.save(commit=False)
            monitor_request.user = request.user
            monitor_request.save()
            try:
                matching.process_new_monitor_request(monitor_request)
            except Exception:
                messages.warning(request, 'Your ride monitor was saved, but matching could not finish right now.')
            messages.success(request, 'Your ride monitor is active. Matching rides will appear below.')
            return redirect('ride_share:my_matches')
    else:
        initial = {
            'direction': RideDirection.TO_UNIVERSITY,
            'destination_location': UIU_LOCATION,
        }
        form = RideMonitorRequestForm(initial=initial)

    locations = Location.objects.filter(is_active=True).order_by('name')
    context = {
        'form': form,
        'locations': locations,
        'UIU_LOCATION': UIU_LOCATION,
    }
    return render(request, 'ride_share/request_ride.html', context)


@login_required
def create_ride(request):
    """Create a new ride post"""
    _expire_past_date_ride_posts()
    Location.ensure_predefined_locations()
    if request.method == 'POST':
        form = RidePostForm(request.POST, user=request.user)
        if form.is_valid():
            ride_post = form.save(commit=False)
            ride_post.user = request.user
            ride_post.save()
            
            # Create the ride group and thread
            with transaction.atomic():
                ride_group = RideGroup.objects.create(
                    ride_post=ride_post,
                    status=RideGroupStatus.FORMING
                )
                
                # Create thread for the ride group
                thread = Thread.objects.create(
                    title=f"Ride: {ride_post.starting_location} → {ride_post.destination_location}",
                    description=f"Ride scheduled for {ride_post.departure_time.strftime('%Y-%m-%d %H:%M')}",
                    visibility=ThreadVisibility.PRIVATE,
                )
                ride_group.thread = thread
                ride_group.save(update_fields=['thread'])
                
                # Add user as initiator
                RideGroupMember.objects.create(
                    group=ride_group,
                    user=request.user,
                    is_initiator=True,
                    status=RideGroupMemberStatus.CONFIRMED
                )
                
                # Add user as thread participant
                ThreadParticipant.objects.create(
                    thread=thread,
                    user=request.user,
                    role=ThreadParticipantRole.AUTHOR
                )

            try:
                matching.process_new_ride_post(ride_post)
            except Exception:
                messages.warning(request, 'Ride created, but matching could not finish right now.')
            
            messages.success(request, 'Ride created successfully!')
            return redirect('ride_share:ride_detail', pk=ride_post.pk)
    else:
        # Pre-fill form fields on GET using UIU location when appropriate
        initial = {}
        # default direction is TO_UNIVERSITY; prefill destination with UIU when empty
        initial['direction'] = RideDirection.TO_UNIVERSITY
        initial['destination_location'] = UIU_LOCATION
        form = RidePostForm(initial=initial, user=request.user)

    locations = Location.objects.filter(is_active=True).order_by('name')
    context = {
        'form': form,
        'locations': locations,
        'UIU_LOCATION': UIU_LOCATION,
    }
    return render(request, 'ride_share/create_ride.html', context)


@login_required
def ride_chat(request, pk):
    """Redirect to thread chat for ride group - leverages threads app"""
    _expire_past_date_ride_posts()
    ride_post = RidePost.objects.filter(pk=pk).first()

    if not ride_post:
        messages.error(request, 'This ride post has been deleted.')
        return redirect('ride_share:all_rides')

    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has expired. Chat is no longer available.')
        return redirect('ride_share:all_rides')

    ride_group = get_object_or_404(RideGroup, ride_post=ride_post)
    
    # Check if user is a confirmed member of the ride group
    member = ride_group.members.filter(user=request.user).first()
    if not member or member.status != RideGroupMemberStatus.CONFIRMED:
        messages.error(request, 'You must be a confirmed member to access the chat. Please request to join the ride.')
        return redirect('ride_share:ride_detail', pk=pk)
    
    # Ensure thread exists
    if not ride_group.thread:
        messages.error(request, 'No chat available for this ride.')
        return redirect('ride_share:ride_detail', pk=pk)
    
    # Redirect to the threads app's thread_detail view for full chat experience
    return redirect('threads:thread_detail', thread_id=ride_group.thread.id)


@login_required
@require_POST
def start_ride(request, pk):
    """Start a ride (organizer only)"""
    _expire_past_date_ride_posts()
    ride_post = get_object_or_404(RidePost, pk=pk)
    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has already expired.')
        return redirect('ride_share:all_rides')

    ride_group = get_object_or_404(RideGroup, ride_post=ride_post)
    member = get_object_or_404(RideGroupMember, group=ride_group, user=request.user)
    
    if not member.is_initiator:
        messages.error(request, 'Only the ride organizer can start the ride.')
        return redirect('ride_share:ride_detail', pk=pk)
    
    if ride_group.status != RideGroupStatus.FORMING:
        messages.error(request, 'Ride is already started or completed.')
        return redirect('ride_share:ride_detail', pk=pk)
    
    # Update ride group status
    ride_group.status = RideGroupStatus.IN_TRANSIT
    ride_group.save(update_fields=['status', 'updated_at'])
    
    # Update ride post status
    ride_post.status = RidePostStatus.CLOSED
    ride_post.save(update_fields=['status', 'updated_at'])
    
    messages.success(request, 'Ride started!')
    return redirect('ride_share:ride_detail', pk=pk)


@login_required
@require_POST
def approve_request(request, ride_pk, member_pk):
    """Organizer approves a pending join request"""
    _expire_past_date_ride_posts()
    ride_post = get_object_or_404(RidePost, pk=ride_pk)
    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has already expired.')
        return redirect('ride_share:all_rides')

    if ride_post.user != request.user:
        messages.error(request, 'Only the organizer can approve requests.')
        return redirect('ride_share:ride_detail', pk=ride_pk)

    ride_group = get_object_or_404(RideGroup, ride_post=ride_post)
    member = get_object_or_404(RideGroupMember, pk=member_pk, group=ride_group)

    if member.status != RideGroupMemberStatus.PENDING:
        messages.warning(request, 'This request is not pending.')
        return redirect('ride_share:ride_detail', pk=ride_pk)

    with transaction.atomic():
        ride_group = RideGroup.objects.select_for_update().get(pk=ride_group.pk)
        member = RideGroupMember.objects.select_for_update().get(pk=member.pk)

        remaining_seats = ride_group.max_capacity - ride_group.current_occupancy
        if remaining_seats < member.party_size:
            messages.error(request, f'Only {remaining_seats} seat(s) are available for this request.')
            return redirect('ride_share:ride_detail', pk=ride_pk)

        member.status = RideGroupMemberStatus.CONFIRMED
        member.save(update_fields=['status', 'updated_at'])
        notify_join_approved(member)

        if ride_group.is_full and ride_post.status == RidePostStatus.OPEN:
            ride_post.status = RidePostStatus.CLOSED
            ride_post.save(update_fields=['status', 'updated_at'])

        # create thread if missing
        if not ride_group.thread:
            thread = Thread.objects.create(
                title=f"Ride: {ride_post.starting_location} → {ride_post.destination_location}",
                description=f"Ride scheduled for {ride_post.departure_time.strftime('%Y-%m-%d %H:%M')}",
                visibility=ThreadVisibility.PRIVATE,
            )
            ride_group.thread = thread
            ride_group.save(update_fields=['thread'])
            ThreadParticipant.objects.create(
                thread=thread,
                user=ride_post.user,
                role=ThreadParticipantRole.AUTHOR
            )

        # add approved user to thread
        ThreadParticipant.objects.get_or_create(
            thread=ride_group.thread,
            user=member.user,
            defaults={'role': ThreadParticipantRole.MEMBER}
        )

    messages.success(request, 'Request approved; user added to the ride and chat.')
    return redirect('ride_share:ride_detail', pk=ride_pk)


@login_required
@require_POST
def reject_request(request, ride_pk, member_pk):
    """Organizer rejects a pending join request"""
    _expire_past_date_ride_posts()
    ride_post = get_object_or_404(RidePost, pk=ride_pk)
    if ride_post.deleted_at or _is_past_date_ride(ride_post):
        if not ride_post.deleted_at:
            ride_post.soft_delete()
        messages.error(request, 'This ride has already expired.')
        return redirect('ride_share:all_rides')
    if ride_post.user != request.user:
        messages.error(request, 'Only the organizer can reject requests.')
        return redirect('ride_share:ride_detail', pk=ride_pk)

    ride_group = get_object_or_404(RideGroup, ride_post=ride_post)
    member = get_object_or_404(RideGroupMember, pk=member_pk, group=ride_group)

    if member.status != RideGroupMemberStatus.PENDING:
        messages.warning(request, 'This request is not pending.')
        return redirect('ride_share:ride_detail', pk=ride_pk)

    member.status = RideGroupMemberStatus.LEFT
    member.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Request rejected.')
    return redirect('ride_share:ride_detail', pk=ride_pk)