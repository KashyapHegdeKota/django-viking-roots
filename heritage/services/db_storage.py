# heritage/services/db_storage.py

import re
from datetime import datetime
from django.db import transaction
from django.contrib.auth.models import User

from heritage.models import (
    Story, FamilyTree, TreeAccess, Person, Fact, Event, Location
)
from ai_interview.models import InterviewSession
from .s3_storage import S3StorageService


class DatabaseStorageService:
    def __init__(self, user):
        self.user = user
        self.s3_service = S3StorageService()
        self.tree = self._get_or_create_default_tree()

    # ------------------------------------------------------------------
    # Tree Management
    # ------------------------------------------------------------------

    def _get_or_create_default_tree(self) -> FamilyTree:
        access = TreeAccess.objects.filter(
            user=self.user, role='owner'
        ).select_related('tree').first()
        if access:
            return access.tree
        tree = FamilyTree.objects.create(
            name=f"{self.user.username}'s Family Tree"
        )
        TreeAccess.objects.create(user=self.user, tree=tree, role='owner')
        return tree

    # ------------------------------------------------------------------
    # Tag Parsing
    # ------------------------------------------------------------------

    def parse_key_value_pairs(self, s: str) -> dict:
        """
        Robust parser that handles values containing spaces and commas.
        [PERSON:id=p1, name=Erik von Thorsen, relation=great grandfather]
        """
        pairs = {}
        pattern = r'(\w+)\s*=\s*([^,=\]]+?)(?=\s*,\s*\w+\s*=|\s*$|\])'
        for match in re.finditer(pattern, s):
            pairs[match.group(1).strip()] = match.group(2).strip()
        return pairs

    def _parse_date(self, date_str: str):
        """Try common date formats, return date object or None."""
        if not date_str:
            return None
        for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _get_or_create_location(self, name: str | None) -> 'Location | None':
        if not name or not name.strip():
            return None
        loc, _ = Location.objects.get_or_create(name=name.strip())
        return loc

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------

    @transaction.atomic
    def extract_and_store_tags(self, text: str) -> tuple[str, dict]:
        """
        Parse all structured tags from AI response text,
        persist to DB, and return cleaned text + summary.
        """
        extracted = {
            'persons': [],
            'events': [],
            'facts': [],
            'user_data': []
        }

        pattern = r'\[(PERSON|FACT|DATA|EVENT):([^\]]+)\]'
        matches = re.findall(pattern, text)

        for tag_type, content in matches:
            try:
                attrs = self.parse_key_value_pairs(content)
                handler = getattr(self, f'_handle_{tag_type.lower()}', None)
                if handler:
                    result = handler(attrs)
                    if result:
                        extracted[{
                            'PERSON': 'persons',
                            'EVENT': 'events',
                            'FACT': 'facts',
                            'DATA': 'user_data'
                        }[tag_type]].append(result)

            except Exception as e:
                print(f"[db_storage] Error processing tag [{tag_type}:{content}] — {e}")

        cleaned_text = re.sub(pattern, '', text).strip()
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
        return cleaned_text, extracted

    # ------------------------------------------------------------------
    # Tag Handlers
    # ------------------------------------------------------------------

    def _handle_data(self, attrs: dict) -> dict | None:
        """Updates the authenticated user's name fields."""
        key = attrs.get('key')
        value = attrs.get('value')
        if not key or not value:
            return None

        if key == 'first_name':
            self.user.first_name = value
            self.user.save(update_fields=['first_name'])
        elif key == 'last_name':
            self.user.last_name = value
            self.user.save(update_fields=['last_name'])
        elif key == 'full_name':
            parts = value.split(' ', 1)
            self.user.first_name = parts[0]
            self.user.last_name = parts[1] if len(parts) > 1 else ''
            self.user.save(update_fields=['first_name', 'last_name'])

        return {key: value}

    def _handle_person(self, attrs: dict) -> dict | None:
        """Creates or updates a Person node in the tree."""
        person_id = attrs.get('id')
        name = attrs.get('name', '')
        if not person_id or not name:
            return None

        parts = name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''

        gender_map = {'M': 'M', 'F': 'F', 'O': 'O'}
        gender = gender_map.get(attrs.get('gender', '').upper(), 'U')

        defaults = {
            'first_name': first_name,
            'last_name': last_name,
            'gender': gender,
        }

        birth_year_str = attrs.get('birth_year', '')
        if birth_year_str and birth_year_str.isdigit():
            defaults['birth_year'] = int(birth_year_str)

        person, _ = Person.objects.update_or_create(
            tree=self.tree,
            gedcom_id=person_id,
            defaults=defaults
        )

        # Store relation to user as a Fact
        if attrs.get('relation'):
            Fact.objects.update_or_create(
                person=person,
                key='RELATION_TO_USER',
                defaults={'value': attrs['relation']}
            )

        # Birth event if location or year provided
        birth_place = attrs.get('birth_place')
        if birth_place or birth_year_str:
            location = self._get_or_create_location(birth_place)
            Event.objects.get_or_create(
                tree=self.tree,
                person=person,
                event_type='BIRT',
                defaults={
                    'location': location,
                    'date_string': birth_year_str or '',
                    'parsed_date': self._parse_date(birth_year_str)
                }
            )

        return {'id': person_id, 'name': name}

    def _handle_event(self, attrs: dict) -> dict | None:
        """Creates an Event linked to a Person."""
        person_id = attrs.get('person_id')
        # Accept both GEDCOM type codes and legacy title field
        event_type = attrs.get('type') or attrs.get('title', 'EVEN')

        if not person_id or not event_type:
            return None

        try:
            person = Person.objects.get(tree=self.tree, gedcom_id=person_id)
        except Person.DoesNotExist:
            print(f"[db_storage] EVENT tag references unknown person_id={person_id}")
            return None

        date_str = attrs.get('date', '')
        date_obj = self._parse_date(date_str)
        location = self._get_or_create_location(attrs.get('location'))

        event, created = Event.objects.get_or_create(
            tree=self.tree,
            person=person,
            event_type=event_type.upper(),
            date_string=date_str,
            defaults={
                'parsed_date': date_obj,
                'location': location
            }
        )

        # Update quick-reference year on person
        if date_obj:
            if event_type.upper() == 'BIRT' and not person.birth_year:
                person.birth_year = date_obj.year
                person.save(update_fields=['birth_year'])
            elif event_type.upper() == 'DEAT' and not person.death_year:
                person.death_year = date_obj.year
                person.save(update_fields=['death_year'])

        return {'type': event_type, 'date': date_str, 'person': person_id}

    def _handle_fact(self, attrs: dict) -> dict | None:
        """Creates a Fact attached to a Person."""
        person_id = attrs.get('person_id')
        key = attrs.get('key')
        value = attrs.get('value')

        if not all([person_id, key, value]):
            return None

        try:
            person = Person.objects.get(tree=self.tree, gedcom_id=person_id)
        except Person.DoesNotExist:
            print(f"[db_storage] FACT tag references unknown person_id={person_id}")
            return None

        # Use update_or_create to avoid duplicate facts on re-runs
        Fact.objects.update_or_create(
            person=person,
            key=key,
            defaults={'value': value}
        )

        return {'person': person_id, 'key': key}

    # ------------------------------------------------------------------
    # Session & Backup
    # ------------------------------------------------------------------

    def save_interview_session(
        self, session_id: str, chat_history: list, completed: bool = False
    ):
        InterviewSession.objects.update_or_create(
            user=self.user,
            session_id=session_id,
            defaults={
                'chat_history': chat_history,
                'completed': completed
            }
        )

    def get_all_heritage_data(self) -> dict:
        """Serializes tree data for S3 backup."""
        people_qs = Person.objects.filter(
            tree=self.tree
        ).prefetch_related('facts', 'events__location')

        people = {}
        for person in people_qs:
            person_data = {
                'first_name': person.first_name,
                'last_name': person.last_name,
                'gender': person.gender,
                'birth_year': person.birth_year,
                'death_year': person.death_year,
            }
            for fact in person.facts.all():
                person_data[fact.key] = fact.value
            people[person.gedcom_id or str(person.id)] = person_data

        events_data = [
            {
                'event_type': evt.event_type,
                'date_string': evt.date_string,
                'parsed_date': evt.parsed_date.isoformat() if evt.parsed_date else None,
                'location': evt.location.name if evt.location else None,
                'person_id': evt.person.gedcom_id if evt.person else None,
            }
            for evt in Event.objects.filter(
                tree=self.tree
            ).select_related('location', 'person')
        ]

        return {
            'user': self.user.username,
            'tree_id': self.tree.id,
            'people': people,
            'events': events_data,
            'metadata': {'generated_at': datetime.now().isoformat()}
        }

    def create_backup_to_s3(self) -> str:
        data = self.get_all_heritage_data()
        return self.s3_service.upload_json_backup(self.user.id, data)
    
    def store_extracted_data(self, extracted: dict):
        for attrs in extracted.get('persons', []):
            self._handle_person(attrs)
        
        for attrs in extracted.get('events', []):
            self._handle_event(attrs)
        
        for attrs in extracted.get('facts', []):
            self._handle_fact(attrs)
        
        for attrs in extracted.get('user_data', []):
            # user_data comes as list of {key: value} dicts
            if isinstance(attrs, dict):
                for key, value in attrs.items():
                    self._handle_data({'key': key, 'value': value})