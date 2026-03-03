from django.http import HttpResponse
from django.urls import path

from . import views


def home(request):
    return HttpResponse("Welcome Home! You are logged in.")


urlpatterns = [
    path("", home, name="home"),
    path("register/", views.register_new_user, name="register"),
    path("login/", views.login_existing_user, name="login"),
    path("logout/", views.logout_user, name="logout"),
    path("verify-otp/", views.verify_otp, name="verify-otp"),
    path("resend-otp/", views.resend_otp, name="resend-otp"),
    path("upload-image/", views.upload_image, name="upload-image"),
    path("images/", views.get_uploaded_images, name="get-images"),
    # Profile endpoints
    path("profile/upload/", views.upload_profile_picture, name="upload-profile-picture"),
    path("profile/", views.get_user_profile, name="get-profile"),
    path("profile/<str:username>/", views.get_user_profile, name="get-user-profile"),
    path("profile/update/", views.update_profile, name="update-profile"),
    path("profile/status/", views.check_profile_status, name="check-profile-status"),
    # Group endpoints (specific patterns first to avoid conflicts)
    path("groups/create/", views.create_group, name="create-group"),
    path("group/<int:group_id>/", views.get_group_detail, name="get-group-detail"),
    path("group/<int:group_id>/update/", views.update_group, name="update-group"),
    path("group/<int:group_id>/delete/", views.delete_group, name="delete-group"),
    path("groups/<str:username>/", views.list_user_groups, name="list-user-groups"),
    # Group membership endpoints
    path("group/<int:group_id>/members/add/", views.add_group_member, name="add-group-member"),
    path("group/<int:group_id>/members/remove/", views.remove_group_member, name="remove-group-member"),
    path("group/<int:group_id>/members/assign-admin/", views.assign_admin_role, name="assign-admin-role"),
    # Group post endpoints
    path("group/<int:group_id>/posts/", views.get_group_posts, name="get-group-posts"),
    path("group/<int:group_id>/posts/create/", views.create_group_post, name="create-group-post"),
    path("group/<int:group_id>/posts/<int:post_id>/delete/", views.delete_group_post, name="delete-group-post"),
    # Group invitation endpoints
    path("groups/invites/", views.get_user_invites, name="get-user-invites"),
    path("group/<int:group_id>/invites/accept/", views.accept_group_invitation, name="accept-group-invitation"),
    path("group/<int:group_id>/invites/reject/", views.reject_group_invitation, name="reject-group-invitation"),
]
