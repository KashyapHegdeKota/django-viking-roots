import os
import re
from datetime import datetime
from django.db import transaction
from gedcom.parser import Parser
from gedcom.element.individual import IndividualElement
from gedcom.element.family import FamilyElement

from ..models import (
    ImportBatch, Ancestor, AncestorFact, 
    HeritageLocation, HeritageEvent, EventParticipation
)

class GedcomImportService:
    """Service to parse any GEDCOM file and map it to the Viking Roots schema"""

    def __init__(self, user):
        self.user = user

    def parse_gedcom_date(self, date_str):
        """
        Converts messy GEDCOM dates ('12 OCT 1890', 'ABT 1890') into Python objects.
        Returns: (date_object, year_integer)
        """
        if not date_str:
            return None, None

        # Clean up modifiers like ABT (About), BEF (Before), AFT (After)
        clean_str = re.sub(r'^(ABT|BEF|AFT|EST|CAL)\s+', '', date_str.upper()).strip()
        
        # Dictionary to map GEDCOM months to numbers
        months = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }

        try:
            parts = clean_str.split()
            if len(parts) == 3:  # "12 OCT 1890"
                day, month_str, year_str = parts
                return datetime(int(year_str), months[month_str], int(day)).date(), int(year_str)
            elif len(parts) == 2:  # "OCT 1890"
                month_str, year_str = parts
                return datetime(int(year_str), months[month_str], 1).date(), int(year_str)
            elif len(parts) == 1:  # "1890"
                return None, int(parts[0])
        except (ValueError, KeyError):
            # If it's completely unparseable (e.g., "Spring 1890"), just extract the year if possible
            year_match = re.search(r'\d{4}', date_str)
            if year_match:
                return None, int(year_match.group())
            
        return None, None

    def get_or_create_location(self, place_string):
        """Deduplicates locations so 'Gimli' maps to one specific map point"""
        if not place_string:
            return None
        
        loc, _ = HeritageLocation.objects.get_or_create(
            name=place_string.strip(),
            defaults={'location_type': 'other'}
        )
        return loc

    @transaction.atomic
    def process_gedcom_file(self, file_path, original_filename):
        """
        The main engine. Wraps everything in a transaction so if it fails, 
        it doesn't leave a half-imported mess in your database.
        """
        # 1. Create the Undo-able Batch
        batch = ImportBatch.objects.create(
            user=self.user,
            filename=original_filename,
            status='processing'
        )

        try:
            # 2. Parse the file
            gedcom_parser = Parser()
            gedcom_parser.parse_file(file_path)

            root_child_elements = gedcom_parser.get_root_child_elements()

            # 3. Process Individuals (INDI)
            for element in root_child_elements:
                if isinstance(element, IndividualElement):
                    self._process_individual(element, batch)

            # Mark complete
            batch.status = 'completed'
            batch.save()
            return batch

        except Exception as e:
            batch.status = 'failed'
            batch.save()
            raise e

    def _process_individual(self, element, batch):
        """Maps a single GEDCOM person to Viking Roots schema"""
        
        # GEDCOM IDs are like '@I1@'. We make them globally unique to the user/batch.
        raw_id = element.get_pointer().replace('@', '')
        unique_id = f"gedcom_{batch.id}_{raw_id}"
        
        # Extract Name
        first, last = element.get_name()
        full_name = f"{first} {last}".strip() if first or last else "Unknown"
        
        # Extract Gender
        gender_map = {'M': 'M', 'F': 'F'}
        gender = gender_map.get(element.get_gender(), 'O')

        # Create Core Ancestor Node
        ancestor, _ = Ancestor.objects.update_or_create(
            user=self.user,
            unique_id=unique_id,
            defaults={
                'name': full_name,
                'gender': gender,
                'relation': 'Imported Relative', # Default until tree logic calculates it
                'source_type': 'gedcom',
                'import_batch': batch
            }
        )

        # Process standard GEDCOM tags (Birth, Death, Custom facts)
        self._process_life_events_and_facts(element, ancestor)


    def _process_life_events_and_facts(self, element, ancestor):
        """Extracts dates, places, and random data and maps to Events or Facts"""
        
        # 1. Handle Birth
        b_date_str, b_place, _ = element.get_birth_data()
        if b_date_str or b_place:
            b_date_obj, b_year = self.parse_gedcom_date(b_date_str)
            b_loc = self.get_or_create_location(b_place)
            
            # Update Ancestor Node for quick sorting
            ancestor.birth_date = b_date_obj
            ancestor.birth_year = b_year
            ancestor.birth_location = b_loc
            ancestor.save()

            # Create the Shared Saga Event
            if b_loc or b_year:
                evt, _ = HeritageEvent.objects.get_or_create(
                    title=f"Birth of {ancestor.name}",
                    date_start=b_date_obj,
                    location=b_loc,
                    defaults={'event_type': 'personal'}
                )
                EventParticipation.objects.get_or_create(event=evt, ancestor=ancestor, role="Principal")

        # 2. Handle Death
        d_date_str, d_place, _ = element.get_death_data()
        if d_date_str or d_place:
            d_date_obj, d_year = self.parse_gedcom_date(d_date_str)
            d_loc = self.get_or_create_location(d_place)
            
            ancestor.death_date = d_date_obj
            ancestor.death_year = d_year
            ancestor.save()

            if d_loc or d_year:
                evt, _ = HeritageEvent.objects.get_or_create(
                    title=f"Passing of {ancestor.name}",
                    date_start=d_date_obj,
                    location=d_loc,
                    defaults={'event_type': 'personal'}
                )
                EventParticipation.objects.get_or_create(event=evt, ancestor=ancestor, role="Principal")

        # 3. The "Catch-All" (The EAV Power Move)
        # Any GEDCOM tag that isn't standard gets dumped into AncestorFact.
        # This guarantees you NEVER lose user data, even if you don't have a column for it.
        ignore_tags = ['BIRT', 'DEAT', 'NAME', 'SEX']
        for child in element.get_child_elements():
            tag = child.get_tag()
            val = child.get_value()
            if tag not in ignore_tags and val:
                # E.g., tag='OCCU', val='Fisherman'
                AncestorFact.objects.get_or_create(
                    ancestor=ancestor,
                    key=tag,
                    defaults={'value': val}
                )