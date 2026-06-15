from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import SkillExchangePostForm, AddExistingSkillForm, ProposeNewSkillForm
from .models import (
    ExchangeMatch,
    ExchangePost,
    ExchangeSession,
    UserSkill,
)
from apps.common.choices import (
    ExchangeMatchStatus,
    ExchangePostStatus,
    ExchangeSessionStatus,
)
from .services import (
    create_exchange_post,
    delete_exchange_post,
    process_match_decision,
    process_session_completion,
    save_session_feedback,
    add_existing_skill_to_profile,
    propose_new_skill,
)

# --- POST MANAGEMENT ---


@login_required
def post_list(request):
    posts = ExchangePost.objects.filter(
        author=request.user,
        status=ExchangePostStatus.MATCHING,
    ).order_by("-created_at")
    return render(request, "skill_exchange/post_list.html", {"posts": posts})


@login_required
def post_create(request):
    if request.method == "POST":
        form = SkillExchangePostForm(request.POST, user=request.user)
        if form.is_valid():
            create_exchange_post(request.user, form)
            messages.success(request, "Exchange post created successfully!")
            return redirect("skill_exchange:post_list")
        for _, errors in form.errors.items():
            for error in errors:
                messages.error(request, str(error))
    else:
        form = SkillExchangePostForm(user=request.user)

    return render(request, "skill_exchange/post_create.html", {"form": form})


@login_required
@require_POST
def post_delete(request, post_id):
    post = get_object_or_404(ExchangePost, pk=post_id, author=request.user)
    delete_exchange_post(post)
    messages.info(request, "Post deleted and pending matches removed.")
    return redirect("skill_exchange:post_list")


# --- MATCHING & HANDSHAKE ---


@login_required
def match_list(request):
    pending_matches = ExchangeMatch.objects.filter(
        Q(ex_p_a__author=request.user) | Q(ex_p_b__author=request.user),
        status=ExchangeMatchStatus.PENDING,
    ).select_related(
        "ex_p_a__author", "ex_p_b__author", "skill_a_offers", "skill_b_offers"
    )

    for match in pending_matches:
        match.user_context = match.get_context_for_user(request.user)
        # Expose partner's skill-exchange rating for the template
        partner = match.user_context.get("partner_user")
        match.partner_sx_rating = getattr(
            getattr(partner, "profile", None), "sx_rating_avg", 0.0
        )

    return render(
        request,
        "skill_exchange/match_list.html",
        {"pending_matches": pending_matches},
    )


@login_required
def session_list(request):
    active_sessions = ExchangeSession.objects.filter(
        Q(match__ex_p_a__author=request.user) | Q(match__ex_p_b__author=request.user),
        status=ExchangeSessionStatus.ACTIVE,
    )

    for session in active_sessions:
        session.user_context = session.match.get_context_for_user(request.user)
        # Expose partner's skill-exchange rating for the template
        partner = session.user_context.get("partner_user")
        session.partner_sx_rating = getattr(
            getattr(partner, "profile", None), "sx_rating_avg", 0.0
        )

    return render(
        request,
        "skill_exchange/session_list.html",
        {"active_sessions": active_sessions},
    )


@login_required
@require_POST
def match_confirm_decision(request, match_id):
    match = get_object_or_404(ExchangeMatch, pk=match_id)
    action = request.POST.get("action")

    result = process_match_decision(match, request.user, action)

    if result["outcome"] == "rejected":
        messages.info(request, "Match declined.")
        return redirect("skill_exchange:match_list")

    if result["outcome"] == "pending":
        messages.success(
            request, "You accepted the match! Waiting for the other user to respond."
        )
        return redirect("skill_exchange:match_list")

    if result["outcome"] == "confirmed":
        messages.success(request, "Match confirmed! A new session has started.")
        return redirect("threads:thread_detail", thread_id=result["thread_id"])

    return redirect("skill_exchange:match_list")


# --- SESSION MANAGEMENT ---


@login_required
@require_POST
def session_complete_decision(request, session_id):
    session = get_object_or_404(
        ExchangeSession, pk=session_id, status=ExchangeSessionStatus.ACTIVE
    )

    result = process_session_completion(session, request.user)

    if result["fully_completed"]:
        messages.success(request, "Exchange successfully completed!")
    else:
        messages.info(request, "Completion status recorded.")

    return redirect("threads:thread_detail", thread_id=session.thread.id)


# --- FEEDBACK MANAGEMENT ---


@login_required
@require_POST
def submit_session_feedback(request, session_id):
    session = get_object_or_404(ExchangeSession, pk=session_id)

    is_participant = (
        session.match.ex_p_a.author == request.user
        or session.match.ex_p_b.author == request.user
    )
    if not is_participant:
        messages.error(request, "You are not a participant in this session.")
        return redirect("skill_exchange:session_list")

    try:
        rating = int(request.POST.get("rating"))
        if not (1 <= rating <= 10):
            raise ValueError
    except (TypeError, ValueError):
        messages.error(
            request, "Invalid rating. Must be a whole number between 1 and 10."
        )
        return redirect("threads:thread_detail", thread_id=session.thread.id)

    notes = request.POST.get("notes", "")

    save_session_feedback(session, request.user, rating, notes)

    messages.success(request, "Your feedback has been saved securely!")
    return redirect("threads:thread_detail", thread_id=session.thread.id)


# ── Skill management ──────────────────────────────────────────────────────────


@login_required
def add_skill(request):
    user = request.user
    existing_form = AddExistingSkillForm(user=user)
    propose_form = ProposeNewSkillForm(user=user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_existing":
            existing_form = AddExistingSkillForm(request.POST, user=user)
            if existing_form.is_valid():
                d = existing_form.cleaned_data
                result = add_existing_skill_to_profile(
                    user=user,
                    skill=d["skill"],
                    proficiency_level=int(d["proficiency_level"]),
                    proficiency_method=d.get("proficiency_method", ""),
                    proficiency_notes=d.get("proficiency_notes", ""),
                    years_experience=d.get("years_experience"),
                )
                if result["success"]:
                    messages.info(
                        request,
                        f'📬 A request to add "{d["skill"].name}" has been submitted and is pending verification.',
                    )
                    return redirect("accounts:profile", handle=user.handle)
                else:
                    messages.error(request, result["error"])
            else:
                # Display non-field errors as messages (field errors shown by template)
                for error in existing_form.non_field_errors():
                    messages.error(request, str(error))

        elif action == "propose_new":
            propose_form = ProposeNewSkillForm(request.POST, user=user)
            if propose_form.is_valid():
                d = propose_form.cleaned_data
                result = propose_new_skill(
                    user=user,
                    name=d["name"],
                    description=d.get("description", ""),
                    proficiency_level=int(d.get("proficiency_level", 1)),
                    proficiency_method=d.get("proficiency_method", ""),
                    proficiency_notes=d.get("proficiency_notes", ""),
                    years_experience=d.get("years_experience"),
                )
                if result["success"]:
                    messages.info(
                        request,
                        "📬 Your skill proposal has been submitted for review. "
                        "It will appear on your profile once a moderator verifies it.",
                    )
                    return redirect("accounts:profile", handle=user.handle)
                else:
                    messages.error(request, result["error"])
            else:
                # Display non-field errors as messages (field errors shown by template)
                for error in propose_form.non_field_errors():
                    messages.error(request, str(error))

    return render(
        request,
        "skill_exchange/add_skill.html",
        {
            "existing_form": existing_form,
            "propose_form": propose_form,
        },
    )


@login_required
@require_POST
def remove_skill(request, userskill_id):
    user_skill = get_object_or_404(UserSkill, id=userskill_id, user=request.user)
    name = user_skill.skill.name
    user_skill.delete()
    messages.success(request, f'"{name}" removed from your profile.')
    return redirect("accounts:profile", handle=request.user.handle)
