import os
import secrets
import threading

from tinydb import Query, TinyDB

SECRET_KEY = secrets.token_hex(32)

ADMIN_PASSWORD = "your_admin_password"


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


db = TinyDB(os.path.join(BASE_DIR, "apps_pro.json"), encoding="utf-8")
Apps = Query()
db_lock = threading.Lock()


active_downloads = set()
active_downloads_lock = threading.Lock()
download_progress = {}
