from django.db import transaction
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.common.choices import (
    ExchangeMatchStatus,
    ExchangePostStatus,
    ExchangeSessionStatus,
    ThreadParticipantRole,
    ThreadStatus,
    ThreadVisibility,
)
from apps.notifications.signals import notify
from apps.threads.models import Thread, ThreadParticipant

from .models import ExchangeMatch, ExchangePost, ExchangeSession, SessionFeedback

# ---------------------------------------------------------------------------
# Post Services
# ---------------------------------------------------------------------------


def has_duplicate_active_post(user, offered_ids: set, needed_ids: set) -> bool:
    """
    Returns True if the user already has an active MATCHING post with the
    exact same offered/needed skill combination.
    Called by the form's clean() to enforce the no-duplicate-post rule.
    """
    active_posts = ExchangePost.objects.filter(
        author=user,
        status=ExchangePostStatus.MATCHING,
        deleted_at__isnull=True,
    ).prefetch_related("skills_offered", "skills_needed")

    for post in active_posts:
        existing_offered = set(post.skills_offered.values_list("id", flat=True))
        existing_needed = set(post.skills_needed.values_list("id", flat=True))
        if offered_ids == existing_offered and needed_ids == existing_needed:
            return True

    return False


def create_exchange_post(user, form) -> ExchangePost:
    """
    Persists a validated SkillExchangePostForm (including M2M) and assigns
    the author atomically, then runs the matching engine.

    Matching intentionally runs outside the atomic block: a partial match
    failure must not roll back the successfully created post.
    """
    with transaction.atomic():
        post = form.save(commit=False)
        post.author = user
        post.save()
        form.save_m2m()

    find_and_create_matches(post)
    return post


def delete_exchange_post(post: ExchangePost) -> None:
    """
    Soft-deletes a post and removes every PENDING match that referenced it
    in one atomic operation. Matches that have already escalated to sessions
    are intentionally left untouched.
    """
    with transaction.atomic():
        post.deleted_at = timezone.now()
        post.status = ExchangePostStatus.DELETED
        post.save()

        ExchangeMatch.objects.filter(
            Q(ex_p_a=post) | Q(ex_p_b=post),
            status=ExchangeMatchStatus.PENDING,
        ).delete()


# ---------------------------------------------------------------------------
# Matching Engine
# ---------------------------------------------------------------------------


def find_and_create_matches(instance: ExchangePost) -> None:
    """
    Matching Engine:
    Finds all potential trades between the given post and every other active
    post. Creates a unique ExchangeMatch record for every valid skill-pair
    combination.

    Atomicity is scoped per-candidate: all skill-pair matches for a single
    candidate are committed together, but a failure for one candidate does
    not roll back matches already created for others.

    Simultaneous post-creation races are handled safely by get_or_create
    backed by the database unique constraint.
    """
    if instance.deleted_at or instance.status != ExchangePostStatus.MATCHING:
        return

    candidates = (
        ExchangePost.objects.filter(
            deleted_at__isnull=True,
            status=ExchangePostStatus.MATCHING,
        )
        .exclude(author=instance.author)
        .prefetch_related("skills_offered", "skills_needed")
    )

    my_offered_ids = set(instance.skills_offered.values_list("id", flat=True))
    my_needed_ids = set(instance.skills_needed.values_list("id", flat=True))

    for cand in candidates:
        cand_offered_ids = set(cand.skills_offered.values_list("id", flat=True))
        cand_needed_ids = set(cand.skills_needed.values_list("id", flat=True))

        i_can_teach_them = my_offered_ids & cand_needed_ids
        they_can_teach_me = cand_offered_ids & my_needed_ids

        if not (i_can_teach_them and they_can_teach_me):
            continue

        with transaction.atomic():
            for s_offered_id in i_can_teach_them:
                for s_needed_id in they_can_teach_me:

                    # Maintain p_a.id < p_b.id to satisfy the DB check constraint
                    if instance.id < cand.id:
                        p_a, p_b = instance, cand
                        skill_a, skill_b = s_offered_id, s_needed_id
                    else:
                        p_a, p_b = cand, instance
                        skill_a, skill_b = s_needed_id, s_offered_id

                    ExchangeMatch.objects.get_or_create(
                        ex_p_a=p_a,
                        ex_p_b=p_b,
                        skill_a_offers_id=skill_a,
                        skill_b_offers_id=skill_b,
                        defaults={"status": ExchangeMatchStatus.PENDING},
                    )


# ---------------------------------------------------------------------------
# Match Services
# ---------------------------------------------------------------------------


def notify_match_created(match: ExchangeMatch) -> None:
    """
    Sends a notification to both participants when a new ExchangeMatch is
    created. Called from the post_save signal handler.
    """
    skill_a = match.skill_a_offers
    skill_b = match.skill_b_offers

    if not (skill_a and skill_b):
        return

    url = reverse("skill_exchange:match_list")

    notify(
        recipient=match.ex_p_a.author,
        verb=f"New skill match: you can teach {skill_a.name}, they can teach {skill_b.name}",
        target=match,
        data={
            "match_id": match.id,
            "url": url,
            "other_author": match.ex_p_b.author.handle or match.ex_p_b.author.email,
        },
    )
    notify(
        recipient=match.ex_p_b.author,
        verb=f"New skill match: you can teach {skill_b.name}, they can teach {skill_a.name}",
        target=match,
        data={
            "match_id": match.id,
            "url": url,
            "other_author": match.ex_p_a.author.handle or match.ex_p_a.author.email,
        },
    )


def process_match_decision(match: ExchangeMatch, user, action: str) -> dict:
    """
    Two-Way Handshake logic.

    Both the rejection and acceptance paths lock the match row with
    SELECT FOR UPDATE before writing. Without this:
      - Two simultaneous accepts both pass the both-accepted check before
        either saves, so no session ever gets created.
      - A concurrent accept + reject can produce an inconsistent status.

    notify() is called outside the atomic block: notifications cannot be
    rolled back, so they must only fire after the DB write is committed.

    Returns one of:
      {"outcome": "rejected"}
      {"outcome": "pending"}
      {"outcome": "confirmed", "thread_id": <int>}
    """
    if action == "rejected":
        with transaction.atomic():
            locked = ExchangeMatch.objects.select_for_update().get(pk=match.pk)
            locked.status = ExchangeMatchStatus.REJECTED
            locked.save()
        return {"outcome": "rejected"}

    thread = None
    other_user = None

    with transaction.atomic():
        locked = ExchangeMatch.objects.select_for_update().get(pk=match.pk)

        if locked.ex_p_a.author == user:
            locked.user_a_accepted = True
            other_user = locked.ex_p_b.author
        else:
            locked.user_b_accepted = True
            other_user = locked.ex_p_a.author

        locked.save()

        # Both sides have now accepted — escalate to a confirmed session
        if locked.user_a_accepted and locked.user_b_accepted:
            locked.status = ExchangeMatchStatus.CONFIRMED
            locked.save()

            thread = Thread.objects.create(
                title=(
                    f"Skill Exchange: "
                    f"{locked.skill_a_offers.name} ↔ {locked.skill_b_offers.name}"
                ),
                visibility=ThreadVisibility.PRIVATE,
            )
            ThreadParticipant.objects.create(
                thread=thread,
                user=locked.ex_p_a.author,
                role=ThreadParticipantRole.MEMBER,
            )
            ThreadParticipant.objects.create(
                thread=thread,
                user=locked.ex_p_b.author,
                role=ThreadParticipantRole.MEMBER,
            )
            ExchangeSession.objects.create(
                match=locked,
                thread=thread,
                status=ExchangeSessionStatus.ACTIVE,
            )

    # Notify outside the transaction — only fires on successful commit
    if thread:
        notify(
            recipient=other_user,
            verb=f"{user.handle or user.email} accepted your skill exchange match.",
            target=locked,
            data={
                "url": reverse(
                    "threads:thread_detail", kwargs={"thread_id": thread.id}
                ),
                "thread_id": thread.id,
            },
        )
        return {"outcome": "confirmed", "thread_id": thread.id}

    return {"outcome": "pending"}


# ---------------------------------------------------------------------------
# Session Services
# ---------------------------------------------------------------------------


def process_session_completion(session: ExchangeSession, user) -> dict:
    """
    Records a user's completion flag and closes the session + thread if both
    participants have confirmed.

    SELECT FOR UPDATE on the session row serializes simultaneous "complete"
    clicks: without the lock, both users could read only their own flag set
    and neither would observe the other's, so the session would never close.

    notify() is called outside the atomic block (see process_match_decision
    for the rationale).

    Returns: {"fully_completed": bool}
    """
    fully_completed = False
    other_user = None
    user_display = user.handle or user.email
    thread_url = reverse(
        "threads:thread_detail", kwargs={"thread_id": session.thread.id}
    )

    with transaction.atomic():
        locked = ExchangeSession.objects.select_for_update().get(pk=session.pk)

        if locked.match.ex_p_a.author == user:
            locked.user_a_completed = True
            other_user = locked.match.ex_p_b.author
        else:
            locked.user_b_completed = True
            other_user = locked.match.ex_p_a.author

        if locked.user_a_completed and locked.user_b_completed:
            locked.status = ExchangeSessionStatus.COMPLETED
            locked.save()
            locked.thread.status = ThreadStatus.CLOSED
            locked.thread.save()
            fully_completed = True
        else:
            locked.save()

    verb = f"{user_display} confirmed completion of the exchange. " + (
        "The session is now closed."
        if fully_completed
        else "You can confirm when you're ready to close the session."
    )

    notify(
        recipient=other_user,
        verb=verb,
        target=session,
        data={"url": thread_url, "thread_id": session.thread.id},
    )

    return {"fully_completed": fully_completed}


# ---------------------------------------------------------------------------
# Feedback Services
# ---------------------------------------------------------------------------


def save_session_feedback(
    session: ExchangeSession, user, rating: int, notes: str
) -> SessionFeedback:
    """
    Creates or updates the SessionFeedback left by *user* for their partner.

    Wrapped in atomic so that any future additions to this function cannot
    accidentally leave the DB in a partial state.
    """
    if session.match.ex_p_a.author == user:
        partner = session.match.ex_p_b.author
    else:
        partner = session.match.ex_p_a.author

    with transaction.atomic():
        feedback, _ = SessionFeedback.objects.update_or_create(
            exchange_session=session,
            rated_by_user=user,
            defaults={
                "rated_user": partner,
                "rating": rating,
                "notes": notes,
            },
        )
    return feedback


def update_user_sx_rating(rated_user) -> None:
    """
    Recalculates and persists the Bayesian average skill-exchange rating for
    *rated_user*. Called after any SessionFeedback is saved or deleted.

    SELECT FOR UPDATE on the profile row prevents a lost-update race:
    without it, two concurrent feedback saves for the same user both read
    the same stale aggregates, compute an incorrect score, and one result
    silently overwrites the other.

    Bayesian formula:  score = (R*v + C*m) / (v + m)
      R = user's raw average rating
      v = number of reviews the user has received
      C = platform-wide average (fallback: 7.0)
      m = confidence weight — reviews needed to move the score off C
    """
    with transaction.atomic():
        # Lock the profile row for the entire read-compute-write cycle
        profile = (
            type(rated_user.profile)
            .objects.select_for_update()
            .get(pk=rated_user.profile.pk)
        )

        stats = SessionFeedback.objects.filter(rated_user=rated_user).aggregate(
            avg_rating=Avg("rating"),
            review_count=Count("rating"),
        )
        R = stats["avg_rating"] or 0.0
        v = stats["review_count"] or 0

        global_stats = SessionFeedback.objects.aggregate(global_avg=Avg("rating"))
        C = global_stats["global_avg"] or 7.0
        m = 3.0

        weighted_score = ((R * v) + (C * m)) / (v + m) if v > 0 else 0.0

        profile.sx_rating_avg = round(weighted_score, 1)
        profile.save(update_fields=["sx_rating_avg"])


# ---------------------------------------------------------------------------
# Skill Management Services
# ---------------------------------------------------------------------------


def add_existing_skill_to_profile(
    user,
    skill,
    proficiency_level,
    proficiency_method,
    proficiency_notes,
    years_experience,
) -> dict:
    """
    Adds a verified skill to a user's profile with PENDING status.
    Handles race conditions via get_or_create with unique constraint.

    Returns:
      {"success": True, "user_skill": UserSkill}
      {"success": False, "error": str}
    """
    from .models import UserSkill
    from apps.common.choices import UserSkillStatus

    with transaction.atomic():
        try:
            user_skill, created = UserSkill.objects.get_or_create(
                user=user,
                skill=skill,
                defaults={
                    "proficiency_level": proficiency_level,
                    "proficiency_method": proficiency_method or "",
                    "proficiency_notes": proficiency_notes or "",
                    "years_experience": years_experience,
                    "status": UserSkillStatus.PENDING,
                },
            )
            if not created:
                return {
                    "success": False,
                    "error": f'"{skill.name}" is already on your profile.',
                }
            return {"success": True, "user_skill": user_skill}
        except Exception as e:
            return {"success": False, "error": f"Failed to add skill: {str(e)}"}


def propose_new_skill(
    user,
    name,
    description,
    proficiency_level,
    proficiency_method,
    proficiency_notes,
    years_experience,
) -> dict:
    """
    Proposes a new skill and adds it to the user's profile with PENDING status.
    Uses get_or_create for the Skill to handle concurrent proposals safely.

    Returns:
      {"success": True, "skill": Skill, "user_skill": UserSkill}
      {"success": False, "error": str}
    """
    from .models import Skill, UserSkill
    from apps.common.choices import SkillStatus, UserSkillStatus

    with transaction.atomic():
        try:
            # get_or_create handles race condition: if two users propose the same skill
            # simultaneously, only one Skill record is created
            skill, skill_created = Skill.objects.get_or_create(
                name=name,
                defaults={
                    "description": description or "",
                    "status": SkillStatus.PENDING,
                },
            )

            # Now create the UserSkill linking this user to the skill (PENDING)
            user_skill, userskill_created = UserSkill.objects.get_or_create(
                user=user,
                skill=skill,
                defaults={
                    "proficiency_level": proficiency_level,
                    "proficiency_method": proficiency_method or "",
                    "proficiency_notes": proficiency_notes or "",
                    "years_experience": years_experience,
                    "status": UserSkillStatus.PENDING,
                },
            )

            if not userskill_created:
                return {
                    "success": False,
                    "error": f'You already have a request to add "{skill.name}".',
                }

            return {"success": True, "skill": skill, "user_skill": user_skill}
        except Exception as e:
            return {"success": False, "error": f"Failed to propose skill: {str(e)}"}
