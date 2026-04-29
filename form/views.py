from email.mime.image import MIMEImage
from html import escape
import json
from pathlib import Path
import secrets
import string
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import UserOTP, UploadedImage, UserProfile


OTP_EXPIRATION_MINUTES = 10
GENERATED_PASSWORD_LENGTH = 18


def _parse_json_body(req):
    if not req.body:
        return {}

    try:
        return json.loads(req.body)
    except json.JSONDecodeError:
        return None


def _admin_required(req):
    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    if not (req.user.is_staff or req.user.is_superuser):
        return JsonResponse({'error': 'Admin access required'}, status=403)

    return None


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _serialize_user(user: User) -> dict:
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'date_joined': user.date_joined.isoformat() if user.date_joined else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
    }


def _generate_secure_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"

    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        has_lower = any(char.islower() for char in password)
        has_upper = any(char.isupper() for char in password)
        has_digit = any(char.isdigit() for char in password)
        has_symbol = any(char in "!@#$%^&*()-_=+" for char in password)
        if has_lower and has_upper and has_digit and has_symbol:
            return password


def _send_welcome_email(user: User, _generated_password: str) -> bool:
    site_url = getattr(settings, "VIKING_ROOTS_SITE_URL", "https://vikingroots.com").rstrip("/")
    password_setup_url = getattr(settings, "VIKING_ROOTS_PASSWORD_SETUP_URL", f"{site_url}/reset-password")
    invite_token = default_token_generator.make_token(user)
    invite_query = urlencode({
        "email": user.email,
        "token": invite_token,
        "source": "invite",
    })
    invite_separator = "&" if "?" in password_setup_url else "?"
    invite_url = f"{password_setup_url}{invite_separator}{invite_query}"
    subject = f"Viking Roots Invitation - {site_url}"

    display_name = user.get_full_name().strip() or user.username
    current_year = timezone.now().year
    timeout_seconds = getattr(settings, "PASSWORD_RESET_TIMEOUT", 60 * 60 * 24 * 3)
    timeout_minutes = max(1, timeout_seconds // 60)
    default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    from_email = getattr(settings, "WELCOME_FROM_EMAIL", None) or (
        f"Team Viking Roots <{default_from_email}>"
        if default_from_email and "<" not in default_from_email
        else default_from_email
    )
    reply_to_email = getattr(settings, "WELCOME_REPLY_TO_EMAIL", None)
    logo_path = Path(getattr(settings, "WELCOME_LOGO_PATH", ""))
    logo_url = getattr(settings, "WELCOME_LOGO_URL", f"{site_url}/img/Logo-Transparent.png")
    logo_content_id = "viking-roots-logo"
    logo_src = f"cid:{logo_content_id}" if logo_path.is_file() else logo_url

    message = (
        f"[Viking Roots]({site_url})\n\n"
        "Welcome to Viking Roots!\n\n"
        f"Hi {display_name},\n\n"
        "An administrator has invited you to access Viking Roots. Please use the link below to set your password "
        "and finish setting up your account.\n\n"
        f"Email: {user.email}\n\n"
        f"Accept Invitation: {invite_url}\n\n"
        f"This link expires in {timeout_minutes} minutes.\n\n"
        "Thank you,\n\n"
        "Team Viking Roots\n\n"
        f"(c) {current_year} Viking Roots. All rights reserved."
    )

    safe_display_name = escape(display_name)
    safe_email = escape(user.email)
    safe_site_url = escape(site_url, quote=True)
    safe_invite_url = escape(invite_url, quote=True)
    safe_logo_src = escape(logo_src, quote=True)

    html_message = f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>Viking Roots</title>
<style>
@media only screen and (max-width: 600px) {{
  .inner-body, .footer {{
    width: 100% !important;
  }}
}}

@media only screen and (max-width: 500px) {{
  .button {{
    width: 100% !important;
  }}
}}
</style>
</head>
<body style="box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #ffffff; color: #4a5568; height: 100%; line-height: 1.4; margin: 0; padding: 0; width: 100% !important;">
<table class="wrapper" width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background-color: #edf2f7; margin: 0; padding: 0; width: 100%;">
<tr>
<td align="center">
<table class="content" width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin: 0; padding: 0; width: 100%;">
<tr>
<td class="header" style="padding: 25px 0; text-align: center;">
<a href="{safe_site_url}" style="color: #2d3748; font-size: 24px; font-weight: 700; text-decoration: none;">
<img src="{safe_logo_src}" alt="Viking Roots" width="220" style="border: none; display: inline-block; height: auto; max-width: 220px; width: 60%;">
</a>
</td>
</tr>
<tr>
<td class="body" width="100%" cellpadding="0" cellspacing="0" style="background-color: #edf2f7; border-bottom: 1px solid #edf2f7; border-top: 1px solid #edf2f7; margin: 0; padding: 0; width: 100%;">
<table class="inner-body" align="center" width="570" cellpadding="0" cellspacing="0" role="presentation" style="background-color: #ffffff; border-color: #e8e5ef; border-radius: 2px; border-width: 1px; box-shadow: 0 2px 0 rgba(0, 0, 150, 0.025), 2px 4px 0 rgba(0, 0, 150, 0.015); margin: 0 auto; padding: 0; width: 570px;">
<tr>
<td class="content-cell" style="max-width: 100vw; padding: 32px;">
<div style="font-size: 16px;">
<p style="font-size: 16px; line-height: 1.5em; margin-top: 0; text-align: left;">Welcome to Viking Roots!</p>
<p style="font-size: 16px; line-height: 1.5em; margin-top: 0; text-align: left;">Hi {safe_display_name},</p>
<p style="font-size: 16px; line-height: 1.5em; margin-top: 0; text-align: left;">An administrator has invited you to access Viking Roots. Please use the link below to set your password and finish setting up your account.</p>
<table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; margin: 22px 0;">
<tr>
<td style="color: #718096; font-size: 14px; padding: 14px 16px 6px 16px;">Email</td>
</tr>
<tr>
<td style="color: #2d3748; font-size: 16px; font-weight: 600; padding: 0 16px 14px 16px;">{safe_email}</td>
</tr>
</table>
<p style="font-size: 16px; line-height: 1.5em; margin-top: 0; text-align: left;">The setup page will prefill your email so you can choose your own password.</p>
<table class="action" align="center" width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin: 30px auto; padding: 0; text-align: center; width: 100%;">
<tr>
<td align="center">
<a href="{safe_invite_url}" class="button button-primary" target="_blank" rel="noopener" style="-webkit-text-size-adjust: none; background-color: #2d3748; border-bottom: 8px solid #2d3748; border-left: 18px solid #2d3748; border-radius: 4px; border-right: 18px solid #2d3748; border-top: 8px solid #2d3748; color: #ffffff; display: inline-block; overflow: hidden; text-decoration: none;">Accept Invitation</a>
</td>
</tr>
</table>
<p style="color: #718096; font-size: 14px; line-height: 1.5em; margin-top: 0; text-align: left;">This link expires in {timeout_minutes} minutes.</p>
<p style="font-size: 16px; line-height: 1.5em; margin-top: 0; text-align: left;">Thank you,</p>
<p style="font-size: 16px; line-height: 1.5em; margin-top: 0; text-align: left;">Team Viking Roots</p>
</div>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td>
<table class="footer" align="center" width="570" cellpadding="0" cellspacing="0" role="presentation" style="margin: 0 auto; padding: 0; text-align: center; width: 570px;">
<tr>
<td class="content-cell" align="center" style="max-width: 100vw; padding: 32px;">
<a href="{safe_site_url}" style="color: #2d3748; font-size: 14px; text-decoration: underline;">VikingRoots.com</a>
<p style="color: #718096; font-size: 12px; line-height: 1.5em; margin-top: 10px; text-align: center;">&copy; {current_year} Viking Roots. All rights reserved.</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""

    email = EmailMultiAlternatives(
        subject,
        message,
        from_email,
        [user.email],
        reply_to=[reply_to_email] if reply_to_email else None,
    )
    email.attach_alternative(html_message, "text/html")
    if logo_path.is_file():
        with logo_path.open("rb") as logo_file:
            logo = MIMEImage(logo_file.read())
        logo.add_header("Content-ID", f"<{logo_content_id}>")
        logo.add_header("Content-Disposition", "inline", filename=logo_path.name)
        email.attach(logo)
    return email.send(fail_silently=True) > 0


def _send_password_reset_email(user: User, token: str) -> bool:
    timeout_seconds = getattr(settings, "PASSWORD_RESET_TIMEOUT", 60 * 60 * 24 * 3)
    timeout_minutes = max(1, timeout_seconds // 60)
    subject = "Your Viking Roots password reset code"
    message = (
        f"Hi {user.username},\n\n"
        "Use this password reset code to choose a new password:\n\n"
        f"{token}\n\n"
        f"This code expires in {timeout_minutes} minutes."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    return send_mail(subject, message, from_email, [user.email], fail_silently=True) > 0


def _generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _send_otp_email(email: str, otp: str) -> bool:
    """Send the OTP to the provided email address."""

    subject = "Your Viking Roots verification code"
    message = f"Your verification code is {otp}. It will expire in {OTP_EXPIRATION_MINUTES} minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    return send_mail(subject, message, from_email, [email], fail_silently=True) > 0


def _get_or_create_user_otp(user: User) -> UserOTP:
    otp_record, _ = UserOTP.objects.get_or_create(
        user=user,
        defaults={
            "otp": _generate_otp(),
            "expires_at": timezone.now() + timedelta(minutes=OTP_EXPIRATION_MINUTES),
        },
    )
    return otp_record


def _refresh_otp_record(otp_record: UserOTP) -> str:
    otp_record.otp = _generate_otp()
    otp_record.expires_at = timezone.now() + timedelta(minutes=OTP_EXPIRATION_MINUTES)
    otp_record.is_verified = False
    otp_record.save(update_fields=['otp', 'expires_at', 'is_verified'])
    return otp_record.otp

@csrf_exempt
def register_new_user(req):
    if req.method == 'POST':
        data = _parse_json_body(req)
        if data is None:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if not username or not email or not password:
            return JsonResponse({'error': 'Username, email, and password are required'}, status=400)

        if password != confirm_password:
            return JsonResponse({'error': 'Passwords do not match'}, status=400)

        existing_email_user = User.objects.filter(email__iexact=email).first()
        if existing_email_user:
            if not existing_email_user.is_active:
                otp_record = _get_or_create_user_otp(existing_email_user)
                otp = _refresh_otp_record(otp_record)
                otp_email_sent = _send_otp_email(existing_email_user.email, otp)

                return JsonResponse({
                    'message': 'Account already exists but is not verified. We sent a new OTP.',
                    'otp_email_sent': otp_email_sent,
                    'requires_otp': True,
                }, status=200)

            return JsonResponse({'error': 'Email already registered'}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already taken'}, status=400)

        candidate_user = User(username=username, email=email)
        try:
            validate_password(password, candidate_user)
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = False
        user.save(update_fields=['is_active'])

        otp_record = _get_or_create_user_otp(user)
        otp = _refresh_otp_record(otp_record)
        otp_email_sent = _send_otp_email(email, otp)

        return JsonResponse({
            'message': 'User registered successfully. Please verify your email.',
            'otp_email_sent': otp_email_sent,
            'requires_otp': True,
        }, status=201)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def login_existing_user(req):
    if req.method == 'POST':
        try:
            data = json.loads(req.body)
            email = data.get('username')  # frontend sends email here
            password = data.get('password')

            try:
                user = User.objects.get(email=email)
                username = user.username
            except User.DoesNotExist:
                return JsonResponse({'error': 'Invalid credentials'}, status=401)

            if not user.is_active:
                return JsonResponse({'error': 'Email is not verified. Please verify your email before logging in.'}, status=403)

            user = authenticate(req, username=username, password=password)
            if user is not None:
                login(req, user)
                # Check if user has completed their profile
                try:
                    profile = UserProfile.objects.get(user=user)
                    profile_completed = profile.profile_completed
                    has_profile_picture = profile.has_profile_picture
                except UserProfile.DoesNotExist:
                    profile_completed = False
                    has_profile_picture = False

                return JsonResponse({
                    'message': 'Login successful',
                    'username': user.username,
                    'email': user.email,
                    'is_staff': user.is_staff,
                    'is_superuser': user.is_superuser,
                    'is_admin': user.is_staff or user.is_superuser,
                    'profile_completed': profile_completed,
                    'has_profile_picture': has_profile_picture,
                })
            else:
                return JsonResponse({'error': 'Invalid credentials'}, status=401)
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)



@csrf_exempt
def logout_user(req):
    logout(req)
    return JsonResponse({'message': 'Logged out'})


@csrf_exempt
def verify_otp(req):
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(req.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    email = data.get('email')
    otp = data.get('otp')

    if not email or not otp:
        return JsonResponse({'error': 'Email and OTP are required'}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    try:
        otp_record = user.otp_record
    except UserOTP.DoesNotExist:
        return JsonResponse({'error': 'OTP not found for user'}, status=404)

    if otp_record.is_verified:
        return JsonResponse({'message': 'Email already verified successfully'}, status=200)

    if otp_record.has_expired():
        return JsonResponse({'error': 'OTP has expired'}, status=400)

    if otp_record.otp != otp:
        return JsonResponse({'error': 'Invalid OTP'}, status=400)

    otp_record.is_verified = True
    otp_record.save(update_fields=['is_verified'])

    user.is_active = True
    user.save(update_fields=['is_active'])

    return JsonResponse({'message': 'Email verified successfully'}, status=200)


@csrf_exempt
def resend_otp(req):
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(req.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    email = data.get('email')
    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    otp_record = _get_or_create_user_otp(user)
    if otp_record.is_verified:
        return JsonResponse({'message': 'Email already verified successfully'}, status=200)

    otp = _refresh_otp_record(otp_record)

    otp_email_sent = _send_otp_email(email, otp)

    return JsonResponse({'message': 'OTP sent successfully', 'otp_email_sent': otp_email_sent}, status=200)


@csrf_exempt
def admin_users(req):
    permission_error = _admin_required(req)
    if permission_error:
        return permission_error

    if req.method == 'GET':
        users = User.objects.all().order_by('id')
        return JsonResponse({'users': [_serialize_user(user) for user in users]}, status=200)

    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    data = _parse_json_body(req)
    if data is None:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()

    if not username or not email:
        return JsonResponse({'error': 'Username and email are required'}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({'error': 'Username already taken'}, status=400)

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({'error': 'Email already registered'}, status=400)

    generated_password = _generate_secure_password()
    user = User.objects.create_user(username=username, email=email, password=generated_password)
    user.first_name = data.get('first_name', '').strip()
    user.last_name = data.get('last_name', '').strip()

    if 'is_active' in data:
        user.is_active = _to_bool(data.get('is_active'))

    if req.user.is_superuser:
        user.is_staff = _to_bool(data.get('is_staff', False))
        user.is_superuser = _to_bool(data.get('is_superuser', False))

    user.save()
    welcome_email_sent = _send_welcome_email(user, generated_password)

    return JsonResponse({
        'message': 'User created successfully',
        'user': _serialize_user(user),
        'welcome_email_sent': welcome_email_sent,
    }, status=201)


@csrf_exempt
def admin_user_detail(req, user_id):
    permission_error = _admin_required(req)
    if permission_error:
        return permission_error

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    if req.method == 'GET':
        return JsonResponse({'user': _serialize_user(user)}, status=200)

    if req.method in ('PUT', 'PATCH'):
        if user.is_superuser and not req.user.is_superuser:
            return JsonResponse({'error': 'Only superusers can edit superuser accounts'}, status=403)

        data = _parse_json_body(req)
        if data is None:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'username' in data:
            username = data.get('username', '').strip()
            if not username:
                return JsonResponse({'error': 'Username is required'}, status=400)
            if User.objects.filter(username=username).exclude(id=user.id).exists():
                return JsonResponse({'error': 'Username already taken'}, status=400)
            user.username = username

        if 'email' in data:
            email = data.get('email', '').strip()
            if not email:
                return JsonResponse({'error': 'Email is required'}, status=400)
            if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
                return JsonResponse({'error': 'Email already registered'}, status=400)
            user.email = email

        if 'first_name' in data:
            user.first_name = data.get('first_name', '').strip()
        if 'last_name' in data:
            user.last_name = data.get('last_name', '').strip()
        if 'is_active' in data:
            if user.id == req.user.id and not _to_bool(data.get('is_active')):
                return JsonResponse({'error': 'You cannot deactivate your own account'}, status=400)
            user.is_active = _to_bool(data.get('is_active'))

        requested_privilege_change = any(field in data for field in ('is_staff', 'is_superuser'))
        if requested_privilege_change:
            if not req.user.is_superuser:
                return JsonResponse({'error': 'Only superusers can change staff or superuser access'}, status=403)

            if user.id == req.user.id and (
                ('is_staff' in data and not _to_bool(data.get('is_staff'))) or
                ('is_superuser' in data and not _to_bool(data.get('is_superuser')))
            ):
                return JsonResponse({'error': 'You cannot remove your own admin access'}, status=400)

            if 'is_staff' in data:
                user.is_staff = _to_bool(data.get('is_staff'))
            if 'is_superuser' in data:
                user.is_superuser = _to_bool(data.get('is_superuser'))

        user.save()
        return JsonResponse({
            'message': 'User updated successfully',
            'user': _serialize_user(user),
        }, status=200)

    if req.method == 'DELETE':
        if user.id == req.user.id:
            return JsonResponse({'error': 'You cannot delete your own account'}, status=400)

        if user.is_superuser and not req.user.is_superuser:
            return JsonResponse({'error': 'Only superusers can delete superuser accounts'}, status=403)

        user.delete()
        return JsonResponse({'message': 'User deleted successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def password_reset_request(req):
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    data = _parse_json_body(req)
    if data is None:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    email = data.get('email', '').strip()
    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)

    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user:
        token = default_token_generator.make_token(user)
        _send_password_reset_email(user, token)

    return JsonResponse({
        'message': 'If an account exists for that email, a password reset code has been sent.',
    }, status=200)


@csrf_exempt
def password_reset_confirm(req):
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    data = _parse_json_body(req)
    if data is None:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    email = data.get('email', '').strip()
    token = data.get('token', '').strip()
    new_password = data.get('new_password', '')

    if not email or not token or not new_password:
        return JsonResponse({'error': 'Email, code, and new password are required'}, status=400)

    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if not user or not default_token_generator.check_token(user, token):
        return JsonResponse({'error': 'Invalid or expired password reset code'}, status=400)

    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

    user.set_password(new_password)
    user.save(update_fields=['password'])

    return JsonResponse({'message': 'Password reset successfully'}, status=200)


@csrf_exempt
def upload_image(req):
    """Handle image upload to S3."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        # Get the uploaded image from request.FILES
        image_file = req.FILES.get('image')
        if not image_file:
            return JsonResponse({'error': 'No image file provided'}, status=400)

        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if image_file.size > max_size:
            return JsonResponse({'error': 'Image file too large. Maximum size is 10MB'}, status=400)

        # Validate file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if image_file.content_type not in allowed_types:
            return JsonResponse({'error': 'Invalid file type. Only JPEG, PNG, GIF, and WebP images are allowed'}, status=400)

        # Get optional metadata
        title = req.POST.get('title', '')
        description = req.POST.get('description', '')

        # Get user if authenticated, otherwise allow anonymous upload
        user = req.user if req.user.is_authenticated else None

        # Create the image record (this will automatically upload to S3)
        uploaded_image = UploadedImage.objects.create(
            user=user,
            image=image_file,
            title=title,
            description=description,
            file_size=image_file.size
        )

        return JsonResponse({
            'message': 'Image uploaded successfully',
            'image': {
                'id': uploaded_image.id,
                'url': uploaded_image.image.url,
                'title': uploaded_image.title,
                'description': uploaded_image.description,
                'file_size': uploaded_image.file_size,
                'uploaded_at': uploaded_image.uploaded_at.isoformat(),
            }
        }, status=201)

    except Exception as e:
        return JsonResponse({'error': f'Upload failed: {str(e)}'}, status=500)


@csrf_exempt
def get_uploaded_images(req):
    """Get list of uploaded images for the current user."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        # Filter by user if authenticated, otherwise return all images
        if req.user.is_authenticated:
            images = UploadedImage.objects.filter(user=req.user)
        else:
            # For anonymous users, return recent public images
            images = UploadedImage.objects.all()[:20]

        images_data = [{
            'id': img.id,
            'url': img.image.url,
            'title': img.title,
            'description': img.description,
            'file_size': img.file_size,
            'uploaded_at': img.uploaded_at.isoformat(),
        } for img in images]

        return JsonResponse({'images': images_data}, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch images: {str(e)}'}, status=500)


@csrf_exempt
def upload_profile_picture(req):
    """Upload or update user's profile picture."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        # Get the uploaded profile picture
        profile_picture = req.FILES.get('profile_picture')
        if not profile_picture:
            return JsonResponse({'error': 'No profile picture provided'}, status=400)

        # Validate file size (max 5MB for profile pictures)
        max_size = 5 * 1024 * 1024  # 5MB
        if profile_picture.size > max_size:
            return JsonResponse({'error': 'Profile picture too large. Maximum size is 5MB'}, status=400)

        # Validate file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if profile_picture.content_type not in allowed_types:
            return JsonResponse({'error': 'Invalid file type. Only JPEG, PNG, and WebP are allowed'}, status=400)

        # Get or create user profile
        profile, created = UserProfile.objects.get_or_create(user=req.user)

        # Get optional profile data
        bio = req.POST.get('bio', profile.bio)
        location = req.POST.get('location', profile.location)
        website = req.POST.get('website', profile.website)

        # Update profile
        profile.profile_picture = profile_picture
        profile.bio = bio
        profile.location = location
        profile.website = website
        profile.profile_completed = True  # Mark profile as completed
        profile.save()

        return JsonResponse({
            'message': 'Profile picture uploaded successfully',
            'profile': {
                'id': profile.id,
                'username': req.user.username,
                'profile_picture_url': profile.profile_picture.url if profile.profile_picture else None,
                'bio': profile.bio,
                'location': profile.location,
                'website': profile.website,
                'profile_completed': profile.profile_completed,
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Upload failed: {str(e)}'}, status=500)


@csrf_exempt
def get_user_profile(req, username=None):
    """Get user profile information."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        # Get profile for specified user or current user
        if username:
            try:
                # Use iexact for case-insensitive lookup
                user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=404)
        else:
            if not req.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            user = req.user

        # Get or create profile
        profile, created = UserProfile.objects.get_or_create(user=user)

        print({
    'profile': {
        'id': profile.id,
        'username': user.username,
        'email': user.email if user == req.user else None,
        'full_name': profile.full_name,
        'profile_picture_url': profile.profile_picture.url if profile.profile_picture else None,
        'cover_photo_url': profile.cover_photo.url if profile.cover_photo else None,
        'bio': profile.bio,
        'location': profile.location,
        'website': profile.website,
        'profile_completed': profile.profile_completed,
        'created_at': profile.created_at.isoformat(),
    }
})

        return JsonResponse({
            'profile': {
                'id': profile.id,
                'username': user.username,
                'email': user.email if user == req.user else None,  # Only show email for own profile
                'full_name': profile.full_name,
                'profile_picture_url': profile.profile_picture.url if profile.profile_picture else None,
                'cover_photo_url': profile.cover_photo.url if profile.cover_photo else None,
                'bio': profile.bio,
                'location': profile.location,
                'website': profile.website,
                'profile_completed': profile.profile_completed,
                'created_at': profile.created_at.isoformat(),
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch profile: {str(e)}'}, status=500)


@csrf_exempt
def update_profile(req):
    """Update user profile information (bio, location, website)."""
    if req.method != 'PUT' and req.method != 'PATCH':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(req.body)

        # Get or create profile
        profile, created = UserProfile.objects.get_or_create(user=req.user)

        # Update fields if provided
        if 'bio' in data:
            profile.bio = data['bio']
        if 'location' in data:
            profile.location = data['location']
        if 'website' in data:
            profile.website = data['website']

        profile.save()

        return JsonResponse({
            'message': 'Profile updated successfully',
            'profile': {
                'id': profile.id,
                'username': req.user.username,
                'profile_picture_url': profile.profile_picture.url if profile.profile_picture else None,
                'bio': profile.bio,
                'location': profile.location,
                'website': profile.website,
                'profile_completed': profile.profile_completed,
            }
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Update failed: {str(e)}'}, status=500)


@csrf_exempt
def check_profile_status(req):
    """Check if user has completed their profile setup."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        profile, created = UserProfile.objects.get_or_create(user=req.user)

        return JsonResponse({
            'profile_completed': profile.profile_completed,
            'has_profile_picture': profile.has_profile_picture,
            'needs_setup': not profile.profile_completed,
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to check profile status: {str(e)}'}, status=500)
