from django.urls import path
from . import views
from django.http import HttpResponse

def home(request):
    return HttpResponse("Welcome Home! You are logged in.")

#urls
urlpatterns = [
    path("", home, name="home"),  # basic homepage
    path("register/", views.register_new_user, name="register"),
    path("login/", views.login_existing_user, name="login"),
    path("logout/", views.logout_user, name="logout"),
] 