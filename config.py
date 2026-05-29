import os
from dotenv import load_dotenv


# Support both common local env filenames.
load_dotenv(".env")
load_dotenv(".env.local")

base_directory = os.path.dirname(os.path.abspath(__file__))


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
OWNER_CELL_PHONE = os.getenv("OWNER_CELL_PHONE", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# Business-friendly name shown on the dashboard.
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Your Business")

database_env_value = os.getenv("DATABASE_FILE", "enterprise_leads.db")
if os.path.isabs(database_env_value):
    DATABASE_FILE = database_env_value
else:
    DATABASE_FILE = os.path.join(base_directory, database_env_value)

# When DATABASE_URL is set (e.g. a hosted Postgres in production) it takes
# priority over the local SQLite file. Left empty for local development.
DATABASE_URL = os.getenv("DATABASE_URL", "")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

