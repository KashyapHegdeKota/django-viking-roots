from django.urls import path
from . import views

app_name = 'recognition'

urlpatterns = [
    # Privacy & Settings
    path('settings/face-tagging/', views.PrivacySettingsView.as_view(), name='privacy_settings'),
    
    # Face Enrollment
    path('faces/enroll/', views.EnrollFaceView.as_view(), name='enroll_face'),
    path('faces/status/', views.EnrollmentStatusView.as_view(), name='enrollment_status'),
    path('faces/delete/', views.DeleteFaceDataView.as_view(), name='delete_face_data'),
    
    # Tag Suggestions
    path('tags/pending/', views.PendingTagsView.as_view(), name='pending_tags'),
    path('tags/<int:tag_id>/review/', views.ReviewTagView.as_view(), name='review_tag'),

    # AWS Lambda Webhook
    path('webhook/lambda-recognition/', views.LambdaRecognitionWebhook.as_view(), name='recognition_webhook'),
]
