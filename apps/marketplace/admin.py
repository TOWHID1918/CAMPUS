from django.contrib import admin
from .models import Listing, ListingPhoto, NegotiationThread, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ["name"]
    search_fields = ["name"]


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display  = ["title", "seller", "category", "price", "status", "created_at"]
    list_filter   = ["status", "category"]
    search_fields = ["title", "seller__email"]


admin.site.register(ListingPhoto)
admin.site.register(NegotiationThread)