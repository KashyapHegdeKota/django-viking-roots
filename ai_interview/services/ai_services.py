import os
import google.generativeai as genai
from django.conf import settings

class QuestionaireService:
    def __init__(self, user_id=None):
        api_key = getattr(settings, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY'))
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in settings or environment")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    @staticmethod
    def get_system_prompt():
        return """
        You are the 'Digital Skald', a friendly, wise, and engaging AI guide for the 'Viking Roots' heritage platform.
        Your task is a two-phase conversational interview.
        --- PHASE 1: The Welcome ---
        1. Start with: "Hail, traveler, and welcome to the digital hearth of Viking Roots! I am your guide. To begin, what name do you go by?"
        2. Tag first name: [DATA:key=first_name, value=Name]
        3. Tag last name: [DATA:key=last_name, value=LastName]
        --- PHASE 2: Weaving the Saga ---
        Ask open-ended questions about ancestors. Dig for DATES (YYYY-MM-DD) and LOCATIONS.
        --- TAGS ---
        1. [PERSON:id=unique_id, name=Name, relation=Relation, gender=M/F/O]
        2. [EVENT:title=Title, date=YYYY-MM-DD, location=LocationName, type=personal/community, person_id=unique_id]
        3. [FACT:person_id=unique_id, key=Key, value=Value]
        """

    def get_initial_message(self):
        return "Hail, traveler, and welcome to the digital hearth of Viking Roots! I am your guide, here to help you chart the great saga of your ancestors. To begin, what name do you go by?"

    def build_chat_history(self, messages):
        history = [{'role': 'user', 'parts': [self.get_system_prompt()]}]
        for msg in messages:
            history.append({'role': msg['role'], 'parts': [msg['content']]})
        return history

    def get_response(self, chat_history, user_message):
        history = self.build_chat_history(chat_history)
        chat = self.model.start_chat(history=history)
        response = chat.send_message(user_message)
        return {'message': response.text, 'extracted_data': None}