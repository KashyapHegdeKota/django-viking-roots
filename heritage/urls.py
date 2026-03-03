from django.urls import path
from . import views

app_name = 'heritage'

urlpatterns = [
    # Data Retrieval (Ticket #160)
    path('data/',     views.get_heritage_data, name='get_heritage_data'),
    path('tree/',     views.get_family_tree,   name='get_family_tree'),
    path('timeline/', views.get_timeline_data, name='get_timeline_data'),

    # Bulk Import (Ticket #156)
    path('upload-gedcom/', views.upload_gedcom, name='upload_gedcom'),
    path('export-gedcom/', views.export_gedcom, name='export_gedcom'),
    
    # Locations — NEW (Ticket #161)
    # GET  /heritage/locations/?search=Gimli
    # POST /heritage/locations/
    path('locations/', views.locations, name='locations'),

    # CRUD APIs for Manual Editing (Ticket #161)
    # Note: check-duplicates must be declared before ancestor/<str:ancestor_id>/
    # otherwise Django will try to match 'check-duplicates' as an ancestor_id.
    path('ancestor/check-duplicates/', views.check_duplicates,  name='check_duplicates'),
    path('ancestor/',                  views.create_ancestor,    name='create_ancestor'),
    path('ancestor/<str:ancestor_id>/', views.manage_ancestor,  name='manage_ancestor'),

    # Ancestor Facts — NEW (Ticket #161)
    path('ancestor/<str:ancestor_id>/facts/',               views.manage_ancestor_facts, name='manage_ancestor_facts'),
    path('ancestor/<str:ancestor_id>/facts/<int:fact_id>/', views.manage_single_fact,    name='manage_single_fact'),

    # Ancestor <-> Event linking — NEW (Ticket #161)
    path('ancestor/<str:ancestor_id>/events/', views.manage_ancestor_events, name='manage_ancestor_events'),

    # Events (Ticket #161)
    path('event/<int:event_id>/', views.manage_event, name='manage_event'),
]