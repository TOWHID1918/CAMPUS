# apps/common/choices.py
from django.db import models


# Lost and Found domain choices
class LostAndFoundStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    REJECTED = "rejected", "Rejected"
    RESOLVED = "resolved", "Resolved"


# class LostAndFoundMatchStatus(models.TextChoices):
#     PENDING = "pending", "Pending"
#     MATCHED = "matched", "Matched"
#     CLOSED = "closed", "Closed"


class LFSuggestedMatchStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DISMISSED = "DISMISSED", "Dismissed"
    CONVERTED = "CONVERTED", "Converted"


class ClaimRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


# Thread domain choices
class ThreadStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    ARCHIVED = "archived", "Archived"


class ThreadMessageStatus(models.TextChoices):
    SENT = "sent", "Sent"
    DELETED = "deleted", "Deleted"


class VoteStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"


# Skill Exchange domain choices
class SkillStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class ExchangePostStatus(models.TextChoices):
    MATCHING = "matching", "Matching"
    DELETED = "deleted", "Deleted"


class ExchangeMatchStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"


class ExchangeSessionStatus(models.TextChoices):
    # PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class SessionFeedbackStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUBMITTED = "submitted", "Submitted"
    REJECTED = "rejected", "Rejected"


# class SessionEndRequestStatus(models.TextChoices):
#     PENDING = "pending", "Pending"
#     APPROVED = "approved", "Approved"
#     DENIED = "denied", "Denied"


# class MatchDecisionStatus(models.TextChoices):
#     PENDING = "pending", "Pending"
#     ACCEPTED = "accepted", "Accepted"
#     REJECTED = "rejected", "Rejected"


# Lost and Found post types
class LostAndFoundPostType(models.TextChoices):
    LOST = "lost", "Lost"
    FOUND = "found", "Found"


# Thread visibility and participant roles
class ThreadVisibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class ThreadParticipantRole(models.TextChoices):
    AUTHOR = "author", "Author"
    MEMBER = "member", "Member"
    MODERATOR = "moderator", "Moderator"


# Vote types
class VoteType(models.TextChoices):
    UPVOTE = "upvote", "Upvote"
    DOWNVOTE = "downvote", "Downvote"


# Accounts domain choices
class ProfileStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    NORMAL = "normal", "Normal"
    FLAGGED = "flagged", "Flagged"
    SUSPENDED = "suspended", "Suspended"

# marketplace listiong status
class ListingStatus(models.TextChoices):
    ACTIVE    = "ACTIVE",    "Active"
    SOLD      = "SOLD",      "Sold"
    ARCHIVED  = "ARCHIVED",  "Archived"

# Ride Sharing domain status and choices
class TransportMethod(models.TextChoices):
    CAR = "car", "Car"
    RICKSHAW = "rickshaw", "Rickshaw"
    CNG = "cng", "CNG"
    MICROBUS = "microbus", "MICROBUS"

TRANSPORT_CAPACITY = {
    TransportMethod.RICKSHAW: 2,
    TransportMethod.CNG:      3,
    TransportMethod.CAR:      4,
}

class RidePostStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"


class RideJoinRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class RideGroupStatus(models.TextChoices):
    FORMING = "forming", "Forming"
    CONFIRMED = "confirmed", "Confirmed"
    IN_TRANSIT = "in_transit", "In Transit"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class RideGroupMemberStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    LEFT = "left", "Left"
    NO_SHOW = "no_show", "No Show"
