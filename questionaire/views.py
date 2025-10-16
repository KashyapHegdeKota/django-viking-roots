from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .services import QuestionaireService

@api_view(['POST'])
@permission_classes([AllowAny])
def start_interview(request):
    """
    Get the initial welcome message
    Returns: initial greeting
    """
    try:
        service = QuestionaireService()
        initial_message = service.get_initial_message()
        
        return Response({
            'message': initial_message
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
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
    try:
        user_message = request.data.get('message', '').strip()
        chat_history = request.data.get('chat_history', [])
        
        if not user_message:
            return Response({
                'error': 'Message cannot be empty'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get AI response
        service = QuestionaireService()
        ai_response = service.get_response(chat_history, user_message)
        
        return Response({
            'message': ai_response
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)