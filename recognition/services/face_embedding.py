"""
Custom Face Embedding Service using DeepFace
Replaces AWS Rekognition with open-source face recognition
"""
import numpy as np
from deepface import DeepFace
from PIL import Image
import io
import logging
from typing import List, Dict, Tuple, Optional
import base64

logger = logging.getLogger(__name__)


class FaceEmbeddingService:
    """
    Service for generating and comparing facial embeddings using DeepFace.
    Supports multiple models: VGG-Face, Facenet, Facenet512, OpenFace, DeepFace, ArcFace, Dlib, SFace
    """
    
    def __init__(self, model_name='Facenet512', detector_backend='retinaface'):
        """
        Initialize the face embedding service.
        
        Args:
            model_name: Model to use for embeddings. Options:
                - 'VGG-Face': 2622 dimensional
                - 'Facenet': 128 dimensional
                - 'Facenet512': 512 dimensional (recommended for accuracy)
                - 'OpenFace': 128 dimensional
                - 'ArcFace': 512 dimensional (recommended for accuracy)
                - 'Dlib': 128 dimensional
            detector_backend: Face detection backend. Options:
                - 'retinaface' (recommended, most accurate)
                - 'mtcnn'
                - 'opencv'
                - 'ssd'
        """
        self.model_name = model_name
        self.detector_backend = detector_backend
        logger.info(f"Initialized FaceEmbeddingService with model={model_name}, detector={detector_backend}")
    
    def extract_embeddings(self, image_bytes: bytes) -> List[Dict]:
        """
        Extract face embeddings from an image.
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            List of dictionaries containing:
                - embedding: numpy array of face embedding
                - facial_area: dict with x, y, w, h coordinates
                - confidence: detection confidence score
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save to temporary bytes buffer for DeepFace
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG')
            img_buffer.seek(0)
            
            # Extract embeddings using DeepFace
            # enforce_detection=False allows processing even if face detection is uncertain
            embeddings_list = DeepFace.represent(
                img_path=img_buffer,
                model_name=self.model_name,
                detector_backend=self.detector_backend,
                enforce_detection=False,  # Changed to False to be more lenient
                align=True  # Align faces for better accuracy
            )
            
            results = []
            for embedding_data in embeddings_list:
                # Convert embedding to numpy array
                embedding = np.array(embedding_data['embedding'])
                
                # Get facial area (bounding box)
                facial_area = embedding_data.get('facial_area', {})
                
                # Calculate confidence (if available)
                confidence = embedding_data.get('face_confidence', 1.0)
                
                results.append({
                    'embedding': embedding,
                    'facial_area': facial_area,
                    'confidence': confidence
                })
            
            logger.info(f"Extracted {len(results)} face embedding(s) from image")
            return results
            
        except ValueError as e:
            # No face detected
            logger.warning(f"No face detected in image: {e}")
            return []
        except Exception as e:
            logger.error(f"Error extracting embeddings: {e}")
            return []
    
    def compare_embeddings(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compare two face embeddings and return similarity score.
        
        Args:
            embedding1: First face embedding
            embedding2: Second face embedding
            
        Returns:
            Similarity score (0-100, higher is more similar)
        """
        try:
            # Normalize embeddings
            embedding1 = embedding1 / np.linalg.norm(embedding1)
            embedding2 = embedding2 / np.linalg.norm(embedding2)
            
            # Calculate cosine similarity
            cosine_similarity = np.dot(embedding1, embedding2)
            
            # Convert to percentage (0-100)
            similarity_score = (cosine_similarity + 1) * 50  # Maps [-1, 1] to [0, 100]
            
            return float(similarity_score)
            
        except Exception as e:
            logger.error(f"Error comparing embeddings: {e}")
            return 0.0
    
    def find_matches(
        self, 
        query_embedding: np.ndarray, 
        stored_embeddings: List[Tuple[int, np.ndarray]], 
        threshold: float = 70.0,
        max_matches: int = 10
    ) -> List[Dict]:
        """
        Find matching faces from stored embeddings.
        
        Args:
            query_embedding: Embedding to search for
            stored_embeddings: List of (user_id, embedding) tuples
            threshold: Minimum similarity score to consider a match (0-100)
            max_matches: Maximum number of matches to return
            
        Returns:
            List of matches sorted by similarity, each containing:
                - user_id: ID of the matched user
                - similarity: Similarity score (0-100)
        """
        matches = []
        
        for user_id, stored_embedding in stored_embeddings:
            try:
                similarity = self.compare_embeddings(query_embedding, stored_embedding)
                
                if similarity >= threshold:
                    matches.append({
                        'user_id': user_id,
                        'similarity': similarity
                    })
            except Exception as e:
                logger.error(f"Error comparing with user {user_id}: {e}")
                continue
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Return top matches
        return matches[:max_matches]
    
    def search_faces_in_image(
        self, 
        image_bytes: bytes, 
        stored_embeddings: List[Tuple[int, np.ndarray]], 
        threshold: float = 70.0
    ) -> List[Dict]:
        """
        Search for known faces in an image.
        
        Args:
            image_bytes: Raw image bytes
            stored_embeddings: List of (user_id, embedding) tuples from enrolled users
            threshold: Minimum similarity score to consider a match
            
        Returns:
            List of matches with user_id, similarity, and bounding box
        """
        try:
            # Extract all faces from the image
            faces = self.extract_embeddings(image_bytes)
            
            if not faces:
                logger.info("No faces detected in image")
                return []
            
            all_matches = []
            
            # For each detected face, find matches
            for face in faces:
                matches = self.find_matches(
                    query_embedding=face['embedding'],
                    stored_embeddings=stored_embeddings,
                    threshold=threshold,
                    max_matches=10
                )
                
                # Add bounding box info to matches
                for match in matches:
                    match['bounding_box'] = face['facial_area']
                    match['detection_confidence'] = face['confidence']
                    all_matches.append(match)
            
            logger.info(f"Found {len(all_matches)} face match(es) in image")
            return all_matches
            
        except Exception as e:
            logger.error(f"Error searching faces in image: {e}")
            return []
    
    @staticmethod
    def embedding_to_base64(embedding: np.ndarray) -> str:
        """Convert numpy embedding to base64 string for storage."""
        return base64.b64encode(embedding.tobytes()).decode('utf-8')
    
    @staticmethod
    def base64_to_embedding(b64_string: str, dtype=np.float64) -> np.ndarray:
        """Convert base64 string back to numpy embedding."""
        return np.frombuffer(base64.b64decode(b64_string), dtype=dtype)
    
    @staticmethod
    def normalize_bounding_box(facial_area: Dict, image_width: int = None, image_height: int = None) -> Dict:
        """
        Normalize bounding box coordinates to 0-1 range (AWS Rekognition format).
        
        Args:
            facial_area: Dict with x, y, w, h (pixel coordinates)
            image_width: Image width in pixels
            image_height: Image height in pixels
            
        Returns:
            Dict with Top, Left, Width, Height (normalized 0-1)
        """
        if not facial_area or not image_width or not image_height:
            return {}
        
        return {
            'Top': facial_area.get('y', 0) / image_height,
            'Left': facial_area.get('x', 0) / image_width,
            'Width': facial_area.get('w', 0) / image_width,
            'Height': facial_area.get('h', 0) / image_height
        }
