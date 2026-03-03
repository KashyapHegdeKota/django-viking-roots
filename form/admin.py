from django.contrib import admin
from .models import UserOTP, UploadedImage, UserProfile, Group, GroupMembership, GroupPost, GroupInvitation


# Register existing models
@admin.register(UserOTP)
class UserOTPAdmin(admin.ModelAdmin):
    list_display = ['user', 'otp', 'is_verified', 'expires_at', 'created_at']
    list_filter = ['is_verified', 'created_at']
    search_fields = ['user__username', 'user__email']


@admin.register(UploadedImage)
class UploadedImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'file_size', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['title', 'user__username']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'location', 'profile_completed', 'created_at']
    list_filter = ['profile_completed', 'created_at']
    search_fields = ['user__username', 'location']


# Register Group models
@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'creator', 'is_public', 'member_count', 'created_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['name', 'description', 'creator__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'group', 'role', 'joined_at']
    list_filter = ['role', 'joined_at']
    search_fields = ['user__username', 'group__name']
    readonly_fields = ['joined_at']


@admin.register(GroupPost)
class GroupPostAdmin(admin.ModelAdmin):
    list_display = ['author', 'group', 'content_preview', 'created_at']
    list_filter = ['created_at', 'group']
    search_fields = ['author__username', 'group__name', 'content']
    readonly_fields = ['created_at', 'updated_at']

    def content_preview(self, obj):
        """Show first 50 characters of content."""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(GroupInvitation)
class GroupInvitationAdmin(admin.ModelAdmin):
    list_display = ['invited_user', 'group', 'invited_by', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['invited_user__username', 'group__name', 'invited_by__username']
    readonly_fields = ['created_at', 'updated_at']

 