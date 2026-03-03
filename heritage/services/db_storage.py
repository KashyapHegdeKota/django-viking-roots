from django.db import transaction
from django.contrib.auth.models import User
import re
from datetime import datetime

# IMPORT FROM HERITAGE
from heritage.models import (
    UserProfile, Ancestor, AncestorFact, Story,
    HeritageEvent, HeritageLocation, EventParticipation
)
# IMPORT FROM AI INTERVIEW
from ai_interview.models import InterviewSession

from .s3_storage import S3StorageService

class DatabaseStorageService:
    def __init__(self, user):
        self.user = user
        self.s3_service = S3StorageService()
        self.profile, _ = UserProfile.objects.get_or_create(user=user)
    
    def parse_key_value_pairs(self, s):
        pairs = {}
        for item in s.split(','):
            if '=' in item:
                k, v = item.split('=', 1)
                pairs[k.strip()] = v.strip()
        return pairs
    
    @transaction.atomic
    def extract_and_store_tags(self, text):
        extracted = {"persons": [], "events": [], "facts": [], "user_data": []}
        pattern = r'\[(PERSON|FACT|DATA|EVENT):([^\]]+)\]'
        matches = re.findall(pattern, text)
        
        for tag_type, content in matches:
            try:
                attrs = self.parse_key_value_pairs(content)
                if tag_type == "DATA":
                    key = attrs.get('key')
                    value = attrs.get('value')
                    if key and value:
                        setattr(self.profile, key, value)
                        self.profile.save()
                        extracted['user_data'].append({key: value})
                
                elif tag_type == "PERSON":
                    person_id = attrs.pop('id', None)
                    if person_id:
                        birth_loc_name = attrs.pop('birth_place', None)
                        location = None
                        if birth_loc_name:
                            location, _ = HeritageLocation.objects.get_or_create(
                                name=birth_loc_name, defaults={'location_type': 'other'}
                            )

                        defaults = {
                            'name': attrs.get('name', ''),
                            'relation': attrs.get('relation', ''),
                            'gender': attrs.get('gender', ''),
                            'origin': attrs.get('origin', ''),
                            'birth_location': location
                        }
                        birth_year = attrs.get('birth_year')
                        if birth_year and birth_year.isdigit():
                            defaults['birth_year'] = int(birth_year)

                        ancestor, _ = Ancestor.objects.update_or_create(
                            user=self.user, unique_id=person_id, defaults=defaults
                        )
                        extracted['persons'].append({'id': person_id, 'name': ancestor.name})
                
                elif tag_type == "EVENT":
                    title = attrs.get('title')
                    date_str = attrs.get('date')
                    loc_name = attrs.get('location')
                    person_id = attrs.get('person_id')

                    if title:
                        date_obj = None
                        if date_str:
                            try:
                                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError: pass

                        location = None
                        if loc_name:
                            location, _ = HeritageLocation.objects.get_or_create(
                                name=loc_name, defaults={'location_type': 'other'}
                            )

                        event, _ = HeritageEvent.objects.get_or_create(
                            title=title, date_start=date_obj,
                            defaults={'location': location, 'event_type': attrs.get('type', 'personal')}
                        )

                        if person_id:
                            try:
                                anc = Ancestor.objects.get(user=self.user, unique_id=person_id)
                                EventParticipation.objects.get_or_create(event=event, ancestor=anc, defaults={'role': 'Principal'})
                                if 'birth' in title.lower() and date_obj:
                                    anc.birth_date = date_obj
                                    anc.birth_year = date_obj.year
                                    anc.save()
                            except Ancestor.DoesNotExist: pass
                        extracted['events'].append({'title': title, 'date': date_str})

                elif tag_type == "FACT":
                    person_id = attrs.pop('person_id', None)
                    key = attrs.pop('key', None)
                    value = attrs.pop('value', None)
                    if person_id and key and value:
                        try:
                            anc = Ancestor.objects.get(user=self.user, unique_id=person_id)
                            AncestorFact.objects.create(ancestor=anc, key=key, value=value)
                            extracted['facts'].append({'person': person_id, 'key': key})
                        except Ancestor.DoesNotExist: pass
            except Exception as e:
                print(f"Error parsing tag content: '{content}'. Error: {e}")
        
        cleaned_text = re.sub(pattern, '', text).strip()
        return cleaned_text, extracted
    
    def get_all_heritage_data(self):
        ancestors = Ancestor.objects.filter(user=self.user).prefetch_related('facts', 'stories', 'media_tags__media')
        people = {}
        for ancestor in ancestors:
            person_data = {
                'name': ancestor.name, 'relation': ancestor.relation,
                'birth_year': ancestor.birth_year,
                'birth_date': ancestor.birth_date.isoformat() if ancestor.birth_date else None,
                'origin': ancestor.origin,
            }
            for fact in ancestor.facts.all(): person_data[fact.key] = fact.value
            if ancestor.stories.exists():
                person_data['stories'] = [{'content': s.content, 'created_at': s.created_at.isoformat()} for s in ancestor.stories.all()]
            
            photos = [tag.media.file.url for tag in ancestor.media_tags.all()]
            person_data['photos'] = photos
            people[ancestor.unique_id] = person_data

        events_data = []
        user_events = HeritageEvent.objects.filter(participants__ancestor__user=self.user).distinct()
        for evt in user_events:
            events_data.append({
                'title': evt.title, 'description': evt.description,
                'date_start': evt.date_start.isoformat() if evt.date_start else None,
                'location': evt.location.name if evt.location else None,
                'event_type': evt.event_type
            })
        
        return {
            'user': self.user.username, 'people': people, 'events': events_data,
            'metadata': {'generated_at': datetime.now().isoformat()}
        }

    def save_interview_session(self, session_id, chat_history, completed=False):
        InterviewSession.objects.update_or_create(
            user=self.user, session_id=session_id,
            defaults={'chat_history': chat_history, 'completed': completed}
        )
    
    def create_backup_to_s3(self):
        data = self.get_all_heritage_data()
        return self.s3_service.upload_json_backup(self.user.id, data)