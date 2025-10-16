from django.urls import path
from . import views

app_name = 'questionaire'

urlpatterns = [
    # Get initial welcome message
    path('start/', views.start_interview, name='start_interview'),
    
    # Send message and get response
    path('message/', views.send_message, name='send_message'),
]