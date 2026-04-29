from django.db import models
from django.contrib.auth.models import User
from community.models import Post

class PrivacySettings(models.Model):
    TAGGING_SCOPES = [
        ('nobody', 'Nobody'),
        ('friends_only', 'Friends Only'),
        ('manual_approval', 'Manual Approval Only')
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='privacy_settings')
    face_tagging_enabled = models.BooleanField(default=False)
    tagging_scope = models.CharField(max_length=20, choices=TAGGING_SCOPES, default='manual_approval')

    def __str__(self):
        return f"Privacy for {self.user.username}"

class FaceEnrollment(models.Model):
    """Tracks if a user has enrolled their face in AWS Rekognition."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='face_enrollment')
    is_enrolled = models.BooleanField(default=False)
    face_ids = models.JSONField(default=list)  # Store IDs from AWS Rekognition
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Enrollment for {self.user.username}: {self.is_enrolled}"

class TagSuggestion(models.Model):
    """Pending, Accepted, or Rejected tag suggestions."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ]
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='face_tags')
    suggested_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_tag_suggestions')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='made_tag_suggestions')
    aws_face_id = models.CharField(max_length=100)
    confidence = models.FloatField()
    bounding_box = models.JSONField() # {"Width": ..., "Height": ..., "Left": ..., "Top": ...}
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Tag for {self.suggested_user.username} on post {self.post.id} ({self.status})"
