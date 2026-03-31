import json
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Q

# Import from THIS app
from .models import (
    AncestorMatch, Post, PostLike, Comment,
    Group, GroupMembership, GroupPost,
)
from .services.matching_service import FamilyMatchingService

def get_user_for_request(request):
    """Get authenticated user or create test user"""
    if request.user.is_authenticated:
        return request.user
    else:
        user, _ = User.objects.get_or_create(username='testuser')
        return user

def _get_person_owner(person):
    """Finds the user who owns the tree this person belongs to."""
    access = person.tree.access_rules.filter(role='owner').first()
    return access.user if access else None

def _get_person_name(person):
    """Safely constructs the full name from the new schema."""
    return f"{person.first_name} {person.last_name}".strip() or "Unknown"


@csrf_exempt
def find_potential_matches(request):
    """Find potential family connections for current user"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            matching_service = FamilyMatchingService()
            
            matches = matching_service.suggest_ancestor_matches_for_user(user)
            connections = matching_service.find_family_connections(user)
            
            potential_matches_data = []
            for m in matches:
                user1 = _get_person_owner(m.person1)
                user2 = _get_person_owner(m.person2)
                
                potential_matches_data.append({
                    'id': m.id,
                    'your_ancestor': _get_person_name(m.person1) if user1 == user else _get_person_name(m.person2),
                    'their_ancestor': _get_person_name(m.person2) if user1 == user else _get_person_name(m.person1),
                    'other_user': user2.username if user1 == user else (user1.username if user1 else 'Unknown'),
                    'confidence': m.confidence_score,
                    'matching_attributes': m.matching_attributes
                })
            
            return JsonResponse({
                'potential_matches': potential_matches_data,
                'family_connections': [
                    {
                        'user': conn['user'].username,
                        'shared_ancestors': conn['shared_ancestors'],
                        'likely_relationship': conn['relationship_hints'][0] if conn['relationship_hints'] else 'related'
                    }
                    for conn in connections
                ]
            }, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def confirm_ancestor_match(request, match_id):
    """Confirm that two persons are the same person"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            match = get_object_or_404(AncestorMatch, id=match_id)
            
            user1 = _get_person_owner(match.person1)
            user2 = _get_person_owner(match.person2)
            
            if user1 != user and user2 != user:
                return JsonResponse({'error': 'Permission denied'}, status=403)
                
            match.status = 'confirmed'
            match.reviewed_by = user
            match.reviewed_at = timezone.now()
            match.save()
            
            matching_service = FamilyMatchingService()
            connection = matching_service.create_family_connection(
                user1,
                user2,
                "Relative", # Hardcoded default since graph tracing handles specifics now
                _get_person_name(match.person1),
                match.confidence_score
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Match confirmed and family connection created'
            }, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)
