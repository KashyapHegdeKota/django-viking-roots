import json
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings

from .models import PrivacySettings, FaceEnrollment, TagSuggestion
from .services.rekognition import RekognitionService
from community.models import Post

def get_user_for_request(request):
    """Get authenticated user or create test user"""
    if request.user.is_authenticated:
        return request.user
    else:
        user, _ = User.objects.get_or_create(username='testuser')
        return user

@csrf_exempt
def privacy_settings_view(request):
    try:
        user = get_user_for_request(request)
        settings_obj, _ = PrivacySettings.objects.get_or_create(user=user)

        if request.method == 'GET':
            return JsonResponse({
                'face_tagging_enabled': settings_obj.face_tagging_enabled,
                'tagging_scope': settings_obj.tagging_scope
            })

        elif request.method == 'PATCH':
            data = json.loads(request.body)
            if 'face_tagging_enabled' in data:
                settings_obj.face_tagging_enabled = data['face_tagging_enabled']
            if 'tagging_scope' in data:
                settings_obj.tagging_scope = data['tagging_scope']
            settings_obj.save()
            return JsonResponse({'message': 'Privacy settings updated'})
            
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def enroll_face_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        user = get_user_for_request(request)
        images = request.FILES.getlist('images')
        
        if not images:
            return JsonResponse({'error': 'No images provided'}, status=400)
            
        rekognition = RekognitionService()
        rekognition.create_collection()
        
        enrollment, _ = FaceEnrollment.objects.get_or_create(user=user)
        new_face_ids = []
        
        for img in images:
            image_bytes = img.read()
            face_records = rekognition.index_faces(user.id, image_bytes)
            for record in face_records:
                new_face_ids.append(record['Face']['FaceId'])
                
        if new_face_ids:
            enrollment.is_enrolled = True
            enrollment.face_ids.extend(new_face_ids)
            enrollment.save()
            return JsonResponse({
                'message': f'Successfully enrolled {len(new_face_ids)} face(s)',
                'face_count': len(enrollment.face_ids)
            })
        else:
            return JsonResponse({'error': 'Could not detect any clear faces in the provided images'}, status=400)
            
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def enrollment_status_view(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        user = get_user_for_request(request)
        enrollment, _ = FaceEnrollment.objects.get_or_create(user=user)
        return JsonResponse({
            'is_enrolled': enrollment.is_enrolled,
            'face_count': len(enrollment.face_ids),
            'last_updated': enrollment.last_updated.isoformat() if enrollment.last_updated else None
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def delete_face_data_view(request):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        user = get_user_for_request(request)
        enrollment = get_object_or_404(FaceEnrollment, user=user)
        rekognition = RekognitionService()
        
        if enrollment.face_ids:
            rekognition.delete_faces(enrollment.face_ids)
            
        enrollment.is_enrolled = False
        enrollment.face_ids = []
        enrollment.save()
        
        settings_obj, _ = PrivacySettings.objects.get_or_create(user=user)
        settings_obj.face_tagging_enabled = False
        settings_obj.save()
        
        return JsonResponse({'message': 'Biometric face data deleted successfully'})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def pending_tags_view(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        user = get_user_for_request(request)
        tags = TagSuggestion.objects.filter(
            suggested_user=user,
            status='pending'
        ).select_related('post', 'uploaded_by')
        
        data = [{
            'id': tag.id,
            'post_id': tag.post.id,
            'post_image': tag.post.image.url if tag.post.image else None,
            'uploaded_by': tag.uploaded_by.username,
            'confidence': tag.confidence,
            'created_at': tag.created_at.isoformat()
        } for tag in tags]
        
        return JsonResponse({'pending_tags': data})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def review_tag_view(request, tag_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        user = get_user_for_request(request)
        data = json.loads(request.body)
        action = data.get('action')
        
        tag = get_object_or_404(TagSuggestion, id=tag_id, suggested_user=user)
        
        if action == 'accept':
            tag.status = 'accepted'
            tag.post.tagged_users.add(user)
        elif action == 'reject':
            tag.status = 'rejected'
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
            
        tag.reviewed_at = timezone.now()
        tag.save()
        return JsonResponse({'message': f'Tag {action}ed successfully'})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def lambda_recognition_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        auth_key = request.headers.get('X-Lambda-Auth-Key')
        if auth_key != settings.LAMBDA_WEBHOOK_KEY:
            print(f"WEBHOOK AUTH FAILED: Expected {settings.LAMBDA_WEBHOOK_KEY}, got {auth_key}")
            return JsonResponse({'error': 'Unauthorized'}, status=401)
            
        data = json.loads(request.body)
        post_id = data.get('post_id')
        matches = data.get('matches', [])
        
        print(f"WEBHOOK RECEIVED: post_id={post_id}, matches_count={len(matches)}")

        post = Post.objects.get(id=post_id)
        uploader = post.author
        
        from django.db.models import Q
        from community.models import FamilyConnection
        friends = FamilyConnection.objects.filter(
            Q(user1=uploader) | Q(user2=uploader),
            status='accepted'
        )
        friend_ids = set()
        for conn in friends:
            friend_ids.add(conn.user1_id if conn.user2_id == uploader.id else conn.user2_id)

        suggestions_created = 0
        for match in matches:
            suggested_user_id = match.get('user_id')
            confidence = match.get('confidence')
            
            if not suggested_user_id:
                continue

            try:
                target_user = User.objects.get(id=int(suggested_user_id))
                privacy_settings, _ = PrivacySettings.objects.get_or_create(user=target_user)
                
                if not privacy_settings.face_tagging_enabled:
                    print(f"SKIP: User {target_user.username} has tagging disabled")
                    continue
                if target_user.id not in friend_ids:
                    print(f"SKIP: User {target_user.username} is not friends with uploader")
                    continue

                TagSuggestion.objects.get_or_create(
                    post=post,
                    suggested_user=target_user,
                    defaults={
                        'uploaded_by': uploader,
                        'aws_face_id': match.get('face_id'),
                        'confidence': confidence,
                        'bounding_box': match.get('bounding_box'),
                        'status': 'pending'
                    }
                )
                suggestions_created += 1
            except Exception as user_err:
                print(f"USER ERROR in match loop: {user_err}")
                continue

        return JsonResponse({'status': 'success', 'suggestions_created': suggestions_created})
        
    except Post.DoesNotExist:
        print(f"WEBHOOK ERROR: Post {post_id} not found")
        return JsonResponse({'error': 'Post not found'}, status=404)
    except Exception as e:
        print(f"WEBHOOK CRITICAL ERROR: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
