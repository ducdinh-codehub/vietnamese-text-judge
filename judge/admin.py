from django.contrib import admin

from .models import LiveComment


@admin.register(LiveComment)
class LiveCommentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "author", "text", "kind", "status", "assigned_to", "restored")
    list_filter = ("kind", "status", "restored")
    search_fields = ("author", "text")
