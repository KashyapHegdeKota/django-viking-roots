import json
import uuid
import os
import traceback
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.files.storage import FileSystemStorage

# Unified Services Import
from .services import (
    QuestionaireService, 
    DatabaseStorageService, 
    FamilyMatchingService, 
    FamilyTreeMergeService,
    GedcomImportService
)

# Unified Models Import
from .models import Ancestor, AncestorMatch, HeritageEvent, HeritageLocation
from django.contrib.auth.models import User

## TODO: Add @login_required decorator to all views in production

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
        user, _ = User.objects.get_or_create(username='testuser')
        return user


# --- INTERVIEW FLOW ---

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
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
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
                return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
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
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
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
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# --- DATA RETRIEVAL ---

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
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def get_family_tree(request):
    """Get structured family tree data for visualization"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            ancestors = Ancestor.objects.filter(user=user).prefetch_related('facts', 'media_tags__media')
            
            tree_data = []
            for ancestor in ancestors:
                photos = []
                for tag in ancestor.media_tags.all():
                    photos.append({
                        'url': tag.media.file.url,
                        'title': tag.media.title,
                        'box_x': tag.box_x,
                        'box_y': tag.box_y
                    })

                node = {
                    'id': ancestor.unique_id,
                    'name': ancestor.name,
                    'relation': ancestor.relation,
                    'gender': ancestor.gender,
                    'birth_year': ancestor.birth_year,
                    'birth_date': ancestor.birth_date.isoformat() if ancestor.birth_date else None,
                    'death_year': ancestor.death_year,
                    'origin': ancestor.origin,
                    'photos': photos
                }
                tree_data.append(node)
            
            return JsonResponse({
                'tree': tree_data,
                'total_ancestors': len(tree_data)
            }, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def get_timeline_data(request):
    """SPONSOR REQUIREMENT: Left-Aligned Chronological Timeline."""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            ancestors = Ancestor.objects.filter(user=user).exclude(birth_year__isnull=True)
            
            timeline_events = []
            
            for anc in ancestors:
                timeline_events.append({
                    'id': f"{anc.unique_id}_birth",
                    'year': anc.birth_year,
                    'date': anc.birth_date.isoformat() if anc.birth_date else None,
                    'title': f"Birth of {anc.name}",
                    'description': f"Born in {anc.birth_location.name if anc.birth_location else anc.origin or 'Unknown'}",
                    'type': 'birth',
                    'person_id': anc.unique_id
                })
                
                if anc.death_year:
                    timeline_events.append({
                        'id': f"{anc.unique_id}_death",
                        'year': anc.death_year,
                        'date': anc.death_date.isoformat() if anc.death_date else None,
                        'title': f"Passing of {anc.name}",
                        'type': 'death',
                        'person_id': anc.unique_id
                    })
                
                for participation in anc.events.all():
                    evt = participation.event
                    timeline_events.append({
                        'id': f"evt_{evt.id}_{anc.id}",
                        'year': evt.date_start.year if evt.date_start else None,
                        'date': evt.date_start.isoformat() if evt.date_start else None,
                        'title': evt.title,
                        'description': f"{anc.name} was a {participation.role}",
                        'type': 'event',
                        'person_id': anc.unique_id
                    })

            def sort_key(x):
                if x['date']: return x['date']
                if x['year']: return f"{x['year']}-01-01"
                return "0000-00-00"

            timeline_events.sort(key=sort_key)
            return JsonResponse({'timeline': timeline_events}, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# --- MANUAL MODIFICATIONS & IMPORTS (Tickets #156 & #161) ---

@csrf_exempt
def upload_gedcom(request):
    """Handle GEDCOM file uploads"""
    if request.method == 'POST' and request.FILES.get('file'):
        try:
            user = get_user_for_request(request)
            gedcom_file = request.FILES['file']
            
            fs = FileSystemStorage()
            filename = fs.save(gedcom_file.name, gedcom_file)
            file_path = fs.path(filename)
            
            importer = GedcomImportService(user)
            batch = importer.process_gedcom_file(file_path, gedcom_file.name)
            
            os.remove(file_path)
            return JsonResponse({'success': True, 'message': f'Successfully processed {batch.filename}'}, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'No file uploaded'}, status=400)


@csrf_exempt
def create_ancestor(request):
    """Create a new ancestor manually (POST)"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            data = json.loads(request.body)
            unique_id = data.get('id') or f"manual_{uuid.uuid4().hex[:8]}"
            
            ancestor = Ancestor.objects.create(
                user=user,
                unique_id=unique_id,
                name=data.get('name', 'Unknown Ancestor'),
                relation=data.get('relation', ''),
                gender=data.get('gender', ''),
                birth_year=data.get('birth_year'),
                death_year=data.get('death_year'),
                origin=data.get('origin', ''),
                source_type='manual'
            )
            return JsonResponse({'success': True, 'id': ancestor.unique_id}, status=201)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def manage_ancestor(request, ancestor_id):
    """Update (PUT) or Delete (DELETE) an existing ancestor"""
    user = get_user_for_request(request)
    try:
        ancestor = Ancestor.objects.get(user=user, unique_id=ancestor_id)
    except Ancestor.DoesNotExist:
        return JsonResponse({'error': 'Ancestor not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'name' in data: ancestor.name = data['name']
            if 'relation' in data: ancestor.relation = data['relation']
            if 'gender' in data: ancestor.gender = data['gender']
            if 'birth_year' in data: ancestor.birth_year = data['birth_year']
            if 'death_year' in data: ancestor.death_year = data['death_year']
            if 'origin' in data: ancestor.origin = data['origin']
            
            ancestor.save()
            return JsonResponse({'success': True, 'message': 'Ancestor updated'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        ancestor.delete()
        return JsonResponse({'success': True, 'message': 'Ancestor deleted'})
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def manage_event(request, event_id):
    """Update (PUT) or Delete (DELETE) a shared timeline event"""
    user = get_user_for_request(request)
    try:
        event = HeritageEvent.objects.get(id=event_id)
        if not event.participants.filter(ancestor__user=user).exists():
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except HeritageEvent.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'title' in data: event.title = data['title']
            if 'description' in data: event.description = data['description']
            if 'event_type' in data: event.event_type = data['event_type']
            
            event.save()
            return JsonResponse({'success': True, 'message': 'Event updated'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        event.delete()
        return JsonResponse({'success': True, 'message': 'Event deleted'})
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# --- COMMUNITY FEATURES (Sprint 9) ---

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