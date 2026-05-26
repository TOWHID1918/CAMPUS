# apps/ride_share/forms.py
from datetime import timedelta

from django import forms
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import RidePost, RideMonitorRequest, RideDirection, Location


class RidePostForm(forms.ModelForm):
    """Form for creating/editing a ride post"""
    
    direction = forms.ChoiceField(
        choices=RideDirection.choices,
        widget=forms.RadioSelect,
        label="Direction",
        help_text="Are you going to university or home?"
    )
    
    class Meta:
        model = RidePost
        fields = [
            'starting_location',
            'destination_location',
            'direction',
            'transport_method',
            'departure_time',
            'notes',
        ]
        widgets = {
            'starting_location': forms.Select(attrs={
                'class': 'form-control',
            }),
            'destination_location': forms.Select(attrs={
                'class': 'form-control',
            }),
            'transport_method': forms.Select(attrs={
                'class': 'form-control',
            }),
            'departure_time': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any notes for potential riders...',
            }),
        }
        labels = {
            'starting_location': 'Starting Location',
            'destination_location': 'Destination Location',
            'transport_method': 'Transport Type',
            'departure_time': 'When do you leave?',
            'notes': 'Additional Notes',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        Location.ensure_predefined_locations()
        super().__init__(*args, **kwargs)
        locations = Location.objects.filter(is_active=True).order_by('name')
        self.fields['starting_location'].queryset = locations
        self.fields['destination_location'].queryset = locations
        self.fields['starting_location'].required = False
        self.fields['destination_location'].required = False
        self.fields['starting_location'].widget = forms.Select(attrs={'class': 'form-control'})
        self.fields['destination_location'].widget = forms.Select(attrs={'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        departure_time = cleaned_data.get('departure_time')
        expires_at = cleaned_data.get('expires_at')
        direction = cleaned_data.get('direction')
        starting_location = cleaned_data.get('starting_location')
        destination_location = cleaned_data.get('destination_location')

        starting_location_fixed = self.data.get('starting_location_fixed')
        destination_location_fixed = self.data.get('destination_location_fixed')

        try:
            uiu_location = Location.objects.get(pk='United International University')
        except Location.DoesNotExist:
            uiu_location = None

        if not starting_location and starting_location_fixed:
            try:
                cleaned_data['starting_location'] = Location.objects.get(pk=starting_location_fixed)
                starting_location = cleaned_data['starting_location']
            except Location.DoesNotExist:
                pass

        if not destination_location and destination_location_fixed:
            try:
                cleaned_data['destination_location'] = Location.objects.get(pk=destination_location_fixed)
                destination_location = cleaned_data['destination_location']
            except Location.DoesNotExist:
                pass

        if direction == RideDirection.TO_UNIVERSITY and uiu_location:
            cleaned_data['destination_location'] = uiu_location
            if starting_location == uiu_location:
                raise forms.ValidationError(
                    "For rides going to university, choose a starting location other than UIU."
                )

        if direction == RideDirection.TO_HOME and uiu_location:
            cleaned_data['starting_location'] = uiu_location
            if destination_location == uiu_location:
                raise forms.ValidationError(
                    "For rides going home, choose a destination location other than UIU."
                )

        if starting_location and destination_location and starting_location == destination_location:
            raise forms.ValidationError(
                "Starting location and destination cannot be the same."
            )
        
        if departure_time and expires_at:
            if expires_at < departure_time:
                raise forms.ValidationError(
                    "Post close time cannot be before departure time."
                )

            now = timezone.now()
            min_allowed = now + timedelta(minutes=30)
            if departure_time < min_allowed:
                raise forms.ValidationError(
                    "Departure time must be at least 30 minutes from now."
                )

            if expires_at < now:
                raise forms.ValidationError(
                    "Post close time must be in the future."
                )

        if departure_time and destination_location and cleaned_data.get('transport_method'):
            window_start = departure_time - timedelta(minutes=30)
            window_end = departure_time + timedelta(minutes=30)

            similar_posts = RidePost.objects.filter(
                destination_location=destination_location,
                transport_method=cleaned_data['transport_method'],
                departure_time__gte=window_start,
                departure_time__lte=window_end,
                deleted_at__isnull=True,
                status='open',
            )

            if self.instance and self.instance.pk:
                similar_posts = similar_posts.exclude(pk=self.instance.pk)

            current_user = self.user or getattr(self.instance, 'user', None)
            if current_user is not None:
                similar_posts = similar_posts.exclude(user=current_user)

            matches = similar_posts.order_by('departure_time')
            if matches.exists():
                def _display_departure_time(dt):
                    if timezone.is_aware(dt):
                        dt = timezone.localtime(dt)
                    return dt.strftime('%I:%M %p')

                # Build a list of links for all similar posts within the time window
                links_html = format_html_join(
                    '',
                    '{} at {} — <a href="{}">Open</a><br/>',
                    (
                        (
                            getattr(p.user, 'handle', None) or getattr(p.user, 'email', 'another user'),
                            _display_departure_time(p.departure_time),
                            reverse('ride_share:ride_detail', args=[p.pk])
                        ) for p in matches
                    )
                )

                if matches.count() == 1:
                    # Keep a short singular message for a single match
                    raise forms.ValidationError(format_html('A similar ride already exists: {}', links_html))
                else:
                    raise forms.ValidationError(format_html('Multiple similar rides were found near your chosen time:<br/>{}', links_html))

        return cleaned_data


class ApproachRideForm(forms.Form):
    """Form for approaching a ride (without creating a post)"""
    
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Tell the rider why you\'d like to join...',
        }),
        label='Message',
        help_text='Optional message to the ride organizer'
    )
    
    party_size = forms.IntegerField(
        min_value=1,
        max_value=4,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'type': 'number',
        }),
        label='Number of Passengers (including you)',
    )


class RideMonitorRequestForm(forms.ModelForm):
    """Form for creating a ride monitor request instead of a direct ride post."""

    direction = forms.ChoiceField(
        choices=RideDirection.choices,
        widget=forms.RadioSelect,
        label='Direction',
        help_text='Are you going to university or home?'
    )

    class Meta:
        model = RideMonitorRequest
        fields = [
            'starting_location',
            'destination_location',
            'direction',
            'transport_method',
            'departure_time',
            'notes',
        ]
        widgets = {
            'starting_location': forms.Select(attrs={'class': 'form-control'}),
            'destination_location': forms.Select(attrs={'class': 'form-control'}),
            'transport_method': forms.Select(attrs={'class': 'form-control'}),
            'departure_time': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional details about your trip...',
            }),
        }
        labels = {
            'starting_location': 'Starting Location',
            'destination_location': 'Destination Location',
            'transport_method': 'Category',
            'departure_time': 'Date & Time',
            'notes': 'Additional Notes',
        }

    def __init__(self, *args, **kwargs):
        Location.ensure_predefined_locations()
        super().__init__(*args, **kwargs)
        locations = Location.objects.filter(is_active=True).order_by('name')
        self.fields['starting_location'].queryset = locations
        self.fields['destination_location'].queryset = locations
        self.fields['starting_location'].required = False
        self.fields['destination_location'].required = False
        self.fields['starting_location'].widget = forms.Select(attrs={'class': 'form-control'})
        self.fields['destination_location'].widget = forms.Select(attrs={'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        departure_time = cleaned_data.get('departure_time')
        direction = cleaned_data.get('direction')
        starting_location = cleaned_data.get('starting_location')
        destination_location = cleaned_data.get('destination_location')
        starting_location_fixed = self.data.get('starting_location_fixed')
        destination_location_fixed = self.data.get('destination_location_fixed')

        try:
            uiu_location = Location.objects.get(pk='United International University')
        except Location.DoesNotExist:
            uiu_location = None

        if not starting_location and starting_location_fixed:
            try:
                cleaned_data['starting_location'] = Location.objects.get(pk=starting_location_fixed)
                starting_location = cleaned_data['starting_location']
            except Location.DoesNotExist:
                pass

        if not destination_location and destination_location_fixed:
            try:
                cleaned_data['destination_location'] = Location.objects.get(pk=destination_location_fixed)
                destination_location = cleaned_data['destination_location']
            except Location.DoesNotExist:
                pass

        if direction == RideDirection.TO_UNIVERSITY and uiu_location:
            cleaned_data['destination_location'] = uiu_location
            if starting_location == uiu_location:
                raise forms.ValidationError(
                    'For rides going to university, choose a starting location other than UIU.'
                )

        if direction == RideDirection.TO_HOME and uiu_location:
            cleaned_data['starting_location'] = uiu_location
            if destination_location == uiu_location:
                raise forms.ValidationError(
                    'For rides going home, choose a destination location other than UIU.'
                )

        if starting_location and destination_location and starting_location == destination_location:
            raise forms.ValidationError('Starting location and destination cannot be the same.')

        if departure_time:
            now = timezone.now()
            min_allowed = now + timedelta(minutes=30)
            if departure_time < min_allowed:
                raise forms.ValidationError('Date & Time must be at least 30 minutes from now.')

        return cleaned_data
