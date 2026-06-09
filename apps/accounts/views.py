from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .forms import RegisterForm
from .models import UserProfile
from apps.skill_exchange.models import UserSkill
from apps.common.choices import UserSkillStatus
from apps.academics.models import Department
from apps.media.models import Photo

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PHOTO_MB = 5


def profile_view(request, handle):
    profile = get_object_or_404(UserProfile, user__handle=handle)
    skills = UserSkill.objects.filter(
        user=profile.user, status=UserSkillStatus.VERIFIED
    ).select_related("skill")
    is_own_profile = request.user.is_authenticated and request.user.handle == handle

    pending_submissions = []
    if is_own_profile:
        pending_submissions = UserSkill.objects.filter(
            user=profile.user, status=UserSkillStatus.PENDING
        ).select_related("skill")

    return render(
        request,
        "accounts/profile.html",
        {
            "profile": profile,
            "skills": skills,
            "is_own_profile": is_own_profile,
            "pending_submissions": pending_submissions,
        },
    )


@login_required
def edit_profile(request, handle):
    if request.user.handle != handle:
        # Viewing someone else's edit page — just redirect to their profile
        return redirect("accounts:profile", handle=handle)

    user = request.user
    profile = get_object_or_404(UserProfile, user=user)

    # Shared context for both GET and a failed POST re-render
    def get_form_context():
        skills = UserSkill.objects.filter(
            user=user, status=UserSkillStatus.VERIFIED
        ).select_related("skill")
        return {
            "profile": profile,
            "skills": [us.skill for us in skills],  # edit page only needs names
            "all_departments": Department.objects.all().order_by("name"),
        }

    if request.method == "GET":
        return render(request, "accounts/profile_edit.html", get_form_context())

    # ── POST processing ──────────────────────────────────────────────────
    data = request.POST

    # ── User fields ──────────────────────────────────────────────────────
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()

    if not first_name or not last_name:
        messages.error(request, "First name and last name are required.")
        return render(request, "accounts/profile_edit.html", get_form_context())

    user.first_name = first_name
    user.last_name = last_name
    user.save(update_fields=["first_name", "last_name"])

    # ── Profile fields ───────────────────────────────────────────────────
    profile.bio = data.get("bio", "").strip()
    profile.student_id = data.get("student_id", "").strip() or None

    dept_id = data.get("department_id")
    if dept_id:
        try:
            profile.department = Department.objects.get(id=dept_id)
        except Department.DoesNotExist:
            profile.department = None
    else:
        profile.department = None

    # ── Photo ────────────────────────────────────────────────────────────
    photo_file = request.FILES.get("photo")
    if photo_file:
        if photo_file.content_type not in ALLOWED_IMAGE_TYPES:
            messages.error(request, "Invalid file type. Use JPEG, PNG, WebP, or GIF.")
            return render(request, "accounts/profile_edit.html", get_form_context())

        if photo_file.size > MAX_PHOTO_MB * 1024 * 1024:
            messages.error(
                request, f"Photo too large. Maximum size is {MAX_PHOTO_MB} MB."
            )
            return render(request, "accounts/profile_edit.html", get_form_context())

        if profile.photo:
            old = profile.photo
            profile.photo = None
            old.delete()

        profile.photo = Photo.objects.create(file=photo_file, uploaded_by=user)

    profile.save(update_fields=["bio", "student_id", "department", "photo"])

    # ── Skills ───────────────────────────────────────────────────────────

    # TODO — Notification hook:
    # If profile verification status changed or XP-granting actions happened,
    # trigger a notification here via the notification system.

    messages.success(request, "Profile updated successfully.")
    return redirect("accounts:profile", handle=handle)


@login_required
def myself(request):
    return redirect("accounts:profile", handle=request.user.handle)


def register(request):
    form = RegisterForm(request.POST or None)

    if form.is_valid():
        form.save()
        return redirect("accounts:login")

    return render(request, "accounts/register.html", {"form": form})
