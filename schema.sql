PRAGMA foreign_keys = ON;

-- =========================
-- 1) DANH MUC HOC KY
-- =========================
CREATE TABLE IF NOT EXISTS HOC_KY (
    HocKy INTEGER NOT NULL CHECK (HocKy IN (1, 2, 3)),
    NamHoc TEXT NOT NULL,
    TenHienThi TEXT,
    TrangThai TEXT NOT NULL DEFAULT 'DANG_DIEN_RA'
        CHECK (TrangThai IN ('DANG_DIEN_RA', 'DA_KET_THUC', 'CHUA_BAT_DAU')),
    NgayBatDau TEXT,
    NgayKetThuc TEXT,
    PRIMARY KEY (HocKy, NamHoc)
);

-- =========================
-- 2) TAI KHOAN / PHAN QUYEN
-- =========================
CREATE TABLE IF NOT EXISTS TAI_KHOAN (
    TenDangNhap TEXT PRIMARY KEY,
    MatKhau TEXT NOT NULL,
    VaiTro TEXT NOT NULL CHECK (VaiTro IN ('Admin', 'Giảng viên', 'Sinh viên')),
    TrangThai TEXT NOT NULL DEFAULT 'HOAT_DONG'
        CHECK (TrangThai IN ('HOAT_DONG', 'BI_KHOA')),
    SoLanSaiMK INTEGER NOT NULL DEFAULT 0 CHECK (SoLanSaiMK >= 0),
    LanDangNhapCuoi TEXT,
    TaoLuc TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CapNhatLuc TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- =========================
-- 3) DANH MUC DOI TUONG
-- =========================
CREATE TABLE IF NOT EXISTS GIANG_VIEN (
    MaGV TEXT PRIMARY KEY,
    HoTen TEXT NOT NULL,
    Khoa TEXT NOT NULL,
    Email TEXT,
    SoDienThoai TEXT,
    TrangThai TEXT NOT NULL DEFAULT 'DANG_CONG_TAC'
        CHECK (TrangThai IN ('DANG_CONG_TAC', 'NGHI_PHEP', 'NGHI_VIEC')),
    FOREIGN KEY (MaGV) REFERENCES TAI_KHOAN (TenDangNhap)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS SINH_VIEN (
    MSSV TEXT PRIMARY KEY,
    HoTen TEXT NOT NULL,
    Lop TEXT NOT NULL,
    Khoa TEXT,
    Email TEXT,
    NgaySinh TEXT,
    GioiTinh TEXT,
    TrangThai TEXT NOT NULL DEFAULT 'DANG_HOC'
        CHECK (TrangThai IN ('DANG_HOC', 'BAO_LUU', 'TOT_NGHIEP', 'THOI_HOC')),
    GPA10 REAL NOT NULL DEFAULT 0 CHECK (GPA10 >= 0 AND GPA10 <= 10),
    GPA4 REAL NOT NULL DEFAULT 0 CHECK (GPA4 >= 0 AND GPA4 <= 4),
    XepLoai TEXT NOT NULL DEFAULT 'Chưa có',
    FOREIGN KEY (MSSV) REFERENCES TAI_KHOAN (TenDangNhap)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS MON_HOC (
    MaMon TEXT PRIMARY KEY,
    TenMon TEXT NOT NULL,
    SoTinChi INTEGER NOT NULL CHECK (SoTinChi > 0),
    KhoaPhuTrach TEXT,
    HeSoCC REAL NOT NULL DEFAULT 0.1,
    HeSoGK REAL NOT NULL DEFAULT 0.3,
    HeSoCK REAL NOT NULL DEFAULT 0.6,
    CHECK (ROUND(HeSoCC + HeSoGK + HeSoCK, 2) = 1.0)
);

-- =========================
-- 3b) DANH MUC KHOA
-- =========================
CREATE TABLE IF NOT EXISTS KHOA (
    MaKhoa TEXT PRIMARY KEY,
    TenKhoa TEXT NOT NULL
);

-- =========================
-- 4) PHAN CONG GIANG DAY
-- =========================
CREATE TABLE IF NOT EXISTS PHAN_CONG (
    MaGV TEXT NOT NULL,
    MaMon TEXT NOT NULL,
    Lop TEXT,
    HocKy INTEGER NOT NULL CHECK (HocKy IN (1, 2, 3)),
    NamHoc TEXT NOT NULL,
    TrangThai TEXT NOT NULL DEFAULT 'DANG_DAY'
        CHECK (TrangThai IN ('DANG_DAY', 'DA_KET_THUC', 'DA_THU_HOI')),
    PRIMARY KEY (MaGV, MaMon, HocKy, NamHoc, Lop),
    FOREIGN KEY (MaGV) REFERENCES GIANG_VIEN (MaGV)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (MaMon) REFERENCES MON_HOC (MaMon)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (HocKy, NamHoc) REFERENCES HOC_KY (HocKy, NamHoc)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- =========================
-- 5) BANG DIEM
-- =========================
CREATE TABLE IF NOT EXISTS DIEM (
    MSSV TEXT NOT NULL,
    MaMon TEXT NOT NULL,
    HocKy INTEGER NOT NULL CHECK (HocKy IN (1, 2, 3)),
    NamHoc TEXT NOT NULL,
    CC REAL CHECK (CC >= 0 AND CC <= 10),
    GK REAL CHECK (GK >= 0 AND GK <= 10),
    CK REAL CHECK (CK >= 0 AND CK <= 10),
    DTB REAL CHECK (DTB >= 0 AND DTB <= 10),
    KetQua TEXT GENERATED ALWAYS AS (
        CASE WHEN DTB IS NOT NULL AND DTB >= 4 THEN 'DAT'
             WHEN DTB IS NOT NULL AND DTB < 4 THEN 'ROT'
             ELSE 'CHUA_CO'
        END
    ) VIRTUAL,
    DaKhoa INTEGER NOT NULL DEFAULT 0 CHECK (DaKhoa IN (0, 1)),
    NguoiNhap TEXT,
    LanCapNhatCuoi TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (MSSV, MaMon, HocKy, NamHoc),
    FOREIGN KEY (MSSV) REFERENCES SINH_VIEN (MSSV)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (MaMon) REFERENCES MON_HOC (MaMon)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (HocKy, NamHoc) REFERENCES HOC_KY (HocKy, NamHoc)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (NguoiNhap) REFERENCES GIANG_VIEN (MaGV)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- =========================
-- 6) NHAT KY HE THONG
-- =========================
CREATE TABLE IF NOT EXISTS NHAT_KY_HE_THONG (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    ThoiGian TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    TenDangNhap TEXT,
    VaiTro TEXT,
    LoaiSuKien TEXT NOT NULL,
    NoiDung TEXT NOT NULL,
    DiaChiIP TEXT,
    FOREIGN KEY (TenDangNhap) REFERENCES TAI_KHOAN (TenDangNhap)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- =========================
-- 7) CHI SO (INDEX)
-- =========================
CREATE INDEX IF NOT EXISTS IDX_SV_LOP ON SINH_VIEN (Lop);
CREATE INDEX IF NOT EXISTS IDX_GV_KHOA ON GIANG_VIEN (Khoa);
CREATE INDEX IF NOT EXISTS IDX_DIEM_MAMON ON DIEM (MaMon);
CREATE INDEX IF NOT EXISTS IDX_DIEM_HOCKY_NAMHOC ON DIEM (HocKy, NamHoc);
CREATE INDEX IF NOT EXISTS IDX_DIEM_MSSV ON DIEM (MSSV);
CREATE INDEX IF NOT EXISTS IDX_PC_GV ON PHAN_CONG (MaGV);
CREATE INDEX IF NOT EXISTS IDX_PC_MON ON PHAN_CONG (MaMon);
CREATE UNIQUE INDEX IF NOT EXISTS UQ_PHAN_CONG_SAFE
    ON PHAN_CONG (MaGV, MaMon, HocKy, NamHoc, COALESCE(Lop, ''));
CREATE INDEX IF NOT EXISTS IDX_NK_THOIGIAN ON NHAT_KY_HE_THONG (ThoiGian);

-- =========================
-- 8) TRIGGER CAP NHAT DTB
-- =========================
CREATE TRIGGER IF NOT EXISTS TRG_DIEM_SET_DTB_INSERT
AFTER INSERT ON DIEM
FOR EACH ROW
WHEN NEW.CC IS NOT NULL AND NEW.GK IS NOT NULL AND NEW.CK IS NOT NULL
BEGIN
    UPDATE DIEM
    SET DTB = ROUND(
            NEW.CC * COALESCE((SELECT HeSoCC FROM MON_HOC WHERE MaMon = NEW.MaMon), 0.1) +
            NEW.GK * COALESCE((SELECT HeSoGK FROM MON_HOC WHERE MaMon = NEW.MaMon), 0.3) +
            NEW.CK * COALESCE((SELECT HeSoCK FROM MON_HOC WHERE MaMon = NEW.MaMon), 0.6), 2
        ),
        LanCapNhatCuoi = datetime('now', 'localtime')
    WHERE MSSV = NEW.MSSV
      AND MaMon = NEW.MaMon
      AND HocKy = NEW.HocKy
      AND NamHoc = NEW.NamHoc;
END;

CREATE TRIGGER IF NOT EXISTS TRG_DIEM_SET_DTB_UPDATE
AFTER UPDATE OF CC, GK, CK ON DIEM
FOR EACH ROW
WHEN NEW.CC IS NOT NULL AND NEW.GK IS NOT NULL AND NEW.CK IS NOT NULL
BEGIN
    UPDATE DIEM
    SET DTB = ROUND(
            NEW.CC * COALESCE((SELECT HeSoCC FROM MON_HOC WHERE MaMon = NEW.MaMon), 0.1) +
            NEW.GK * COALESCE((SELECT HeSoGK FROM MON_HOC WHERE MaMon = NEW.MaMon), 0.3) +
            NEW.CK * COALESCE((SELECT HeSoCK FROM MON_HOC WHERE MaMon = NEW.MaMon), 0.6), 2
        ),
        LanCapNhatCuoi = datetime('now', 'localtime')
    WHERE MSSV = NEW.MSSV
      AND MaMon = NEW.MaMon
      AND HocKy = NEW.HocKy
      AND NamHoc = NEW.NamHoc;
END;

-- =========================
-- 9) TRIGGER CAP NHAT GPA
-- =========================
-- GPA: chỉ điểm đã công bố (DaKhoa=1), trọng số theo số tín chỉ môn học
CREATE TRIGGER IF NOT EXISTS TRG_GPA_AFTER_DIEM_INSERT
AFTER INSERT ON DIEM
FOR EACH ROW
WHEN NEW.DTB IS NOT NULL AND COALESCE(NEW.DaKhoa, 0) = 1
BEGIN
    UPDATE SINH_VIEN
    SET GPA10 = COALESCE((
            SELECT ROUND(SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3)), 2)
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = NEW.MSSV
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
        ), 0),
        GPA4 = COALESCE((
            SELECT ROUND(
                (SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))) * 0.4, 2
            )
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = NEW.MSSV
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
        ), 0),
        XepLoai = CASE
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 8.5 THEN 'Xuất sắc'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 7.0 THEN 'Giỏi'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 5.5 THEN 'Khá'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 4.0 THEN 'Trung bình'
            ELSE 'Yếu / Kém'
        END
    WHERE MSSV = NEW.MSSV;
END;

CREATE TRIGGER IF NOT EXISTS TRG_GPA_AFTER_DIEM_UPDATE
AFTER UPDATE OF DTB, DaKhoa ON DIEM
FOR EACH ROW
BEGIN
    UPDATE SINH_VIEN
    SET GPA10 = COALESCE((
            SELECT ROUND(SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3)), 2)
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = NEW.MSSV
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
        ), 0),
        GPA4 = COALESCE((
            SELECT ROUND(
                (SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))) * 0.4, 2
            )
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = NEW.MSSV
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
        ), 0),
        XepLoai = CASE
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 8.5 THEN 'Xuất sắc'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 7.0 THEN 'Giỏi'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 5.5 THEN 'Khá'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = NEW.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 4.0 THEN 'Trung bình'
            ELSE 'Yếu / Kém'
        END
    WHERE MSSV = NEW.MSSV;
END;

CREATE TRIGGER IF NOT EXISTS TRG_GPA_AFTER_DIEM_DELETE
AFTER DELETE ON DIEM
FOR EACH ROW
BEGIN
    UPDATE SINH_VIEN
    SET GPA10 = COALESCE((
            SELECT ROUND(SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3)), 2)
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = OLD.MSSV
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
        ), 0),
        GPA4 = COALESCE((
            SELECT ROUND(
                (SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))) * 0.4, 2
            )
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = OLD.MSSV
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
        ), 0),
        XepLoai = CASE
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = OLD.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 8.5 THEN 'Xuất sắc'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = OLD.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 7.0 THEN 'Giỏi'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = OLD.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 5.5 THEN 'Khá'
            WHEN COALESCE((
                SELECT SUM(d.DTB * COALESCE(m.SoTinChi, 3)) * 1.0 / SUM(COALESCE(m.SoTinChi, 3))
                FROM DIEM d LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                WHERE d.MSSV = OLD.MSSV AND COALESCE(d.DaKhoa, 0) = 1 AND d.DTB IS NOT NULL
            ), 0) >= 4.0 THEN 'Trung bình'
            ELSE 'Yếu / Kém'
        END
    WHERE MSSV = OLD.MSSV;
END;

-- =========================
-- 10) DU LIEU MAU TOI THIEU
-- =========================
INSERT OR IGNORE INTO HOC_KY (HocKy, NamHoc, TenHienThi, TrangThai)
VALUES
    (1, '2024-2025', 'Học kỳ 1 — 2024-2025', 'DANG_DIEN_RA'),
    (2, '2024-2025', 'Học kỳ 2 — 2024-2025', 'CHUA_BAT_DAU');

INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES
    ('CNTT', 'Công nghệ thông tin'),
    ('DULICH', 'Du lịch — Khách sạn');

-- =========================
-- 3c) DANH MUC LOP (lop chua co SV van dung cho phan cong / loc)
-- =========================
CREATE TABLE IF NOT EXISTS DANH_MUC_LOP (
    MaLop TEXT PRIMARY KEY
);
