from django.urls import path
from . import views

app_name = 'questionaire'

urlpatterns = [
    # Interview Flow
    path('start/', views.start_interview, name='start_interview'),
    path('message/', views.send_message, name='send_message'),
    path('complete/', views.complete_interview, name='complete_interview'),
    
    # Data Retrieval (Ticket #160)
    path('data/', views.get_heritage_data, name='get_heritage_data'),
    path('tree/', views.get_family_tree, name='get_family_tree'),
    path('timeline/', views.get_timeline_data, name='get_timeline_data'),

    # Bulk Import (Ticket #156)
    path('upload-gedcom/', views.upload_gedcom, name='upload_gedcom'),

    # CRUD APIs for Manual Editing (Ticket #161)
    path('ancestor/', views.create_ancestor, name='create_ancestor'),
    path('ancestor/<str:ancestor_id>/', views.manage_ancestor, name='manage_ancestor'),
    path('event/<int:event_id>/', views.manage_event, name='manage_event'),

    # Community & Sharing (Sprint 9)
    path('matches/', views.find_potential_matches, name='find_matches'),
    path('matches/<int:match_id>/confirm/', views.confirm_ancestor_match, name='confirm_match'),
    path('tree/merged/', views.get_merged_family_tree, name='merged_tree'),
]