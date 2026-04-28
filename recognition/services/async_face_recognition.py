"""
Asynchronous Face Recognition Processing
Replaces AWS Lambda with Celery tasks for face recognition
"""
import logging
import requests
import os
from typing import Dict, List
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from ..models import PrivacySettings, TagSuggestion
from community.models import Post, FamilyConnection
from .face_recognition_service import FaceRecognitionService

logger = logging.getLogger(__name__)


def process_post_for_face_recognition(post_id: int) -> Dict:
    """
    Process a post image for face recognition and create tag suggestions.
    This function can be called directly or wrapped in a Celery task.
    
    Args:
        post_id: ID of the post to process
        
    Returns:
        Dict with processing results
    """
    try:
        post = Post.objects.get(id=post_id)
        
        if not post.image:
            return {
                'success': False,
                'message': 'No image in post',
                'suggestions_created': 0
            }
        
        # 1. Get image bytes correctly for local or remote storage
        try:
            # Check if we should use local file path or URL
            use_local_path = False
            try:
                # If it's a local file storage, .path will work
                file_path = post.image.path
                if os.path.exists(file_path):
                    use_local_path = True
            except (NotImplementedError, AttributeError, ValueError):
                # S3 storage doesn't support .path
                use_local_path = False

            if use_local_path:
                with open(post.image.path, 'rb') as f:
                    image_bytes = f.read()
            elif post.image.url.startswith('http'):
                # S3 or remote storage
                response = requests.get(post.image.url, timeout=10)
                response.raise_for_status()
                image_bytes = response.content
            else:
                # Fallback for relative URLs
                with post.image.open('rb') as f:
                    image_bytes = f.read()
        except Exception as img_err:
            logger.error(f"Failed to read image for post {post_id}: {img_err}")
            return {
                'success': False,
                'message': f'Failed to read image: {str(img_err)}',
                'suggestions_created': 0
            }
        
        # 2. Use custom face recognition service
        face_service = FaceRecognitionService()
        
        # Get similarity threshold from settings (default 70%)
        threshold = getattr(settings, 'FACE_RECOGNITION_THRESHOLD', 70.0)
        
        matches = face_service.search_faces_in_image(image_bytes, threshold=threshold)
        
        if not matches:
            return {
                'success': True,
                'message': f'No face matches found for post {post_id}',
                'suggestions_created': 0
            }
        
        # 3. Process matches and apply privacy filters
        uploader = post.author
        suggestions_created = 0
        
        # Get uploader's friends list
        friends = FamilyConnection.objects.filter(
            Q(user1=uploader) | Q(user2=uploader),
            status='accepted'
        )
        friend_ids = set()
        for conn in friends:
            friend_ids.add(conn.user1_id if conn.user2_id == uploader.id else conn.user2_id)
        
        # Allow self-tagging
        friend_ids.add(uploader.id)
        
        for match in matches:
            suggested_user_id = match.get('user_id')
            confidence = match.get('confidence', 0)
            
            if not suggested_user_id:
                continue
            
            try:
                target_user = User.objects.get(id=int(suggested_user_id))
                
                # Privacy checks
                privacy_settings, _ = PrivacySettings.objects.get_or_create(user=target_user)
                
                if not privacy_settings.face_tagging_enabled:
                    logger.info(f"Skip: User {target_user.username} has tagging disabled")
                    continue
                
                # Check tagging scope
                if privacy_settings.tagging_scope == 'friends_only':
                    if target_user.id not in friend_ids:
                        logger.info(f"Skip: User {target_user.username} is not friends with uploader and scope is friends_only")
                        continue
                elif privacy_settings.tagging_scope == 'nobody':
                    if target_user.id != uploader.id:
                        logger.info(f"Skip: User {target_user.username} tagging scope is nobody")
                        continue
                
                # Create tag suggestion
                TagSuggestion.objects.get_or_create(
                    post=post,
                    suggested_user=target_user,
                    defaults={
                        'uploaded_by': uploader,
                        'aws_face_id': match.get('face_id', ''),
                        'confidence': confidence,
                        'bounding_box': match.get('bounding_box', {}),
                        'status': 'pending'
                    }
                )
                suggestions_created += 1
                
            except (User.DoesNotExist, ValueError) as e:
                logger.warning(f"Error processing match for user {suggested_user_id}: {e}")
                continue
        
        logger.info(f"Created {suggestions_created} tag suggestions for post {post_id}")
        
        return {
            'success': True,
            'message': f'Created {suggestions_created} tag suggestions',
            'suggestions_created': suggestions_created
        }
        
    except Post.DoesNotExist:
        logger.error(f"Post {post_id} not found")
        return {
            'success': False,
            'message': f'Post {post_id} not found',
            'suggestions_created': 0
        }
    except Exception as e:
        logger.error(f"Error processing post {post_id}: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'suggestions_created': 0
        }
