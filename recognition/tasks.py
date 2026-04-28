from celery import shared_task
from django.contrib.auth.models import User
from community.models import Post, FamilyConnection
from .models import PrivacySettings, TagSuggestion
from .services.rekognition import RekognitionService
import requests
from django.db.models import Q

@shared_task
def process_photo_for_tags(post_id):
    """
    Background task to detect faces in a post and create tag suggestions.
    """
    try:
        post = Post.objects.get(id=post_id)
        if not post.image:
            return "No image in post"

        # 1. Get image bytes
        # If on S3, we fetch it. If local (DEBUG), we read from disk.
        if post.image.url.startswith('http'):
            response = requests.get(post.image.url)
            image_bytes = response.content
        else:
            with post.image.open('rb') as f:
                image_bytes = f.read()

        # 2. Call AWS Rekognition
        rekognition = RekognitionService()
        matches = rekognition.search_faces_by_image(image_bytes)

        if not matches:
            return f"No face matches found for post {post_id}"

        # 3. Process matches and apply privacy filters
        uploader = post.author
        suggestions_created = 0

        # Get uploader's friends list (confirmed connections)
        friends = FamilyConnection.objects.filter(
            Q(user1=uploader) | Q(user2=uploader),
            status='accepted'
        )
        friend_ids = set()
        for conn in friends:
            friend_ids.add(conn.user1_id if conn.user2_id == uploader.id else conn.user2_id)

        for match in matches:
            face = match['Face']
            suggested_user_id = face.get('ExternalImageId')
            confidence = match.get('Similarity', 0)

            if not suggested_user_id:
                continue

            try:
                target_user = User.objects.get(id=int(suggested_user_id))
                
                # PRIVACY RULES:
                # 1. Target must have tagging enabled
                # 2. Target must be a friend of the uploader
                
                settings = PrivacySettings.objects.get(user=target_user)
                if not settings.face_tagging_enabled:
                    continue
                
                if target_user.id not in friend_ids:
                    continue

                # Create pending suggestion
                TagSuggestion.objects.get_or_create(
                    post=post,
                    suggested_user=target_user,
                    defaults={
                        'uploaded_by': uploader,
                        'aws_face_id': face['FaceId'],
                        'confidence': confidence,
                        'bounding_box': face['BoundingBox'],
                        'status': 'pending'
                    }
                )
                suggestions_created += 1

            except (User.DoesNotExist, PrivacySettings.DoesNotExist, ValueError):
                continue

        return f"Created {suggestions_created} tag suggestions for post {post_id}"

    except Post.DoesNotExist:
        return f"Post {post_id} not found"
    except Exception as e:
        return f"Error processing post {post_id}: {str(e)}"
