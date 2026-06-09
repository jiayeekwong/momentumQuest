from rest_framework import serializers

from scrape_jobs.models import Skill
from .models import JobApplication, JobListing, JobSkill


class JobListingWriteSerializer(serializers.ModelSerializer):
    required_skills = serializers.ListField(
        child=serializers.CharField(max_length=100),
        write_only=True,
        required=False,
        default=list,
    )

    class Meta:
        model = JobListing
        fields = [
            'id', 'job_title', 'category', 'description',
            'salary_min', 'salary_max', 'work_mode',
            'experience_level', 'closing_date', 'status',
            'required_skills',
        ]

    def _sync_skills(self, job, skill_names):
        JobSkill.objects.filter(job=job).delete()
        for name in skill_names:
            skill = Skill.objects.filter(skill_name__iexact=name).first()
            if not skill:
                skill = Skill.objects.create(skill_name=name)
            JobSkill.objects.get_or_create(job=job, skill=skill)

    def create(self, validated_data):
        skill_names = validated_data.pop('required_skills', [])
        job = JobListing.objects.create(**validated_data)
        self._sync_skills(job, skill_names)
        return job

    def update(self, instance, validated_data):
        skill_names = validated_data.pop('required_skills', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if skill_names is not None:
            self._sync_skills(instance, skill_names)
        return instance


class JobListingReadSerializer(serializers.ModelSerializer):
    required_skills    = serializers.SerializerMethodField()
    applicants_count   = serializers.SerializerMethodField()
    category_name      = serializers.CharField(source='category.category_name',
                                               read_only=True, default=None)
    company            = serializers.SerializerMethodField()

    class Meta:
        model = JobListing
        fields = [
            'id', 'job_title', 'category', 'category_name', 'company', 'description',
            'salary_min', 'salary_max', 'work_mode', 'experience_level',
            'closing_date', 'status', 'posted_time',
            'required_skills', 'applicants_count',
        ]

    def get_required_skills(self, obj):
        return list(obj.job_skills.select_related('skill')
                       .values_list('skill__skill_name', flat=True))

    def get_applicants_count(self, obj):
        return obj.applications.count()

    def get_company(self, obj):
        return {
            'id': obj.company.company_id,
            'company_name': obj.company.company_name,
        } if obj.company else None


class JobListingSummarySerializer(serializers.ModelSerializer):
    applicants_count = serializers.SerializerMethodField()
    category_name    = serializers.CharField(source='category.category_name',
                                              read_only=True, default=None)

    class Meta:
        model = JobListing
        fields = [
            'id', 'job_title', 'category_name', 'status',
            'closing_date', 'posted_time', 'applicants_count',
            'work_mode', 'experience_level',
        ]

    def get_applicants_count(self, obj):
        return obj.applications.count()


class JobApplicationSerializer(serializers.ModelSerializer):
    student_name   = serializers.CharField(source='student.student_name', read_only=True)
    student_email  = serializers.CharField(source='student.user.email', read_only=True)
    student_skills = serializers.SerializerMethodField()
    match_score    = serializers.SerializerMethodField()
    job_title      = serializers.CharField(source='job.job_title', read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            'id', 'student_name', 'student_email', 'student_skills',
            'match_score', 'job_title', 'job',
            'cv_url', 'status', 'applied_time', 'is_read',
            'needs_work_permit', 'available_from', 'phone', 'cover_note',
        ]

    def get_student_skills(self, obj):
        return list(
            obj.student.student_skills
               .select_related('skill')
               .values_list('skill__skill_name', flat=True)
        )

    def get_match_score(self, obj):
        job_skills = set(
            obj.job.job_skills.values_list('skill__skill_name', flat=True)
        )
        if not job_skills:
            return 0
        student_skills = set(
            ss.lower() for ss in
            obj.student.student_skills.values_list('skill__skill_name', flat=True)
        )
        matched = sum(1 for s in job_skills if s.lower() in student_skills)
        return round(matched / len(job_skills) * 100)


class JobApplicationStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobApplication
        fields = ['status']
