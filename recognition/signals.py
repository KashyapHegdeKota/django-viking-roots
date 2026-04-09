from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import PrivacySettings, FaceEnrollment

@receiver(post_save, sender=User)
def create_user_recognition_records(sender, instance, created, **kwargs):
    if created:
        PrivacySettings.objects.get_or_create(user=instance)
        FaceEnrollment.objects.get_or_create(user=instance)
