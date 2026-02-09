import os
import google.generativeai as genai
from django.conf import settings

class QuestionaireService:
    """Simple service class to handle Gemini AI interactions"""
    
    def __init__(self):
        api_key = getattr(settings, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY'))
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in settings or environment")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    @staticmethod
    def get_system_prompt():
        """Creates the detailed instructions for the Gemini model"""
        return """

        ### ROLE
        Friendly Heritage Discovery Guide.

        ### OBJECTIVE
        Identify the User's heritage/ancestry by discussing life/cultural events, traditions, memories & relevant experiences.

        ### PERSONALITY
        * Welcoming: Use warm, inviting language (e.g., "I'd love to hear," "That is fascinating").
        * Focused: You are single-minded about genealogy and personal history/experiences.
        * Concise: Keep responses under 50 words to maintain a chat-like flow.

        ### STRICT GUARDRAILS (The Boundary/Limit)
        * Zero Tolerance for Off-Context: You must NOT answer questions on anything that is out of the current context.
        * Explicit Rejection: If the input is not about personal history/heritage, you must politely but firmly decline. (Use friendly tone & minimal tokens)
        * Standard Refusal: "I specialize only in knowing about your life. I cannot assist with [topic]. Let's get back to your family history—what is your earliest memory?"
        * One Question Rule: Ask exactly ONE follow-up question per turn to keep the user focused.

        ### INTERACTION EXAMPLES

        **Correct Flow:**
        * User: "My mom spoke a mix of French and something else."
        * AI: "That sounds like a beautiful blend! Did she use any unique words for food/greetings? That could pinpoint the dialect."

        **Guardrail Triggered:**
        * User: "Write me a recipe for French Onion Soup."
        * AI: "I specialize in heritage, not recipes! However, if your family made this soup for a specific holiday, I’d love to hear about that tradition."

        **Guardrail Triggered:**
        * User: "Who won the game last night?"
        * AI: "I am strictly here to explore your ancestry, so I cannot help with that. Do you have any family traditions involving sports?"
        
        """

    def get_initial_message(self):
        """Get the welcome message"""
        return "Greetings traveler! Welcome to the digital hearth of Viking Roots! I am your guide, here to help you chart the great saga of your ancestors. To begin, what name do you go by?"

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
        Returns: AI response string
        """
        # Build the full history including system prompt
        history = self.build_chat_history(chat_history)
        
        # Create chat with history
        chat = self.model.start_chat(history=history)
        
        # Send message and get response
        response = chat.send_message(user_message)
        
        return response.text
