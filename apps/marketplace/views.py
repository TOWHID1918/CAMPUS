from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.http import HttpResponseForbidden

from apps.media.models import Photo
from apps.threads.models import Thread, ThreadParticipant
from apps.common.choices import (
    ThreadVisibility,
    ThreadParticipantRole,
    ThreadStatus,
    NegotiationStatus,
)

from .models import (
    Listing,
    ListingPhoto,
    NegotiationThread,
    ListingStatus,
    Category,
    PurchaseRequest,
    PurchaseRequestStatus,
)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PHOTO_MB = 5


def listing_list(request):
    listings = (
        Listing.objects.filter(status=ListingStatus.ACTIVE)
        .select_related("seller", "category")
        .prefetch_related("photos__photo")
        .order_by("-created_at")
    )

    category_id = request.GET.get("category", "")
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "newest")

    if category_id:
        listings = listings.filter(category_id=category_id)
    
    if search:
        listings = listings.filter(title__icontains=search)
        print(f"DEBUG search='{search}' results={listings.count()}")

    if sort == "oldest":
        listings = listings.order_by("created_at")
    elif sort == "price_low":
        listings = listings.order_by("price")
    elif sort == "price_high":
        listings = listings.order_by("-price")
    else:
        listings = listings.order_by("-created_at")

    return render(
        request,
        "marketplace/listing_list.html",
        {
            "listings": listings,
            "categories": Category.objects.all(),
            "current_category": category_id,
            "current_sort": sort,
            "current_search": search,
        },
    )


def listing_detail(request, listing_id):

    listing = get_object_or_404(Listing, id=listing_id)

    negotiation = None

    if request.user.is_authenticated:

        negotiation = NegotiationThread.objects.filter(
            listing=listing, buyer=request.user
        ).first()

    return render(
        request,
        "marketplace/listing_detail.html",
        {
            "listing": listing,
            "negotiation": negotiation,
        },
    )


@login_required
def create_listing(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        price = request.POST.get("price", "").strip()
        stock = request.POST.get("stock", "1").strip()
        category_id = request.POST.get("category", "")
        photos = request.FILES.getlist("photos")

        errors = []
        if not title:
            errors.append("Title is required.")
        if not price:
            errors.append("Price is required.")
        else:
            try:
                price = float(price)
                if price < 0:
                    raise ValueError
            except ValueError:
                errors.append("Enter a valid price.")
        try:
            stock = int(stock)
            if stock < 1:
                raise ValueError
        except ValueError:
            errors.append("Stock quantity must be a whole number of at least 1.")

        category = None
        if category_id:
            category = Category.objects.filter(pk=category_id).first()

        for f in photos:
            if f.content_type not in ALLOWED_IMAGE_TYPES:
                errors.append(f"{f.name}: invalid file type.")
            if f.size > MAX_PHOTO_MB * 1024 * 1024:
                errors.append(f"{f.name}: exceeds {MAX_PHOTO_MB} MB limit.")

        if errors:
            return render(
                request,
                "marketplace/listing_form.html",
                {
                    "errors": errors,
                    "post": request.POST,
                    "max_mb": MAX_PHOTO_MB,
                    "categories": Category.objects.all(),
                },
            )

        with transaction.atomic():
            listing = Listing.objects.create(
                seller=request.user,
                title=title,
                description=description,
                price=price,
                stock=stock,
                category=category,
            )
            for idx, f in enumerate(photos):
                photo = Photo.objects.create(file=f, uploaded_by=request.user)
                ListingPhoto.objects.create(listing=listing, photo=photo, order=idx)

        return redirect("marketplace:listing_detail", listing_id=listing.id)

    return render(
        request,
        "marketplace/listing_form.html",
        {
            "max_mb": MAX_PHOTO_MB,
            "categories": Category.objects.all(),
        },
    )


@login_required
def edit_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id, seller=request.user)

    if request.method == "POST":
        listing.title = request.POST.get("title", listing.title).strip()
        listing.description = request.POST.get("description", "").strip()
        price = request.POST.get("price", "").strip()
        stock = request.POST.get("stock", "1").strip()
        category_id = request.POST.get("category", "")

        errors = []
        try:
            listing.price = float(price)
        except ValueError:
            errors.append("Enter a valid price.")
        try:
            stock = int(stock)
            if stock < 1:
                raise ValueError
            listing.stock = stock
        except ValueError:
            errors.append("Stock quantity must be a whole number of at least 1.")
        if errors:
            return render(
                request,
                "marketplace/listing_form.html",
                {
                    "listing": listing,
                    "errors": errors,
                    "max_mb": MAX_PHOTO_MB,
                    "categories": Category.objects.all(),
                },
            )

        listing.category = Category.objects.filter(pk=category_id).first() if category_id else None

        status = request.POST.get("status")
        if status in ListingStatus.values:
            listing.status = status

        listing.save(
            update_fields=[
                "title",
                "description",
                "price",
                "stock",
                "category",
                "status",
                "updated_at",
            ]
        )

        photos = request.FILES.getlist("photos")
        for idx, f in enumerate(photos):
            if f.content_type not in ALLOWED_IMAGE_TYPES:
                continue
            if f.size > MAX_PHOTO_MB * 1024 * 1024:
                continue
            photo = Photo.objects.create(file=f, uploaded_by=request.user)
            last_order = listing.photos.count()
            ListingPhoto.objects.create(
                listing=listing, photo=photo, order=last_order + idx
            )

        return redirect("marketplace:listing_detail", listing_id=listing.id)

    return render(
        request,
        "marketplace/listing_form.html",
        {
            "listing": listing,
            "max_mb": MAX_PHOTO_MB,
            "categories": Category.objects.all(),
        },
    )


@login_required
def submit_purchase_request(request, listing_id):
    listing = get_object_or_404(
        Listing,
        pk=listing_id,
        status=ListingStatus.ACTIVE,
    )

    if listing.seller == request.user:
        return HttpResponseForbidden("You cannot request your own listing.")

    existing = PurchaseRequest.objects.filter(
        buyer=request.user,
        listing=listing,
    ).first()

    if existing:
        return redirect("marketplace:listing_detail", listing_id=listing.id)

    if request.method == "POST":
        message = request.POST.get("message", "").strip()

        PurchaseRequest.objects.create(
            buyer=request.user,
            listing=listing,
            message=message,
        )

    return redirect("marketplace:listing_detail", listing_id=listing.id)


@login_required
def review_purchase_requests(request, listing_id):
    listing = get_object_or_404(
        Listing,
        pk=listing_id,
        seller=request.user,
    )

    requests = (
        PurchaseRequest.objects.filter(listing=listing)
        .select_related("buyer")
        .order_by("-created_at")
    )

    return render(
        request,
        "marketplace/review_purchase_requests.html",
        {
            "listing": listing,
            "requests": requests,
            "PurchaseRequestStatus": PurchaseRequestStatus,
        },
    )


@login_required
def approve_purchase_request(request, listing_id, request_id):
    listing = get_object_or_404(
        Listing,
        pk=listing_id,
        seller=request.user,
    )

    purchase_request = get_object_or_404(
        PurchaseRequest,
        pk=request_id,
        listing=listing,
        status=PurchaseRequestStatus.PENDING,
    )

    if request.method == "POST":
        with transaction.atomic():

            # approve selected request
            purchase_request.status = PurchaseRequestStatus.APPROVED
            purchase_request.save(update_fields=["status", "updated_at"])

            # reject others
            PurchaseRequest.objects.filter(
                listing=listing,
                status=PurchaseRequestStatus.PENDING,
            ).exclude(pk=purchase_request.pk).update(
                status=PurchaseRequestStatus.REJECTED
            )

            # mark listing sold
            listing.status = ListingStatus.SOLD
            listing.save(update_fields=["status", "updated_at"])

            # create private thread
            thread = Thread.objects.create(
                title=f"Marketplace purchase: {listing.title}",
                visibility=ThreadVisibility.PRIVATE,
            )

            ThreadParticipant.objects.create(
                thread=thread,
                user=request.user,
                role=ThreadParticipantRole.AUTHOR,
            )

            ThreadParticipant.objects.create(
                thread=thread,
                user=purchase_request.buyer,
                role=ThreadParticipantRole.MEMBER,
            )

            NegotiationThread.objects.create(
                listing=listing,
                buyer=purchase_request.buyer,
                thread=thread,
            )

        return redirect(
            "threads:thread_detail",
            thread_id=thread.id,
        )

    return render(
        request,
        "marketplace/approve_purchase_request.html",
        {
            "listing": listing,
            "purchase_request": purchase_request,
        },
    )


@login_required
def contact_seller(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)

    if request.user == listing.seller:
        return HttpResponseForbidden("You cannot contact yourself.")

    if listing.status != ListingStatus.ACTIVE:
        return HttpResponseForbidden("This listing is no longer active.")

    existing = (
        NegotiationThread.objects.filter(listing=listing, buyer=request.user)
        .select_related("thread")
        .first()
    )

    if existing:
        return redirect("threads:thread_detail", thread_id=existing.thread.id)

    with transaction.atomic():
        thread = Thread.objects.create(
            title=f"Re: {listing.title}",
            visibility=ThreadVisibility.PRIVATE,
        )
        ThreadParticipant.objects.create(
            thread=thread,
            user=request.user,
            role=ThreadParticipantRole.MEMBER,
        )
        ThreadParticipant.objects.create(
            thread=thread,
            user=listing.seller,
            role=ThreadParticipantRole.AUTHOR,
        )
        NegotiationThread.objects.create(
            listing=listing,
            buyer=request.user,
            thread=thread,
        )

    return redirect("threads:thread_detail", thread_id=thread.id)


@login_required
def my_listings(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "newest")
    listings = (
        Listing.objects.filter(seller=request.user)
        .select_related("category")
        .prefetch_related("photos__photo")
        .order_by("-created_at")
    )
    if search:
        listings = listings.filter(title__icontains=search)
    if sort == "oldest":
        listings = listings.order_by("created_at")
    elif sort == "price_low":
        listings = listings.order_by("price")
    elif sort == "price_high":
        listings = listings.order_by("-price")
    else:
        listings = listings.order_by("-created_at")
    return render(
        request,
        "marketplace/my_listings.html",
        {
            "listings": listings,
            "current_search": search,
            "current_sort": sort,
        },
    )


@login_required
def my_negotiations_buyer(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "newest")
    negotiations = (
        NegotiationThread.objects.filter(buyer=request.user)
        .select_related("listing", "listing__seller", "listing__category", "thread")
        .prefetch_related("listing__photos__photo")
        .order_by("-created_at")
    )
    if search:
        negotiations = negotiations.filter(listing__title__icontains=search)
    if sort == "oldest":
        negotiations = negotiations.order_by("created_at")
    elif sort == "price_low":
        negotiations = negotiations.order_by("listing__price")
    elif sort == "price_high":
        negotiations = negotiations.order_by("-listing__price")
    else:
        negotiations = negotiations.order_by("-created_at")
    return render(
        request,
        "marketplace/negotiations_buyer.html",
        {
            "negotiations": negotiations,
            "current_search": search,
            "current_sort": sort,
        },
    )


@login_required
def review_inquiries(request, listing_id):
    """
    Seller reviews all negotiations/inquiries for one listing.
    Similar to lost_found.review_claims
    """

    listing = get_object_or_404(
        Listing.objects.select_related("category"),
        pk=listing_id,
        seller=request.user,
    )

    inquiries = (
        NegotiationThread.objects.filter(listing=listing)
        .select_related("buyer", "thread")
        .order_by("-created_at")
    )

    return render(
        request,
        "marketplace/review_inquiries.html",
        {
            "listing": listing,
            "inquiries": inquiries,
        },
    )


@login_required
def request_chat(request, listing_id):

    listing = get_object_or_404(Listing, id=listing_id)

    if listing.seller == request.user:
        messages.error(request, "You cannot request your own listing.")
        return redirect("marketplace:listing_detail", listing_id=listing.id)

    existing = NegotiationThread.objects.filter(
        listing=listing, buyer=request.user
    ).first()

    if existing:
        messages.warning(request, "Request already exists.")
        return redirect("marketplace:listing_detail", listing_id=listing.id)

    NegotiationThread.objects.create(
        listing=listing,
        buyer=request.user,
        seller=listing.seller,
        status=NegotiationStatus.PENDING,
    )

    messages.success(request, "Chat request sent.")

    return redirect("marketplace:listing_detail", listing_id=listing.id)


@login_required
def accept_negotiation(request, negotiation_id):

    negotiation = get_object_or_404(
        NegotiationThread, id=negotiation_id, seller=request.user
    )

    # prevent accepting twice
    if negotiation.status != NegotiationStatus.PENDING:
        return redirect("marketplace:negotiations_seller")

    with transaction.atomic():

        # create private thread
        thread = Thread.objects.create(
            title=f"Marketplace: {negotiation.listing.title}",
            visibility=ThreadVisibility.PRIVATE,
        )

        # seller participant
        ThreadParticipant.objects.create(
            thread=thread,
            user=negotiation.seller,
            role=ThreadParticipantRole.AUTHOR,
        )

        # buyer participant
        ThreadParticipant.objects.create(
            thread=thread,
            user=negotiation.buyer,
            role=ThreadParticipantRole.MEMBER,
        )

        # connect thread to negotiation
        negotiation.thread = thread
        negotiation.status = NegotiationStatus.ACCEPTED
        negotiation.save(update_fields=["thread", "status"])

    messages.success(request, "Chat request accepted.")

    return redirect("threads:thread_detail", thread_id=thread.id)


@login_required
def confirm_negotiation(request, negotiation_id):

    negotiation = get_object_or_404(
        NegotiationThread,
        id=negotiation_id,
        seller=request.user,
        status=NegotiationStatus.ACCEPTED,
    )

    listing = negotiation.listing

    if listing.status == ListingStatus.SOLD:
        messages.info(request, "This listing has already been marked sold.")
        return redirect("threads:thread_detail", thread_id=negotiation.thread.id)

    with transaction.atomic():
        other_negotiations = listing.negotiation_threads.exclude(id=negotiation.id)
        for other in other_negotiations:
            if other.status != NegotiationStatus.REJECTED:
                other.status = NegotiationStatus.REJECTED
                other.save(update_fields=["status"])
                if other.thread:
                    other.thread.status = ThreadStatus.CLOSED
                    other.thread.save(update_fields=["status"])

        listing.status = ListingStatus.SOLD
        listing.save(update_fields=["status"])

    messages.success(request, "Negotiation confirmed and listing marked sold.")
    return redirect("threads:thread_detail", thread_id=negotiation.thread.id)


@login_required
def open_negotiation_conversation(request, negotiation_id):
    """
    Open conversation for a negotiation.
    If no thread exists yet, create it (similar to accept flow).
    """
    negotiation = get_object_or_404(NegotiationThread, id=negotiation_id)

    # Verify user is either buyer or seller
    if request.user != negotiation.buyer and request.user != negotiation.seller:
        return HttpResponseForbidden()

    # If thread doesn't exist, create it
    if not negotiation.thread:
        with transaction.atomic():
            # create private thread
            thread = Thread.objects.create(
                title=f"Marketplace: {negotiation.listing.title}",
                visibility=ThreadVisibility.PRIVATE,
            )

            # seller participant
            ThreadParticipant.objects.create(
                thread=thread,
                user=negotiation.seller,
                role=ThreadParticipantRole.AUTHOR,
            )

            # buyer participant
            ThreadParticipant.objects.create(
                thread=thread,
                user=negotiation.buyer,
                role=ThreadParticipantRole.MEMBER,
            )

            # connect thread to negotiation
            negotiation.thread = thread
            if negotiation.status == NegotiationStatus.PENDING:
                negotiation.status = NegotiationStatus.ACCEPTED
            negotiation.save(update_fields=["thread", "status"])

    return redirect("threads:thread_detail", thread_id=negotiation.thread.id)


@login_required
def reject_negotiation(request, negotiation_id):

    negotiation = get_object_or_404(
        NegotiationThread, id=negotiation_id, seller=request.user
    )

    with transaction.atomic():
        negotiation.status = NegotiationStatus.REJECTED
        negotiation.save(update_fields=["status"])

        if negotiation.thread and negotiation.thread.status != ThreadStatus.CLOSED:
            negotiation.thread.status = ThreadStatus.CLOSED
            negotiation.thread.save(update_fields=["status"])

    messages.success(request, "Chat request rejected.")

    return redirect("marketplace:review_inquiries", listing_id=negotiation.listing.id)
