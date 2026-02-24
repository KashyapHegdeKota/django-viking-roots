# questionaire/services/matching_service.py
from django.db.models import Q
from django.contrib.auth.models import User
from ..models import Ancestor, AncestorMatch, FamilyConnection
from difflib import SequenceMatcher
import jellyfish

class FamilyMatchingService:
    """Finds potential family connections between users"""
    
    def __init__(self):
        self.name_similarity_threshold = 0.85
        self.match_confidence_threshold = 0.7
    
    def name_similarity(self, name1, name2):
        name1, name2 = name1.lower().strip(), name2.lower().strip()
        jaro = jellyfish.jaro_winkler_similarity(name1, name2)
        seq = SequenceMatcher(None, name1, name2).ratio()
        return max(jaro, seq)
    
    def find_matching_ancestors(self, ancestor, exclude_user=None):
        potential_matches = []
        other_ancestors = Ancestor.objects.exclude(user=ancestor.user)
        if exclude_user:
            other_ancestors = other_ancestors.exclude(user=exclude_user)
        
        for other_ancestor in other_ancestors:
            name_sim = self.name_similarity(ancestor.name, other_ancestor.name)
            if name_sim < self.name_similarity_threshold:
                continue
            
            matching_attrs = {}
            confidence_factors = [name_sim]
            
            if ancestor.birth_year and other_ancestor.birth_year:
                year_diff = abs(ancestor.birth_year - other_ancestor.birth_year)
                if year_diff <= 2:
                    matching_attrs['birth_year'] = True
                    confidence_factors.append(1.0)
                elif year_diff <= 5:
                    matching_attrs['birth_year'] = 'close'
                    confidence_factors.append(0.5)
            
            if ancestor.origin and other_ancestor.origin:
                origin_sim = self.name_similarity(ancestor.origin, other_ancestor.origin)
                if origin_sim > 0.8:
                    matching_attrs['origin'] = True
                    confidence_factors.append(origin_sim)
            
            # FIX: Properly handle the new HeritageLocation model mapping
            anc_loc = ancestor.birth_location.name if ancestor.birth_location else None
            other_loc = other_ancestor.birth_location.name if other_ancestor.birth_location else None
            
            if anc_loc and other_loc:
                place_sim = self.name_similarity(anc_loc, other_loc)
                if place_sim > 0.8:
                    matching_attrs['birth_place'] = True
                    confidence_factors.append(place_sim)
            
            confidence = sum(confidence_factors) / len(confidence_factors)
            if confidence >= self.match_confidence_threshold:
                potential_matches.append({
                    'ancestor': other_ancestor,
                    'confidence': confidence,
                    'matching_attributes': matching_attrs
                })
        
        return sorted(potential_matches, key=lambda x: x['confidence'], reverse=True)
    
    def suggest_ancestor_matches_for_user(self, user):
        user_ancestors = Ancestor.objects.filter(user=user)
        all_matches = []
        for ancestor in user_ancestors:
            matches = self.find_matching_ancestors(ancestor)
            for match in matches:
                existing = AncestorMatch.objects.filter(
                    Q(ancestor1=ancestor, ancestor2=match['ancestor']) |
                    Q(ancestor1=match['ancestor'], ancestor2=ancestor)
                ).first()
                if not existing:
                    ancestor_match = AncestorMatch.objects.create(
                        ancestor1=ancestor, ancestor2=match['ancestor'],
                        confidence_score=match['confidence'],
                        matching_attributes=match['matching_attributes'], status='suggested'
                    )
                    all_matches.append(ancestor_match)
        return all_matches
    
    def find_family_connections(self, user):
        connections = {}
        user_ancestors = Ancestor.objects.filter(user=user)
        matches = AncestorMatch.objects.filter(
            Q(ancestor1__in=user_ancestors) | Q(ancestor2__in=user_ancestors), status='confirmed'
        )
        for match in matches:
            other_ancestor = match.ancestor2 if match.ancestor1.user == user else match.ancestor1
            other_user = other_ancestor.user
            if other_user.id not in connections:
                connections[other_user.id] = {'user': other_user, 'shared_ancestors': [], 'relationship_hints': []}
            connections[other_user.id]['shared_ancestors'].append({
                'name': match.ancestor1.name,
                'relation_to_user1': match.ancestor1.relation,
                'relation_to_user2': match.ancestor2.relation,
            })
            rel_hint = self.infer_user_relationship(match.ancestor1.relation, match.ancestor2.relation)
            if rel_hint:
                connections[other_user.id]['relationship_hints'].append(rel_hint)
        return list(connections.values())
    
    def infer_user_relationship(self, relation1, relation2):
        relation1, relation2 = relation1.lower(), relation2.lower()
        if relation1 == relation2:
            if any(x in relation1 for x in ['parent', 'father', 'mother']): return 'siblings'
            elif 'grandparent' in relation1: return 'cousins'
            elif 'great-grandparent' in relation1: return 'second cousins'
        if ('parent' in relation1 and 'grandparent' in relation2) or ('grandparent' in relation1 and 'parent' in relation2):
            return 'parent-child'
        return 'related'
    
    def create_family_connection(self, user1, user2, connection_type, shared_ancestor_name, confidence):
        if user1.id > user2.id: user1, user2 = user2, user1
        connection, created = FamilyConnection.objects.get_or_create(
            user1=user1, user2=user2,
            defaults={'connection_type': connection_type, 'shared_ancestor_name': shared_ancestor_name, 'confidence_score': confidence}
        )
        return connection