from django.db.models import Q
from django.contrib.auth.models import User
from difflib import SequenceMatcher
import jellyfish

# CROSS APP IMPORTS - Updated to use Person, TreeAccess, and Event!
from heritage.models import Person, TreeAccess, Event
from community.models import AncestorMatch, FamilyConnection

class FamilyMatchingService:
    def __init__(self):
        self.name_similarity_threshold = 0.85
        self.match_confidence_threshold = 0.7
    
    def name_similarity(self, name1, name2):
        name1, name2 = name1.lower().strip(), name2.lower().strip()
        if not name1 or not name2: return 0.0
        return max(jellyfish.jaro_winkler_similarity(name1, name2), SequenceMatcher(None, name1, name2).ratio())
    
    def _get_full_name(self, person):
        return f"{person.first_name} {person.last_name}".strip()

    def _get_user_trees(self, user):
        """Helper to get all trees a user has access to"""
        return [access.tree for access in TreeAccess.objects.filter(user=user)]

    def find_matching_persons(self, person, exclude_user=None):
        potential_matches = []
        person_name = self._get_full_name(person)
        if not person_name: return []

        # Find all trees the excluded user owns (so we don't match against ourselves)
        exclude_trees = self._get_user_trees(exclude_user) if exclude_user else []
        
        # Get all other people in the database, prefetching birth events for comparison
        other_persons = Person.objects.exclude(tree__in=exclude_trees).prefetch_related('events__location')
        
        for other_person in other_persons:
            other_name = self._get_full_name(other_person)
            name_sim = self.name_similarity(person_name, other_name)
            
            if name_sim < self.name_similarity_threshold: continue
            
            matching_attrs = {}
            confidence_factors = [name_sim]
            
            # Compare Birth Years
            if person.birth_year and other_person.birth_year:
                year_diff = abs(person.birth_year - other_person.birth_year)
                if year_diff <= 2: 
                    matching_attrs['birth_year'] = True
                    confidence_factors.append(1.0)
                elif year_diff <= 5: 
                    matching_attrs['birth_year'] = 'close'
                    confidence_factors.append(0.5)
            
            # Compare Birth Locations (via Event table)
            person_birth = person.events.filter(event_type='BIRT').first()
            other_birth = other_person.events.filter(event_type='BIRT').first()
            
            if person_birth and person_birth.location and other_birth and other_birth.location:
                place_sim = self.name_similarity(person_birth.location.name, other_birth.location.name)
                if place_sim > 0.8: 
                    matching_attrs['birth_place'] = True
                    confidence_factors.append(place_sim)
            
            confidence = sum(confidence_factors) / len(confidence_factors)
            if confidence >= self.match_confidence_threshold:
                potential_matches.append({
                    'person': other_person, 
                    'confidence': confidence, 
                    'matching_attributes': matching_attrs
                })
                
        return sorted(potential_matches, key=lambda x: x['confidence'], reverse=True)
    
    def suggest_ancestor_matches_for_user(self, user):
        user_trees = self._get_user_trees(user)
        user_persons = Person.objects.filter(tree__in=user_trees)
        
        all_matches = []
        for person in user_persons:
            matches = self.find_matching_persons(person, exclude_user=user)
            for match in matches:
                # Check if this match was already suggested
                existing = AncestorMatch.objects.filter(
                    Q(person1=person, person2=match['person']) | 
                    Q(person1=match['person'], person2=person)
                ).first()
                
                if not existing:
                    all_matches.append(AncestorMatch.objects.create(
                        person1=person, 
                        person2=match['person'], 
                        confidence_score=match['confidence'],
                        matching_attributes=match['matching_attributes'], 
                        status='suggested'
                    ))
        return all_matches
    
    def find_family_connections(self, user):
        connections = {}
        user_trees = self._get_user_trees(user)
        user_persons = Person.objects.filter(tree__in=user_trees)
        
        matches = AncestorMatch.objects.filter(
            Q(person1__in=user_persons) | Q(person2__in=user_persons), 
            status='confirmed'
        )
        
        for match in matches:
            # Figure out which person belongs to the OTHER user
            is_user1_ours = match.person1 in user_persons
            our_person = match.person1 if is_user1_ours else match.person2
            other_person = match.person2 if is_user1_ours else match.person1
            
            # Find the owner of the other person's tree
            other_access = other_person.tree.access_rules.filter(role='owner').first()
            if not other_access: continue
            other_user = other_access.user
            
            if other_user.id not in connections: 
                connections[other_user.id] = {
                    'user': other_user, 
                    'shared_ancestors': [], 
                    'relationship_hints': []
                }
                
            connections[other_user.id]['shared_ancestors'].append({
                'name': self._get_full_name(our_person)
            })
            
            connections[other_user.id]['relationship_hints'].append('related')
            
        return list(connections.values())
    
    def create_family_connection(self, user1, user2, connection_type, shared_ancestor_name, confidence):
        if user1.id > user2.id: user1, user2 = user2, user1
        conn, _ = FamilyConnection.objects.get_or_create(
            user1=user1, user2=user2, 
            defaults={
                'connection_type': connection_type, 
                'shared_ancestor_name': shared_ancestor_name, 
                'confidence_score': confidence
            }
        )
        return conn
    
    from heritage.models import Person

    def get_all_ancestors(person_id):
        query = """
        WITH RECURSIVE ancestor_path AS (
            SELECT id, first_name, last_name, 0 as generation
            FROM heritage_person
            WHERE id = %s
            UNION ALL
            ... (rest of the SQL logic from above) ...
        )
        SELECT * FROM ancestor_path;
        """
        
        # Django returns Person objects even from raw SQL!
        ancestors = Person.objects.raw(query, [person_id])
        return ancestors