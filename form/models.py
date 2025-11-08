from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class UserOTP(models.Model):
    """Stores the one-time-password for a user during email verification."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="otp_record")
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = "User OTP"
        verbose_name_plural = "User OTPs"

    def __str__(self):
        return f"OTP for {self.user.email}"

    def has_expired(self) -> bool:
        """Return True if the OTP has expired."""

        return timezone.now() >= self.expires_at


def upload_image_path(instance, filename):
    """Generate upload path for images."""
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4()}.{ext}'
    return f'media/images/{filename}'


class UploadedImage(models.Model):
    """Stores uploaded images to S3."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="uploaded_images", null=True, blank=True)
    image = models.ImageField(upload_to=upload_image_path)
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_size = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Uploaded Image"
        verbose_name_plural = "Uploaded Images"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title or 'Image'} uploaded by {self.user.username if self.user else 'Anonymous'}"


def upload_profile_picture_path(instance, filename):
    """Generate upload path for profile pictures."""
    ext = filename.split('.')[-1]
    filename = f'profile_{uuid.uuid4()}.{ext}'
    return f'media/profiles/{filename}'


def upload_cover_photo_path(instance, filename):
    """Generate upload path for cover photos."""
    ext = filename.split('.')[-1]
    filename = f'cover_{uuid.uuid4()}.{ext}'
    return f'media/covers/{filename}'


class UserProfile(models.Model):
    """Extended user profile for social media features."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    profile_picture = models.ImageField(upload_to=upload_profile_picture_path, null=True, blank=True)
    cover_photo = models.ImageField(upload_to=upload_cover_photo_path, null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile_completed = models.BooleanField(default=False)  # True when profile picture is uploaded

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def full_name(self):
        """Return user's full name or username."""
        return self.user.get_full_name() or self.user.username

    @property
    def has_profile_picture(self):
        """Check if user has uploaded a profile picture."""
        return bool(self.profile_picture)

