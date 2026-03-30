from django.urls import path
from . import views

app_name = 'ai_interview'

urlpatterns = [
    # Interview Flow
    path('start/', views.start_interview, name='start_interview'),
    path('message/', views.send_message, name='send_message'),
    path('complete/', views.complete_interview, name='complete_interview'),
]