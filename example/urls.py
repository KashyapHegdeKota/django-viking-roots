# example/urls.py
from django.urls import path

from example.views import index


urlpatterns = [
    path('', index),
]

urlpatterns = [
    path('hello/', hello_world),
]