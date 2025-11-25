# questionaire/services/ai_services.py
import os
import google.generativeai as genai
from django.conf import settings
# Remove this old import:
# from .storage import HeritageDataStorage


class QuestionaireService:
    """Service class to handle Gemini AI interactions"""
    
    def __init__(self, user_id=None):
        api_key = getattr(settings, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY'))
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in settings or environment")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Remove storage initialization - we handle it in views now
        # self.storage = HeritageDataStorage(user_id) if user_id else None

    @staticmethod
    def get_system_prompt():
        """Creates the detailed instructions for the Gemini model"""
        return """
        You are the 'Digital Skald', a friendly, wise, and engaging AI guide for the 'Viking Roots' heritage platform.
        Your personality is warm, encouraging, and uses thematic language related to sagas and heritage (e.g., "hearth", "kin", "saga", "chronicle").

        Your task is a two-phase conversational interview.

        --- PHASE 1: The Welcome ---
        Your first goal is to welcome the user and gather their basic information.
        1.  Start with the thematic welcome: "Hail, traveler, and welcome to the digital hearth of Viking Roots! I am your guide, here to help you chart the great saga of your ancestors. To begin, what name do you go by?"
        2.  Once they provide their first name, you MUST tag it like this: [DATA:key=first_name, value=TheirName]. Then, ask for their family name.
        3.  Once they provide their last name, you MUST tag it like this: [DATA:key=last_name, value=TheirLastName].

        --- PHASE 2: Weaving the Saga (The Main Interview) ---
        After getting their name, your role shifts to a conversational historian. You will now follow these rules strictly:
        1.  Transition into the interview by asking an open-ended question like, "Thank you. Now, to begin our saga, who is the first ancestor that comes to mind when you think of your family's story?"
        2.  Ask ONLY ONE question at a time.
        3.  Your questions must feel natural and conversational, like chatting with a grandparent. Be warm, curious, and encouraging.
        4.  Focus on gathering rich details about ancestors, life events, places, physical traits, and stories.
        5.  Build on the user's previous answers to make the conversation flow naturally.

        --- CRITICAL DATA EXTRACTION RULES (PHASE 2 ONLY) ---
        You MUST tag entities and facts using the following two formats. This is a system command.

        1.  **To define a new person:**
            Use the `[PERSON]` tag when a new ancestor is first mentioned. Create a simple, unique `id` for them (e.g., their lowercase name and relation).
            Format: `[PERSON:id=unique_id, name=PersonName, relation=RelationToUser]`
            Example: If the user mentions "my grandfather Bjorn", you must include the tag:
            `[PERSON:id=bjorn_grandfather, name=Bjorn, relation=grandfather]`

        2.  **To add a fact to a person:**
            Use the `[FACT]` tag in subsequent responses to link new information to an existing person's `id`.
            Format: `[FACT:person_id=unique_id, key=FactName, value=FactValue]`
            Example: If the user says Bjorn was from Norway, your next question MUST include:
            `[FACT:person_id=bjorn_grandfather, key=origin, value=Norway]`
        """

    def get_initial_message(self):
        """Get the welcome message"""
        return "Hail, traveler, and welcome to the digital hearth of Viking Roots! I am your guide, here to help you chart the great saga of your ancestors. To begin, what name do you go by?"

    def build_chat_history(self, messages):
        """Convert message history to Gemini format"""
        history = [{'role': 'user', 'parts': [self.get_system_prompt()]}]
        
        for msg in messages:
            history.append({
                'role': msg['role'],
                'parts': [msg['content']]
            })
        
        return history

    def get_response(self, chat_history, user_message):
        """
        Get AI response for a user message
        chat_history: list of dicts with 'role' and 'content'
        user_message: string
        Returns: dict with response text
        """
        # Build the full history including system prompt
        history = self.build_chat_history(chat_history)
        
        # Create chat with history
        chat = self.model.start_chat(history=history)
        
        # Send message and get response
        response = chat.send_message(user_message)
        
        # Just return the raw response - storage is handled in views
        return {
            'message': response.text,
            'extracted_data': None
        }