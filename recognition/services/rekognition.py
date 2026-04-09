import boto3
from django.conf import settings
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

class RekognitionService:
    def __init__(self):
        self.client = boto3.client(
            'rekognition',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        self.collection_id = getattr(settings, 'AWS_REKOGNITION_COLLECTION_ID', 'viking-roots-faces')

    def create_collection(self):
        """Create a Rekognition collection if it doesn't exist."""
        try:
            logger.info(f"Creating collection: {self.collection_id}")
            self.client.create_collection(CollectionId=self.collection_id)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
                return True
            logger.error(f"Error creating collection: {e}")
            return False

    def index_faces(self, user_id, image_bytes):
        """
        Register a face into the collection.
        user_id is stored as ExternalImageId so we can identify the person later.
        """
        try:
            response = self.client.index_faces(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                ExternalImageId=str(user_id),
                MaxFaces=1,
                QualityFilter="AUTO"
            )
            return response['FaceRecords']
        except ClientError as e:
            logger.error(f"Error indexing face: {e}")
            return []

    def search_faces_by_image(self, image_bytes, threshold=80):
        """Search for faces in an image that match our collection."""
        try:
            response = self.client.search_faces_by_image(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                FaceMatchThreshold=threshold,
                MaxFaces=10
            )
            return response['FaceMatches']
        except ClientError as e:
            logger.error(f"Error searching faces: {e}")
            return []

    def delete_faces(self, face_ids):
        """Remove specific face IDs from the collection."""
        if not face_ids:
            return
        try:
            self.client.delete_faces(
                CollectionId=self.collection_id,
                FaceIds=face_ids
            )
            return True
        except ClientError as e:
            logger.error(f"Error deleting faces: {e}")
            return False
