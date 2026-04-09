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

    @staticmethod
    def get_story_system_prompt():
        return """
        You are the 'Keeper of Tales', an attentive and encouraging AI listener for the 'Viking Roots' platform.
        Your goal is to help the user narrate a deep, meaningful story about their family or a specific ancestor.
        
        --- GUIDELINES ---
        1. Be an active listener. Use phrases like "How did that feel?", "What happened next?", and "What a remarkable memory."
        2. Focus on one story at a time. 
        3. Once you have a complete narrative, output a [STORY] tag.
        
        --- TAG ---
        [STORY:ancestor_name=Name, content=The full narrative text, context=Topic/Event]
        """

    def get_initial_message(self):
        return "Hail, traveler, and welcome to the digital hearth of Viking Roots! I am your guide, here to help you chart the great saga of your ancestors. To begin, what name do you go by?"

    def build_chat_history(self, messages, system_prompt=None):
        if system_prompt is None:
            system_prompt = self.get_system_prompt()
        history = [{'role': 'user', 'parts': [system_prompt]}]
        for msg in messages:
            history.append({'role': msg['role'], 'parts': [msg['content']]})
        return history

    def get_response(self, chat_history, user_message, mode='factual'):
        system_prompt = self.get_story_system_prompt() if mode == 'story' else self.get_system_prompt()
        history = self.build_chat_history(chat_history, system_prompt)
        chat = self.model.start_chat(history=history)
        response = chat.send_message(user_message)
        return {'message': response.text, 'extracted_data': None}

    def generate_dynamic_prompts(self, heritage_summary):
        prompt = f"""
        Based on this family heritage data: {heritage_summary}
        Generate 3 highly personalized, engaging story prompts for the user. 
        Focus on specific names, locations, or gaps.
        If no data is present, provide 3 general but evocative prompts about childhood, traditions, and family elders.
        Return ONLY a JSON list of 3 strings.
        """
        response = self.model.generate_content(prompt)
        try:
            import json
            # Clean up potential markdown formatting in response
            clean_text = response.text.strip().replace('```json', '').replace('```', '')
            return json.loads(clean_text)
        except:
            return [
                "What is your earliest childhood memory?",
                "What traditions did your family keep?",
                "Who was the storyteller in your family?"
            ]