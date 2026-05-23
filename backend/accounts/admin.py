from django.contrib import admin
from .models import User, Student, Company, AdminProfile

admin.site.register(User)
admin.site.register(Student)
admin.site.register(Company)
admin.site.register(AdminProfile)