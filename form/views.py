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

from .models import UserOTP, UploadedImage, UserProfile, Group, GroupMembership, GroupPost, GroupInvitation


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


# ==================== GROUP VIEWS ====================

@csrf_exempt
def create_group(req):
    """Create a new group."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        # Check if profile is completed
        profile = UserProfile.objects.get(user=req.user)
        if not profile.profile_completed:
            return JsonResponse({'error': 'Please complete your profile before creating a group'}, status=403)

        # Handle multipart/form-data (for image upload) or JSON
        if req.content_type and 'multipart/form-data' in req.content_type:
            name = req.POST.get('name')
            description = req.POST.get('description', '')
            is_public = req.POST.get('is_public', 'false').lower() == 'true'
            image = req.FILES.get('image')
        else:
            data = json.loads(req.body)
            name = data.get('name')
            description = data.get('description', '')
            is_public = data.get('is_public', False)
            image = None

        if not name:
            return JsonResponse({'error': 'Group name is required'}, status=400)

        # Validate name length
        if len(name) > 100:
            return JsonResponse({'error': 'Group name too long (max 100 characters)'}, status=400)

        # Create the group
        group = Group.objects.create(
            name=name,
            description=description,
            creator=req.user,
            is_public=is_public,
            image=image if image else None
        )

        # Automatically add creator as admin
        GroupMembership.objects.create(
            group=group,
            user=req.user,
            role='admin'
        )

        return JsonResponse({
            'message': 'Group created successfully',
            'group': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'creator': group.creator.username,
                'is_public': group.is_public,
                'image_url': group.image.url if group.image else None,
                'member_count': group.member_count,
                'created_at': group.created_at.isoformat(),
            }
        }, status=201)

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User profile not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Failed to create group: {str(e)}'}, status=500)


@csrf_exempt
def list_user_groups(req, username):
    """List all groups that a specific user is a member of."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        # Get the user whose groups we want to see
        try:
            profile_user = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Get groups the profile user is a member of
        user_groups = Group.objects.filter(memberships__user=profile_user).distinct()

        groups_data = []
        for group in user_groups:
            # Check if the requesting user is a member (for displaying role)
            is_member = False
            user_role = None
            if req.user.is_authenticated:
                membership = GroupMembership.objects.filter(group=group, user=req.user).first()
                if membership:
                    is_member = True
                    user_role = membership.role

            groups_data.append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'creator': group.creator.username,
                'is_public': group.is_public,
                'image_url': group.image.url if group.image else None,
                'member_count': group.member_count,
                'created_at': group.created_at.isoformat(),
                'is_member': is_member,
                'user_role': user_role,
            })

        return JsonResponse({
            'groups': groups_data,
            'profile_username': username,
            'is_own_profile': req.user.is_authenticated and req.user.username == username
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch groups: {str(e)}'}, status=500)


@csrf_exempt
def get_group_detail(req, group_id):
    """Get detailed information about a specific group."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        group = Group.objects.get(id=group_id)

        # Check if user has access to view this group
        is_member = False
        user_role = None
        if req.user.is_authenticated:
            membership = GroupMembership.objects.filter(group=group, user=req.user).first()
            if membership:
                is_member = True
                user_role = membership.role

        # Only members can view private groups
        if not group.is_public and not is_member:
            return JsonResponse({'error': 'You do not have permission to view this group'}, status=403)

        # Get member list
        members = GroupMembership.objects.filter(group=group).select_related('user')
        members_data = [{
            'id': m.user.id,
            'username': m.user.username,
            'role': m.role,
            'joined_at': m.joined_at.isoformat(),
        } for m in members]

        return JsonResponse({
            'group': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'creator': group.creator.username,
                'is_public': group.is_public,
                'image_url': group.image.url if group.image else None,
                'member_count': group.member_count,
                'admin_count': group.admin_count,
                'created_at': group.created_at.isoformat(),
                'is_member': is_member,
                'user_role': user_role,
                'members': members_data,
            }
        }, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch group: {str(e)}'}, status=500)


@csrf_exempt
def update_group(req, group_id):
    """Update group information (admin only)."""
    if req.method != 'PUT' and req.method != 'PATCH':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        group = Group.objects.get(id=group_id)

        # Check if user is an admin
        membership = GroupMembership.objects.filter(group=group, user=req.user, role='admin').first()
        if not membership:
            return JsonResponse({'error': 'Only group admins can update the group'}, status=403)

        data = json.loads(req.body)

        # Update fields if provided
        if 'name' in data:
            group.name = data['name']
        if 'description' in data:
            group.description = data['description']
        if 'is_public' in data:
            group.is_public = data['is_public']

        group.save()

        return JsonResponse({
            'message': 'Group updated successfully',
            'group': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'is_public': group.is_public,
                'updated_at': group.updated_at.isoformat(),
            }
        }, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Failed to update group: {str(e)}'}, status=500)


@csrf_exempt
def delete_group(req, group_id):
    """Delete a group (creator only)."""
    if req.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        group = Group.objects.get(id=group_id)

        # Only the creator can delete the group
        if group.creator != req.user:
            return JsonResponse({'error': 'Only the group creator can delete the group'}, status=403)

        group.delete()

        return JsonResponse({'message': 'Group deleted successfully'}, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to delete group: {str(e)}'}, status=500)


@csrf_exempt
def add_group_member(req, group_id):
    """Send an invitation to join the group (admin only)."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(req.body)
        username = data.get('username')

        if not username:
            return JsonResponse({'error': 'Username is required'}, status=400)

        group = Group.objects.get(id=group_id)

        # Check if requester is an admin
        requester_membership = GroupMembership.objects.filter(group=group, user=req.user, role='admin').first()
        if not requester_membership:
            return JsonResponse({'error': 'Only group admins can send invitations'}, status=403)

        # Get the user to invite
        try:
            user_to_invite = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Check if user is already a member
        if GroupMembership.objects.filter(group=group, user=user_to_invite).exists():
            return JsonResponse({'error': 'User is already a member of this group'}, status=400)

        # Check if there's already a pending invitation
        existing_invitation = GroupInvitation.objects.filter(
            group=group, 
            invited_user=user_to_invite, 
            status='pending'
        ).first()
        
        if existing_invitation:
            return JsonResponse({'error': 'An invitation has already been sent to this user'}, status=400)

        # Create the invitation
        invitation = GroupInvitation.objects.create(
            group=group,
            invited_user=user_to_invite,
            invited_by=req.user,
            status='pending'
        )

        return JsonResponse({
            'message': 'Invitation sent successfully',
            'invitation': {
                'id': invitation.id,
                'invited_user': user_to_invite.username,
                'invited_by': req.user.username,
                'status': invitation.status,
                'created_at': invitation.created_at.isoformat(),
            }
        }, status=201)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Failed to send invitation: {str(e)}'}, status=500)


@csrf_exempt
def remove_group_member(req, group_id):
    """Remove a member from the group (admin only)."""
    if req.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(req.body)
        username = data.get('username')

        if not username:
            return JsonResponse({'error': 'Username is required'}, status=400)

        group = Group.objects.get(id=group_id)

        # Check if requester is an admin
        requester_membership = GroupMembership.objects.filter(group=group, user=req.user, role='admin').first()
        if not requester_membership:
            return JsonResponse({'error': 'Only group admins can remove members'}, status=403)

        # Get the user to remove
        try:
            user_to_remove = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Cannot remove the group creator
        if user_to_remove == group.creator:
            return JsonResponse({'error': 'Cannot remove the group creator'}, status=403)

        # Remove the membership
        membership = GroupMembership.objects.filter(group=group, user=user_to_remove).first()
        if not membership:
            return JsonResponse({'error': 'User is not a member of this group'}, status=400)

        membership.delete()

        return JsonResponse({'message': 'Member removed successfully'}, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Failed to remove member: {str(e)}'}, status=500)


@csrf_exempt
def assign_admin_role(req, group_id):
    """Assign or revoke admin role for a member (admin only)."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(req.body)
        username = data.get('username')
        make_admin = data.get('make_admin', True)  # True to promote, False to demote

        if not username:
            return JsonResponse({'error': 'Username is required'}, status=400)

        group = Group.objects.get(id=group_id)

        # Check if requester is an admin
        requester_membership = GroupMembership.objects.filter(group=group, user=req.user, role='admin').first()
        if not requester_membership:
            return JsonResponse({'error': 'Only group admins can assign roles'}, status=403)

        # Get the user to modify
        try:
            user_to_modify = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Cannot modify the creator's role
        if user_to_modify == group.creator:
            return JsonResponse({'error': 'Cannot modify the group creator\'s role'}, status=403)

        # Get the membership
        membership = GroupMembership.objects.filter(group=group, user=user_to_modify).first()
        if not membership:
            return JsonResponse({'error': 'User is not a member of this group'}, status=400)

        # Update role
        new_role = 'admin' if make_admin else 'member'
        membership.role = new_role
        membership.save()

        return JsonResponse({
            'message': f'User role updated to {new_role}',
            'membership': {
                'user': user_to_modify.username,
                'role': membership.role,
            }
        }, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Failed to update role: {str(e)}'}, status=500)


@csrf_exempt
def create_group_post(req, group_id):
    """Create a post in a group (members only)."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        group = Group.objects.get(id=group_id)

        # Check if user is a member
        membership = GroupMembership.objects.filter(group=group, user=req.user).first()
        if not membership:
            return JsonResponse({'error': 'Only group members can post'}, status=403)

        # Handle multipart/form-data (for image upload) or JSON
        if req.content_type and 'multipart/form-data' in req.content_type:
            content = req.POST.get('content')
            image = req.FILES.get('image')
        else:
            data = json.loads(req.body)
            content = data.get('content')
            image = None

        if not content:
            return JsonResponse({'error': 'Post content is required'}, status=400)

        # Create the post
        post = GroupPost.objects.create(
            group=group,
            author=req.user,
            content=content,
            image=image if image else None
        )

        return JsonResponse({
            'message': 'Post created successfully',
            'post': {
                'id': post.id,
                'content': post.content,
                'author': post.author.username,
                'image_url': post.image.url if post.image else None,
                'created_at': post.created_at.isoformat(),
            }
        }, status=201)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Failed to create post: {str(e)}'}, status=500)


@csrf_exempt
def get_group_posts(req, group_id):
    """Get all posts in a group (members only)."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        group = Group.objects.get(id=group_id)

        # Check if user is a member (or if group is public)
        if not group.is_public:
            if not req.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)

            membership = GroupMembership.objects.filter(group=group, user=req.user).first()
            if not membership:
                return JsonResponse({'error': 'Only group members can view posts'}, status=403)

        # Get all posts
        posts = GroupPost.objects.filter(group=group).select_related('author')
        posts_data = [{
            'id': post.id,
            'content': post.content,
            'author': post.author.username,
            'image_url': post.image.url if post.image else None,
            'created_at': post.created_at.isoformat(),
            'updated_at': post.updated_at.isoformat(),
            'is_edited': post.is_edited,
        } for post in posts]

        return JsonResponse({'posts': posts_data}, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch posts: {str(e)}'}, status=500)


@csrf_exempt
def delete_group_post(req, group_id, post_id):
    """Delete a post from a group (post author or admin only)."""
    if req.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        group = Group.objects.get(id=group_id)
        post = GroupPost.objects.get(id=post_id, group=group)

        # Check if user is the author or an admin
        membership = GroupMembership.objects.filter(group=group, user=req.user).first()
        if not membership:
            return JsonResponse({'error': 'You are not a member of this group'}, status=403)

        if post.author != req.user and membership.role != 'admin':
            return JsonResponse({'error': 'Only the post author or group admins can delete this post'}, status=403)

        post.delete()

        return JsonResponse({'message': 'Post deleted successfully'}, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except GroupPost.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to delete post: {str(e)}'}, status=500)


# ==================== GROUP INVITATION VIEWS ====================

@csrf_exempt
def get_user_invites(req):
    """Get all pending group invitations for the current user."""
    if req.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        # Get all pending invitations for the user
        invitations = GroupInvitation.objects.filter(
            invited_user=req.user,
            status='pending'
        ).select_related('group', 'invited_by')

        invitations_data = [{
            'id': inv.id,
            'group': {
                'id': inv.group.id,
                'name': inv.group.name,
                'description': inv.group.description,
                'image_url': inv.group.image.url if inv.group.image else None,
                'member_count': inv.group.member_count,
            },
            'invited_by': {
                'username': inv.invited_by.username,
            },
            'status': inv.status,
            'created_at': inv.created_at.isoformat(),
        } for inv in invitations]

        return JsonResponse({
            'invitations': invitations_data,
            'count': len(invitations_data)
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch invitations: {str(e)}'}, status=500)


@csrf_exempt
def accept_group_invitation(req, group_id):
    """Accept a pending group invitation."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        group = Group.objects.get(id=group_id)

        # Get the pending invitation
        invitation = GroupInvitation.objects.filter(
            group=group,
            invited_user=req.user,
            status='pending'
        ).first()

        if not invitation:
            return JsonResponse({'error': 'No pending invitation found for this group'}, status=404)

        # Check if user is already a member (edge case)
        if GroupMembership.objects.filter(group=group, user=req.user).exists():
            # Update invitation status anyway
            invitation.status = 'accepted'
            invitation.save()
            return JsonResponse({'error': 'You are already a member of this group'}, status=400)

        # Create the membership
        membership = GroupMembership.objects.create(
            group=group,
            user=req.user,
            role='member'
        )

        # Update invitation status
        invitation.status = 'accepted'
        invitation.save()

        return JsonResponse({
            'message': 'Invitation accepted successfully',
            'membership': {
                'group': group.name,
                'role': membership.role,
                'joined_at': membership.joined_at.isoformat(),
            }
        }, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to accept invitation: {str(e)}'}, status=500)


@csrf_exempt
def reject_group_invitation(req, group_id):
    """Reject a pending group invitation."""
    if req.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not req.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        group = Group.objects.get(id=group_id)

        # Get the pending invitation
        invitation = GroupInvitation.objects.filter(
            group=group,
            invited_user=req.user,
            status='pending'
        ).first()

        if not invitation:
            return JsonResponse({'error': 'No pending invitation found for this group'}, status=404)

        # Update invitation status
        invitation.status = 'rejected'
        invitation.save()

        return JsonResponse({
            'message': 'Invitation rejected successfully'
        }, status=200)

    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Failed to reject invitation: {str(e)}'}, status=500)

