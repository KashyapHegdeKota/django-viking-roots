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
]
