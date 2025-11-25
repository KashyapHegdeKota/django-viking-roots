# questionaire/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    """Extended user profile for heritage data"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='heritage_profile')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    interview_completed = models.BooleanField(default=False)
    interview_started_at = models.DateTimeField(null=True, blank=True)
    interview_completed_at = models.DateTimeField(null=True, blank=True)
    json_backup_url = models.URLField(blank=True, null=True, help_text="S3 URL of full JSON backup")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Heritage Profile"


class Ancestor(models.Model):
    """Individual ancestor/family member"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ancestors')
    
    # Basic info
    unique_id = models.CharField(max_length=100, help_text="Unique identifier like 'bjorn_grandfather'")
    name = models.CharField(max_length=200)
    relation = models.CharField(max_length=100, help_text="Relationship to user (e.g., grandfather, aunt)")
    
    # Optional structured fields
    birth_year = models.IntegerField(null=True, blank=True)
    death_year = models.IntegerField(null=True, blank=True)
    birth_place = models.CharField(max_length=200, blank=True)
    origin = models.CharField(max_length=200, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'unique_id']
        indexes = [
            models.Index(fields=['user', 'unique_id']),
            models.Index(fields=['user', 'relation']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.relation}) - {self.user.username}"


class AncestorFact(models.Model):
    """Additional facts/attributes about ancestors"""
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='facts')
    key = models.CharField(max_length=100, help_text="Fact name (e.g., occupation, hair_color)")
    value = models.TextField(help_text="Fact value")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['ancestor', 'key']),
        ]
    
    def __str__(self):
        return f"{self.ancestor.name}: {self.key} = {self.value}"


class Story(models.Model):
    """Stories and narratives about ancestors"""
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='stories')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stories')
    
    content = models.TextField()
    context = models.CharField(max_length=200, blank=True, help_text="Context of the story")
    
    # Social features
    is_public = models.BooleanField(default=False)
    likes_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['ancestor', '-created_at']),
        ]
    
    def __str__(self):
        return f"Story about {self.ancestor.name} by {self.user.username}"


class AncestorMedia(models.Model):
    """Photos, documents, and other media"""
    MEDIA_TYPES = [
        ('photo', 'Photo'),
        ('document', 'Document'),
        ('video', 'Video'),
        ('audio', 'Audio'),
    ]
    
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='media')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ancestor_media')
    
    file = models.FileField(upload_to='ancestor_media/%Y/%m/')
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    
    # Metadata
    file_size = models.IntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.media_type}: {self.title or self.file.name}"


class InterviewSession(models.Model):
    """Track interview chat sessions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_sessions')
    session_id = models.CharField(max_length=100, unique=True)
    
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    completed = models.BooleanField(default=False)
    
    # Store raw chat history as JSON
    chat_history = models.JSONField(default=list)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Interview: {self.user.username} - {self.started_at.date()}"