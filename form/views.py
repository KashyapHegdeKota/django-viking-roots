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

from .models import UserOTP, UploadedImage, UserProfile


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
        user.is_active = True  # Email verification disabled
        user.save(update_fields=['is_active'])

        # OTP verification disabled for now
        # otp_record = _get_or_create_user_otp(user)
        # otp = _refresh_otp_record(otp_record)
        # _send_otp_email(email, otp)

        return JsonResponse({'message': 'User registered successfully. You can now login.'}, status=201)
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

            # Email verification disabled for now
            # if not user.is_active:
            #     return JsonResponse({'error': 'Email is not verified'}, status=403)

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
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=404)
        else:
            if not req.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            user = req.user

        # Get or create profile
        profile, created = UserProfile.objects.get_or_create(user=user)

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
