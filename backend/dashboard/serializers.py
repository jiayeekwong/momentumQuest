from rest_framework import serializers

from .models import Announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    admin_name = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ['id', 'admin_name', 'title', 'message', 'supporting_doc', 'publish_time']
        read_only_fields = ['id', 'admin_name', 'publish_time']

    def get_admin_name(self, obj):
        return obj.admin.admin_name if obj.admin else None
