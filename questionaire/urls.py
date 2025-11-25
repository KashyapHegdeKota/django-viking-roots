# questionaire/urls.py
from django.urls import path
from . import views

app_name = 'questionaire'

urlpatterns = [
    path('start/', views.start_interview, name='start_interview'),
    path('message/', views.send_message, name='send_message'),
    path('complete/', views.complete_interview, name='complete_interview'),
    path('data/', views.get_heritage_data, name='get_heritage_data'),
    path('tree/', views.get_family_tree, name='get_family_tree'),
    path('matches/', views.find_potential_matches, name='find_matches'),
    path('matches/<int:match_id>/confirm/', views.confirm_ancestor_match, name='confirm_match'),
    path('tree/merged/', views.get_merged_family_tree, name='merged_tree'),
]