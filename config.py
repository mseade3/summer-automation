import os
from dotenv import load_dotenv


# Support both common local env filenames.
load_dotenv(".env")
load_dotenv(".env.local")


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

DATABASE_FILE = os.getenv("DATABASE_FILE", "missed_call_text_back.db")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

