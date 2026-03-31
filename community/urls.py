from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    # Community & Sharing (Sprint 9)
    path('matches/', views.find_potential_matches, name='find_matches'),
    path('matches/<int:match_id>/confirm/', views.confirm_ancestor_match, name='confirm_match'),
]