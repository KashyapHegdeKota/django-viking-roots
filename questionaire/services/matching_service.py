# questionaire/services/matching_service.py
from django.db.models import Q
from django.contrib.auth.models import User
from ..models import Ancestor, AncestorMatch, FamilyConnection  # Use ..
from difflib import SequenceMatcher
import jellyfish


class FamilyMatchingService:
    """Finds potential family connections between users"""
    
    def __init__(self):
        self.name_similarity_threshold = 0.85
        self.match_confidence_threshold = 0.7
    
    def name_similarity(self, name1, name2):
        """Calculate similarity between two names"""
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        # Use Jaro-Winkler distance (good for names)
        jaro = jellyfish.jaro_winkler_similarity(name1, name2)
        
        # Also check substring matches
        seq = SequenceMatcher(None, name1, name2).ratio()
        
        return max(jaro, seq)
    
    def find_matching_ancestors(self, ancestor, exclude_user=None):
        """Find ancestors from other users that might be the same person"""
        potential_matches = []
        
        # Get all ancestors with similar names from other users
        other_ancestors = Ancestor.objects.exclude(user=ancestor.user)
        if exclude_user:
            other_ancestors = other_ancestors.exclude(user=exclude_user)
        
        for other_ancestor in other_ancestors:
            # Calculate name similarity
            name_sim = self.name_similarity(ancestor.name, other_ancestor.name)
            
            if name_sim < self.name_similarity_threshold:
                continue
            
            # Check matching attributes
            matching_attrs = {}
            confidence_factors = [name_sim]
            
            # Birth year match (exact or within 2 years)
            if ancestor.birth_year and other_ancestor.birth_year:
                year_diff = abs(ancestor.birth_year - other_ancestor.birth_year)
                if year_diff <= 2:
                    matching_attrs['birth_year'] = True
                    confidence_factors.append(1.0)
                elif year_diff <= 5:
                    matching_attrs['birth_year'] = 'close'
                    confidence_factors.append(0.5)
            
            # Origin match
            if ancestor.origin and other_ancestor.origin:
                origin_sim = self.name_similarity(ancestor.origin, other_ancestor.origin)
                if origin_sim > 0.8:
                    matching_attrs['origin'] = True
                    confidence_factors.append(origin_sim)
            
            # Birth place match
            if ancestor.birth_place and other_ancestor.birth_place:
                place_sim = self.name_similarity(ancestor.birth_place, other_ancestor.birth_place)
                if place_sim > 0.8:
                    matching_attrs['birth_place'] = True
                    confidence_factors.append(place_sim)
            
            # Calculate overall confidence
            confidence = sum(confidence_factors) / len(confidence_factors)
            
            if confidence >= self.match_confidence_threshold:
                potential_matches.append({
                    'ancestor': other_ancestor,
                    'confidence': confidence,
                    'matching_attributes': matching_attrs
                })
        
        return sorted(potential_matches, key=lambda x: x['confidence'], reverse=True)
    
    def suggest_ancestor_matches_for_user(self, user):
        """Find all potential matches for a user's ancestors"""
        user_ancestors = Ancestor.objects.filter(user=user)
        all_matches = []
        
        for ancestor in user_ancestors:
            matches = self.find_matching_ancestors(ancestor)
            for match in matches:
                # Check if match already exists
                existing = AncestorMatch.objects.filter(
                    Q(ancestor1=ancestor, ancestor2=match['ancestor']) |
                    Q(ancestor1=match['ancestor'], ancestor2=ancestor)
                ).first()
                
                if not existing:
                    # Create suggested match
                    ancestor_match = AncestorMatch.objects.create(
                        ancestor1=ancestor,
                        ancestor2=match['ancestor'],
                        confidence_score=match['confidence'],
                        matching_attributes=match['matching_attributes'],
                        status='suggested'
                    )
                    all_matches.append(ancestor_match)
        
        return all_matches
    
    def find_family_connections(self, user):
        """Find other users who might be related based on ancestor matches"""
        connections = {}
        
        # Get all ancestor matches involving this user
        user_ancestors = Ancestor.objects.filter(user=user)
        
        matches = AncestorMatch.objects.filter(
            Q(ancestor1__in=user_ancestors) | Q(ancestor2__in=user_ancestors),
            status='confirmed'
        )
        
        for match in matches:
            # Determine the other user
            other_ancestor = match.ancestor2 if match.ancestor1.user == user else match.ancestor1
            other_user = other_ancestor.user
            
            if other_user.id not in connections:
                connections[other_user.id] = {
                    'user': other_user,
                    'shared_ancestors': [],
                    'relationship_hints': []
                }
            
            connections[other_user.id]['shared_ancestors'].append({
                'name': match.ancestor1.name,
                'relation_to_user1': match.ancestor1.relation,
                'relation_to_user2': match.ancestor2.relation,
            })
            
            # Infer relationship between users
            rel_hint = self.infer_user_relationship(
                match.ancestor1.relation,
                match.ancestor2.relation
            )
            if rel_hint:
                connections[other_user.id]['relationship_hints'].append(rel_hint)
        
        return list(connections.values())
    
    def infer_user_relationship(self, relation1, relation2):
        """Infer relationship between two users based on shared ancestor"""
        relation1 = relation1.lower()
        relation2 = relation2.lower()
        
        # Same relation = likely siblings or cousins
        if relation1 == relation2:
            if 'parent' in relation1 or 'father' in relation1 or 'mother' in relation1:
                return 'siblings'
            elif 'grandparent' in relation1:
                return 'cousins'
            elif 'great-grandparent' in relation1:
                return 'second cousins'
        
        # One is parent, other is grandparent = parent-child
        if ('parent' in relation1 and 'grandparent' in relation2) or \
           ('grandparent' in relation1 and 'parent' in relation2):
            return 'parent-child'
        
        return 'related'
    
    def create_family_connection(self, user1, user2, connection_type, shared_ancestor_name, confidence):
        """Create a family connection between two users"""
        # Always put lower ID first for consistency
        if user1.id > user2.id:
            user1, user2 = user2, user1
        
        connection, created = FamilyConnection.objects.get_or_create(
            user1=user1,
            user2=user2,
            defaults={
                'connection_type': connection_type,
                'shared_ancestor_name': shared_ancestor_name,
                'confidence_score': confidence
            }
        )
        
        return connection