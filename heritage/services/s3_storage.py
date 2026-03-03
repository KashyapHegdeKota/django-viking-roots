import json
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from datetime import datetime

class S3StorageService:
    """Handle S3 operations for heritage data"""
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    
    def upload_json_backup(self, user_id, data):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_key = f'heritage_backups/user_{user_id}/backup_{timestamp}.json'
        try:
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=json_data.encode('utf-8'),
                ContentType='application/json',
                ServerSideEncryption='AES256'
            )
            return f"https://{self.bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_key}"
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            raise