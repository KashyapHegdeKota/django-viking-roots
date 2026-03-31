# ai_interview/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('start/',   views.start_interview,    name='start_interview'),
    path('message/', views.send_message,        name='send_message'),
    path('complete/', views.complete_interview, name='complete_interview'),
    path('history/', views.get_session_history, name='get_session_history'),
]