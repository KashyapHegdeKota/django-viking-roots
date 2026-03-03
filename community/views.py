import json
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User

# Import from THIS app
from .models import AncestorMatch
from .services.matching_service import FamilyMatchingService
from .services.tree_merge_service import FamilyTreeMergeService

def get_user_for_request(request):
    """Get authenticated user or create test user"""
    if request.user.is_authenticated:
        return request.user
    else:
        user, _ = User.objects.get_or_create(username='testuser')
        return user

@csrf_exempt
def find_potential_matches(request):
    """Find potential family connections for current user"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            matching_service = FamilyMatchingService()
            
            matches = matching_service.suggest_ancestor_matches_for_user(user)
            connections = matching_service.find_family_connections(user)
            
            return JsonResponse({
                'potential_matches': [
                    {
                        'id': m.id,
                        'your_ancestor': m.ancestor1.name if m.ancestor1.user == user else m.ancestor2.name,
                        'their_ancestor': m.ancestor2.name if m.ancestor1.user == user else m.ancestor1.name,
                        'other_user': m.ancestor2.user.username if m.ancestor1.user == user else m.ancestor1.user.username,
                        'confidence': m.confidence_score,
                        'matching_attributes': m.matching_attributes
                    }
                    for m in matches
                ],
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
    """Confirm that two ancestors are the same person"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            match = get_object_or_404(AncestorMatch, id=match_id)
            
            if match.ancestor1.user != user and match.ancestor2.user != user:
                return JsonResponse({'error': 'Permission denied'}, status=403)
                
            match.status = 'confirmed'
            match.reviewed_by = user
            match.reviewed_at = timezone.now()
            match.save()
            
            matching_service = FamilyMatchingService()
            connection = matching_service.create_family_connection(
                match.ancestor1.user,
                match.ancestor2.user,
                matching_service.infer_user_relationship(
                    match.ancestor1.relation,
                    match.ancestor2.relation
                ),
                match.ancestor1.name,
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

@csrf_exempt
def get_merged_family_tree(request):
    """Get merged family tree for user and their connections"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user = get_user_for_request(request)
            
            user_ids = data.get('user_ids', [user.id])
            users = User.objects.filter(id__in=user_ids)
            
            merge_service = FamilyTreeMergeService(users)
            merged_tree = merge_service.build_merged_tree()
            
            return JsonResponse(merged_tree, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)