# questionaire/services/db_storage.py

from django.db import transaction
from django.contrib.auth.models import User
from ..models import UserProfile, Ancestor, AncestorFact, Story, InterviewSession  # Use .. to go up one level
from .s3_storage import S3StorageService
from datetime import datetime
import re


class DatabaseStorageService:
    """Handle database operations for heritage data"""
    
    def __init__(self, user):
        self.user = user
        self.s3_service = S3StorageService()
        
        # Get or create user profile
        self.profile, _ = UserProfile.objects.get_or_create(user=user)
    
    def parse_key_value_pairs(self, s):
        """Helper function to parse comma-separated key=value strings"""
        return dict(item.strip().split('=', 1) for item in s.split(','))
    
    @transaction.atomic
    def extract_and_store_tags(self, text):
        """
        Extract tags from AI response and store in database
        Returns: (cleaned_text, extracted_data_dict)
        """
        extracted = {"persons": [], "facts": [], "user_data": []}
        
        # Pattern to find all tag types
        pattern = r'\[(PERSON|FACT|DATA):([^\]]+)\]'
        matches = re.findall(pattern, text)
        
        for tag_type, content in matches:
            try:
                attributes = self.parse_key_value_pairs(content)
                
                if tag_type == "DATA":
                    key = attributes.get('key')
                    value = attributes.get('value')
                    if key and value:
                        # Store user data in profile
                        setattr(self.profile, key, value)
                        self.profile.save()
                        extracted['user_data'].append({key: value})
                
                elif tag_type == "PERSON":
                    person_id = attributes.pop('id', None)
                    if person_id:
                        # Create or update ancestor
                        ancestor, created = Ancestor.objects.update_or_create(
                            user=self.user,
                            unique_id=person_id,
                            defaults={
                                'name': attributes.get('name', ''),
                                'relation': attributes.get('relation', ''),
                                'birth_year': attributes.get('birth_year'),
                                'birth_place': attributes.get('birth_place', ''),
                                'origin': attributes.get('origin', ''),
                            }
                        )
                        extracted['persons'].append({
                            'id': person_id,
                            'data': attributes,
                            'created': created
                        })
                
                elif tag_type == "FACT":
                    person_id = attributes.pop('person_id', None)
                    fact_key = attributes.pop('key', None)
                    fact_value = attributes.pop('value', None)
                    
                    if person_id and fact_key and fact_value:
                        try:
                            ancestor = Ancestor.objects.get(user=self.user, unique_id=person_id)
                            
                            # Check if it's a structured field
                            if fact_key in ['birth_year', 'death_year', 'birth_place', 'origin']:
                                setattr(ancestor, fact_key, fact_value)
                                ancestor.save()
                            else:
                                # Store as a fact
                                AncestorFact.objects.update_or_create(
                                    ancestor=ancestor,
                                    key=fact_key,
                                    defaults={'value': fact_value}
                                )
                            
                            extracted['facts'].append({
                                'person_id': person_id,
                                'key': fact_key,
                                'value': fact_value
                            })
                        except Ancestor.DoesNotExist:
                            pass
                            
            except Exception as e:
                print(f"Error parsing tag content: '{content}'. Error: {e}")
        
        # Clean text of tags
        cleaned_text = re.sub(pattern, '', text).strip()
        
        return cleaned_text, extracted
    
    def get_all_heritage_data(self):
        """Get all heritage data for this user in JSON format"""
        ancestors = Ancestor.objects.filter(user=self.user).prefetch_related('facts', 'stories')
        
        people = {}
        for ancestor in ancestors:
            person_data = {
                'name': ancestor.name,
                'relation': ancestor.relation,
            }
            
            # Add optional fields
            if ancestor.birth_year:
                person_data['birth_year'] = ancestor.birth_year
            if ancestor.death_year:
                person_data['death_year'] = ancestor.death_year
            if ancestor.birth_place:
                person_data['birth_place'] = ancestor.birth_place
            if ancestor.origin:
                person_data['origin'] = ancestor.origin
            
            # Add facts
            for fact in ancestor.facts.all():
                person_data[fact.key] = fact.value
            
            # Add stories
            if ancestor.stories.exists():
                person_data['stories'] = [
                    {
                        'content': story.content,
                        'context': story.context,
                        'created_at': story.created_at.isoformat()
                    }
                    for story in ancestor.stories.all()
                ]
            
            people[ancestor.unique_id] = person_data
        
        return {
            'user': {
                'first_name': self.profile.first_name,
                'last_name': self.profile.last_name,
                'username': self.user.username,
            },
            'people': people,
            'metadata': {
                'total_ancestors': len(people),
                'interview_completed': self.profile.interview_completed,
                'last_updated': self.profile.updated_at.isoformat()
            }
        }
    
    def create_backup_to_s3(self):
        """Create a JSON backup and upload to S3"""
        data = self.get_all_heritage_data()
        url = self.s3_service.upload_json_backup(self.user.id, data)
        
        # Update profile with backup URL
        self.profile.json_backup_url = url
        self.profile.save()
        
        return url
    
    def save_interview_session(self, session_id, chat_history, completed=False):
        """Save or update interview session"""
        session, created = InterviewSession.objects.update_or_create(
            user=self.user,
            session_id=session_id,
            defaults={
                'chat_history': chat_history,
                'completed': completed
            }
        )
        return session