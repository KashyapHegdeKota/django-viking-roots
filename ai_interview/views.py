# ai_interview/views.py

import json
import uuid
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User

from .services.ai_services import QuestionaireService
from .models import InterviewSession
from heritage.services.db_storage import DatabaseStorageService


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def get_or_create_session_id(request) -> str:
    if 'interview_session_id' not in request.session:
        request.session['interview_session_id'] = str(uuid.uuid4())
    return request.session['interview_session_id']


def get_user_for_request(request) -> User:
    if request.user.is_authenticated:
        return request.user
    # Dev fallback — remove before production
    user, _ = User.objects.get_or_create(username='testuser')
    return user


def require_post(view_fn):
    """Simple decorator to reject non-POST requests cleanly."""
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)
        return view_fn(request, *args, **kwargs)
    return wrapper


# ------------------------------------------------------------------
# Views
# ------------------------------------------------------------------

@csrf_exempt
@require_post
def start_interview(request):
    """
    Initialises a new interview session and returns the opening message.
    Called once when the user lands on the interview page.
    """
    try:
        user = get_user_for_request(request)
        session_id = get_or_create_session_id(request)

        # If a session already exists and is incomplete, resume it
        existing = InterviewSession.objects.filter(
            user=user, completed=False
        ).order_by('-last_activity').first()

        if existing:
            return JsonResponse({
                'message': (
                    "Welcome back! It looks like we were in the middle of your saga. "
                    "Shall we continue where we left off?"
                ),
                'session_id': existing.session_id,
                'resuming': True,
                'chat_history': existing.chat_history,
            }, status=200)

        # Fresh session
        service = QuestionaireService()
        initial_message = service.get_initial_message()

        storage = DatabaseStorageService(user)
        storage.save_interview_session(
            session_id=session_id,
            chat_history=[{
                'role': 'model',
                'content': initial_message
            }]
        )

        return JsonResponse({
            'message': initial_message,
            'session_id': session_id,
            'resuming': False,
            'chat_history': [],
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_post
def send_message(request):
    """
    Receives a user message, gets AI response, extracts structured tags,
    persists everything, and returns the cleaned response.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    try:
        user_message = body.get('message', '').strip()
        chat_history = body.get('chat_history', [])
        session_id = body.get('session_id') or get_or_create_session_id(request)

        if not user_message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        user = get_user_for_request(request)

        # -- AI Response --
        service = QuestionaireService()
        result = service.get_response(chat_history, user_message)

        cleaned_message = result['message']
        extracted_data = result.get('extracted_data', {})

        # -- Persist structured data to heritage schema --
        storage = DatabaseStorageService(user)
        if extracted_data:
            storage.store_extracted_data(extracted_data)

        # -- Update session history --
        updated_history = chat_history + [
            {'role': 'user',  'content': user_message},
            {'role': 'model', 'content': cleaned_message},
        ]
        storage.save_interview_session(
            session_id=session_id,
            chat_history=updated_history,
        )

        return JsonResponse({
            'message': cleaned_message,
            'extracted_data': extracted_data,
            'session_id': session_id,
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_post
def complete_interview(request):
    """
    Marks the session as complete and triggers an S3 backup.
    Called when the user explicitly ends the interview.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    try:
        user = get_user_for_request(request)
        session_id = body.get('session_id') or get_or_create_session_id(request)

        # Mark session complete
        updated = InterviewSession.objects.filter(
            user=user,
            session_id=session_id
        ).update(completed=True)

        if not updated:
            return JsonResponse(
                {'error': 'Session not found. Cannot mark as complete.'},
                status=404
            )

        # Backup to S3
        storage = DatabaseStorageService(user)
        backup_url = storage.create_backup_to_s3()

        return JsonResponse({
            'success': True,
            'backup_url': backup_url,
            'message': 'Your saga has been saved to the archives.',
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_post
def get_session_history(request):
    """
    Returns the chat history for a given session.
    Useful for the frontend to restore state on page reload.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    try:
        user = get_user_for_request(request)
        session_id = body.get('session_id')

        if not session_id:
            return JsonResponse({'error': 'session_id is required'}, status=400)

        try:
            session = InterviewSession.objects.get(
                user=user,
                session_id=session_id
            )
        except InterviewSession.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        return JsonResponse({
            'session_id': session.session_id,
            'chat_history': session.chat_history,
            'completed': session.completed,
            'started_at': session.started_at.isoformat(),
            'last_activity': session.last_activity.isoformat(),
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)