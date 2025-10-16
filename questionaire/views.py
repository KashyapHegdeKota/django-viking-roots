from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import QuestionaireService
import json


@csrf_exempt
def start_interview(request):
    """
    Get the initial welcome message
    Returns: initial greeting
    """
    if request.method == 'POST':
        try:
            service = QuestionaireService()
            initial_message = service.get_initial_message()
            
            return JsonResponse({
                'message': initial_message
            }, status=200)
            
        except Exception as e:
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def send_message(request):
    """
    Send a message and get AI response
    Expected payload: {
        "message": "user message here",
        "chat_history": [
            {"role": "model", "content": "..."},
            {"role": "user", "content": "..."},
            ...
        ]
    }
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
            chat_history = data.get('chat_history', [])
            
            if not user_message:
                return JsonResponse({
                    'error': 'Message cannot be empty'
                }, status=400)
            
            # Get AI response
            service = QuestionaireService()
            ai_response = service.get_response(chat_history, user_message)
            
            return JsonResponse({
                'message': ai_response
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'error': str(e)
            }, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)