import json
import uuid
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User

# Import AI Service from THIS app
from .services.ai_services import QuestionaireService

# IMPORT DATABASE STORAGE FROM THE CORE HERITAGE APP
from heritage.services.db_storage import DatabaseStorageService

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
            
            service = QuestionaireService()
            ai_response = service.get_response(chat_history, user_message)
            
            storage = DatabaseStorageService(user)
            cleaned_text, extracted_data = storage.extract_and_store_tags(ai_response['message'])
            
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
            
            storage.profile.interview_completed = True
            storage.profile.interview_completed_at = timezone.now()
            storage.profile.save()
            
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