import json

from rest_framework import serializers

from .models import Announcement


class CategoriesField(serializers.Field):
    """Accepts either a Python list or a JSON-encoded string (FormData/multipart)."""

    def to_internal_value(self, data):
        if isinstance(data, list):
            return data
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return parsed if isinstance(parsed, list) else []
            except (ValueError, TypeError):
                return []
        return []

    def to_representation(self, value):
        return value if value else []


class AnnouncementSerializer(serializers.ModelSerializer):
    admin_name = serializers.SerializerMethodField()
    categories = CategoriesField(default=list, required=False)

    class Meta:
        model = Announcement
        fields = [
            'id', 'admin_name', 'title', 'message',
            'categories', 'audience', 'supporting_doc', 'publish_time',
        ]
        read_only_fields = ['id', 'admin_name', 'publish_time']

    def get_admin_name(self, obj):
        return obj.admin.admin_name if obj.admin else None
