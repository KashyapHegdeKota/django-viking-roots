# questionaire/storage.py
import os
import re
import json
from datetime import datetime
from django.conf import settings
from pathlib import Path


class HeritageDataStorage:
    """Handles storage and retrieval of heritage interview data"""
    
    def __init__(self, user_id):
        """
        Initialize storage for a specific user
        user_id: unique identifier for the user (can be Django user.id or session key)
        """
        self.user_id = user_id
        self.storage_dir = Path(settings.MEDIA_ROOT) / 'heritage_data'
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.storage_dir / f'user_{user_id}_heritage.json'
        
    def _get_default_structure(self):
        """Returns the default JSON structure"""
        return {
            "user": {},
            "people": {},
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "version": "1.0"
            }
        }
    
    def load_data(self):
        """Load existing data or create new structure"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # If file is corrupted, return default structure
                return self._get_default_structure()
        return self._get_default_structure()
    
    def save_data(self, data):
        """Save data to JSON file"""
        # Update last_updated timestamp
        data['metadata']['last_updated'] = datetime.now().isoformat()
        
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def parse_key_value_pairs(self, s):
        """Helper function to parse comma-separated key=value strings"""
        return dict(item.strip().split('=', 1) for item in s.split(','))
    
    def extract_and_store_tags(self, text):
        """
        Finds [PERSON], [FACT], and [DATA] tags, stores the data,
        and returns the cleaned text for the user to see.
        Returns: (cleaned_text, extracted_data_dict)
        """
        data = self.load_data()
        extracted = {"persons": [], "facts": [], "user_data": []}
        
        # Combined pattern to find all tag types
        pattern = r'\[(PERSON|FACT|DATA):([^\]]+)\]'
        matches = re.findall(pattern, text)
        
        for tag_type, content in matches:
            try:
                attributes = self.parse_key_value_pairs(content)
                
                if tag_type == "DATA":
                    key = attributes.get('key')
                    value = attributes.get('value')
                    if key and value:
                        data['user'][key] = value
                        extracted['user_data'].append({key: value})
                
                elif tag_type == "PERSON":
                    person_id = attributes.pop('id', None)
                    if person_id:
                        data['people'][person_id] = attributes
                        extracted['persons'].append({
                            'id': person_id,
                            'data': attributes
                        })
                
                elif tag_type == "FACT":
                    person_id = attributes.pop('person_id', None)
                    fact_key = attributes.pop('key', None)
                    fact_value = attributes.pop('value', None)
                    
                    if person_id and fact_key and fact_value:
                        if person_id in data['people']:
                            data['people'][person_id][fact_key] = fact_value
                            extracted['facts'].append({
                                'person_id': person_id,
                                'key': fact_key,
                                'value': fact_value
                            })
                            
            except Exception as e:
                print(f"Error parsing tag content: '{content}'. Error: {e}")
        
        # Save updated data
        self.save_data(data)
        
        # Clean text of tags
        cleaned_text = re.sub(pattern, '', text).strip()
        
        return cleaned_text, extracted
    
    def get_all_data(self):
        """Get all stored heritage data for this user"""
        return self.load_data()
    
    def delete_data(self):
        """Delete the user's heritage data file"""
        if self.filepath.exists():
            self.filepath.unlink()
            return True
        return False
    
    def export_for_display(self):
        """Export data in a format suitable for frontend display"""
        data = self.load_data()
        
        # Convert people dict to list for easier frontend rendering
        people_list = []
        for person_id, person_data in data['people'].items():
            people_list.append({
                'id': person_id,
                **person_data
            })
        
        return {
            'user': data['user'],
            'ancestors': people_list,
            'metadata': data['metadata']
        }