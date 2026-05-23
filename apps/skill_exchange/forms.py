from django import forms

from .models import ExchangePost
from .services import has_duplicate_active_post


class SkillExchangePostForm(forms.ModelForm):
    class Meta:
        model = ExchangePost
        fields = ["description", "skills_offered", "skills_needed"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        # Pop the user from kwargs before initializing the superclass
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

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
