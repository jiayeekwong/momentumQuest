from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "title", "audience", "approval_status", "submitted_by",
        "reviewed_by", "publish_time")
    list_filter = ("audience", "approval_status")
    search_fields  = ("title", "message")
    readonly_fields = ("submitted_at", "reviewed_at", "publish_time")
