from django.urls import path
from . import views

app_name = 'recognition'

urlpatterns = [
    # Privacy & Settings
    path('settings/face-tagging/', views.privacy_settings_view, name='privacy_settings'),
    
    # Face Enrollment
    path('faces/enroll/', views.enroll_face_view, name='enroll_face'),
    path('faces/status/', views.enrollment_status_view, name='enrollment_status'),
    path('faces/delete/', views.delete_face_data_view, name='delete_face_data'),
    
    # Tag Suggestions
    path('tags/pending/', views.pending_tags_view, name='pending_tags'),
    path('tags/<int:tag_id>/review/', views.review_tag_view, name='review_tag'),

    # AWS Lambda Webhook
    path('webhook/lambda-recognition/', views.lambda_recognition_webhook, name='recognition_webhook'),
]
