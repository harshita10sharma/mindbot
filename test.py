import os
from dotenv import load_dotenv
from chat_engine import get_response

load_dotenv()
print("Key prefix:", (os.getenv("GROQ_API_KEY") or "")[:4] + "...")

session_id = "test_001"
query = "I feel overwhelmed. Give me two gentle, practical coping tips."
resp = get_response(session_id, query)
print("\nAI Response:\n", resp)
