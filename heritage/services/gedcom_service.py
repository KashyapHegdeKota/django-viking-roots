import os
import re
from datetime import datetime
from django.db import transaction
from gedcom.parser import Parser
from gedcom.element.individual import IndividualElement
from gedcom.element.family import FamilyElement

from heritage.models import (
    FamilyTree, TreeAccess, Location, Person, 
    FamilyGroup, ChildLink, Event, Fact
)

class GedcomImportService:
    def __init__(self, user):
        self.user = user
        self.tree = None

    def _sanitize_gedcom_file(self, file_path):
        """Fixes common GEDCOM formatting issues that crash python-gedcom"""
        with open(file_path, 'rb') as f:
            content = f.read()
            
        # 1. Remove UTF-8 Byte Order Mark (BOM)
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]
            
        # 2. Ensure file ends with a proper newline
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
        loc, _ = Location.objects.get_or_create(name=place_string.strip())
        return loc

    @transaction.atomic
    def process_gedcom_file(self, file_path, original_filename):
        self._sanitize_gedcom_file(file_path)
        
        gedcom_parser = Parser()
        gedcom_parser.parse_file(file_path)

        # 1. Create a new Tree container for this import
        tree_name = f"Imported Tree: {original_filename.replace('.ged', '')}"
        self.tree = FamilyTree.objects.create(name=tree_name)
        
        # 2. Grant the uploading user Owner access
        TreeAccess.objects.create(user=self.user, tree=self.tree, role='owner')

        # Dictionary to temporarily hold created people so we can link them in Pass 2
        people_map = {} 
        
        elements = gedcom_parser.get_root_child_elements()

        # ==========================================
        # PASS 1: Create all Individuals (INDI)
        # ==========================================
        for element in elements:
            if isinstance(element, IndividualElement):
                raw_id = element.get_pointer().replace('@', '')
                first, last = element.get_name()
                gender = {'M': 'M', 'F': 'F'}.get(element.get_gender(), 'U')

                # Create the Person
                person = Person.objects.create(
                    tree=self.tree,
                    gedcom_id=raw_id,
                    first_name=first.strip() if first else "",
                    last_name=last.strip() if last else "",
                    gender=gender
                )
                people_map[raw_id] = person

                # Birth Event
                b_date_str, b_place, _ = element.get_birth_data()
                if b_date_str or b_place:
                    b_date_obj, b_year = self.parse_gedcom_date(b_date_str)
                    b_loc = self.get_or_create_location(b_place)
                    Event.objects.create(
                        tree=self.tree, person=person, event_type='BIRT',
                        date_string=b_date_str or '', parsed_date=b_date_obj, location=b_loc
                    )
                    person.birth_year = b_year

                # Death Event
                d_date_str, d_place, _ = element.get_death_data()
                if d_date_str or d_place:
                    d_date_obj, d_year = self.parse_gedcom_date(d_date_str)
                    d_loc = self.get_or_create_location(d_place)
                    Event.objects.create(
                        tree=self.tree, person=person, event_type='DEAT',
                        date_string=d_date_str or '', parsed_date=d_date_obj, location=d_loc
                    )
                    person.death_year = d_year

                person.save() # Save the quick-reference years

                # Other Facts
                ignore_tags = ['BIRT', 'DEAT', 'NAME', 'SEX', 'FAMS', 'FAMC']
                for child in element.get_child_elements():
                    tag = child.get_tag()
                    val = child.get_value()
                    if tag not in ignore_tags and val:
                        Fact.objects.create(person=person, key=tag, value=val)

        # ==========================================
        # PASS 2: Create Families & Links (FAM) - FIXED
        # ==========================================
        for element in elements:
            if element.get_tag() == 'FAM':
                fam_id = element.get_pointer().replace('@', '')

                husb_id = None
                wife_id = None
                child_ids = []
                marr_date_str = ''
                marr_plac_str = ''

                # Safely loop through all children instead of using the nonexistent method
                for child in element.get_child_elements():
                    tag = child.get_tag()
                    if tag == 'HUSB':
                        husb_id = child.get_value().replace('@', '')
                    elif tag == 'WIFE':
                        wife_id = child.get_value().replace('@', '')
                    elif tag == 'CHIL':
                        child_ids.append(child.get_value().replace('@', ''))
                    elif tag == 'MARR':
                        for m_child in child.get_child_elements():
                            if m_child.get_tag() == 'DATE':
                                marr_date_str = m_child.get_value()
                            elif m_child.get_tag() == 'PLAC':
                                marr_plac_str = m_child.get_value()

                husband = people_map.get(husb_id)
                wife = people_map.get(wife_id)

                # Create the Family Group
                family = FamilyGroup.objects.create(
                    tree=self.tree,
                    gedcom_id=fam_id,
                    husband=husband,
                    wife=wife
                )

                # Marriage Event
                if marr_date_str or marr_plac_str:
                    m_date_obj, _ = self.parse_gedcom_date(marr_date_str)
                    m_loc = self.get_or_create_location(marr_plac_str)

                    Event.objects.create(
                        tree=self.tree, family=family, event_type='MARR',
                        date_string=marr_date_str, parsed_date=m_date_obj, location=m_loc
                    )

                # Link Children
                for child_id in child_ids:
                    child_person = people_map.get(child_id)
                    if child_person:
                        ChildLink.objects.create(family=family, child=child_person)

        return self.tree