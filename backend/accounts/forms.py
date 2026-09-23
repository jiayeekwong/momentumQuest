"""Admin forms for the custom User model.

These exist because ``accounts.User`` replaces the username with an email and
Django's stock admin forms are declared against ``django.contrib.auth.User``:
their ``Meta.model`` is that model and their ``Meta.fields`` is ``("username",)``,
which this model does not have.

Without them the admin fell back to a plain ModelForm over every editable field.
``password`` is an ordinary CharField on AbstractBaseUser, so it rendered as a
single visible text box and was written to the database exactly as typed --
unhashed. Users created that way could not log in, because check_password
compares a raw string against something that is not a hash, and their passwords
were readable by anyone who could read the table or a backup of it.

``AdminUserCreationForm`` hashes once, through ``set_password``, and adds the
admin's "no usable password" option. ``UserChangeForm`` renders the stored hash
read-only, so editing a user cannot overwrite a good hash with plain text.
"""

from django.contrib.auth import forms as auth_forms

from .models import User


class UserCreationForm(auth_forms.AdminUserCreationForm):
    """Add User: asks for the password twice, validates it, hashes it once."""

    class Meta(auth_forms.AdminUserCreationForm.Meta):
        model = User
        # The login field. REQUIRED_FIELDS is empty, and role has a default, so
        # email is all that must be collected alongside the password.
        fields = ("email",)


class UserChangeForm(auth_forms.UserChangeForm):
    """Edit User: the password is shown as a hash and cannot be typed over."""

    class Meta(auth_forms.UserChangeForm.Meta):
        model = User
        fields = "__all__"
