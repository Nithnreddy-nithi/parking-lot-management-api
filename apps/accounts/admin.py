from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Application access", {"fields": ("role",)}),
        ("Audit timestamps", {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (("Application access", {"fields": ("role",)}),)
    readonly_fields = ("created_at", "updated_at")
    list_display = ("username", "email", "role", "is_active", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("role",)
