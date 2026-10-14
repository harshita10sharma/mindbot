"""Central configuration. Every value can be overridden with an environment variable."""
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Model routing. Each Groq model has its own free-tier rate-limit bucket, so the
# analyzer/critic run on a different model than the responder to spread load.
RESPONDER_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
ANALYZER_MODEL = os.getenv("GROQ_ANALYZER_MODEL", "openai/gpt-oss-120b")
CRITIC_MODEL = os.getenv("GROQ_CRITIC_MODEL", "openai/gpt-oss-120b")
CRISIS_MODEL = os.getenv("GROQ_CRISIS_MODEL", "openai/gpt-oss-120b")  # rare but highest-stakes replies
SUMMARY_MODEL = os.getenv("GROQ_SUMMARY_MODEL", "openai/gpt-oss-120b")
JUDGE_MODEL = os.getenv("GROQ_JUDGE_MODEL", "openai/gpt-oss-120b")
GUARD_MODEL = os.getenv("GROQ_GUARD_MODEL", "meta-llama/llama-prompt-guard-2-86m")
TRANSCRIBE_MODEL = os.getenv("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo")

# Feature switches (set to "0" to disable a pipeline stage, e.g. to save tokens).
ENABLE_ANALYZER = os.getenv("ENABLE_ANALYZER", "1") == "1"
ENABLE_CRITIC = os.getenv("ENABLE_CRITIC", "1") == "1"
ENABLE_GUARD = os.getenv("ENABLE_GUARD", "1") == "1"

# Storage
DB_PATH = os.getenv("MINDBOT_DB_PATH", os.path.join(os.path.dirname(__file__), "mindbot.db"))
DATA_DIR = os.getenv("MINDBOT_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

# Conversation window sent to the responder (user+assistant turns).
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "8"))

# Optional shared secret for clinician endpoints. Empty = open (demo mode).
CLINICIAN_TOKEN = os.getenv("CLINICIAN_TOKEN", "")
