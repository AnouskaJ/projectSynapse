"""
LLM service (Gemini) wrapper
"""
from google import genai

from synapseBackendFlask.config import GEMINI_API_KEY, GEMINI_MODEL

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

class LLMWrapper:
    """Wrapper around Gemini API client"""
    
    def __init__(self, client, model):
        self.client = client
        self.model = model

    def generate_content(self, contents, **kwargs):
        """Generate content using Gemini"""
        if isinstance(contents, str):
            contents = [contents]
        return self.client.models.generate_content(
            model=self.model,
            contents=contents,
            **kwargs
        )

# Global LLM instance
llm = LLMWrapper(client, GEMINI_MODEL)