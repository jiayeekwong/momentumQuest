import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from rest_framework import serializers

from resources.attachments import (
    ANNOUNCEMENT_ATTACHMENT_DIR,
    InvalidAttachmentReceipt,
    build_attachment_url,
    managed_attachment_name,
    verify_attachment_receipt,
)
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
    attachment_receipt = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=2048)
    supporting_doc = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=200)

    class Meta:
        model = Announcement
        fields = [
            'id', 'admin_name', 'title', 'message',
            'categories', 'audience', 'supporting_doc', 'attachment_receipt',
            'publish_time',
        ]
        read_only_fields = ['id', 'admin_name', 'publish_time']

    def get_admin_name(self, obj):
        return obj.admin.admin_name if obj.admin else None

    def validate_supporting_doc(self, value):
        if not value or managed_attachment_name(
                value, ANNOUNCEMENT_ATTACHMENT_DIR):
            return value
        try:
            URLValidator()(value)
        except DjangoValidationError:
            raise serializers.ValidationError('Enter a valid URL.')
        return value

    def validate(self, attrs):
        receipt = attrs.pop('attachment_receipt', '')
        requested_url = attrs.get('supporting_doc')
        if receipt:
            request = self.context.get('request')
            if request is None:
                raise serializers.ValidationError({
                    'attachment_receipt': 'The upload could not be verified.'})
            try:
                path, name = verify_attachment_receipt(
                    receipt, request.user.id, ANNOUNCEMENT_ATTACHMENT_DIR)
            except InvalidAttachmentReceipt as exc:
                raise serializers.ValidationError(
                    {'attachment_receipt': str(exc)})
            if Announcement.objects.filter(attachment_path=path).exists():
                raise serializers.ValidationError({
                    'attachment_receipt':
                        'This upload has already been attached to an announcement.'
                })
            attrs['supporting_doc'] = build_attachment_url(
                request, ANNOUNCEMENT_ATTACHMENT_DIR, name)
            self._attachment_path = path
        elif managed_attachment_name(
                requested_url, ANNOUNCEMENT_ATTACHMENT_DIR):
            raise serializers.ValidationError({
                'attachment_receipt':
                    'Upload the attachment again before publishing.'
            })
        return attrs

    def create(self, validated_data):
        if hasattr(self, '_attachment_path'):
            validated_data['attachment_path'] = self._attachment_path
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError:
            path = validated_data.get('attachment_path')
            if path and Announcement.objects.filter(
                    attachment_path=path).exists():
                raise serializers.ValidationError({
                    'attachment_receipt':
                        'This upload has already been attached to an announcement.'
                })
            raise
