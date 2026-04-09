import json
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser

from .models import PrivacySettings, FaceEnrollment, TagSuggestion
from .services.rekognition import RekognitionService
from community.models import Post

class PrivacySettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings_obj, _ = PrivacySettings.objects.get_or_create(user=request.user)
        return Response({
            'face_tagging_enabled': settings_obj.face_tagging_enabled,
            'tagging_scope': settings_obj.tagging_scope
        })

    def patch(self, request):
        settings_obj, _ = PrivacySettings.objects.get_or_create(user=request.user)
        data = request.data
        
        if 'face_tagging_enabled' in data:
            settings_obj.face_tagging_enabled = data['face_tagging_enabled']
        if 'tagging_scope' in data:
            settings_obj.tagging_scope = data['tagging_scope']
            
        settings_obj.save()
        return Response({'message': 'Privacy settings updated'})

class EnrollFaceView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """
        Expects 1 to 5 images for enrollment.
        """
        images = request.FILES.getlist('images')
        if not images:
            return Response({'error': 'No images provided'}, status=400)
        
        rekognition = RekognitionService()
        rekognition.create_collection()
        
        enrollment, _ = FaceEnrollment.objects.get_or_create(user=request.user)
        new_face_ids = []
        
        for img in images:
            image_bytes = img.read()
            face_records = rekognition.index_faces(request.user.id, image_bytes)
            for record in face_records:
                new_face_ids.append(record['Face']['FaceId'])
        
        if new_face_ids:
            enrollment.is_enrolled = True
            enrollment.face_ids.extend(new_face_ids)
            enrollment.save()
            return Response({
                'message': f'Successfully enrolled {len(new_face_ids)} face(s)',
                'face_count': len(enrollment.face_ids)
            })
        else:
            return Response({'error': 'Could not detect any clear faces in the provided images'}, status=400)

class EnrollmentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        enrollment, _ = FaceEnrollment.objects.get_or_create(user=request.user)
        return Response({
            'is_enrolled': enrollment.is_enrolled,
            'face_count': len(enrollment.face_ids),
            'last_updated': enrollment.last_updated
        })

class DeleteFaceDataView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        enrollment = get_object_or_404(FaceEnrollment, user=request.user)
        rekognition = RekognitionService()
        
        if enrollment.face_ids:
            rekognition.delete_faces(enrollment.face_ids)
            
        enrollment.is_enrolled = False
        enrollment.face_ids = []
        enrollment.save()
        
        # Also disable tagging in privacy settings
        settings_obj, _ = PrivacySettings.objects.get_or_create(user=request.user)
        settings_obj.face_tagging_enabled = False
        settings_obj.save()
        
        return Response({'message': 'Biometric face data deleted successfully'})

@method_decorator(csrf_exempt, name='dispatch')
class LambdaRecognitionWebhook(APIView):
    """
    Webhook for AWS Lambda to send back face recognition results.
    Secured by a shared secret key in the headers.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        auth_key = request.headers.get('X-Lambda-Auth-Key')
        if auth_key != settings.LAMBDA_WEBHOOK_KEY:
            return Response({'error': 'Unauthorized'}, status=401)

        post_id = request.data.get('post_id')
        matches = request.data.get('matches', [])
        
        try:
            post = Post.objects.get(id=post_id)
            uploader = post.author
            
            # Get uploader's friends list
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
                
                try:
                    target_user = User.objects.get(id=int(suggested_user_id))
                    
                    # Privacy & Friendship Filters
                    privacy_settings, _ = PrivacySettings.objects.get_or_create(user=target_user)
                    if not privacy_settings.face_tagging_enabled:
                        continue
                    if target_user.id not in friend_ids:
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
                except (User.DoesNotExist, PrivacySettings.DoesNotExist, ValueError):
                    continue

            return Response({'status': 'success', 'suggestions_created': suggestions_created})
            
        except Post.DoesNotExist:
            return Response({'error': 'Post not found'}, status=404)

class PendingTagsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tags = TagSuggestion.objects.filter(
            suggested_user=request.user,
            status='pending'
        ).select_related('post', 'uploaded_by')
        
        data = [{
            'id': tag.id,
            'post_id': tag.post.id,
            'post_image': tag.post.image.url if tag.post.image else None,
            'uploaded_by': tag.uploaded_by.username,
            'confidence': tag.confidence,
            'created_at': tag.created_at
        } for tag in tags]
        
        return Response({'pending_tags': data})

class ReviewTagView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tag_id):
        action = request.data.get('action') # 'accept' or 'reject'
        tag = get_object_or_404(TagSuggestion, id=tag_id, suggested_user=request.user)
        
        if action == 'accept':
            tag.status = 'accepted'
            # If accepted, we could also add the user to the Post's tagged_users M2M
            tag.post.tagged_users.add(request.user)
        elif action == 'reject':
            tag.status = 'rejected'
        else:
            return Response({'error': 'Invalid action'}, status=400)
            
        tag.reviewed_at = timezone.now()
        tag.save()
        return Response({'message': f'Tag {action}ed successfully'})
