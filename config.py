import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DATABASE_URL = os.environ["DATABASE_URL"]

# Comma-separated list of allowed CORS origins, e.g. "https://a.com,https://b.com"
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOW_ORIGINS", "https://flipup-frontend.onrender.com").split(",")
    if origin.strip()
]
