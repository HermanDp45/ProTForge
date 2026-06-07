from pathlib import Path
import os

# BACKEND_DIR = Path(__file__).resolve().parent

# UPLOAD_DIR = BACKEND_DIR / "uploads"
# UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = Path(
    os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads")
).resolve()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)