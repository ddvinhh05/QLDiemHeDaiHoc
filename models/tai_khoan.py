import sqlite3

from db_config import DB_PATH
from models.password_utils import hash_password, verify_password


class TaiKhoanModel:
    @staticmethod
    def _connect():
        return sqlite3.connect(DB_PATH)

    @classmethod
    def auth(cls, ten_dang_nhap, mat_khau):
        conn = cls._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT TenDangNhap, VaiTro, MatKhau FROM TAI_KHOAN WHERE TenDangNhap = ?",
            (ten_dang_nhap,),
        )
        row = cur.fetchone()
        conn.close()
        if not row or not verify_password(mat_khau, row[2]):
            return None
        return (row[0], row[1])

    @classmethod
    def get_all(cls):
        conn = cls._connect()
        cur = conn.cursor()
        cur.execute("SELECT TenDangNhap, VaiTro FROM TAI_KHOAN")
        rows = cur.fetchall()
        conn.close()
        return rows

    @classmethod
    def create(cls, ten_dang_nhap, mat_khau, vai_tro):
        conn = cls._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO TAI_KHOAN (TenDangNhap, MatKhau, VaiTro) VALUES (?, ?, ?)",
            (ten_dang_nhap, hash_password(mat_khau), vai_tro),
        )
        conn.commit()
        conn.close()

    @classmethod
    def update_role(cls, ten_dang_nhap, vai_tro):
        conn = cls._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE TAI_KHOAN SET VaiTro = ? WHERE TenDangNhap = ?",
            (vai_tro, ten_dang_nhap),
        )
        conn.commit()
        conn.close()

    @classmethod
    def update_password(cls, ten_dang_nhap, mat_khau):
        conn = cls._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE TAI_KHOAN SET MatKhau = ? WHERE TenDangNhap = ?",
            (hash_password(mat_khau), ten_dang_nhap),
        )
        conn.commit()
        conn.close()
