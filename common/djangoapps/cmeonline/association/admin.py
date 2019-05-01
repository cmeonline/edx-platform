from __future__ import absolute_import
from django.contrib import admin
from .models import Association

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User


# Define an inline admin descriptor for Association model
# which acts a bit like a singleton
class AssociationInline(admin.StackedInline):
    model = Association
    can_delete = False
    verbose_name_plural = 'association'

# Define a new User admin
class UserAdmin(BaseUserAdmin):
    inlines = (AssociationInline, )

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
