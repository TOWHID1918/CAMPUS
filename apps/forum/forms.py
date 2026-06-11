from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.academics.models import Course, Department
from apps.forum.models import ForumThread
from apps.threads.models import ThreadMessage

User = get_user_model()


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError(self.error_messages["required"])
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [super(MultipleFileField, self).clean(f, initial) for f in data]


class ForumThreadCreateForm(forms.Form):
    title = forms.CharField(max_length=255)
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        required=True,
        help_text="Main body text for your thread.",
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(), required=False
    )
    course = forms.ModelChoiceField(queryset=Course.objects.all(), required=False)

    participants = forms.CharField(
        required=False,
        help_text="Enter comma-separated handles/student IDs, or type 'anyone' for a Public thread.",
    )

    is_announcement = forms.BooleanField(
        required=False,
        label="Mark as Announcement",
        help_text="Check this box to make this thread an announcement (Only moderators can create announcement threads).",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_participants(self):
        data = self.cleaned_data.get("participants", "").strip()
        if not data or data.lower() == "anyone":
            return []  # Indicates public thread

        entries = [u.strip() for u in data.split(",") if u.strip()]
        users = list(
            User.objects.filter(
                Q(handle__in=entries) | Q(profile__student_id__in=entries)
            )
        )

        found_entries = {u.handle for u in users} | {
            u.profile.student_id for u in users if u.profile.student_id
        }
        missing = [entry for entry in entries if entry not in found_entries]
        if missing:
            raise ValidationError(f"Users not found: {', '.join(missing)}")

        return users

    def clean(self):
        cleaned_data = super().clean()
        is_announcement = cleaned_data.get("is_announcement", False)

        if is_announcement:
            if not self.user or not getattr(self.user.profile, "is_moderator", False):
                raise ValidationError(
                    "Only moderators are allowed to create announcement threads."
                )
        return cleaned_data


class ForumThreadEditForm(forms.ModelForm):
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        required=True,
        help_text="Edit the main body text for your thread.",
    )
    participants = forms.CharField(
        required=False,
        help_text="Edit comma-separated handles/student IDs to change participants.",
    )

    class Meta:
        model = ForumThread
        fields = ["title", "department", "course"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.thread:
            self.fields["description"].initial = self.instance.thread.description
            # Populate current participants as comma-separated handles
            current_participants = self.instance.thread.participants.exclude(
                user=self.instance.author
            ).values_list("user__handle", flat=True)
            if current_participants:
                self.fields["participants"].initial = ", ".join(current_participants)

    def clean_participants(self):
        data = self.cleaned_data.get("participants", "").strip()
        if not data:
            return []  # No additional participants

        entries = [u.strip() for u in data.split(",") if u.strip()]
        users = list(
            User.objects.filter(
                Q(handle__in=entries) | Q(profile__student_id__in=entries)
            )
        )

        found_entries = {u.handle for u in users} | {
            u.profile.student_id for u in users if u.profile.student_id
        }
        missing = [entry for entry in entries if entry not in found_entries]
        if missing:
            raise ValidationError(f"Users not found: {', '.join(missing)}")

        return users


class ThreadMessageForm(forms.ModelForm):
    uploaded_photos = MultipleFileField(required=False, label="Attach Photos")

    class Meta:
        model = ThreadMessage
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Add a reply..."}
            ),
        }
