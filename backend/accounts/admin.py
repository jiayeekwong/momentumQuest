from django.contrib import admin
from django.contrib.auth.models import Group
from .models import User, Student, Company, AdminProfile

admin.site.register(User)
admin.site.register(Student)
admin.site.register(Company)
admin.site.register(AdminProfile)

# Hide Django's built-in Groups from the admin — this project uses the custom
# `role` field for authorization, not Django Groups.
admin.site.unregister(Group)