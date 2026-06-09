from django.contrib import admin
from django.utils import timezone
from django.contrib import messages as django_messages

from apps.common.choices import SkillStatus, UserSkillStatus
from .models import (
    ExchangeMatch,
    ExchangePost,
    ExchangeSession,
    SessionFeedback,
    Skill,
    UserSkill,
)

# ── Skill ─────────────────────────────────────────────────────────────────────


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "status")
    list_filter = ("status",)
    search_fields = ("name",)


# ── UserSkill ─────────────────────────────────────────────────────────────────


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "proficiency_level", "status")
    list_filter = ("status",)
    search_fields = ("user__email", "skill__name")
    actions = ["verify_skills", "reject_skills"]

    def verify_skills(self, request, queryset):
        pending = queryset.filter(status=UserSkillStatus.PENDING)
        count = 0

        for user_skill in pending:
            user_skill.status = UserSkillStatus.VERIFIED
            user_skill.save(update_fields=["status"])

            Skill.objects.filter(pk=user_skill.skill_id).update(
                status=SkillStatus.VERIFIED
            )

            count += 1

        self.message_user(
            request,
            f"✅ {count} skill(s) verified and now visible on profiles.",
            django_messages.SUCCESS,
        )

    verify_skills.short_description = "✅ Verify selected skills"

    def reject_skills(self, request, queryset):
        count = queryset.filter(status=UserSkillStatus.PENDING).update(
            status=UserSkillStatus.REJECTED
        )
        self.message_user(
            request, f"❌ {count} skill(s) rejected.", django_messages.WARNING
        )

    reject_skills.short_description = "❌ Reject selected skills"


# ── Remaining models ──────────────────────────────────────────────────────────

admin.site.register(ExchangePost)
admin.site.register(ExchangeMatch)
admin.site.register(ExchangeSession)
admin.site.register(SessionFeedback)
