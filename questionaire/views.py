# questionaire/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .services import QuestionaireService, DatabaseStorageService
from .models import Ancestor
import json
import uuid

##TODO Make login a requirement for all calls here. @login_required

def get_or_create_session_id(request):
    """Get or create a unique session ID"""
    if 'interview_session_id' not in request.session:
        request.session['interview_session_id'] = str(uuid.uuid4())
    return request.session['interview_session_id']


def get_user_for_request(request):
    """Get authenticated user or create test user"""
    if request.user.is_authenticated:
        return request.user
    else:
        # For testing without auth, create or use a test user
        from django.contrib.auth.models import User
        user, _ = User.objects.get_or_create(username='testuser')
        return user


@csrf_exempt
def start_interview(request):
    """Get the initial welcome message"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            
            session_id = get_or_create_session_id(request)
            service = QuestionaireService()
            initial_message = service.get_initial_message()
            
            # Initialize storage with actual user object
            storage = DatabaseStorageService(user)
            storage.profile.interview_started_at = timezone.now()
            storage.profile.save()
            
            return JsonResponse({
                'message': initial_message,
                'session_id': session_id
            }, status=200)
            
        except Exception as e:
            import traceback
            traceback.print_exc()  # This will show full error in console
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def send_message(request):
    """Send a message and get AI response with data extraction"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
            chat_history = data.get('chat_history', [])
            
            if not user_message:
                return JsonResponse({
                    'error': 'Message cannot be empty'
                }, status=400)
            
            user = get_user_for_request(request)
            
            # Get AI response
            service = QuestionaireService()
            ai_response = service.get_response(chat_history, user_message)
            
            # Extract and store data in database
            storage = DatabaseStorageService(user)
            cleaned_text, extracted_data = storage.extract_and_store_tags(ai_response['message'])
            
            # Save interview session
            session_id = get_or_create_session_id(request)
            updated_history = chat_history + [
                {'role': 'user', 'content': user_message},
                {'role': 'model', 'content': cleaned_text}
            ]
            storage.save_interview_session(session_id, updated_history)
            
            return JsonResponse({
                'message': cleaned_text,
                'extracted_data': extracted_data
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON'
            }, status=400)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def get_heritage_data(request):
    """Get all collected heritage data for the current user"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            storage = DatabaseStorageService(user)
            data = storage.get_all_heritage_data()
            
            return JsonResponse(data, status=200)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def complete_interview(request):
    """Mark interview as complete and create S3 backup"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            storage = DatabaseStorageService(user)
            
            # Mark as complete
            storage.profile.interview_completed = True
            storage.profile.interview_completed_at = timezone.now()
            storage.profile.save()
            
            # Create S3 backup
            backup_url = storage.create_backup_to_s3()
            
            return JsonResponse({
                'success': True,
                'backup_url': backup_url,
                'message': 'Interview completed and data backed up successfully'
            }, status=200)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def get_family_tree(request):
    """Get structured family tree data for visualization"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            ancestors = Ancestor.objects.filter(user=user).prefetch_related('facts')
            
            tree_data = []
            for ancestor in ancestors:
                node = {
                    'id': ancestor.unique_id,
                    'name': ancestor.name,
                    'relation': ancestor.relation,
                    'birth_year': ancestor.birth_year,
                    'death_year': ancestor.death_year,
                    'origin': ancestor.origin,
                }
                tree_data.append(node)
            
            return JsonResponse({
                'tree': tree_data,
                'total_ancestors': len(tree_data)
            }, status=200)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

# questionaire/views.py (add these)

@csrf_exempt
def find_potential_matches(request):
    """Find potential family connections for current user"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            
            matching_service = FamilyMatchingService()
            
            # Find ancestor matches
            matches = matching_service.suggest_ancestor_matches_for_user(user)
            
            # Find family connections
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
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def confirm_ancestor_match(request, match_id):
    """Confirm that two ancestors are the same person"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            
            match = AncestorMatch.objects.get(id=match_id)
            match.status = 'confirmed'
            match.reviewed_by = user
            match.reviewed_at = timezone.now()
            match.save()
            
            # Create family connection if not exists
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
            import traceback
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
            
            # Get list of user IDs to include in merge
            user_ids = data.get('user_ids', [user.id])
            users = User.objects.filter(id__in=user_ids)
            
            # Build merged tree
            merge_service = FamilyTreeMergeService(users)
            merged_tree = merge_service.build_merged_tree()
            
            return JsonResponse(merged_tree, status=200)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)