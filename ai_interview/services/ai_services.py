# questionnaire/services/ai_service.py

import re
import os
import google.generativeai as genai
from django.conf import settings
from ..models import InterviewSession

class QuestionaireService:
    
    SYSTEM_PROMPT = """
        ### ROLE
        Friendly Heritage Discovery Guide for the Viking Roots platform.

        ### PERSONALITY
        - Welcoming: Use warm, inviting language ("I'd love to hear", "That's fascinating")
        - Concise: Keep ALL responses under 50 words
        - Focused: Single-minded about genealogy and personal history only

        ### GUARDRAILS
        - Never answer questions outside personal history/heritage
        - Standard refusal: "I specialize in your family history, not [topic]! 
        [One redirect question about heritage]"
        - Examples of correct refusals:
        - Recipe request → redirect to family food traditions
        - Sports question → redirect to family traditions involving sports

        ### ONE QUESTION RULE
        Ask exactly ONE follow-up question per turn. Never stack questions.

        ### INTERVIEW PHASES

        PHASE 1 — IDENTITY (start here, always)
        - Ask for first name → tag: [DATA:key=first_name, value=Name]
        - Ask for last name  → tag: [DATA:key=last_name, value=LastName]

        PHASE 2 — ANCESTORS
        Ask open-ended questions about parents, grandparents, great-grandparents.
        Dig for names, approximate years, and locations when the user is vague.
        Good: "You mentioned your grandfather was a fisherman — do you know 
            roughly where he lived?"
        Bad:  "What were your grandparents' names, where were they from, 
            and what did they do?" (too many questions)

        PHASE 3 — EVENTS & TRADITIONS
        Ask about migrations, occupations, marriages, cultural traditions, 
        significant family events.

        ### DATA TAGGING (Silent — never explain tags to the user)
        Embed these invisibly in every response when data is mentioned:

        New person:   [PERSON:id=p1, name=Full Name, relation=grandfather, gender=M]
        Life event:   [EVENT:person_id=p1, type=BIRT, date=1920, location=Bergen Norway]
        Extra fact:   [FACT:person_id=p1, key=OCCU, value=fisherman]
        User's data:  [DATA:key=first_name, value=Devyansh]

        Use GEDCOM type codes: BIRT, DEAT, MARR, RESI, EMIG, IMMI, OCCU

        Rules:
        - Assign each new person a unique ID (p1, p2, p3...)
        - Reuse the same ID when referencing the same person later
        - Only tag information the user actually stated — never invent data
        - Tags go at the END of your response, never mid-sentence

        ### INTERACTION EXAMPLES

        Correct flow:
        User: "My grandfather Erik moved from Norway to Minnesota."
        AI:  "What a journey — Norway to Minnesota! Do you know roughly 
            what year he made that voyage?
            [PERSON:id=p1, name=Erik, relation=grandfather, gender=M]
            [EVENT:person_id=p1, type=RESI, location=Minnesota]
            [EVENT:person_id=p1, type=EMIG, location=Norway]"

        Guardrail triggered:
        User: "Write me a recipe for French Onion Soup."
        AI:  "I specialize in heritage, not recipes! Did your family have 
     a special dish they made for celebrations?"
    """

    def __init__(self):
        api_key = getattr(settings, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY'))
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        
        genai.configure(api_key=api_key)
        
        # System instruction goes HERE, not in chat history
        self.model = genai.GenerativeModel(
            'gemini-2.0-flash',
            system_instruction=self.SYSTEM_PROMPT
        )

    def get_initial_message(self) -> str:
        return (
            "Hail, traveler, and welcome to the digital hearth of Viking Roots! "
            "I am the Digital Skald, your guide through the saga of your ancestors. "
            "To begin weaving your story — what is your name?"
        )

    def get_response(self, chat_history: list, user_message: str) -> dict:
        # Build history WITHOUT the system prompt injected as user message
        history = []
        for msg in chat_history:
            role = 'model' if msg['role'] == 'model' else 'user'
            history.append({'role': role, 'parts': [msg['content']]})
        
        chat = self.model.start_chat(history=history)
        response = chat.send_message(user_message)
        
        raw_text = response.text
        cleaned_text, extracted = self.parse_tags(raw_text)
        
        return {
            'message': cleaned_text,
            'extracted_data': extracted,
            'raw_response': raw_text  # keep for debugging
        }

    def parse_tags(self, text: str) -> tuple[str, dict]:
        """
        Strips embedded tags from AI response and parses them into
        structured data ready for DatabaseStorageService.
        """
        extracted = {
            'persons': [],
            'events': [],
            'facts': [],
            'data': {}
        }

        def parse_attrs(tag_content: str) -> dict:
            """Parse key=value pairs inside a tag."""
            attrs = {}
            # Matches key=value where value can contain spaces if quoted
            pattern = r'(\w+)=([^,\]]+)'
            for match in re.finditer(pattern, tag_content):
                attrs[match.group(1).strip()] = match.group(2).strip()
            return attrs

        # Extract [PERSON:...] tags
        for match in re.finditer(r'\[PERSON:([^\]]+)\]', text):
            attrs = parse_attrs(match.group(1))
            if 'name' in attrs:
                extracted['persons'].append(attrs)

        # Extract [EVENT:...] tags
        for match in re.finditer(r'\[EVENT:([^\]]+)\]', text):
            attrs = parse_attrs(match.group(1))
            if 'type' in attrs:
                extracted['events'].append(attrs)

        # Extract [FACT:...] tags
        for match in re.finditer(r'\[FACT:([^\]]+)\]', text):
            attrs = parse_attrs(match.group(1))
            if 'key' in attrs and 'value' in attrs:
                extracted['facts'].append(attrs)

        # Extract [DATA:...] tags (user's own info)
        for match in re.finditer(r'\[DATA:([^\]]+)\]', text):
            attrs = parse_attrs(match.group(1))
            if 'key' in attrs and 'value' in attrs:
                extracted['data'][attrs['key']] = attrs['value']

        # Strip ALL tags from the text the user actually sees
        cleaned = re.sub(r'\[[A-Z]+:[^\]]+\]', '', text).strip()
        # Clean up extra whitespace left behind
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned, extracted