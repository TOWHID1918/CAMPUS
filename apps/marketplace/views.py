from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import models, transaction
from django.http import HttpResponseForbidden

from apps.media.models import Photo
from apps.threads.models import Thread, ThreadParticipant
from apps.common.choices import (
    ThreadVisibility,
    ThreadParticipantRole,
    ThreadStatus,
    OrderStatus,
)

from .models import (
    Listing,
    ListingPhoto,
    PurchaseOrder,
    ListingStatus,
    Category,
)
from apps.notifications.signals import notify

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PHOTO_MB = 5

ACCEPTED_ORDER_STATUSES = [
    OrderStatus.ACCEPTED,
    OrderStatus.COMPLETED,
]
TERMINAL_ORDER_STATUSES = [OrderStatus.REJECTED, OrderStatus.RECEIVED]


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

    active_order = None
    pending_request = None
    pending_orders_count = 0

    if request.user.is_authenticated:
        pending_request = (
            PurchaseOrder.objects.filter(
                listing=listing,
                buyer=request.user,
                status=OrderStatus.PENDING,
            )
            .order_by("-created_at")
            .first()
        )

        active_order = (
            PurchaseOrder.objects.filter(
                listing=listing,
                buyer=request.user,
                status__in=ACCEPTED_ORDER_STATUSES,
                thread__isnull=False,
            )
            .order_by("-created_at")
            .first()
        )

    # Count pending order requests for seller
    if request.user.is_authenticated and request.user == listing.seller:
        pending_orders_count = PurchaseOrder.objects.filter(
            listing=listing,
            status=OrderStatus.PENDING,
        ).count()

    return render(
        request,
        "marketplace/listing_detail.html",
        {
            "listing": listing,
            "active_order": active_order,
            "pending_request": pending_request,
            "pending_orders_count": pending_orders_count,
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

        listing.category = (
            Category.objects.filter(pk=category_id).first() if category_id else None
        )

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
def review_orders(request, listing_id):
    listing = get_object_or_404(
        Listing,
        pk=listing_id,
        seller=request.user,
    )

    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "first")
    # Orders shown in the Orders page
    requests = PurchaseOrder.objects.filter(listing=listing).select_related(
        "buyer", "thread"
    )

    if search:
        requests = requests.filter(
            models.Q(buyer__handle__icontains=search)
            | models.Q(buyer__email__icontains=search)
        )

    if sort == "quantity_low":
        requests = requests.order_by("quantity", "created_at")
    elif sort == "quantity_high":
        requests = requests.order_by("-quantity", "created_at")
    elif sort == "latest":
        requests = requests.order_by("-created_at")
    else:
        requests = requests.order_by("created_at")

    return render(
        request,
        "marketplace/review_orders.html",
        {
            "listing": listing,
            "requests": requests,
            "current_search": search,
            "current_sort": sort,
        },
    )


@login_required
def approve_purchase_request(request, listing_id, request_id):
    listing = get_object_or_404(
        Listing,
        pk=listing_id,
        seller=request.user,
    )

    # Try to load the order thread but handle missing/changed state gracefully
    order = (
        PurchaseOrder.objects.select_related("buyer", "listing")
        .filter(pk=request_id)
        .first()
    )

    if not order:
        messages.error(request, "Order request not found.")
        return redirect("marketplace:review_orders", listing_id=listing.id)

    if order.listing_id != listing.id:
        messages.error(request, "Order does not belong to this listing.")
        return redirect("marketplace:review_orders", listing_id=listing.id)

    if order.status != OrderStatus.PENDING:
        messages.info(request, "This order request is no longer pending.")
        return redirect("marketplace:review_orders", listing_id=listing.id)

    if request.method == "POST":
        with transaction.atomic():
            thread = Thread.objects.create(
                title=f"Marketplace order: {listing.title}",
                visibility=ThreadVisibility.PRIVATE,
            )

            ThreadParticipant.objects.create(
                thread=thread,
                user=request.user,
                role=ThreadParticipantRole.AUTHOR,
            )

            ThreadParticipant.objects.create(
                thread=thread,
                user=order.buyer,
                role=ThreadParticipantRole.MEMBER,
            )

            order.thread = thread
            order.status = OrderStatus.ACCEPTED
            order.save(update_fields=["thread", "status"])

            # notify buyer that their order was accepted via review
            try:
                notify(
                    order.buyer,
                    "Order accepted — private conversation created",
                    target=order,
                    data={
                        "thread_id": thread.id,
                        "order_id": order.id,
                        "listing_id": listing.id,
                        "url": reverse("threads:thread_detail", args=[thread.id]),
                    },
                )
            except Exception:
                pass

        return redirect(
            "threads:thread_detail",
            thread_id=thread.id,
        )

    return render(
        request,
        "marketplace/approve_purchase_request.html",
        {
            "listing": listing,
            "purchase_request": order,
        },
    )


@login_required
def reject_purchase_request(request, listing_id, request_id):
    listing = get_object_or_404(
        Listing,
        pk=listing_id,
        seller=request.user,
    )

    order = (
        PurchaseOrder.objects.select_related("buyer", "listing")
        .filter(pk=request_id)
        .first()
    )

    if not order or order.listing_id != listing.id:
        messages.error(request, "Order request not found.")
        return redirect("marketplace:review_orders", listing_id=listing.id)

    if request.method == "POST":
        if order.status != OrderStatus.PENDING:
            messages.info(request, "This order request is no longer pending.")
        else:
            order.status = OrderStatus.REJECTED
            order.save(update_fields=["status"])
            messages.success(request, "Order request rejected.")
            try:
                notify(
                    order.buyer,
                    "Order request rejected by seller",
                    target=order,
                    data={
                        "order_id": order.id,
                        "listing_id": listing.id,
                        "url": reverse("marketplace:listing_detail", args=[listing.id]),
                    },
                )
            except Exception:
                pass

    return redirect("marketplace:review_orders", listing_id=listing.id)


@login_required
def complete_order(request, order_id):
    order = get_object_or_404(
        PurchaseOrder,
        id=order_id,
        seller=request.user,
        status=OrderStatus.ACCEPTED,
    )

    if request.method == "POST":
        order.status = OrderStatus.COMPLETED
        order.save(update_fields=["status"])
        messages.success(
            request, "Order marked complete. Waiting for buyer confirmation."
        )
        try:
            notify(
                order.buyer,
                "Seller marked your order as complete",
                target=order,
                data={
                    "order_id": order.id,
                    "listing_id": order.listing.id,
                    "url": reverse("threads:thread_detail", args=[order.thread.id]),
                },
            )
        except Exception:
            pass

    return redirect("threads:thread_detail", thread_id=order.thread.id)


@login_required
def confirm_order_received(request, order_id):
    order = get_object_or_404(
        PurchaseOrder,
        id=order_id,
        buyer=request.user,
        status=OrderStatus.COMPLETED,
    )

    if request.method == "POST":
        with transaction.atomic():
            order.status = OrderStatus.RECEIVED
            order.save(update_fields=["status"])

            listing = order.listing
            # decrement available stock by the ordered quantity
            try:
                listing.stock = max(0, listing.stock - order.quantity)
            except Exception:
                listing.stock = 0

            if listing.stock == 0:
                listing.status = ListingStatus.SOLD
                listing.save(update_fields=["stock", "status", "updated_at"])
            else:
                listing.save(update_fields=["stock", "updated_at"])

        messages.success(request, "Order confirmed received.")
        try:
            notify(
                order.seller,
                "Buyer confirmed receipt for the order",
                target=order,
                data={
                    "order_id": order.id,
                    "listing_id": order.listing.id,
                    "url": reverse("threads:thread_detail", args=[order.thread.id]),
                },
            )
        except Exception:
            pass

    return redirect("threads:thread_detail", thread_id=order.thread.id)


@login_required
def contact_seller(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)

    if request.user == listing.seller:
        return HttpResponseForbidden("You cannot contact yourself.")

    if listing.status != ListingStatus.ACTIVE:
        return HttpResponseForbidden("This listing is no longer active.")

    existing = (
        PurchaseOrder.objects.filter(listing=listing, buyer=request.user)
        .exclude(status__in=TERMINAL_ORDER_STATUSES)
        .select_related("thread")
        .first()
    )
    if existing:
        # If a private thread already exists, open it. Otherwise inform buyer their request is pending.
        if existing.thread:
            return redirect("threads:thread_detail", thread_id=existing.thread.id)
        else:
            messages.info(request, "You already have an open request for this listing.")
            return redirect("marketplace:listing_detail", listing_id=listing.id)

    # Create an order record (default quantity 1) but do not create a private thread yet.
    with transaction.atomic():
        order = PurchaseOrder.objects.create(
            listing=listing,
            buyer=request.user,
            seller=listing.seller,
            status=OrderStatus.PENDING,
            quantity=1,
        )

    # Notify the seller about the new order/inquiry
    try:
        notify(
            listing.seller,
            "New inquiry about your listing",
            target=order,
            data={
                "order_id": order.id,
                "listing_id": listing.id,
                "url": reverse("marketplace:review_orders", args=[listing.id]),
            },
        )
    except Exception:
        pass

    messages.success(request, "Contact request submitted. The seller will be notified.")

    return redirect("marketplace:listing_detail", listing_id=listing.id)


@login_required
def my_listings(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "newest")
    listings = (
        Listing.objects.filter(seller=request.user)
        .select_related("category")
        .prefetch_related("photos__photo")
        .annotate(
            pending_orders_count=models.Count(
                "purchase_orders",
                filter=models.Q(purchase_orders__status=OrderStatus.PENDING),
            )
        )
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
def my_orders_buyer(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "newest")
    orders = (
        PurchaseOrder.objects.filter(buyer=request.user)
        .select_related("listing", "listing__seller", "listing__category", "thread")
        .prefetch_related("listing__photos__photo")
        .order_by("-created_at")
    )
    if search:
        orders = orders.filter(listing__title__icontains=search)
    if sort == "oldest":
        orders = orders.order_by("created_at")
    elif sort == "price_low":
        orders = orders.order_by("listing__price")
    elif sort == "price_high":
        orders = orders.order_by("-listing__price")
    else:
        orders = orders.order_by("-created_at")
    return render(
        request,
        "marketplace/orders_buyer.html",
        {
            "orders": orders,
            "current_search": search,
            "current_sort": sort,
        },
    )


@login_required
def review_inquiries(request, listing_id):
    # Redirect legacy inquiries URL to the unified orders page
    return redirect("marketplace:review_orders", listing_id=listing_id)


@login_required
def request_chat(request, listing_id):

    listing = get_object_or_404(
        Listing,
        id=listing_id,
        status=ListingStatus.ACTIVE,
    )

    if listing.seller == request.user:
        return HttpResponseForbidden("You cannot request your own listing.")

    if listing.stock <= 0:
        messages.error(request, "This listing is currently out of stock.")
        return redirect("marketplace:listing_detail", listing_id=listing.id)

    existing_order = (
        PurchaseOrder.objects.filter(
            listing=listing,
            buyer=request.user,
        )
        .exclude(status__in=TERMINAL_ORDER_STATUSES)
        .exists()
    )

    if existing_order:
        messages.warning(request, "You already have an active order for this listing.")
        return redirect("marketplace:listing_detail", listing_id=listing.id)

    if request.method == "POST":
        quantity = request.POST.get("quantity", "1").strip()
        message = request.POST.get("message", "").strip()
        errors = []

        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except ValueError:
            errors.append("Enter a valid order quantity.")

        if quantity > listing.stock:
            errors.append("Requested quantity cannot exceed available stock.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("marketplace:listing_detail", listing_id=listing.id)

        order = PurchaseOrder.objects.create(
            listing=listing,
            buyer=request.user,
            seller=listing.seller,
            quantity=quantity,
            message=message,
            status=OrderStatus.PENDING,
        )
        # Notify the seller about the new order request
        try:
            notify(
                listing.seller,
                "New order request for your listing",
                target=order,
                data={
                    "url": reverse("marketplace:listing_detail", args=[listing.id]),
                    "order_id": order.id,
                    "listing_id": listing.id,
                },
            )
        except Exception:
            pass
        messages.success(request, "Order request submitted.")

    return redirect("marketplace:listing_detail", listing_id=listing.id)


@login_required
def accept_order(request, order_id):

    order = get_object_or_404(PurchaseOrder, id=order_id, seller=request.user)

    # prevent accepting twice
    if order.status != OrderStatus.PENDING:
        return redirect("marketplace:review_inquiries", listing_id=order.listing.id)

    with transaction.atomic():

        # create private thread
        thread = Thread.objects.create(
            title=f"Marketplace: {order.listing.title}",
            visibility=ThreadVisibility.PRIVATE,
        )

        # seller participant
        ThreadParticipant.objects.create(
            thread=thread,
            user=order.seller,
            role=ThreadParticipantRole.AUTHOR,
        )

        # buyer participant
        ThreadParticipant.objects.create(
            thread=thread,
            user=order.buyer,
            role=ThreadParticipantRole.MEMBER,
        )

        # connect thread to order
        order.thread = thread
        order.status = OrderStatus.ACCEPTED
        order.save(update_fields=["thread", "status"])

    # notify buyer that their chat request was accepted
    try:
        notify(
            order.buyer,
            "Chat request accepted — conversation created",
            target=order,
            data={
                "thread_id": thread.id,
                "order_id": order.id,
                "listing_id": order.listing.id,
                "url": reverse("threads:thread_detail", args=[thread.id]),
            },
        )
    except Exception:
        pass

    messages.success(request, "Chat request accepted.")

    return redirect("threads:thread_detail", thread_id=thread.id)


@login_required
def confirm_order(request, order_id):

    order = get_object_or_404(
        PurchaseOrder,
        id=order_id,
        seller=request.user,
        status=OrderStatus.ACCEPTED,
    )

    listing = order.listing

    if listing.status == ListingStatus.SOLD:
        messages.info(request, "This listing has already been marked sold.")
        return redirect("threads:thread_detail", thread_id=order.thread.id)

    with transaction.atomic():
        other_orders = listing.purchase_orders.exclude(id=order.id)
        for other in other_orders:
            if other.status != OrderStatus.REJECTED:
                other.status = OrderStatus.REJECTED
                other.save(update_fields=["status"])
                try:
                    notify(
                        other.buyer,
                        "Order request rejected — another buyer confirmed purchase",
                        target=other,
                        data={
                            "order_id": other.id,
                            "listing_id": listing.id,
                            "url": reverse(
                                "marketplace:listing_detail", args=[listing.id]
                            ),
                        },
                    )
                except Exception:
                    pass
                if other.thread:
                    other.thread.status = ThreadStatus.ARCHIVED
                    other.thread.save(update_fields=["status"])

        listing.status = ListingStatus.SOLD
        listing.save(update_fields=["status"])
    # notify confirmed buyer
    try:
        notify(
            order.buyer,
            "Order confirmed — listing marked sold",
            target=order,
            data={
                "order_id": order.id,
                "listing_id": listing.id,
                "url": reverse("threads:thread_detail", args=[order.thread.id]),
            },
        )
    except Exception:
        pass

    messages.success(request, "Order confirmed and listing marked sold.")
    return redirect("threads:thread_detail", thread_id=order.thread.id)


@login_required
def open_order(request, order_id):
    """
    Open conversation for an order.
    If no thread exists yet, create it (similar to accept flow).
    """
    order = get_object_or_404(PurchaseOrder, id=order_id)

    # Verify user is either buyer or seller
    if request.user != order.buyer and request.user != order.seller:
        return HttpResponseForbidden()

    # If thread doesn't exist, create it
    if not order.thread:
        # Only create the private thread if the seller has already accepted the order.
        if order.status != OrderStatus.ACCEPTED:
            messages.info(
                request, "This conversation hasn't been approved by the seller yet."
            )
            return redirect("marketplace:listing_detail", listing_id=order.listing.id)

        with transaction.atomic():
            # create private thread
            thread = Thread.objects.create(
                title=f"Marketplace: {order.listing.title}",
                visibility=ThreadVisibility.PRIVATE,
            )

            # seller participant
            ThreadParticipant.objects.create(
                thread=thread,
                user=order.seller,
                role=ThreadParticipantRole.AUTHOR,
            )

            # buyer participant
            ThreadParticipant.objects.create(
                thread=thread,
                user=order.buyer,
                role=ThreadParticipantRole.MEMBER,
            )

            # connect thread to order
            order.thread = thread
            order.save(update_fields=["thread"])

    return redirect("threads:thread_detail", thread_id=order.thread.id)


@login_required
def reject_order(request, order_id):

    order = get_object_or_404(PurchaseOrder, id=order_id, seller=request.user)

    with transaction.atomic():
        order.status = OrderStatus.REJECTED
        order.save(update_fields=["status"])

        if order.thread and order.thread.status != ThreadStatus.ARCHIVED:
            order.thread.status = ThreadStatus.ARCHIVED
            order.thread.save(update_fields=["status"])

    try:
        notify(
            order.buyer,
            "Chat request rejected by seller",
            target=order,
            data={
                "order_id": order.id,
                "listing_id": order.listing.id,
                "url": reverse("marketplace:listing_detail", args=[order.listing.id]),
            },
        )
    except Exception:
        pass

    messages.success(request, "Chat request rejected.")

    return redirect("marketplace:review_inquiries", listing_id=order.listing.id)
