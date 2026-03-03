import os
import re
from datetime import datetime
from django.db import transaction
from gedcom.parser import Parser
from gedcom.element.individual import IndividualElement

from heritage.models import (
    ImportBatch, Ancestor, AncestorFact, 
    HeritageLocation, HeritageEvent, EventParticipation
)

class GedcomImportService:
    def __init__(self, user):
        self.user = user

    def _sanitize_gedcom_file(self, file_path):
        """Fixes common GEDCOM formatting issues that crash python-gedcom"""
        with open(file_path, 'rb') as f:
            content = f.read()
            
        # 1. Remove UTF-8 Byte Order Mark (BOM) if present (fixes line 1 crashes)
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]
            
        # 2. Ensure file ends with a proper newline (Fixes the "0 TRLR" crash)
        # We strip any weird trailing spaces and force a clean newline
        content = content.rstrip() + b'\r\n'
        
        with open(file_path, 'wb') as f:
            f.write(content)

    def parse_gedcom_date(self, date_str):
        if not date_str: return None, None
        clean_str = re.sub(r'^(ABT|BEF|AFT|EST|CAL)\s+', '', date_str.upper()).strip()
        months = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
        try:
            parts = clean_str.split()
            if len(parts) == 3: return datetime(int(parts[2]), months[parts[1]], int(parts[0])).date(), int(parts[2])
            elif len(parts) == 2: return datetime(int(parts[1]), months[parts[0]], 1).date(), int(parts[1])
            elif len(parts) == 1: return None, int(parts[0])
        except (ValueError, KeyError):
            year_match = re.search(r'\d{4}', date_str)
            if year_match: return None, int(year_match.group())
        return None, None

    def get_or_create_location(self, place_string):
        if not place_string: return None
        loc, _ = HeritageLocation.objects.get_or_create(name=place_string.strip(), defaults={'location_type': 'other'})
        return loc

    @transaction.atomic
    def process_gedcom_file(self, file_path, original_filename):
        batch = ImportBatch.objects.create(user=self.user, filename=original_filename, status='processing')
        try:
            self._sanitize_gedcom_file(file_path)
            
            gedcom_parser = Parser()
            gedcom_parser.parse_file(file_path)
            
            for element in gedcom_parser.get_root_child_elements():
                if isinstance(element, IndividualElement):
                    self._process_individual(element, batch)
                    
            batch.status = 'completed'
            batch.save()
            return batch
        except Exception as e:
            batch.status = 'failed'
            batch.save()
            raise e

    def _process_individual(self, element, batch):
        raw_id = element.get_pointer().replace('@', '')
        unique_id = f"gedcom_{batch.id}_{raw_id}"
        first, last = element.get_name()
        full_name = f"{first} {last}".strip() if first or last else "Unknown"
        gender = {'M': 'M', 'F': 'F'}.get(element.get_gender(), 'O')

        ancestor, _ = Ancestor.objects.update_or_create(
            user=self.user, unique_id=unique_id,
            defaults={'name': full_name, 'gender': gender, 'relation': 'Imported Relative', 'source_type': 'gedcom', 'import_batch': batch}
        )
        self._process_life_events_and_facts(element, ancestor)

    def _process_life_events_and_facts(self, element, ancestor):
        b_date_str, b_place, _ = element.get_birth_data()
        if b_date_str or b_place:
            b_date_obj, b_year = self.parse_gedcom_date(b_date_str)
            b_loc = self.get_or_create_location(b_place)
            ancestor.birth_date = b_date_obj
            ancestor.birth_year = b_year
            ancestor.birth_location = b_loc
            ancestor.save()
            if b_loc or b_year:
                evt, _ = HeritageEvent.objects.get_or_create(title=f"Birth of {ancestor.name}", date_start=b_date_obj, location=b_loc, defaults={'event_type': 'personal'})
                EventParticipation.objects.get_or_create(event=evt, ancestor=ancestor, role="Principal")

        d_date_str, d_place, _ = element.get_death_data()
        if d_date_str or d_place:
            d_date_obj, d_year = self.parse_gedcom_date(d_date_str)
            d_loc = self.get_or_create_location(d_place)
            ancestor.death_date = d_date_obj
            ancestor.death_year = d_year
            ancestor.save()
            if d_loc or d_year:
                evt, _ = HeritageEvent.objects.get_or_create(title=f"Passing of {ancestor.name}", date_start=d_date_obj, location=d_loc, defaults={'event_type': 'personal'})
                EventParticipation.objects.get_or_create(event=evt, ancestor=ancestor, role="Principal")

        ignore_tags = ['BIRT', 'DEAT', 'NAME', 'SEX']
        for child in element.get_child_elements():
            tag = child.get_tag()
            val = child.get_value()
            if tag not in ignore_tags and val:
                AncestorFact.objects.get_or_create(ancestor=ancestor, key=tag, defaults={'value': val})
                
class GedcomExportService:
    def __init__(self, user):
        self.user = user

    def generate_gedcom(self):
        """Fetches user data from RDS and builds a GEDCOM 5.5 string"""
        ancestors = Ancestor.objects.filter(user=self.user).prefetch_related('facts', 'birth_location')
        
        lines = []
        
        # 1. THE HEADER
        lines.append("0 HEAD")
        lines.append("1 SOUR VikingRoots")
        lines.append("2 NAME Viking Roots Heritage Engine")
        lines.append("1 GEDC")
        lines.append("2 VERS 5.5.5")
        lines.append("2 FORM LINEAGE-LINKED")
        lines.append("1 CHAR UTF-8")
        lines.append(f"1 DATE {datetime.now().strftime('%d %b %Y').upper()}")
        
        # 2. THE INDIVIDUALS
        for anc in ancestors:
            # Create a safe, unique GEDCOM pointer
            safe_id = f"@I{anc.id}@"
            lines.append(f"0 {safe_id} INDI")
            
            # Formatted Name (GEDCOM requires slashes around the surname)
            parts = anc.name.rsplit(' ', 1)
            if len(parts) == 2:
                ged_name = f"{parts[0]} /{parts[1]}/"
            else:
                ged_name = f"{anc.name} //"
            lines.append(f"1 NAME {ged_name}")
            
            # Gender
            if anc.gender:
                lines.append(f"1 SEX {anc.gender}")
            
            # Birth Event
            if anc.birth_year or anc.birth_date or anc.birth_location or anc.origin:
                lines.append("1 BIRT")
                if anc.birth_date:
                    lines.append(f"2 DATE {anc.birth_date.strftime('%d %b %Y').upper()}")
                elif anc.birth_year:
                    lines.append(f"2 DATE {anc.birth_year}")
                
                if anc.birth_location:
                    lines.append(f"2 PLAC {anc.birth_location.name}")
                elif anc.origin:
                    lines.append(f"2 PLAC {anc.origin}")
                    
            # Death Event
            if anc.death_year or anc.death_date:
                lines.append("1 DEAT")
                if anc.death_date:
                    lines.append(f"2 DATE {anc.death_date.strftime('%d %b %Y').upper()}")
                elif anc.death_year:
                    lines.append(f"2 DATE {anc.death_year}")
                    
            # Extracted AI Facts & Notes
            for fact in anc.facts.all():
                # If it's an original 3-4 letter GEDCOM tag, export it natively
                if len(fact.key) <= 4 and fact.key.isupper():
                    lines.append(f"1 {fact.key} {fact.value}")
                else:
                    # Otherwise, export the AI's custom fact as a standard note
                    lines.append(f"1 NOTE {fact.key}: {fact.value}")
                    
        # 3. THE TRAILER (With the carriage return to prevent crashes!)
        lines.append("0 TRLR")
        
        return "\n".join(lines) + "\n"