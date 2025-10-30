from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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

