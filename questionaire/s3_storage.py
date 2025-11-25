# questionaire/s3_storage.py
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
        """
        Upload full heritage data as JSON backup to S3
        Returns: S3 URL of the uploaded file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_key = f'heritage_backups/user_{user_id}/backup_{timestamp}.json'
        
        try:
            # Convert data to JSON string
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=json_data.encode('utf-8'),
                ContentType='application/json',
                ServerSideEncryption='AES256'
            )
            
            # Generate URL
            url = f"https://{self.bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_key}"
            return url
            
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            raise
    
    def download_json_backup(self, user_id, backup_filename=None):
        """
        Download JSON backup from S3
        If backup_filename is None, gets the most recent backup
        """
        try:
            if backup_filename:
                file_key = f'heritage_backups/user_{user_id}/{backup_filename}'
            else:
                # List all backups and get the most recent
                prefix = f'heritage_backups/user_{user_id}/'
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix
                )
                
                if 'Contents' not in response:
                    return None
                
                # Sort by last modified and get most recent
                files = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
                if not files:
                    return None
                
                file_key = files[0]['Key']
            
            # Download the file
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            
            # Parse JSON
            json_data = response['Body'].read().decode('utf-8')
            return json.loads(json_data)
            
        except ClientError as e:
            print(f"Error downloading from S3: {e}")
            return None
    
    def list_backups(self, user_id):
        """List all JSON backups for a user"""
        try:
            prefix = f'heritage_backups/user_{user_id}/'
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            backups = []
            for obj in response['Contents']:
                backups.append({
                    'filename': obj['Key'].split('/')[-1],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat()
                })
            
            return sorted(backups, key=lambda x: x['last_modified'], reverse=True)
            
        except ClientError as e:
            print(f"Error listing S3 backups: {e}")
            return []