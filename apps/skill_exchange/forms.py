from django import forms

from .models import ExchangePost
from .services import has_duplicate_active_post
from apps.common.choices import SkillStatus, UserSkillStatus
from .models import ExchangePost, Skill, SkillSubmission, UserSkill


class SkillExchangePostForm(forms.ModelForm):
    class Meta:
        model = ExchangePost
        fields = ["description", "skills_offered", "skills_needed"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user:
            # skills_offered — only skills the user has on their profile
            user_skill_ids = UserSkill.objects.filter(
                user=self.user,
                status=UserSkillStatus.APPROVED,
            ).values_list('skill_id', flat=True)

            self.fields['skills_offered'].queryset = Skill.objects.filter(
                id__in=user_skill_ids
            ).order_by('name')

        # skills_needed — all approved skills, shown to everyone
        self.fields['skills_needed'].queryset = Skill.objects.filter(
            status=SkillStatus.APPROVED
        ).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        offered_skills = cleaned_data.get("skills_offered")
        needed_skills = cleaned_data.get("skills_needed")

        if offered_skills and needed_skills:
            offered_ids = set(s.id for s in offered_skills)
            needed_ids = set(s.id for s in needed_skills)

            # Check 1: Prevent offering and requesting the same skill
            if offered_ids & needed_ids:
                raise forms.ValidationError(
                    "You cannot offer a skill that you are also requesting."
                )

            # Check 2: Prevent duplicate active posts by this user
            if self.user and has_duplicate_active_post(
                self.user, offered_ids, needed_ids
            ):
                raise forms.ValidationError(
                    "You already have an active post offering and requesting this exact combination of skills."
                )

        return cleaned_data


ROLE_CHOICES = [
    ('', '-- Select role --'),
    ('teach', 'I can teach this'),
    ('learn', 'I want to learn this'),
    ('both',  'Both — teach & learn'),
]

PROFICIENCY_CHOICES = [
    ('', '-- Select level --'),
    (1, 'Beginner (1)'),
    (2, 'Elementary (2)'),
    (3, 'Intermediate (3)'),
    (4, 'Advanced (4)'),
    (5, 'Expert (5)'),
]


class AddExistingSkillForm(forms.Form):
    skill = forms.ModelChoiceField(
        queryset=Skill.objects.filter(status=SkillStatus.APPROVED).order_by('name'),
        empty_label='-- Select an approved skill --',
    )
    proficiency_level  = forms.ChoiceField(choices=PROFICIENCY_CHOICES)
    proficiency_method = forms.CharField(
        max_length=100, required=False,
        help_text="e.g. Self-taught, University course, Bootcamp"
    )
    proficiency_notes  = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False
    )
    years_experience   = forms.DecimalField(
        max_digits=4, decimal_places=1, required=False, min_value=0
    )
    # role removed — hardcoded to 'both' in the view

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        skill = cleaned.get('skill')
        if skill and self.user:
            if UserSkill.objects.filter(user=self.user, skill=skill).exists():
                raise forms.ValidationError(
                    f'"{skill.name}" is already on your profile.'
                )
        return cleaned


class ProposeNewSkillForm(forms.ModelForm):
    class Meta:
        model  = SkillSubmission
        fields = [
            'name', 'description',
            'proficiency_level', 'proficiency_method',
            'proficiency_notes', 'years_experience',
        ]
        widgets = {
            'description':       forms.Textarea(attrs={'rows': 3}),
            'proficiency_notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proficiency_level'].widget = forms.Select(
            choices=PROFICIENCY_CHOICES
        )

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Skill.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(
                f'"{name}" already exists in the skill registry — '
                'use "Add an existing skill" instead.'
            )
        if SkillSubmission.objects.filter(
            name__iexact=name,
            status=SkillSubmission.STATUS_PENDING
        ).exists():
            raise forms.ValidationError(
                f'A submission for "{name}" is already pending review.'
            )
        return name