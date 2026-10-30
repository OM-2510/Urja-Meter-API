import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("URL")
EMAIL = os.getenv("USERNAME", "")
PASSWORD = os.getenv("PASSWORD", "")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

