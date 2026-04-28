"""
High-level Face Recognition Service
Handles enrollment, matching, and database operations for custom face embeddings
"""
import logging
from typing import List, Dict, Optional
from django.contrib.auth.models import User
from django.conf import settings
import numpy as np

from .face_embedding import FaceEmbeddingService
from ..models import FaceEnrollment

logger = logging.getLogger(__name__)


class FaceRecognitionService:
    """
    High-level service for face recognition operations.
    Manages the interaction between face embeddings and database storage.
    """
    
    def __init__(self):
        # Get model configuration from settings or use defaults
        model_name = getattr(settings, 'FACE_RECOGNITION_MODEL', 'Facenet512')
        detector_backend = getattr(settings, 'FACE_DETECTOR_BACKEND', 'retinaface')
        
        self.embedding_service = FaceEmbeddingService(
            model_name=model_name,
            detector_backend=detector_backend
        )
        self.model_name = model_name
        logger.info(f"Initialized FaceRecognitionService with model={model_name}")
    
    def enroll_user_faces(self, user: User, image_bytes_list: List[bytes]) -> Dict:
        """
        Enroll a user's face by processing multiple images and storing embeddings.
        
        Args:
            user: User object
            image_bytes_list: List of image bytes (5 images recommended)
            
        Returns:
            Dict with success status, message, and face count
        """
        try:
            enrollment, _ = FaceEnrollment.objects.get_or_create(user=user)
            
            new_embeddings = []
            faces_processed = 0
            
            for image_bytes in image_bytes_list:
                # Extract embeddings from each image
                faces = self.embedding_service.extract_embeddings(image_bytes)
                
                for face in faces:
                    # Convert embedding to base64 for storage
                    embedding_b64 = self.embedding_service.embedding_to_base64(face['embedding'])
                    new_embeddings.append(embedding_b64)
                    faces_processed += 1
            
            if not new_embeddings:
                return {
                    'success': False,
                    'message': 'Could not detect any clear faces in the provided images',
                    'face_count': 0
                }
            
            # Store embeddings in database
            enrollment.embeddings.extend(new_embeddings)
            enrollment.embedding_model = self.model_name
            enrollment.is_enrolled = True
            enrollment.save()
            
            logger.info(f"Enrolled {faces_processed} face(s) for user {user.username}")
            
            return {
                'success': True,
                'message': f'Successfully enrolled {faces_processed} face(s)',
                'face_count': len(enrollment.embeddings)
            }
            
        except Exception as e:
            logger.error(f"Error enrolling user faces: {e}")
            return {
                'success': False,
                'message': f'Error during enrollment: {str(e)}',
                'face_count': 0
            }
    
    def delete_user_enrollment(self, user: User) -> bool:
        """
        Delete all face data for a user.
        
        Args:
            user: User object
            
        Returns:
            True if successful
        """
        try:
            enrollment = FaceEnrollment.objects.get(user=user)
            enrollment.embeddings = []
            enrollment.face_ids = []  # Clear legacy data too
            enrollment.is_enrolled = False
            enrollment.save()
            
            logger.info(f"Deleted face enrollment for user {user.username}")
            return True
            
        except FaceEnrollment.DoesNotExist:
            logger.warning(f"No enrollment found for user {user.username}")
            return True
        except Exception as e:
            logger.error(f"Error deleting enrollment: {e}")
            return False
    
    def get_enrollment_status(self, user: User) -> Dict:
        """
        Get enrollment status for a user.
        
        Args:
            user: User object
            
        Returns:
            Dict with enrollment info
        """
        try:
            enrollment = FaceEnrollment.objects.get(user=user)
            return {
                'is_enrolled': enrollment.is_enrolled,
                'face_count': len(enrollment.embeddings),
                'model': enrollment.embedding_model,
                'last_updated': enrollment.last_updated.isoformat() if enrollment.last_updated else None
            }
        except FaceEnrollment.DoesNotExist:
            return {
                'is_enrolled': False,
                'face_count': 0,
                'model': None,
                'last_updated': None
            }
    
    def load_all_enrolled_embeddings(self) -> List[tuple]:
        """
        Load all enrolled user embeddings from database.
        
        Returns:
            List of (user_id, embedding) tuples
        """
        enrolled_users = FaceEnrollment.objects.filter(
            is_enrolled=True,
            embeddings__isnull=False
        ).exclude(embeddings=[])
        
        all_embeddings = []
        
        for enrollment in enrolled_users:
            user_id = enrollment.user.id
            
            # Convert each stored embedding back to numpy array
            for embedding_b64 in enrollment.embeddings:
                try:
                    embedding = self.embedding_service.base64_to_embedding(embedding_b64)
                    all_embeddings.append((user_id, embedding))
                except Exception as e:
                    logger.error(f"Error loading embedding for user {user_id}: {e}")
                    continue
        
        logger.info(f"Loaded {len(all_embeddings)} embeddings from {enrolled_users.count()} users")
        return all_embeddings
    
    def search_faces_in_image(
        self, 
        image_bytes: bytes, 
        threshold: float = 70.0
    ) -> List[Dict]:
        """
        Search for enrolled faces in an image.
        
        Args:
            image_bytes: Raw image bytes
            threshold: Minimum similarity score (0-100)
            
        Returns:
            List of matches with user_id, confidence (similarity), and bounding_box
        """
        try:
            # Load all enrolled embeddings
            stored_embeddings = self.load_all_enrolled_embeddings()
            
            if not stored_embeddings:
                logger.info("No enrolled users to match against")
                return []
            
            # Search for matches
            matches = self.embedding_service.search_faces_in_image(
                image_bytes=image_bytes,
                stored_embeddings=stored_embeddings,
                threshold=threshold
            )
            
            # Format matches to match the expected structure
            formatted_matches = []
            for match in matches:
                formatted_matches.append({
                    'user_id': match['user_id'],
                    'confidence': match['similarity'],  # Rename similarity to confidence
                    'bounding_box': match.get('bounding_box', {}),
                    'face_id': f"custom-{match['user_id']}-{int(match['similarity'])}"  # Generate a pseudo face_id
                })
            
            logger.info(f"Found {len(formatted_matches)} face match(es)")
            return formatted_matches
            
        except Exception as e:
            logger.error(f"Error searching faces: {e}")
            return []
