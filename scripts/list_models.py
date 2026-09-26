"""Print Gemini model ids available to your key. Pick AGENT_MODEL / JUDGE_MODEL from this list.
Then check your per-model limits at https://aistudio.google.com/rate-limit"""
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for m in client.models.list():
    actions = getattr(m, "supported_actions", None)
    if actions is None or "generateContent" in actions:
        print(m.name)
