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
from resources import private_storage
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
    author_name = serializers.SerializerMethodField()
    author_type = serializers.SerializerMethodField()
    reviewed_by_name = serializers.CharField(
        source='reviewed_by.admin_name', read_only=True, default=None)
    categories = CategoriesField(default=list, required=False)
    attachment_receipt = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=2048)
    supporting_doc = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=200)

    class Meta:
        model = Announcement
        fields = [
            'id', 'admin_name', 'author_name', 'author_type',
            'reviewed_by_name', 'title', 'message',
            'categories', 'audience', 'supporting_doc', 'attachment_receipt',
            'approval_status', 'rejection_reason', 'submitted_at',
            'reviewed_at', 'publish_time',
        ]
        read_only_fields = [
            'id', 'admin_name', 'author_name', 'author_type',
            'reviewed_by_name', 'approval_status', 'rejection_reason',
            'submitted_at', 'reviewed_at', 'publish_time',
        ]

    def get_admin_name(self, obj):
        return self.get_author_name(obj)

    def get_author_name(self, obj):
        if obj.submitted_by_id and obj.submitted_by.role == 'COMPANY':
            company = getattr(obj.submitted_by, 'company_profile', None)
            return company.company_name if company else None
        if obj.admin:
            return obj.admin.admin_name
        if obj.submitted_by_id:
            profile = getattr(obj.submitted_by, 'admin_profile', None)
            return profile.admin_name if profile else obj.submitted_by.email
        return None

    def get_author_type(self, obj):
        if obj.submitted_by_id:
            return obj.submitted_by.role
        return 'ADMIN' if obj.admin_id else None

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
        requested_url = attrs.get(
            'supporting_doc',
            self.instance.supporting_doc if self.instance else None,
        )
        existing_unchanged = bool(
            self.instance and requested_url == self.instance.supporting_doc)
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
            used = Announcement.objects.filter(attachment_path=path)
            if self.instance:
                used = used.exclude(pk=self.instance.pk)
            if used.exists():
                raise serializers.ValidationError({
                    'attachment_receipt':
                        'This upload has already been attached to an announcement.'
                })
            attrs['supporting_doc'] = build_attachment_url(
                request, ANNOUNCEMENT_ATTACHMENT_DIR, name)
            self._attachment_path_update = path
        elif managed_attachment_name(
                requested_url, ANNOUNCEMENT_ATTACHMENT_DIR):
            if not existing_unchanged:
                raise serializers.ValidationError({
                    'attachment_receipt':
                        'Upload the attachment again before saving.'
                })
        elif (self.instance is not None and 'supporting_doc' in attrs
              and not existing_unchanged):
            self._attachment_path_update = None
        return attrs

    def create(self, validated_data):
        if hasattr(self, '_attachment_path_update'):
            validated_data['attachment_path'] = self._attachment_path_update
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

    def update(self, instance, validated_data):
        old_path = instance.attachment_path
        if hasattr(self, '_attachment_path_update'):
            validated_data['attachment_path'] = self._attachment_path_update
        try:
            with transaction.atomic():
                updated = super().update(instance, validated_data)
                if old_path and old_path != updated.attachment_path:
                    transaction.on_commit(
                        lambda path=old_path: private_storage.delete(path))
                return updated
        except IntegrityError:
            path = validated_data.get('attachment_path')
            if path and Announcement.objects.filter(
                    attachment_path=path).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({
                    'attachment_receipt':
                        'This upload has already been attached to an announcement.'
                })
            raise


class AnnouncementReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['approval_status', 'rejection_reason']

    def validate(self, attrs):
        decision = attrs.get('approval_status')
        if decision not in {
            Announcement.ApprovalStatus.APPROVED,
            Announcement.ApprovalStatus.REJECTED,
        }:
            raise serializers.ValidationError({
                'approval_status': 'Choose APPROVED or REJECTED.'})
        if (decision == Announcement.ApprovalStatus.REJECTED
                and not attrs.get('rejection_reason', '').strip()):
            raise serializers.ValidationError({
                'rejection_reason': 'Give the company a reason for rejection.'})
        if self.instance.approval_status != Announcement.ApprovalStatus.PENDING:
            raise serializers.ValidationError({
                'approval_status':
                    'Only a pending announcement can be reviewed.'})
        if decision == Announcement.ApprovalStatus.APPROVED:
            attrs['rejection_reason'] = ''
        return attrs
