from django.db import models
from django.contrib.auth.models import User

class ImportBatch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    filename = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='processing')

class HeritageLocation(models.Model):
    name = models.CharField(max_length=200)
    original_name = models.CharField(max_length=200, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_type = models.CharField(max_length=50, choices=[('farm', 'Farm/Homestead'), ('town', 'Town'), ('cemetery', 'Cemetery'), ('other', 'Other')], default='other')

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='heritage_profile')
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    access_level = models.CharField(max_length=20, choices=[('contributor', 'Contributor'), ('curator', 'Curator')], default='contributor')
    interview_completed = models.BooleanField(default=False)
    interview_started_at = models.DateTimeField(null=True, blank=True)
    interview_completed_at = models.DateTimeField(null=True, blank=True)
    json_backup_url = models.URLField(blank=True, null=True)

class Ancestor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ancestors')
    import_batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)
    unique_id = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    relation = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], blank=True)
    birth_date = models.DateField(null=True, blank=True)
    birth_year = models.IntegerField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    death_year = models.IntegerField(null=True, blank=True)
    birth_location = models.ForeignKey(HeritageLocation, related_name='births', null=True, blank=True, on_delete=models.SET_NULL)
    origin = models.CharField(max_length=200, blank=True)
    source_type = models.CharField(max_length=20, choices=[('ai_chat', 'AI Interview'), ('manual', 'Manual Entry'), ('gedcom', 'GEDCOM')], default='ai_chat')

    father = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='children_as_father'
    )
    mother = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='children_as_mother'
    )
    spouses = models.ManyToManyField(
        'self', 
        blank=True
    )

class AncestorFact(models.Model):
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='facts')
    key = models.CharField(max_length=100)
    value = models.TextField()

class HeritageEvent(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date_start = models.DateField(null=True, blank=True)
    date_end = models.DateField(null=True, blank=True)
    location = models.ForeignKey(HeritageLocation, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=[('personal', 'Personal'), ('community', 'Community')], default='personal')

class EventParticipation(models.Model):
    event = models.ForeignKey(HeritageEvent, on_delete=models.CASCADE, related_name='participants')
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='events')
    role = models.CharField(max_length=100)

class HeritageMedia(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='heritage_media/%Y/%m/')
    media_type = models.CharField(max_length=20, choices=[('photo', 'Photo'), ('audio', 'Audio'), ('doc', 'Document'), ('video', 'Video')])
    title = models.CharField(max_length=200, blank=True)

class MediaTag(models.Model):
    media = models.ForeignKey(HeritageMedia, on_delete=models.CASCADE, related_name='tags')
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='media_tags')
    box_x = models.FloatField(default=0)
    box_y = models.FloatField(default=0)

class Story(models.Model):
    ancestor = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='stories')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stories')
    content = models.TextField()
    context = models.CharField(max_length=200, blank=True)