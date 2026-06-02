from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display   = ("title", "audience", "admin", "publish_time")
    list_filter    = ("audience",)
    search_fields  = ("title", "message")
    readonly_fields = ("publish_time",)
