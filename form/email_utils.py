"""Utility helpers for transactional email delivery."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def send_welcome_email(user):
    """Send the onboarding welcome email to a newly created user."""
    if not user.email:
        return

    context = {
        "user": user,
        "support_email": settings.DEFAULT_FROM_EMAIL,
    }

    subject = "Welcome to Viking Roots"
    html_body = render_to_string("emails/welcome_email.html", context)
    text_body = strip_tags(html_body)

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email_message.attach_alternative(html_body, "text/html")
    email_message.send(fail_silently=True)
