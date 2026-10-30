import os
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

BASE_URL = os.getenv("BASE_URL")
EMAIL = os.getenv("EMAIL", "")
PASSWORD = os.getenv("PASSWORD", "")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))
