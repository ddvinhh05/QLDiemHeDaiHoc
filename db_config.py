from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "database" / "quanlydiem.db")
"""Đường dẫn SQLite tuyệt đối theo thư mục chứa file này (không phụ thuộc cwd)."""
import os

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_DIR = os.path.join(_PROJECT_DIR, "database")
os.makedirs(_DB_DIR, exist_ok=True)
DB_PATH = os.path.join(_DB_DIR, "quanlydiem.db")
