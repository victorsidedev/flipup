import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DATABASE_URL = os.environ["DATABASE_URL"]
