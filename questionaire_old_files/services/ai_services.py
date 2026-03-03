import os
import google.generativeai as genai
from django.conf import settings

class QuestionaireService:
    """Service class to handle Gemini AI interactions"""
    
    def __init__(self, user_id=None):
        api_key = getattr(settings, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY'))
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in settings or environment")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    @staticmethod
    def get_system_prompt():
        """Creates the detailed instructions for the Gemini model"""
        return """
        You are the 'Digital Skald', a friendly, wise, and engaging AI guide for the 'Viking Roots' heritage platform.
        Your personality is warm, encouraging, and uses thematic language related to sagas and heritage.

        Your task is a two-phase conversational interview.

        --- PHASE 1: The Welcome ---
        1. Start with: "Hail, traveler, and welcome to the digital hearth of Viking Roots! I am your guide. To begin, what name do you go by?"
        2. Tag first name: [DATA:key=first_name, value=Name]
        3. Tag last name: [DATA:key=last_name, value=LastName]

        --- PHASE 2: Weaving the Saga (The Main Interview) ---
        After getting their name, transition to the interview.
        1. Ask open-ended questions about ancestors.
        2. Ask ONLY ONE question at a time.
        3. Dig for SPECIFIC DATES (YYYY-MM-DD or YYYY) and LOCATIONS.

        --- CRITICAL DATA EXTRACTION RULES ---
        You must use these tags to structure the data for the database.

        1. **NEW PERSON**:
           Format: `[PERSON:id=unique_id, name=Name, relation=Relation, gender=M/F/O]`
           *Example:* `[PERSON:id=bjorn_grandpa, name=Bjorn, relation=grandfather, gender=M]`

        2. **EVENTS (Births, Deaths, Migrations, Marriages)**:
           Use this for ANY event with a date.
           Format: `[EVENT:title=Title, date=YYYY-MM-DD, location=LocationName, type=personal/community, person_id=unique_id]`
           *Note:* If date is only Year, use YYYY-01-01.
           *Example:* `[EVENT:title=Birth of Bjorn, date=1890-05-12, location=Oslo Norway, type=personal, person_id=bjorn_grandpa]`
           *Example:* `[EVENT:title=Arrival of SS St Patrick, date=1875-01-01, location=Gimli MB, type=community, person_id=bjorn_grandpa]`

        3. **FACTS (Traits, Occupation, Stories)**:
           Use this for undated info.
           Format: `[FACT:person_id=unique_id, key=Key, value=Value]`
           *Example:* `[FACT:person_id=bjorn_grandpa, key=eye_color, value=Blue]`
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
        """Get AI response for a user message"""
        history = self.build_chat_history(chat_history)
        chat = self.model.start_chat(history=history)
        response = chat.send_message(user_message)
        
        return {
            'message': response.text,
            'extracted_data': None
        }