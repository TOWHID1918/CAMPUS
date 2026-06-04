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
    SkillSubmission,
    UserSkill,
)


# ── Skill ─────────────────────────────────────────────────────────────────────

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ('name', 'status')
    list_filter   = ('status',)
    search_fields = ('name',)


# ── UserSkill ─────────────────────────────────────────────────────────────────

@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display  = ('user', 'skill', 'proficiency_level', 'role', 'status')
    list_filter   = ('status', 'role')
    search_fields = ('user__email', 'skill__name')
    actions       = ['approve_skills', 'reject_skills']

    def approve_skills(self, request, queryset):
        pending = queryset.filter(status=UserSkillStatus.PENDING)
        count = 0

        for user_skill in pending:
            user_skill.status = UserSkillStatus.APPROVED
            user_skill.save(update_fields=['status'])

           
            Skill.objects.filter(pk=user_skill.skill_id).update(status=SkillStatus.APPROVED)
            
            count += 1

        self.message_user(
            request,
            f'✅ {count} skill(s) approved and now visible on profiles.',
            django_messages.SUCCESS
        )

    approve_skills.short_description = '✅ Approve selected skills'

    def reject_skills(self, request, queryset):
        count = queryset.filter(status=UserSkillStatus.PENDING).update(
            status=UserSkillStatus.REJECTED
        )
        self.message_user(
            request,
            f'❌ {count} skill(s) rejected.',
            django_messages.WARNING
        )

    reject_skills.short_description = '❌ Reject selected skills'


# ── Remaining models ──────────────────────────────────────────────────────────

admin.site.register(ExchangePost)
admin.site.register(ExchangeMatch)
admin.site.register(ExchangeSession)
admin.site.register(SessionFeedback)