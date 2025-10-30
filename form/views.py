import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import UserOTP


OTP_EXPIRATION_MINUTES = 10


def _generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _send_otp_email(email: str, otp: str) -> None:
    """Send the OTP to the provided email address."""

    subject = "Your Viking Roots verification code"
    message = f"Your verification code is {otp}. It will expire in {OTP_EXPIRATION_MINUTES} minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    send_mail(subject, message, from_email, [email], fail_silently=True)


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
        data = json.loads(req.body)
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if password != confirm_password:
            return JsonResponse({'error': 'Passwords do not match'}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already taken'}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already registered'}, status=400)

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = False
        user.save(update_fields=['is_active'])

        otp_record = _get_or_create_user_otp(user)
        otp = _refresh_otp_record(otp_record)

        _send_otp_email(email, otp)

        return JsonResponse({'message': 'User registered successfully. OTP sent to email.'}, status=201)
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
                return JsonResponse({'error': 'Email is not verified'}, status=403)

            user = authenticate(req, username=username, password=password)
            if user is not None:
                login(req, user)
                return JsonResponse({'message': 'Login successful'})
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

    _send_otp_email(email, otp)

    return JsonResponse({'message': 'OTP sent successfully'}, status=200)
