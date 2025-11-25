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
]