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
]
