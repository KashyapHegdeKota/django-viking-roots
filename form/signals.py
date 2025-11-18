from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .email_utils import send_welcome_email
from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile automatically when a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def send_welcome_email_on_create(sender, instance, created, **kwargs):
    """Send the onboarding welcome email once the user record exists."""
    if created:
        send_welcome_email(instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved."""
    if hasattr(instance, 'profile'):
        instance.profile.save()
