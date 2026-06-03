"""Đường dẫn CSDL SQLite — luôn theo thư mục dự án, không phụ thuộc cwd."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DB_DIR / "quanlydiem.db")
