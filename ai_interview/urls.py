from django.urls import path
from . import views

app_name = 'ai_interview'

urlpatterns = [
    # Main Interview Flow
    path('start/', views.start_interview, name='start_interview'),
    path('message/', views.send_message, name='send_message'),
    path('complete/', views.complete_interview, name='complete_interview'),
    
    # Dynamic Story Prompts & Story Interviews
    path('story/prompts/', views.get_dynamic_prompts, name='get_story_prompts'),
    path('story/start/', views.start_story_interview, name='start_story_interview'),
    path('story/message/', views.send_story_message, name='send_story_message'),
]