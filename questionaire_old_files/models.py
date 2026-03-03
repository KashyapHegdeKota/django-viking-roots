from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# --- UTILITY MODELS ---

class ImportBatch(models.Model):
    """Tracks bulk imports (GEDCOM) so they can be undone"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    filename = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=[('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')],
        default='processing'
    )

    def __str__(self):
        return f"Batch: {self.filename} ({self.uploaded_at.date()})"


class HeritageLocation(models.Model):
    """
    First-Class Citizen for Places (The 'Where')
    Used for Homesteads, Birthplaces, Cemeteries.
    """
    name = models.CharField(max_length=200, help_text="Current name, e.g., 'Gimli, MB'")
    original_name = models.CharField(max_length=200, blank=True, help_text="Historical name, e.g., 'Vídney'")
    
    # Geospatial for Maps
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    location_type = models.CharField(
        max_length=50, 
        choices=[('farm', 'Farm/Homestead'), ('town', 'Town'), ('cemetery', 'Cemetery'), ('other', 'Other')],
        default='other'
    )

    def __str__(self):
        return self.original_name or self.name


# --- CORE IDENTITY ---

class UserProfile(models.Model):
    """Extended user profile for heritage data"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='heritage_profile')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    
    # Access Control
    access_level = models.CharField(
        max_length=20, 
        choices=[('contributor', 'Contributor'), ('curator', 'Curator')], 
        default='contributor'
    )
    
    # Interview State
    interview_completed = models.BooleanField(default=False)
    interview_started_at = models.DateTimeField(null=True, blank=True)
    interview_completed_at = models.DateTimeField(null=True, blank=True)
    json_backup_url = models.URLField(blank=True, null=True, help_text="S3 URL of full JSON backup")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Heritage Profile"


class Ancestor(models.Model):
    """
    The Index/Identity Node (The 'Who').
    Now supports precise dates and links to Import Batches.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ancestors')
    import_batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)
    
    # Identity
    unique_id = models.CharField(max_length=100, help_text="Unique identifier like 'bjorn_grandfather'")
    name = models.CharField(max_length=200)
    relation = models.CharField(max_length=100, help_text="Relationship to user")
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], blank=True)
    
    # Vital Stats (The 'When')
    birth_date = models.DateField(null=True, blank=True)
    birth_year = models.IntegerField(null=True, blank=True, help_text="Fallback if full date unknown")
    death_date = models.DateField(null=True, blank=True)
    death_year = models.IntegerField(null=True, blank=True)
    
    # Link to Location (The 'Where')
    birth_location = models.ForeignKey(HeritageLocation, related_name='births', null=True, blank=True, on_delete=models.SET_NULL)
    origin = models.CharField(max_length=200, blank=True, help_text="Legacy field for simple text origin")
    
    # Provenance
    source_type = models.CharField(
        max_length=20, 
        choices=[('ai_chat', 'AI Interview'), ('manual', 'Manual Entry'), ('gedcom', 'GEDCOM')],
        default='ai_chat'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'unique_id']
        indexes = [
            models.Index(fields=['user', 'unique_id']),
            models.Index(fields=['user', 'relation']),
        ]

    def __str__(self):
        return f"{self.name} ({self.birth_year or '?'})"


class AncestorFact(models.Model):
    """Unstructured AI Data (The 'What else')"""
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


# --- THE SAGA ENGINE (EVENTS) ---

class HeritageEvent(models.Model):
    """
    Shared History (The 'Saga').
    Example: 'Arrival of S.S. St. Patrick' or '1950 Flood'.
    """
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    date_start = models.DateField(null=True, blank=True)
    date_end = models.DateField(null=True, blank=True)
    
    location = models.ForeignKey(HeritageLocation, on_delete=models.SET_NULL, null=True, blank=True)
    
    event_type = models.CharField(
        max_length=20,
        choices=[('personal', 'Personal (Birth/Marriage)'), ('community', 'Community (Migration/Festival)')],
        default='personal'
    )

    def __str__(self):
        return f"{self.title} ({self.date_start.year if self.date_start else '?'})"


class EventParticipation(models.Model):
    """Links people to events with roles"""
    event = models.ForeignKey(HeritageEvent, on_delete=models.CASCADE, related_name='participants')
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='events')
    role = models.CharField(max_length=100, help_text="e.g. Passenger, Witness, Groom")

    def __str__(self):
        return f"{self.ancestor.name} was {self.role} at {self.event.title}"


# --- MEDIA & EVIDENCE ---

class HeritageMedia(models.Model):
    """
    The Asset (Photo/Doc).
    Decoupled from Ancestor so one photo can have multiple people.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='heritage_media/%Y/%m/')
    media_type = models.CharField(max_length=20, choices=[('photo', 'Photo'), ('audio', 'Audio'), ('doc', 'Document'), ('video', 'Video')])
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    
    # Metadata
    file_size = models.IntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title or self.file.name


class MediaTag(models.Model):
    """Tags a specific person in a photo"""
    media = models.ForeignKey(HeritageMedia, on_delete=models.CASCADE, related_name='tags')
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='media_tags')
    
    # Coordinates for 'Face Box' on the UI (0.0 to 1.0 percentage)
    box_x = models.FloatField(default=0)
    box_y = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.ancestor.name} in {self.media.title}"


# --- CHAT & STORY ---

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


# --- COMMUNITY & MATCHING ---

class FamilyConnection(models.Model):
    """Connects users who share family members"""
    CONNECTION_STATUS = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_connections_initiated')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_connections_received')
    
    connection_type = models.CharField(max_length=50, help_text="e.g., siblings, cousins, parent-child")
    confidence_score = models.FloatField(help_text="AI confidence 0-1 that these users are related")
    
    # Matching ancestors that suggest the connection
    shared_ancestor_name = models.CharField(max_length=200, blank=True)
    
    status = models.CharField(max_length=20, choices=CONNECTION_STATUS, default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['user1', 'user2']
        indexes = [
            models.Index(fields=['user1', 'status']),
            models.Index(fields=['user2', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user1.username} ↔ {self.user2.username} ({self.connection_type})"


class AncestorMatch(models.Model):
    """Links the same person described by different users"""
    MATCH_STATUS = [
        ('suggested', 'Suggested by AI'),
        ('confirmed', 'Confirmed by users'),
        ('rejected', 'Not the same person'),
    ]
    
    ancestor1 = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='matches_as_first')
    ancestor2 = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='matches_as_second')
    
    confidence_score = models.FloatField(help_text="0-1 confidence they're the same person")
    matching_attributes = models.JSONField(default=dict, help_text="Which fields match")
    
    status = models.CharField(max_length=20, choices=MATCH_STATUS, default='suggested')
    
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ['ancestor1', 'ancestor2']
    
    def __str__(self):
        return f"Match: {self.ancestor1.name} ↔ {self.ancestor2.name} ({self.confidence_score:.2f})"


class MergedFamilyTree(models.Model):
    """Represents a merged view of multiple users' trees"""
    name = models.CharField(max_length=200, help_text="e.g., 'The Hegde Family Tree'")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_trees')
    members = models.ManyToManyField(User, related_name='family_trees')
    
    is_public = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name