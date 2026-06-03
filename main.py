import sys
import csv
import sqlite3
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta, date
import time

from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QDate, QEvent, Qt
from PyQt6.QtGui import QBrush, QColor, QPixmap

from models.gpa_utils import (
    compute_published_gpa,
    hoc_luc_tu_gpa10 as _gpa_hoc_luc,
    recalc_all_student_gpa,
    sync_student_gpa_record,
)
from models.password_utils import hash_password, is_password_hashed, verify_password
from models.tai_khoan import TaiKhoanModel
from ui_charts import GradeChartHost
from views.admin.admin_view import Ui_AdminDashboard
from views.giang_vien.gv_view import Ui_GVDashboard
from views.shared.login_view import Ui_MainWindow as Ui_Login
from views.sinh_vien.sv_view import Ui_SVDashboard

from db_config import DB_PATH
from report_export import export_to_excel, export_to_pdf


def _hoc_luc_tu_gpa10(gpa10):
    return _gpa_hoc_luc(gpa10)


def _published_gpa_stats(mssv):
    """GPA / xếp loại: điểm đã công bố, trọng số theo tín chỉ."""
    return compute_published_gpa(mssv, fetch_all)


def _wrap_report_page_in_scroll(page_widget, page_layout, chart_widget=None, table_widgets=()):
    """Đưa toàn bộ nội dung tab báo cáo vào QScrollArea — cuộn xem biểu đồ phía dưới."""
    if getattr(page_widget, "_reportScrollDone", False):
        return
    exp_h = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    pref = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    table_set = set(table_widgets)

    pending = []
    while page_layout.count():
        pending.append(page_layout.takeAt(0))

    if chart_widget is not None:
        chart_widget.setParent(None)

    scroll = QScrollArea(parent=page_widget)
    scroll.setObjectName("scrollBaoCao")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    content = QWidget()
    content.setObjectName("scrollBaoCaoContent")
    inner = QVBoxLayout(content)
    inner.setSpacing(10)
    inner.setContentsMargins(2, 2, 2, 16)

    for item in pending:
        if item is None:
            continue
        w = item.widget()
        lo = item.layout()
        if w is not None:
            if w in table_set or isinstance(w, QTableWidget):
                w.setMinimumHeight(130)
                w.setMaximumHeight(185)
                w.setSizePolicy(exp_h)
                w.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            inner.addWidget(w)
        elif lo is not None:
            wrap = QWidget()
            wrap.setLayout(lo)
            if lo.objectName() in ("rowPanelsBaoCao", "rowPanelsBaoCao2"):
                wrap.setMinimumHeight(155)
                wrap.setMaximumHeight(195)
                wrap.setSizePolicy(exp_h)
                for i in range(lo.count()):
                    lo.setStretch(i, 1)
                    cw = lo.itemAt(i).widget()
                    if isinstance(cw, QTableWidget):
                        cw.setMinimumHeight(120)
                        cw.setMaximumHeight(175)
                        cw.setSizePolicy(exp_h)
            elif lo.objectName() == "bcMainSplit":
                wrap.setMinimumHeight(340)
                wrap.setSizePolicy(
                    QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                )
                for i in range(lo.count()):
                    lo.setStretch(i, 1)
                    fr = lo.itemAt(i).widget()
                    fl = fr.layout() if fr is not None else None
                    if fl is None:
                        continue
                    for j in range(fl.count()):
                        it = fl.itemAt(j)
                        tw = it.widget() if it else None
                        if isinstance(tw, QTableWidget):
                            tw.setMinimumHeight(100)
                            tw.setMaximumHeight(160)
                            tw.setSizePolicy(exp_h)
                            fl.setStretch(j, 1)
            inner.addWidget(wrap)

    if chart_widget is not None:
        chart_widget.setMinimumHeight(200)
        chart_widget.setMaximumHeight(260)
        chart_widget.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        )
        inner.addWidget(chart_widget)

    scroll.setWidget(content)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.addWidget(scroll)
    page_layout.setStretch(0, 1)
    setattr(page_widget, "_reportScrollDone", True)


def _configure_gv_bao_cao_page(ui, chart_widget=None):
    tables = (
        ui.tbBaoCaoTheoLop,
        ui.tbBaoCaoDtbLop,
        ui.tbBaoCaoPhanBo,
        ui.tbBaoCaoCanhBao,
        ui.tbBaoCaoXuat,
    )
    _wrap_report_page_in_scroll(
        ui.pageBaoCao,
        ui.pageBaoCaoLayout,
        chart_widget=chart_widget,
        table_widgets=tables,
    )


def _configure_admin_bao_cao_page(ui, chart_widget=None):
    tables = (
        ui.tbBcTheoLop,
        ui.tbBcPhanBo,
        ui.tbBcKhoa,
        ui.tbBcXuat,
    )
    split = getattr(ui, "bcMainSplit", None)
    if split is not None:
        for i in range(split.count()):
            split.setStretch(i, 1)
    for fname in ("frameBcLeft", "frameBcCenter", "frameBcRight"):
        frame = getattr(ui, fname, None)
        if frame is not None:
            frame.setMinimumWidth(200)
    _wrap_report_page_in_scroll(
        ui.pageBaoCaoAdmin,
        ui.pageBaoCaoAdminLayout,
        chart_widget=chart_widget,
        table_widgets=tables,
    )


def migrate_plain_passwords_to_hash():
    if not table_exists("TAI_KHOAN"):
        return
    for user, pwd in fetch_all("SELECT TenDangNhap, MatKhau FROM TAI_KHOAN"):
        if pwd and not is_password_hashed(str(pwd)):
            execute_query(
                "UPDATE TAI_KHOAN SET MatKhau = ? WHERE TenDangNhap = ?",
                (hash_password(str(pwd)), user),
            )


def _goi_y_gpa_chan(gpa10):
    g = float(gpa10 or 0)
    if g < 8.5:
        gap = max(0.0, 8.5 - g)
        return f"Cần thêm {gap:.2f} điểm để đạt học lực Xuất sắc (≥ 8.5)."
    gap_top = max(0.0, 10.0 - g)
    return f"Cần thêm {gap_top:.2f} điểm nữa để đạt tối đa thang 10 (nếu còn môn học)."


def fetch_all(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def execute_query(query, params=()):
    last_error = None
    for attempt in range(3):
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            cur = conn.cursor()
            cur.execute(query, params)
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            last_error = e
            if "locked" not in str(e).lower() or attempt == 2:
                raise
            time.sleep(0.25 * (attempt + 1))
        finally:
            if conn is not None:
                conn.close()
    if last_error:
        raise last_error


def log_event(username, role, event_type, content):
    if not table_exists("NHAT_KY_HE_THONG"):
        return
    try:
        execute_query(
            """
            INSERT INTO NHAT_KY_HE_THONG (TenDangNhap, VaiTro, LoaiSuKien, NoiDung)
            VALUES (?, ?, ?, ?)
            """,
            (username, role, event_type, content),
        )
    except Exception:
        return


def table_exists(table_name):
    rows = fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return bool(rows)


def _admin_active_hoc_ky_row():
    """Học kỳ ưu tiên: đang diễn ra; nếu không có thì lấy mới nhất."""
    if not table_exists("HOC_KY"):
        return None
    r = fetch_all(
        """
        SELECT HocKy, NamHoc, NgayKetThuc
        FROM HOC_KY
        WHERE TrangThai = 'DANG_DIEN_RA'
        ORDER BY NamHoc DESC, HocKy DESC
        LIMIT 1
        """
    )
    if r:
        return r[0]
    r = fetch_all(
        """
        SELECT HocKy, NamHoc, NgayKetThuc
        FROM HOC_KY
        ORDER BY NamHoc DESC, HocKy DESC
        LIMIT 1
        """
    )
    return r[0] if r else None


def _days_from_today_date_str(s):
    if not s:
        return None
    t = str(s).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(t, fmt).date()
            return (d - date.today()).days
        except ValueError:
            continue
    return None


def normalize_role_text(role_text):
    """Chuẩn hóa vai trò (bỏ dấu) để so khớp « Giảng viên » / « Sinh viên » ổn định."""
    if role_text is None:
        return ""
    text = str(role_text).strip().lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d")


def role_is_admin(role_text):
    n = normalize_role_text(role_text)
    return "admin" in n


def role_is_giang_vien(role_text):
    n = normalize_role_text(role_text).replace(" ", "")
    return "giangvien" in n


def role_is_sinh_vien(role_text):
    n = normalize_role_text(role_text).replace(" ", "")
    return "sinhvien" in n


def _import_sv_col_key(cell):
    t = str(cell or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").replace(" ", "")


def _import_sv_row_is_header(row):
    if not row:
        return False
    k0 = _import_sv_col_key(row[0])
    if k0 in ("mssv", "ma", "masinhvien", "masv", "tendangnhap", "username", "taikhoan", "madangnhap"):
        return True
    known = 0
    for c in row:
        k = _import_sv_col_key(c)
        if k in (
            "mssv",
            "ma",
            "masv",
            "hoten",
            "hovaten",
            "lop",
            "khoa",
            "email",
            "vaitro",
            "trangthai",
            "matkhau",
            "password",
            "mk",
        ):
            known += 1
    return known >= 2


def _import_sv_header_column_map(header_row):
    """Ánh xạ tên cột (tiếng Việt/Anh) -> chỉ số cột cho file export đầy đủ."""
    out = {"mssv": None, "hoten": None, "lop": None, "khoa": None, "matkhau": None}
    for i, cell in enumerate(header_row):
        k = _import_sv_col_key(cell)
        if not k:
            continue
        if out["mssv"] is None and k in (
            "mssv",
            "ma",
            "masv",
            "masinhvien",
            "username",
            "tendangnhap",
            "taikhoan",
            "madangnhap",
        ):
            out["mssv"] = i
        elif out["hoten"] is None and (
            k in ("hoten", "hovaten", "ten", "name") or "hoten" in k or "hovaten" in k
        ):
            out["hoten"] = i
        elif out["lop"] is None and (
            k in ("lop", "malop", "tenlop", "lopmon", "lopchuyennganh")
            and "vaitro" not in k
            and "role" not in k
        ):
            out["lop"] = i
        elif out["khoa"] is None and k in ("khoa", "tenkhoa", "makhoa", "khoaphutrach", "nganh", "donvi"):
            out["khoa"] = i
        elif out["matkhau"] is None and k in ("matkhau", "password", "mk", "matkh", "pass", "matkhausv"):
            out["matkhau"] = i
    return out


def _import_sv_cell_str(row, idx):
    if idx >= len(row) or row[idx] is None:
        return ""
    v = row[idx]
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def _fetch_khoa_display_map():
    """MaKhoa -> TenKhoa (để hiển thị tên đầy đủ thay cho mã tắt)."""
    if not table_exists("KHOA"):
        return {}
    try:
        return {str(ma).strip(): str(ten or ma).strip() for ma, ten in fetch_all("SELECT MaKhoa, TenKhoa FROM KHOA")}
    except Exception:
        return {}


def _khoa_display_name(raw_ma_or_ten, d):
    x = str(raw_ma_or_ten or "").strip()
    if not x:
        return "—"
    if x in d:
        t = d[x].strip()
        return t if t else x
    for ma, ten in d.items():
        if str(ten).strip() == x:
            return str(ten).strip() or x
    return x


def _khoa_canonical_key(raw_ma_or_ten, d):
    """Chuẩn hóa về MaKhoa để so khớp bộ lọc (mã hoặc tên đều ra cùng mã)."""
    x = str(raw_ma_or_ten or "").strip()
    if not x:
        return ""
    if x in d:
        return x
    for ma, ten in d.items():
        if str(ten).strip() == x:
            return ma
    return x


def ensure_danh_muc_lop_table():
    """Bang ma lop doc lap; dong bo tu SINH_VIEN."""
    try:
        execute_query(
            """
            CREATE TABLE IF NOT EXISTS DANH_MUC_LOP (
                MaLop TEXT PRIMARY KEY
            )
            """
        )
    except Exception:
        return
    try:
        execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", ("CNTT14.C.1",))
    except Exception:
        pass
    if not table_exists("SINH_VIEN"):
        return
    try:
        for (lop,) in fetch_all(
            "SELECT DISTINCT trim(Lop) FROM SINH_VIEN WHERE Lop IS NOT NULL AND trim(Lop) <> ''"
        ):
            if lop:
                execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (lop,))
    except Exception:
        pass


def ensure_khoa_master_table():
    """Bảng danh mục KHOA (mã + tên); đồng bộ mã đang dùng ở GIANG_VIEN."""
    try:
        execute_query(
            """
            CREATE TABLE IF NOT EXISTS KHOA (
                MaKhoa TEXT PRIMARY KEY,
                TenKhoa TEXT NOT NULL
            )
            """
        )
    except Exception:
        return
    for ma, ten in (("CNTT", "Công nghệ thông tin"), ("DULICH", "Du lịch — Khách sạn")):
        try:
            execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (ma, ten))
        except Exception:
            pass
    if not table_exists("GIANG_VIEN"):
        return
    try:
        for (ma,) in fetch_all(
            "SELECT DISTINCT trim(Khoa) FROM GIANG_VIEN WHERE Khoa IS NOT NULL AND trim(Khoa) <> ''"
        ):
            if ma:
                execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (ma, ma))
    except Exception:
        pass


def ensure_diem_danh_table():
    """Bảng điểm danh theo từng buổi học của môn/lớp/học kỳ."""
    try:
        execute_query(
            """
            CREATE TABLE IF NOT EXISTS DIEM_DANH (
                MSSV TEXT NOT NULL,
                MaMon TEXT NOT NULL,
                HocKy INTEGER NOT NULL,
                NamHoc TEXT NOT NULL,
                NgayHoc TEXT NOT NULL,
                CoMat INTEGER NOT NULL DEFAULT 1 CHECK (CoMat IN (0, 1)),
                NguoiDiemDanh TEXT,
                LanCapNhat TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                PRIMARY KEY (MSSV, MaMon, HocKy, NamHoc, NgayHoc)
            )
            """
        )
    except Exception:
        return
    try:
        execute_query(
            "CREATE INDEX IF NOT EXISTS IDX_DD_MON_HK ON DIEM_DANH (MaMon, HocKy, NamHoc, NgayHoc)"
        )
    except Exception:
        pass


def bootstrap_database():
    schema_path = Path(DB_PATH).resolve().parent / "schema.sql"
    if not schema_path.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    cur.executescript(schema_path.read_text(encoding="utf-8"))

    # Đồng bộ profile cơ bản cho tài khoản vai trò.
    cur.execute(
        """
        INSERT OR IGNORE INTO GIANG_VIEN (MaGV, HoTen, Khoa)
        SELECT TenDangNhap, TenDangNhap, 'CNTT'
        FROM TAI_KHOAN
        WHERE VaiTro = 'Giảng viên'
        """
    )
    conn.commit()
    conn.close()
    ensure_khoa_master_table()
    ensure_danh_muc_lop_table()
    ensure_diem_danh_table()
    migrate_plain_passwords_to_hash()
    conn2 = sqlite3.connect(DB_PATH)
    conn2.execute("PRAGMA foreign_keys = ON")
    cur2 = conn2.cursor()
    cur2.execute(
        """
        INSERT OR IGNORE INTO TAI_KHOAN
            (TenDangNhap, MatKhau, VaiTro, TrangThai, SoLanSaiMK, TaoLuc, CapNhatLuc)
        SELECT MSSV, ?, 'Sinh viên', 'HOAT_DONG', 0, datetime('now', 'localtime'), datetime('now', 'localtime')
        FROM SINH_VIEN
        WHERE MSSV NOT IN (SELECT TenDangNhap FROM TAI_KHOAN)
        """,
        (hash_password("12345678"),),
    )
    conn2.commit()
    conn2.close()
    recalc_all_student_gpa(fetch_all, execute_query)


class StudentApp(QWidget):
    _HK_LABELS = {
        0: "Học kỳ 1 — 2024–2025",
        1: "Học kỳ 2 — 2023–2024",
        2: "Học kỳ 1 — 2023–2024",
    }

    def __init__(self, username=""):
        super().__init__()
        self.username = username
        self.ui = Ui_SVDashboard()
        self.ui.setupUi(self)
        self._trend_pct_labels = {}
        self._arrange_student_tabs()
        self._wire_sv_grade_tables()
        self._score_filter = "all"
        self._all_diem_rows = []
        self._pill_map = [
            ("all", self.ui.btnTatCa),
            (0, self.ui.btnHK202425),
            (1, self.ui.btnHK202324),
            (2, self.ui.btnHK1202324),
        ]
        self.ui.btnLogout.clicked.connect(self._logout_click)
        btn_change_pwd = getattr(self.ui, "btnChangePassword", None)
        txt_new_pwd = getattr(self.ui, "leNewPassword", None)
        if btn_change_pwd is not None:
            btn_change_pwd.clicked.connect(self._change_password)
        if txt_new_pwd is not None:
            txt_new_pwd.textChanged.connect(self._update_password_strength)
        txt_tra_cuu = getattr(self.ui, "leTraCuuSearch", None)
        if txt_tra_cuu is not None:
            txt_tra_cuu.textChanged.connect(self._filter_tra_cuu)
        for key, btn in self._pill_map:
            btn.clicked.connect(lambda _=False, k=key: self._set_score_filter(k))
        self._student_info = self._load_student_info()
        self._load_data()
        if getattr(self.ui, "lblPasswordStrength", None) is not None and getattr(
            self.ui, "pbPasswordStrength", None
        ) is not None:
            self._update_password_strength("")

    def _logout_click(self):
        self._go_login_screen()

    def _arrange_student_tabs(self):
        pages = getattr(self.ui, "pages", None)
        tab_gpa = getattr(self.ui, "tabGPA", None)
        tab_bang_diem = getattr(self.ui, "tabBangDiem", None)
        if pages is None or tab_gpa is None or tab_bang_diem is None:
            return
        gpa_index = pages.indexOf(tab_gpa)
        if gpa_index > 0:
            title = pages.tabText(gpa_index)
            pages.removeTab(gpa_index)
            pages.insertTab(0, tab_gpa, title)
        bd_index = pages.indexOf(tab_bang_diem)
        if bd_index != 1:
            title = pages.tabText(bd_index)
            pages.removeTab(bd_index)
            pages.insertTab(1, tab_bang_diem, title)
        pages.setCurrentWidget(tab_gpa)
        self._setup_overview_layout()

    def _setup_overview_layout(self):
        cards = getattr(self.ui, "cardsGPALayout", None)
        if cards is not None:
            for i in range(cards.count()):
                cards.setStretch(i, 1)
        detail = getattr(self.ui, "gpaDetailLayout", None)
        if detail is not None:
            for i in range(detail.count()):
                detail.setStretch(i, 1)
        tab_lay = getattr(self.ui, "tabGPALayout", None)
        if tab_lay is not None:
            for i in range(tab_lay.count()):
                it = tab_lay.itemAt(i)
                if it and it.spacerItem() is not None:
                    tab_lay.setStretch(i, 1)
                    break
        hint = getattr(self.ui, "gpaHintBar", None)
        if hint is not None:
            hint.hide()
        self._configure_trend_bars()

    def _configure_trend_bars(self):
        fixed = QSizePolicy.Policy.Fixed
        expanding = QSizePolicy.Policy.Expanding
        for i in range(1, 6):
            lbl = getattr(self.ui, f"lblTrend{i}", None)
            pb = getattr(self.ui, f"pbTrend{i}", None)
            row_lay = getattr(self.ui, f"trendRow{i}Layout", None)
            if lbl is not None:
                lbl.setMinimumWidth(108)
                lbl.setMaximumWidth(108)
                lbl.setSizePolicy(fixed, fixed)
            if pb is not None and row_lay is not None:
                pb.setMinimumHeight(26)
                pb.setMaximumHeight(26)
                pb.setTextVisible(False)
                pb.setSizePolicy(expanding, fixed)
                if i not in self._trend_pct_labels:
                    bar_idx = row_lay.indexOf(pb)
                    if bar_idx < 0:
                        bar_idx = 1
                    row_lay.removeWidget(pb)
                    trend_card = getattr(self.ui, "trendCard", None)
                    wrapper = QWidget(parent=trend_card)
                    wrapper.setSizePolicy(expanding, fixed)
                    grid = QGridLayout(wrapper)
                    grid.setContentsMargins(0, 0, 0, 0)
                    grid.setSpacing(0)
                    pb.setParent(wrapper)
                    grid.addWidget(pb, 0, 0)
                    pct_lbl = QLabel(parent=wrapper)
                    pct_lbl.setObjectName(f"lblTrendPct{i}")
                    pct_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    pct_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    grid.addWidget(pct_lbl, 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
                    row_lay.insertWidget(bar_idx, wrapper, 1)
                    self._trend_pct_labels[i] = pct_lbl
                row_lay.setStretch(0, 0)
                row_lay.setStretch(1, 1)

    def _set_trend_bar(self, index, gpa_value):
        pb = getattr(self.ui, f"pbTrend{index}", None)
        if pb is None:
            return
        pct = max(0, min(100, int(round(float(gpa_value) * 10))))
        pb.setValue(pct)
        pct_lbl = self._trend_pct_labels.get(index)
        if pct_lbl is not None:
            pct_lbl.setText(f"{pct}%")

    def _style_xep_loai_badge(self, tier_index):
        badge = getattr(self.ui, "lblXepLoaiValue", None)
        if badge is None:
            return
        styles = {
            1: ("#ecfdf5", "#047857", "#a7f3d0"),
            2: ("#eff6ff", "#1d4ed8", "#bfdbfe"),
            3: ("#fff7ed", "#c2410c", "#fed7aa"),
            4: ("#fdf2f8", "#be185d", "#fbcfe8"),
            5: ("#fef2f2", "#b91c1c", "#fecaca"),
        }
        bg, fg, border = styles.get(tier_index, styles[4])
        badge.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border};"
            " border-radius:14px; padding:4px 14px; font-size:13px; font-weight:700;"
        )

    def _wire_sv_grade_tables(self):
        exp = QSizePolicy.Policy.Expanding
        tb_bang_diem = getattr(self.ui, "tbBangDiem", None)
        tb_tra_cuu = getattr(self.ui, "tbTraCuu", None)
        if self.ui.outerLayout.count() >= 2:
            self.ui.outerLayout.setStretch(1, 1)
        if tb_bang_diem is None:
            return
        tb_bang_diem.setSizePolicy(exp, exp)
        hdr_bd = tb_bang_diem.horizontalHeader()
        hdr_bd.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4, 5):
            hdr_bd.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hdr_bd.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        if tb_tra_cuu is not None:
            tb_tra_cuu.setSizePolicy(exp, exp)
            hdr_tc = tb_tra_cuu.horizontalHeader()
            tb_tra_cuu.setColumnCount(3)
            tb_tra_cuu.setHorizontalHeaderLabels(["Môn học", "ĐTB", "Kết quả"])
            tb_tra_cuu.verticalHeader().setVisible(False)
            tb_tra_cuu.setAlternatingRowColors(True)
            hdr_tc.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr_tc.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr_tc.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for lay_name, table in (("tabBangDiemLayout", tb_bang_diem), ("tabTraCuuLayout", tb_tra_cuu)):
            lay = getattr(self.ui, lay_name, None)
            if lay is None or table is None:
                continue
            for i in range(lay.count()):
                it = lay.itemAt(i)
                w = it.widget() if it else None
                if w is table:
                    lay.setStretch(i, 1)
                    break

    def _go_login_screen(self):
        self.login_window = LoginApp()
        self.login_window.show()
        self.close()

    @staticmethod
    def _initials(ho_ten):
        parts = [p for p in str(ho_ten).strip().split() if p]
        if not parts:
            return "SV"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def _load_student_info(self):
        try:
            rows = fetch_all(
                "SELECT MSSV, HoTen, Lop, GPA10, GPA4, XepLoai FROM SINH_VIEN WHERE MSSV = ?",
                (self.username,),
            )
            if rows:
                return rows[0]
        except Exception:
            pass
        return (self.username, self.username, "N/A", 0.0, 0.0, "Chưa có")

    def _khoa_from_lop(self, lop):
        s = str(lop or "").upper()
        if "CNTT" in s or "IT" in s:
            return "Công nghệ thông tin"
        if "QTKD" in s:
            return "Quản trị kinh doanh"
        return "—"

    def _set_score_filter(self, key):
        self._score_filter = key
        for k, btn in self._pill_map:
            btn.setObjectName("btnPillActive" if k == key else "btnPill")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._render_bang_diem()

    def _fetch_diem_rows(self, mssv):
        rows = []
        try:
            if table_exists("MON_HOC"):
                raw = fetch_all(
                    """
                    SELECT d.MaMon, COALESCE(m.TenMon, d.MaMon), COALESCE(m.SoTinChi, 3),
                           d.CC, d.GK, d.CK, d.DTB
                    FROM DIEM d
                    LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
                    WHERE d.MSSV = ? AND COALESCE(d.DaKhoa, 0) = 1
                    ORDER BY d.MaMon
                    """,
                    (mssv,),
                )
            else:
                raw = fetch_all(
                    """
                    SELECT d.MaMon, d.MaMon, 3, d.CC, d.GK, d.CK, d.DTB
                    FROM DIEM d
                    WHERE d.MSSV = ? AND COALESCE(d.DaKhoa, 0) = 1
                    ORDER BY d.MaMon
                    """,
                    (mssv,),
                )
            for ma_mon, ten, tc, cc, gk, ck, dtb in raw:
                b = abs(hash(ma_mon)) % 3
                rows.append((ma_mon, ten, tc, cc, gk, ck, float(dtb), b))
        except Exception:
            pass
        return rows

    def _badge_label(self, passed):
        text = "Đậu" if passed else "Rớt"
        lb = QLabel(text)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if passed:
            lb.setStyleSheet(
                "background:#dcfce7;color:#166534;padding:4px 12px;border-radius:14px;font-weight:600;font-size:12px;"
            )
        else:
            lb.setStyleSheet(
                "background:#fee2e2;color:#991b1b;padding:4px 12px;border-radius:14px;font-weight:600;font-size:12px;"
            )
        return lb

    def _render_bang_diem(self):
        table = self.ui.tbBangDiem
        table.clearContents()
        table.setRowCount(0)
        table.setColumnCount(7)
        headers = ["Môn học", "TC", "CC", "GK", "CK", "ĐTB", "Kết quả"]
        for i, h in enumerate(headers):
            table.setHorizontalHeaderItem(i, QTableWidgetItem(h))
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)

        def row_passes_bucket(b):
            if self._score_filter == "all":
                return True
            return b == self._score_filter

        grouped = {0: [], 1: [], 2: []}
        for row in self._all_diem_rows:
            if row_passes_bucket(row[7]):
                grouped[row[7]].append(row)

        order = [0, 1, 2] if self._score_filter == "all" else [self._score_filter]
        r = 0
        for b in order:
            rows = grouped[b]
            if not rows:
                continue
            table.insertRow(r)
            title = QTableWidgetItem(f"  {self._HK_LABELS[b]}")
            title.setBackground(QBrush(QColor("#ecfdf5")))
            title.setForeground(QBrush(QColor("#14532d")))
            f = title.font()
            f.setBold(True)
            title.setFont(f)
            table.setItem(r, 0, title)
            table.setSpan(r, 0, 1, 7)
            r += 1
            for _ma, ten, tc, cc, gk, ck, dtb, _b in rows:
                table.insertRow(r)
                pass_ok = dtb >= 5.0
                vals = [ten, tc, cc, gk, ck, f"{dtb:.2f}", ""]
                for c, val in enumerate(vals):
                    if c == 6:
                        continue
                    it = QTableWidgetItem(str(val))
                    if c >= 1:
                        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 5:
                        if dtb < 5.0:
                            it.setForeground(QBrush(QColor("#b91c1c")))
                        elif dtb < 6.5:
                            it.setForeground(QBrush(QColor("#b45309")))
                        else:
                            it.setForeground(QBrush(QColor("#1d4ed8")))
                    table.setItem(r, c, it)
                table.setCellWidget(r, 6, self._badge_label(pass_ok))
                r += 1

    def _filter_tra_cuu(self, keyword=""):
        table = getattr(self.ui, "tbTraCuu", None)
        if table is None:
            return
        key = str(keyword or "").strip().lower()
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            text = item.text().lower() if item is not None else ""
            table.setRowHidden(row, bool(key and key not in text))

    def _load_data(self):
        mssv, ho_ten, lop, _gpa10_db, _gpa4_db, _xep_loai_db = self._student_info
        g10, g4, hoc_luc, _published_cnt = _published_gpa_stats(mssv)
        tier = _hoc_luc_tu_gpa10(g10)[1]
        self.ui.lblStudentTitle.setText(f"{ho_ten} ({mssv})")
        self.ui.lblHeaderName.setText(ho_ten)
        email = f"{mssv.lower()}@abc.edu.vn"
        khoa = self._khoa_from_lop(lop)
        ngay_sinh = "—"
        if hasattr(self.ui, "lblHeroMetaLine"):
            self.ui.lblHeroMetaLine.setText(f"{mssv}  ·  {lop}  ·  {khoa}")
        elif getattr(self.ui, "lblHeaderMeta", None) is not None:
            self.ui.lblHeaderMeta.setVisible(True)
            self.ui.lblHeaderMeta.setText(f"MSSV: {mssv}  ·  Lớp: {lop}  ·  Khoa: {khoa}")
        lbl_gpa10 = getattr(self.ui, "lblGpa10Value", None)
        if lbl_gpa10 is not None:
            lbl_gpa10.setText(f"{g10:.2f}")
        lbl_gpa4 = getattr(self.ui, "lblGpa4Value", None)
        if lbl_gpa4 is not None:
            lbl_gpa4.setText(f"{g4:.2f}")
        self.ui.lblXepLoaiValue.setText(hoc_luc)
        self._style_xep_loai_badge(tier)
        profile_fields = {
            "lblHoTenProfile": ho_ten,
            "lblMssvProfile": mssv,
            "lblNgaySinhProfile": ngay_sinh,
            "lblLopProfile": lop,
            "lblKhoaProfile": khoa,
            "lblEmailProfile": email,
            "lblPhoneProfile": "—",
            "lblTrangThaiProfile": "Đang học",
        }
        for name, value in profile_fields.items():
            lb = getattr(self.ui, name, None)
            if lb is not None:
                lb.setText(value)

        self._all_diem_rows = self._fetch_diem_rows(mssv)
        self._set_score_filter(self._score_filter)
        tb_tra_cuu = getattr(self.ui, "tbTraCuu", None)
        if tb_tra_cuu is not None:
            tb_tra_cuu.setColumnCount(3)
            tb_tra_cuu.setHorizontalHeaderLabels(["Môn học", "ĐTB", "Kết quả"])
            tb_tra_cuu.setRowCount(0)
            for idx, row in enumerate(self._all_diem_rows):
                tb_tra_cuu.insertRow(idx)
                tb_tra_cuu.setItem(idx, 0, QTableWidgetItem(str(row[1])))
                tb_tra_cuu.setItem(idx, 1, QTableWidgetItem(f"{row[6]:.2f}"))
                tb_tra_cuu.setItem(
                    idx, 2, QTableWidgetItem("Đậu" if row[6] >= 4 else "Rớt")
                )

        txt_tra_cuu = getattr(self.ui, "leTraCuuSearch", None)
        if txt_tra_cuu is not None:
            self._filter_tra_cuu(txt_tra_cuu.text())

        try:
            tong_tc = sum(int(r[2]) for r in self._all_diem_rows)
            fails = [r[1] for r in self._all_diem_rows if r[6] < 5.0]
            mon_rot = len(fails)
            self.ui.lblGpa10CardBig.setText(f"{g10:.2f}")
            self.ui.lblGpa4CardBig.setText(f"{g4:.2f}")
            self.ui.lblTinChiCardBig.setText(str(tong_tc))
            self.ui.lblMonRotCardBig.setText(str(mon_rot))
            self.ui.lblMonRotCardSub.setText(str(fails[0]) if fails else "—")
            self._apply_gpa_legends(tier)
            self.ui.lblGpaQuyDoi10.setText(f"{g10:.2f}")
            self.ui.lblGpaQuyDoi4.setText(f"{g4:.2f}")
            xl_du_kien = getattr(self.ui, "lblXepLoaiDuKien", None)
            if xl_du_kien is not None:
                xl_du_kien.setText(hoc_luc)
            self.ui.lblTotNghiep.setText(
                "Đủ điều kiện (GPA ≥ 2.0)" if g4 >= 2.0 else "Chưa đủ (GPA < 2.0)"
            )
            hk_labels = ["HK1 2022-23", "HK2 2022-23", "HK1 2023-24", "HK2 2023-24", "HK1 2024-25"]
            spread = min(2.5, max(0.6, g10 * 0.25))
            start = max(0.0, g10 - spread)
            trend_vals = [round(start + (g10 - start) * i / 4, 2) for i in range(5)]
            trend_vals[-1] = round(g10, 2)
            trend_widgets = [
                (self.ui.lblTrend1, self.ui.pbTrend1),
                (self.ui.lblTrend2, self.ui.pbTrend2),
                (self.ui.lblTrend3, self.ui.pbTrend3),
                (self.ui.lblTrend4, self.ui.pbTrend4),
                (self.ui.lblTrend5, self.ui.pbTrend5),
            ]
            for idx, ((lbl, _pb), hk, val) in enumerate(
                zip(trend_widgets, hk_labels, trend_vals), start=1
            ):
                lbl.setText(hk)
                self._set_trend_bar(idx, val)
        except Exception:
            pass

    def _apply_gpa_legends(self, tier_index):
        specs = [
            ("#16a34a", "≥ 8.5 — Xuất sắc"),
            ("#2563eb", "7.0 – 8.4 — Giỏi"),
            ("#ea580c", "5.5 – 6.9 — Khá"),
            ("#db2777", "4.0 – 5.4 — Trung bình"),
            ("#dc2626", "&lt; 4.0 — Yếu / Kém"),
        ]
        labels = [
            self.ui.lblLegend1,
            self.ui.lblLegend2,
            self.ui.lblLegend3,
            self.ui.lblLegend4,
            self.ui.lblLegend5,
        ]
        for i, (lbl, (col, txt)) in enumerate(zip(labels, specs), start=1):
            mark = " ✓" if i == tier_index else ""
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setText(f'<span style="color:{col};">●</span> {txt}{mark}')

    def _update_password_strength(self, text=""):
        if getattr(self.ui, "lblPasswordStrength", None) is None or getattr(
            self.ui, "pbPasswordStrength", None
        ) is None:
            return
        pwd = text if isinstance(text, str) else self.ui.txtNewPassword.text()
        if not pwd.strip():
            self.ui.lblPasswordStrength.setText("Độ mạnh: —")
            self.ui.pbPasswordStrength.setValue(0)
            return
        if len(pwd) < 8:
            self.ui.lblPasswordStrength.setText("Độ mạnh: Yếu — cần tối thiểu 8 ký tự")
            self.ui.pbPasswordStrength.setValue(1)
            return
        score = 1
        if any(c.islower() for c in pwd):
            score += 1
        if any(c.isupper() for c in pwd):
            score += 1
        if any(c.isdigit() for c in pwd):
            score += 1
        if any((not c.isalnum() and not c.isspace()) for c in pwd):
            score += 1
        bar = min(4, score)
        self.ui.pbPasswordStrength.setValue(bar)
        if score <= 2:
            self.ui.lblPasswordStrength.setText(
                "Độ mạnh: Yếu — thêm chữ hoa, số hoặc ký tự đặc biệt"
            )
        elif score == 3:
            self.ui.lblPasswordStrength.setText("Độ mạnh: Trung bình — thêm ký tự đặc biệt")
        elif score == 4:
            self.ui.lblPasswordStrength.setText("Độ mạnh: Khá — có thể thêm ký tự đặc biệt")
        else:
            self.ui.lblPasswordStrength.setText("Độ mạnh: Mạnh")

    def _change_password(self):
        required = (
            getattr(self.ui, "leCurrentPassword", None),
            getattr(self.ui, "leNewPassword", None),
            getattr(self.ui, "leConfirmPassword", None),
        )
        if any(w is None for w in required):
            QMessageBox.warning(
                self,
                "Thiếu giao diện",
                "Trang Sinh viên hiện không có khối đổi mật khẩu. Vui lòng đồng bộ lại file UI.",
            )
            return
        current_pwd = self.ui.leCurrentPassword.text().strip()
        new_pwd = self.ui.leNewPassword.text().strip()
        confirm_pwd = self.ui.leConfirmPassword.text().strip()
        if not current_pwd or not new_pwd or not confirm_pwd:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ các trường mật khẩu.")
            return
        if len(new_pwd) < 8:
            QMessageBox.warning(self, "Mật khẩu yếu", "Mật khẩu mới phải có ít nhất 8 ký tự.")
            return
        if new_pwd != confirm_pwd:
            QMessageBox.warning(self, "Không khớp", "Xác nhận mật khẩu mới không trùng khớp.")
            return
        if not TaiKhoanModel.auth(self.username, current_pwd):
            QMessageBox.warning(self, "Sai mật khẩu", "Mật khẩu hiện tại chưa chính xác.")
            return
        try:
            TaiKhoanModel.update_password(self.username, new_pwd)
            self.ui.leCurrentPassword.clear()
            self.ui.leNewPassword.clear()
            self.ui.leConfirmPassword.clear()
            self._update_password_strength("")
            log_event(self.username, "Sinh viên", "Quản trị", "Đổi mật khẩu")
            QMessageBox.information(self, "Thành công", "Đổi mật khẩu thành công.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không đổi được mật khẩu: {e}")


class LecturerApp(QWidget):
    def __init__(self, username=""):
        super().__init__()
        self.username = username
        self.ui = Ui_GVDashboard()
        self.ui.setupUi(self)
        self._stretch_lecturer_sv_list_layout()
        self.ui.lblGiangVien.setText(self.username)
        self.ui.btnLogout.clicked.connect(self._logout_click)
        self.all_students = []
        self._all_score_rows = []
        self._scores_locked = False
        self._wire_events()
        self._wire_diem_danh_ui()
        self.load_dashboard_data()
        self._stretch_bao_cao_tables()
        self._bao_cao_chart = GradeChartHost("Phân bố điểm trung bình môn")
        _configure_gv_bao_cao_page(self.ui, self._bao_cao_chart)
        self.switch_page("tong_quan")

    def _stretch_bao_cao_tables(self):
        exp = QSizePolicy.Policy.Expanding
        page = getattr(self.ui, "pageBaoCao", None)
        if page is not None:
            page.setSizePolicy(exp, exp)
        for tbl in (
            getattr(self.ui, "tbBaoCaoTheoLop", None),
            getattr(self.ui, "tbBaoCaoDtbLop", None),
            getattr(self.ui, "tbBaoCaoPhanBo", None),
            getattr(self.ui, "tbBaoCaoCanhBao", None),
            getattr(self.ui, "tbBaoCaoXuat", None),
        ):
            if tbl is None:
                continue
            tbl.setSizePolicy(exp, exp)
            hdr = tbl.horizontalHeader()
            n = tbl.columnCount()
            if n <= 1:
                hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                continue
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for c in range(1, n):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

    def _stretch_lecturer_sv_list_layout(self):
        exp = QSizePolicy.Policy.Expanding
        if self.ui.rootLayout.count() >= 3:
            self.ui.rootLayout.setStretch(2, 1)
        self.ui.pages.setSizePolicy(exp, exp)
        self.ui.tbSinhVien.setSizePolicy(exp, exp)
        lay = self.ui.pageDanhSachLayout
        for i in range(lay.count()):
            it = lay.itemAt(i)
            if it and it.widget() is self.ui.tbSinhVien:
                lay.setStretch(i, 1)
                break
        hdr = self.ui.tbSinhVien.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for c in (4, 5, 6, 7, 8):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

    def _wire_events(self):
        self.ui.txtTimSinhVien.textChanged.connect(self.filter_students)
        self.ui.btnXuatBaoCao.clicked.connect(self._export_lecturer_sv_list_dialog)
        self.ui.btnLuuDiem.clicked.connect(self.save_scores_from_table)
        self.ui.btnHuyThayDoi.clicked.connect(self.load_score_table)
        self.ui.btnNopKhoaDiem.clicked.connect(self.submit_and_lock_scores)
        self.ui.btnTaiDanhSach.clicked.connect(self.reload_score_scope)
        self.ui.pages.currentChanged.connect(self._on_lecturer_tab_changed)
        self.ui.cbLopSV.currentIndexChanged.connect(self.filter_students)
        self.ui.cbMonSV.currentIndexChanged.connect(self.filter_students)
        self.ui.cbTrangThaiSV.currentIndexChanged.connect(self.filter_students)
        self.ui.cbBaoCaoHocKy.currentIndexChanged.connect(self.render_bao_cao_tab)
        self.ui.cbBaoCaoLop.currentIndexChanged.connect(self.render_bao_cao_tab)
        self.ui.cbBaoCaoMon.currentIndexChanged.connect(self.render_bao_cao_tab)
        self.ui.btnXuatTatCaExcel.clicked.connect(lambda: self._export_lecturer_bao_cao("excel"))
        self.ui.btnXuatTatCaPdf.clicked.connect(lambda: self._export_lecturer_bao_cao("pdf"))
        self.ui.cbHocKy.currentIndexChanged.connect(self._on_lecturer_term_changed)
        self.ui.cbMonNhap.currentIndexChanged.connect(self.load_score_table)
        self.ui.cbLopNhap.currentIndexChanged.connect(self.load_score_table)
        self.ui.txtMkMoiGV.textChanged.connect(self._update_lecturer_password_strength)
        self.ui.btnLuuMkGV.clicked.connect(self._change_lecturer_password)
        self.ui.btnThemSinhVien.clicked.connect(self.add_student)
        btn_dd_today = getattr(self.ui, "btnDiemDanhHomNay", None)
        if btn_dd_today is not None:
            btn_dd_today.clicked.connect(self._goto_diem_danh_tab_from_nhap)
        btn_dd_history = getattr(self.ui, "btnTaiLichSuDiemDanh", None)
        if btn_dd_history is not None:
            btn_dd_history.clicked.connect(self.load_attendance_history)
        dt_filter_dd = getattr(self.ui, "dtFilterLichSuDiemDanh", None)
        if dt_filter_dd is not None:
            dt_filter_dd.dateChanged.connect(self.load_attendance_history)
        chk_filter_dd = getattr(self.ui, "chkLocTheoNgayDiemDanh", None)
        if chk_filter_dd is not None:
            chk_filter_dd.stateChanged.connect(self.load_attendance_history)

    def _wire_diem_danh_ui(self):
        """Gắn sự kiện tab Điểm danh (widget định nghĩa trong gv_dashboard.ui)."""
        self.ui.dtDdNgay.setDate(QDate.currentDate())
        dt_filter_dd = getattr(self.ui, "dtFilterLichSuDiemDanh", None)
        if dt_filter_dd is not None:
            dt_filter_dd.setDate(QDate.currentDate())
        self.ui.btnDdLuu.clicked.connect(self._save_attendance_from_dd_tab)
        self.ui.btnDdLamMoi.clicked.connect(self.load_attendance_history)
        self.ui.dtDdNgay.dateChanged.connect(self.load_attendance_history)
        self.ui.cbDdHocKy.currentIndexChanged.connect(self._on_dd_term_changed)
        self.ui.cbDdMon.currentIndexChanged.connect(self.load_attendance_history)
        self.ui.cbDdLop.currentIndexChanged.connect(self.load_attendance_history)
        self.ui.txtDdTim.textChanged.connect(self._dd_roll_apply_filter)
        self.ui.btnDdCoMatTatCa.clicked.connect(self._dd_roll_set_all_present)
        hdr_n = self.ui.tbDdNhap.horizontalHeader()
        hdr_n.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr_n.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr_n.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr_n.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tb_ls = getattr(self.ui, "tbLichSuDiemDanh", None)
        if tb_ls is not None:
            hdr_ls = tb_ls.horizontalHeader()
            hdr_ls.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr_ls.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr_ls.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hdr_ls.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr_ls.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

    def _on_dd_term_changed(self):
        # Đồng bộ học kỳ sang combo chính để dùng chung _current_term() nếu cần
        term = self.ui.cbDdHocKy.currentData()
        if term is None:
            return
        for i in range(self.ui.cbHocKy.count()):
            if self.ui.cbHocKy.itemData(i) == term:
                self.ui.cbHocKy.setCurrentIndex(i)
                break
        self._on_lecturer_term_changed()
        self.load_attendance_history()

    def _goto_diem_danh_tab_from_nhap(self):
        """Chuyển sang tab Điểm danh với cùng HK / môn / lớp đang chọn ở Nhập điểm."""
        ma = self.ui.cbMonNhap.currentData() or ""
        if not ma:
            QMessageBox.information(
                self,
                "Chưa chọn môn",
                "Vui lòng chọn một môn học ở phần Nhập điểm trước.",
            )
            return
        term_main = self.ui.cbHocKy.currentData()
        if isinstance(term_main, tuple) and len(term_main) == 2:
            for i in range(self.ui.cbDdHocKy.count()):
                if self.ui.cbDdHocKy.itemData(i) == term_main:
                    if self.ui.cbDdHocKy.currentIndex() != i:
                        self.ui.cbDdHocKy.setCurrentIndex(i)
                    break
        for i in range(self.ui.cbDdMon.count()):
            if self.ui.cbDdMon.itemData(i) == ma:
                self.ui.cbDdMon.setCurrentIndex(i)
                break
        lop = self.ui.cbLopNhap.currentData() or ""
        for i in range(self.ui.cbDdLop.count()):
            if (self.ui.cbDdLop.itemData(i) or "") == lop:
                self.ui.cbDdLop.setCurrentIndex(i)
                break
        self.ui.dtDdNgay.setDate(QDate.currentDate())
        self.ui.pages.setCurrentWidget(self.ui.pageDiemDanh)
        self.ui.lblHeader.setText("Điểm danh")
        self.load_attendance_history()

    def reload_score_scope(self):
        """Nạp lại phạm vi lớp/môn từ DB rồi tải lại bảng nhập điểm."""
        self._on_lecturer_term_changed()
        self.load_score_table()

    def load_attendance_history(self):
        current = self.ui.pages.currentWidget()
        if current is self.ui.pageDiemDanh:
            selected_mon = self.ui.cbDdMon.currentData() or ""
            selected_lop = self.ui.cbDdLop.currentData() or ""
            term = self.ui.cbDdHocKy.currentData() or self.ui.cbHocKy.currentData()
            hoc_ky, nam_hoc = term if isinstance(term, tuple) and len(term) == 2 else self._current_term()
            if not selected_mon:
                self._load_dd_roll_table("", selected_lop, hoc_ky, nam_hoc)
                return
            self._load_dd_roll_table(selected_mon, selected_lop, hoc_ky, nam_hoc)
            return
        if current is not self.ui.pageNhapDiem:
            return

        tb = getattr(self.ui, "tbLichSuDiemDanh", None)
        if tb is None:
            return
        selected_mon = self.ui.cbMonNhap.currentData() or ""
        selected_lop = self.ui.cbLopNhap.currentData() or ""
        hoc_ky, nam_hoc = self._current_term()
        tb.setRowCount(0)
        if not selected_mon:
            return
        ensure_diem_danh_table()
        chk_filter = getattr(self.ui, "chkLocTheoNgayDiemDanh", None)
        filter_by_day = chk_filter.isChecked() if chk_filter is not None else False
        if filter_by_day:
            dt_filter = getattr(self.ui, "dtFilterLichSuDiemDanh", None)
            if dt_filter is None:
                return
            ngay_filter = dt_filter.date().toString("yyyy-MM-dd")
            rows = fetch_all(
                """
                SELECT dd.NgayHoc, s.MSSV, s.HoTen, s.Lop, dd.CoMat
                FROM DIEM_DANH dd
                JOIN SINH_VIEN s ON s.MSSV = dd.MSSV
                WHERE dd.MaMon = ? AND dd.HocKy = ? AND dd.NamHoc = ?
                  AND (? = '' OR s.Lop = ?)
                  AND dd.NgayHoc = ?
                ORDER BY s.MSSV
                """,
                (selected_mon, hoc_ky, nam_hoc, selected_lop, selected_lop, ngay_filter),
            )
        else:
            rows = fetch_all(
                """
                SELECT dd.NgayHoc, s.MSSV, s.HoTen, s.Lop, dd.CoMat
                FROM DIEM_DANH dd
                JOIN SINH_VIEN s ON s.MSSV = dd.MSSV
                WHERE dd.MaMon = ? AND dd.HocKy = ? AND dd.NamHoc = ?
                  AND (? = '' OR s.Lop = ?)
                ORDER BY dd.NgayHoc DESC, s.MSSV
                """,
                (selected_mon, hoc_ky, nam_hoc, selected_lop, selected_lop),
            )
        for i, (ngay, mssv, ho_ten, lop, co_mat) in enumerate(rows):
            tb.insertRow(i)
            tb.setItem(i, 0, QTableWidgetItem(str(ngay)))
            tb.setItem(i, 1, QTableWidgetItem(str(mssv)))
            tb.setItem(i, 2, QTableWidgetItem(str(ho_ten)))
            tb.setItem(i, 3, QTableWidgetItem(str(lop)))
            st = "Có mặt" if int(co_mat) == 1 else "Vắng"
            it = QTableWidgetItem(st)
            if int(co_mat) == 0:
                it.setForeground(QBrush(QColor("#b91c1c")))
            tb.setItem(i, 4, it)

    def _students_for_selected_lop(self):
        selected_lop = self.ui.cbLopNhap.currentData() or ""
        rows = []
        for mssv, ho_ten, lop, *_ in self.all_students:
            if selected_lop and str(lop) != str(selected_lop):
                continue
            rows.append((str(mssv), str(ho_ten), str(lop)))
        return rows

    def _students_for_lop(self, lop_value: str):
        target = str(lop_value or "").strip()
        rows = []
        for mssv, ho_ten, lop, *_ in self.all_students:
            if target and str(lop) != target:
                continue
            rows.append((str(mssv), str(ho_ten), str(lop)))
        return rows

    def _persist_attendance_rows(self, tb, selected_mon, hk, nam, selected_date):
        """Ghi DB từ bảng có cột checkbox «Có mặt» ở index 3. Trả về số dòng đã ghi."""
        ensure_diem_danh_table()
        n = 0
        for i in range(tb.rowCount()):
            item = tb.item(i, 0)
            if item is None:
                continue
            mssv = item.text().strip()
            if not mssv:
                continue
            cell = tb.cellWidget(i, 3)
            ck = cell.findChild(QCheckBox) if cell else None
            co_mat = 1 if (ck and ck.isChecked()) else 0
            execute_query(
                "DELETE FROM DIEM_DANH WHERE MSSV=? AND MaMon=? AND HocKy=? AND NamHoc=? AND NgayHoc=?",
                (mssv, selected_mon, hk, nam, selected_date),
            )
            execute_query(
                """
                INSERT INTO DIEM_DANH (MSSV, MaMon, HocKy, NamHoc, NgayHoc, CoMat, NguoiDiemDanh, LanCapNhat)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                """,
                (mssv, selected_mon, hk, nam, selected_date, co_mat, self.username),
            )
            n += 1
        return n

    def _sv_rows_from_attendance_tb(self, tb):
        rows = []
        for i in range(tb.rowCount()):
            it0 = tb.item(i, 0)
            it1 = tb.item(i, 1)
            it2 = tb.item(i, 2)
            if it0 is None:
                continue
            rows.append((it0.text().strip(), it1.text() if it1 else "", it2.text() if it2 else ""))
        return rows

    def _load_dd_roll_table(self, selected_mon, selected_lop, hoc_ky, nam_hoc):
        """Nạp danh sách SV + checkbox theo ngày (tab Điểm danh)."""
        tb = self.ui.tbDdNhap
        lbl = self.ui.lblDdRoll
        tb.setRowCount(0)
        self.ui.txtDdTim.blockSignals(True)
        self.ui.txtDdTim.clear()
        self.ui.txtDdTim.blockSignals(False)
        if not selected_mon:
            if lbl is not None:
                lbl.setText("Chọn một môn học để hiển thị danh sách.")
            return
        if selected_lop:
            sv_rows = self._students_for_lop(str(selected_lop))
        else:
            sv_rows = self._students_for_lop("")
        if not sv_rows:
            if lbl is not None:
                lbl.setText(
                    "Không có sinh viên trong phạm vi lớp đã chọn. Thử «Tất cả lớp» hoặc đổi học kỳ."
                )
            return
        if lbl is not None:
            lbl.setText("")
        ensure_diem_danh_table()
        ngay = self.ui.dtDdNgay.date().toString("yyyy-MM-dd")
        co_map = {
            str(mssv): int(co_mat)
            for mssv, co_mat in fetch_all(
                """
                SELECT MSSV, CoMat
                FROM DIEM_DANH
                WHERE MaMon = ? AND HocKy = ? AND NamHoc = ? AND NgayHoc = ?
                """,
                (selected_mon, hoc_ky, nam_hoc, ngay),
            )
        }
        for i, (mssv, ho_ten, lop) in enumerate(sv_rows):
            tb.insertRow(i)
            tb.setItem(i, 0, QTableWidgetItem(mssv))
            tb.setItem(i, 1, QTableWidgetItem(ho_ten))
            tb.setItem(i, 2, QTableWidgetItem(lop))
            ck = QCheckBox("Có mặt")
            ck.setChecked(bool(co_map.get(mssv, 1)))
            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(8, 0, 8, 0)
            lay.addWidget(ck)
            lay.addStretch(1)
            tb.setCellWidget(i, 3, wrap)

    def _dd_roll_apply_filter(self, _text=None):
        tb = getattr(self, "tbDdNhap", None)
        if tb is None or getattr(self, "txtDdTim", None) is None:
            return
        q = self.ui.txtDdTim.text().strip().lower()
        for r in range(tb.rowCount()):
            if not q:
                tb.setRowHidden(r, False)
                continue
            it0 = tb.item(r, 0)
            it1 = tb.item(r, 1)
            mssv = it0.text().lower() if it0 else ""
            name = it1.text().lower() if it1 else ""
            tb.setRowHidden(r, q not in mssv and q not in name)

    def _dd_roll_set_all_present(self):
        tb = getattr(self, "tbDdNhap", None)
        if tb is None:
            return
        for r in range(tb.rowCount()):
            cell = tb.cellWidget(r, 3)
            ck = cell.findChild(QCheckBox) if cell else None
            if ck is not None:
                ck.setChecked(True)

    def _save_attendance_from_dd_tab(self):
        tb = getattr(self, "tbDdNhap", None)
        if tb is None:
            return
        selected_mon = self.ui.cbDdMon.currentData() or ""
        term = self.ui.cbDdHocKy.currentData() or self.ui.cbHocKy.currentData()
        if not isinstance(term, tuple) or len(term) != 2:
            hk, nam = self._current_term()
        else:
            hk, nam = int(term[0]), str(term[1])
        if not selected_mon:
            QMessageBox.information(self, "Chưa chọn môn", "Vui lòng chọn một môn học trước khi lưu.")
            return
        sv_rows = self._sv_rows_from_attendance_tb(tb)
        if not sv_rows:
            QMessageBox.information(self, "Danh sách trống", "Không có sinh viên để lưu điểm danh.")
            return
        selected_date = self.ui.dtDdNgay.date().toString("yyyy-MM-dd")
        saved = self._persist_attendance_rows(tb, selected_mon, hk, nam, selected_date)
        self._apply_attendance_to_cc(selected_mon, hk, nam, sv_rows)
        self.load_score_table()
        dt_filter = getattr(self.ui, "dtFilterLichSuDiemDanh", None)
        if dt_filter is not None:
            dt_filter.setDate(self.ui.dtDdNgay.date())
        chk_filter = getattr(self.ui, "chkLocTheoNgayDiemDanh", None)
        if chk_filter is not None:
            chk_filter.setChecked(True)
        self.load_attendance_history()
        self.filter_students()
        QMessageBox.information(self, "Đã lưu điểm danh", f"Đã lưu {saved} sinh viên cho ngày {selected_date}.")

    def _open_attendance_dialog(
        self,
        initial_date: QDate | None = None,
        selected_mon_override: str | None = None,
        selected_lop_override: str | None = None,
        term_override: tuple | None = None,
    ):
        selected_mon = (selected_mon_override if selected_mon_override is not None else (self.ui.cbMonNhap.currentData() or ""))
        selected_lop = (selected_lop_override if selected_lop_override is not None else (self.ui.cbLopNhap.currentData() or ""))
        if term_override is not None and isinstance(term_override, tuple) and len(term_override) == 2:
            hk, nam = int(term_override[0]), str(term_override[1])
        else:
            hk, nam = self._current_term()
        if not selected_mon:
            QMessageBox.information(
                self,
                "Chưa chọn môn",
                "Vui lòng chọn một môn học (tab Điểm danh hoặc phần Nhập điểm) trước khi điểm danh.",
            )
            return
        if selected_lop:
            sv_rows = self._students_for_lop(str(selected_lop))
        else:
            sv_rows = self._students_for_lop("")
        if not sv_rows:
            QMessageBox.information(
                self,
                "Không có sinh viên",
                "Không có sinh viên trong phạm vi lớp đã chọn. Thử chọn «Tất cả lớp» hoặc học kỳ khác.",
            )
            return
        ensure_diem_danh_table()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Điểm danh — {selected_mon} — {selected_lop or 'Tất cả lớp'}")
        dlg.resize(820, 580)
        root = QVBoxLayout(dlg)
        row_top = QHBoxLayout()
        row_top.addWidget(QLabel(f"HK{hk} — {nam}"))
        row_top.addStretch(1)
        row_top.addWidget(QLabel("Ngày buổi học:"))
        dt_pick = QDateEdit(dlg)
        dt_pick.setCalendarPopup(True)
        dt_pick.setDisplayFormat("dd/MM/yyyy")
        dt_pick.setDate(initial_date if initial_date is not None else QDate.currentDate())
        row_top.addWidget(dt_pick)
        root.addLayout(row_top)
        row_find = QHBoxLayout()
        row_find.addWidget(QLabel("Tìm nhanh:"))
        txt_loc_sv = QLineEdit(dlg)
        txt_loc_sv.setPlaceholderText("Gõ MSSV hoặc họ tên…")
        row_find.addWidget(txt_loc_sv, 1)
        btn_all_here = QPushButton("Có mặt tất cả", dlg)
        btn_all_here.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_all_here.setToolTip("Đánh dấu tất cả sinh viên là có mặt (kể cả dòng đang ẩn do lọc).")
        row_find.addWidget(btn_all_here)
        root.addLayout(row_find)
        hint_dlg = QLabel(
            "Mặc định tất cả có mặt. Bỏ chọn «Có mặt» ở những sinh viên vắng. Đổi ngày để xem hoặc sửa buổi khác.",
            dlg,
        )
        hint_dlg.setWordWrap(True)
        hint_dlg.setStyleSheet("color:#64748b;font-size:12px;padding:2px 0 6px 0;")
        root.addWidget(hint_dlg)
        tb = QTableWidget(dlg)
        tb.setColumnCount(4)
        tb.setHorizontalHeaderLabels(["MSSV", "Họ tên", "Lớp", "Có mặt"])
        tb.setRowCount(0)
        tb.setAlternatingRowColors(True)
        root.addWidget(tb)
        tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tb.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tb.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for i, (mssv, ho_ten, lop) in enumerate(sv_rows):
            tb.insertRow(i)
            tb.setItem(i, 0, QTableWidgetItem(mssv))
            tb.setItem(i, 1, QTableWidgetItem(ho_ten))
            tb.setItem(i, 2, QTableWidgetItem(lop))
            ck = QCheckBox("Có mặt")
            ck.setChecked(True)
            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(8, 0, 8, 0)
            lay.addWidget(ck)
            lay.addStretch(1)
            tb.setCellWidget(i, 3, wrap)

        def _apply_row_filter():
            q = txt_loc_sv.text().strip().lower()
            for r in range(tb.rowCount()):
                if not q:
                    tb.setRowHidden(r, False)
                    continue
                mssv = tb.item(r, 0).text().lower()
                name = tb.item(r, 1).text().lower()
                tb.setRowHidden(r, q not in mssv and q not in name)

        txt_loc_sv.textChanged.connect(_apply_row_filter)

        def _set_all_present():
            for r in range(tb.rowCount()):
                cell = tb.cellWidget(r, 3)
                ck2 = cell.findChild(QCheckBox) if cell else None
                if ck2 is not None:
                    ck2.setChecked(True)

        btn_all_here.clicked.connect(_set_all_present)

        def _fill_checkbox_by_date():
            ngay = dt_pick.date().toString("yyyy-MM-dd")
            m = {
                str(mssv): int(co_mat)
                for mssv, co_mat in fetch_all(
                    """
                    SELECT MSSV, CoMat
                    FROM DIEM_DANH
                    WHERE MaMon = ? AND HocKy = ? AND NamHoc = ? AND NgayHoc = ?
                    """,
                    (selected_mon, hk, nam, ngay),
                )
            }
            for rr in range(tb.rowCount()):
                ms = tb.item(rr, 0).text().strip()
                cell = tb.cellWidget(rr, 3)
                ck2 = cell.findChild(QCheckBox) if cell else None
                if ck2 is None:
                    continue
                ck2.setChecked(bool(m.get(ms, 1)))

        dt_pick.dateChanged.connect(lambda _d: _fill_checkbox_by_date())
        _fill_checkbox_by_date()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, parent=dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        selected_date = dt_pick.date().toString("yyyy-MM-dd")
        saved = self._persist_attendance_rows(tb, selected_mon, hk, nam, selected_date)
        self._apply_attendance_to_cc(selected_mon, hk, nam, sv_rows)
        self.load_score_table()
        if hasattr(self, "dtDdNgay"):
            self.ui.dtDdNgay.setDate(dt_pick.date())
        dt_filter = getattr(self.ui, "dtFilterLichSuDiemDanh", None)
        if dt_filter is not None:
            dt_filter.setDate(dt_pick.date())
        chk_filter = getattr(self.ui, "chkLocTheoNgayDiemDanh", None)
        if chk_filter is not None:
            chk_filter.setChecked(True)
        self.load_attendance_history()
        self.filter_students()
        QMessageBox.information(self, "Đã lưu điểm danh", f"Đã lưu {saved} sinh viên cho ngày {selected_date}.")

    def _apply_attendance_to_cc(self, ma_mon, hoc_ky, nam_hoc, sv_rows):
        for mssv, _ten, _lop in sv_rows:
            r = fetch_all(
                """
                SELECT COUNT(*), SUM(CASE WHEN CoMat = 1 THEN 1 ELSE 0 END)
                FROM DIEM_DANH
                WHERE MSSV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ?
                """,
                (mssv, ma_mon, hoc_ky, nam_hoc),
            )
            tong = int(r[0][0]) if r else 0
            co_mat = int(r[0][1] or 0) if r else 0
            if tong <= 0:
                continue
            cc_val = round(co_mat * 10.0 / tong, 1)
            existing = fetch_all(
                "SELECT COALESCE(DaKhoa, 0) FROM DIEM WHERE MSSV=? AND MaMon=? AND HocKy=? AND NamHoc=?",
                (mssv, ma_mon, hoc_ky, nam_hoc),
            )
            if existing:
                if int(existing[0][0]) == 1:
                    continue
                execute_query(
                    """
                    UPDATE DIEM
                    SET CC = ?, NguoiNhap = ?, LanCapNhatCuoi = datetime('now', 'localtime')
                    WHERE MSSV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ?
                    """,
                    (cc_val, self.username, mssv, ma_mon, hoc_ky, nam_hoc),
                )
            else:
                execute_query(
                    """
                    INSERT INTO DIEM (MSSV, MaMon, HocKy, NamHoc, CC, DaKhoa, NguoiNhap, LanCapNhatCuoi)
                    VALUES (?, ?, ?, ?, ?, 0, ?, datetime('now', 'localtime'))
                    """,
                    (mssv, ma_mon, hoc_ky, nam_hoc, cc_val, self.username),
                )

    def switch_page(self, page_name):
        if page_name == "tong_quan":
            self.ui.pages.setCurrentWidget(self.ui.pageTongQuan)
            self.ui.lblHeader.setText("Tổng quan giảng viên")
            self.render_overview()
        elif page_name == "nhap_diem":
            self.ui.pages.setCurrentWidget(self.ui.pageNhapDiem)
            self.ui.lblHeader.setText("Nhập điểm theo lớp và môn")
            self._style_nhap_diem_table()
            self.load_score_table()
        elif page_name == "bao_cao":
            self.ui.pages.setCurrentWidget(self.ui.pageBaoCao)
            self.ui.lblHeader.setText("Thống kê và báo cáo")
            self.render_bao_cao_tab()
        elif page_name == "ho_so":
            self.ui.pages.setCurrentWidget(self.ui.pageHoSo)
            self.ui.lblHeader.setText("Hồ sơ giảng viên")
            self.render_ho_so_tab()
        else:
            self.ui.pages.setCurrentWidget(self.ui.pageDanhSachSV)
            self.ui.lblHeader.setText("Danh sách sinh viên")
            self.filter_students()

    def _on_lecturer_tab_changed(self, _index):
        current = self.ui.pages.currentWidget()
        if current is self.ui.pageTongQuan:
            self.ui.lblHeader.setText("Tổng quan giảng viên")
            self.render_overview()
        elif current is self.ui.pageNhapDiem:
            self.ui.lblHeader.setText("Nhập điểm theo lớp và môn")
            self._style_nhap_diem_table()
            self.load_score_table()
        elif current is self.ui.pageBaoCao:
            self.ui.lblHeader.setText("Thống kê và báo cáo")
            self.render_bao_cao_tab()
        elif current is self.ui.pageHoSo:
            self.ui.lblHeader.setText("Hồ sơ giảng viên")
            self.render_ho_so_tab()
        elif current is self.ui.pageDiemDanh:
            self.ui.lblHeader.setText("Điểm danh")
            self.load_attendance_history()
        else:
            self.ui.lblHeader.setText("Danh sách sinh viên")
            self.filter_students()

    def _style_nhap_diem_table(self):
        table = self.ui.tbNhapDiem
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4, 5, 6, 7):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)

    def _logout_click(self):
        self._go_login_screen()

    def _go_login_screen(self):
        self.login_window = LoginApp()
        self.login_window.show()
        self.close()

    def _phan_cong_trang_thai_clause(self):
        """Điều kiện lọc phân công đang dạy; rỗng nếu CSDL cũ không có cột TrangThai."""
        c = getattr(self, "_cache_pc_tt_clause", None)
        if c is not None:
            return c
        if not table_exists("PHAN_CONG"):
            self._cache_pc_tt_clause = ""
            return ""
        try:
            names = {str(r[1]) for r in fetch_all("PRAGMA table_info(PHAN_CONG)")}
        except Exception:
            names = set()
        self._cache_pc_tt_clause = (
            " AND COALESCE(p.TrangThai, 'DANG_DAY') = 'DANG_DAY' " if "TrangThai" in names else ""
        )
        return self._cache_pc_tt_clause

    def _lecturer_scope_for_term(self, hk, nam):
        """
        Cập nhật self.all_students theo phân công học kỳ.
        Trả về (mon_rows, lop_rows) để nạp combo; mỗi phần tử lop_rows là tuple (ma_lop,).
        """
        base_sv = fetch_all("SELECT MSSV, HoTen, Lop, GPA10, GPA4, XepLoai FROM SINH_VIEN ORDER BY MSSV")
        clause = self._phan_cong_trang_thai_clause()
        assigned_rows = []
        if table_exists("PHAN_CONG"):
            assigned_rows = fetch_all(
                f"""
                SELECT DISTINCT p.MaMon, COALESCE(m.TenMon, p.MaMon), COALESCE(p.Lop, '')
                FROM PHAN_CONG p
                LEFT JOIN MON_HOC m ON m.MaMon = p.MaMon
                WHERE p.MaGV = ? AND p.HocKy = ? AND p.NamHoc = ?
                {clause}
                ORDER BY p.MaMon
                """,
                (self.username, hk, nam),
            )
        assigned_mon = {}
        assigned_lop = set()
        for ma, ten, lop in assigned_rows:
            assigned_mon[ma] = ten
            if str(lop).strip():
                assigned_lop.add(str(lop).strip())
        if not table_exists("PHAN_CONG"):
            self.all_students = list(base_sv)
            mon_rows = fetch_all("SELECT MaMon, COALESCE(TenMon, MaMon) FROM MON_HOC ORDER BY MaMon")
            lop_rows = fetch_all(
                "SELECT DISTINCT Lop FROM SINH_VIEN WHERE Lop IS NOT NULL AND trim(Lop) <> '' ORDER BY Lop"
            )
            return mon_rows, lop_rows
        if not assigned_rows:
            self.all_students = []
            return [], []
        mon_rows = sorted([(ma, ten) for ma, ten in assigned_mon.items()], key=lambda x: x[0])
        if assigned_lop:
            self.all_students = [row for row in base_sv if str(row[2]).strip() in assigned_lop]
            lop_rows = [(lop,) for lop in sorted(assigned_lop)]
        else:
            self.all_students = list(base_sv)
            lop_set = sorted({str(row[2]).strip() for row in self.all_students if str(row[2]).strip()})
            lop_rows = [(x,) for x in lop_set]
        return mon_rows, lop_rows

    def _fill_lecturer_mon_lop_combos(self, mon_rows, lop_rows):
        self.ui.cbMonNhap.blockSignals(True)
        self.ui.cbLopNhap.blockSignals(True)
        self.ui.cbMonNhap.clear()
        self.ui.cbMonSV.clear()
        self.ui.cbBaoCaoMon.clear()
        self.ui.cbMonNhap.addItem("Tất cả môn", "")
        self.ui.cbMonSV.addItem("Tất cả môn", "")
        self.ui.cbBaoCaoMon.addItem("Tất cả môn", "")
        for ma, ten in mon_rows:
            label = f"{ma} — {ten}"
            self.ui.cbMonNhap.addItem(label, ma)
            self.ui.cbMonSV.addItem(label, ma)
            self.ui.cbBaoCaoMon.addItem(label, ma)
        self.ui.cbLopNhap.clear()
        self.ui.cbLopSV.clear()
        self.ui.cbBaoCaoLop.clear()
        self.ui.cbLopNhap.addItem("Tất cả lớp", "")
        self.ui.cbLopSV.addItem("Tất cả lớp", "")
        self.ui.cbBaoCaoLop.addItem("Tất cả lớp", "")
        for (lop,) in lop_rows:
            self.ui.cbLopNhap.addItem(lop, lop)
            self.ui.cbLopSV.addItem(lop, lop)
            self.ui.cbBaoCaoLop.addItem(lop, lop)
        # Đồng bộ sang tab Điểm danh
        self.ui.cbDdMon.blockSignals(True)
        self.ui.cbDdMon.clear()
        self.ui.cbDdMon.addItem("Tất cả môn", "")
        for ma, ten in mon_rows:
            self.ui.cbDdMon.addItem(f"{ma} — {ten}", ma)
        self.ui.cbDdMon.blockSignals(False)
        if self.ui.cbDdMon.count() > 1:
            self.ui.cbDdMon.setCurrentIndex(1)
        self.ui.cbDdLop.blockSignals(True)
        self.ui.cbDdLop.clear()
        self.ui.cbDdLop.addItem("Tất cả lớp", "")
        for (lop,) in lop_rows:
            self.ui.cbDdLop.addItem(lop, lop)
        self.ui.cbDdLop.blockSignals(False)

        if self.ui.cbDdHocKy.count() <= 0:
            # đồng bộ HK từ combo chính
            self.ui.cbDdHocKy.blockSignals(True)
            self.ui.cbDdHocKy.clear()
            for i in range(self.ui.cbHocKy.count()):
                self.ui.cbDdHocKy.addItem(self.ui.cbHocKy.itemText(i), self.ui.cbHocKy.itemData(i))
            self.ui.cbDdHocKy.blockSignals(False)
        self.ui.cbMonNhap.blockSignals(False)
        self.ui.cbLopNhap.blockSignals(False)

    def _on_lecturer_term_changed(self, _idx=None):
        """Đổi học kỳ trên tổng quan / nhập điểm → nạp lại phạm vi lớp/môn và thống kê."""
        try:
            hk, nam = self._current_term()
            mon_rows, lop_rows = self._lecturer_scope_for_term(hk, nam)
            self._fill_lecturer_mon_lop_combos(mon_rows, lop_rows)
            cur = self.ui.pages.currentWidget()
            if cur is self.ui.pageTongQuan:
                self.render_overview()
            elif cur is self.ui.pageDanhSachSV:
                self.filter_students()
            elif cur is self.ui.pageNhapDiem:
                self.load_score_table()
            elif cur is self.ui.pageBaoCao:
                self.render_bao_cao_tab()
        except Exception as e:
            print("Lỗi đổi học kỳ GV:", e)

    def load_dashboard_data(self):
        try:
            prev_term = self.ui.cbHocKy.currentData() if self.ui.cbHocKy.count() > 0 else None
            self.ui.cbHocKy.blockSignals(True)
            self.ui.cbHocKy.clear()
            self.ui.cbHocKy.addItem("Học kỳ 1 — 2024-2025", (1, "2024-2025"))
            self.ui.cbHocKy.addItem("Học kỳ 2 — 2024-2025", (2, "2024-2025"))
            set_idx = 0
            if prev_term is not None:
                for i in range(self.ui.cbHocKy.count()):
                    if self.ui.cbHocKy.itemData(i) == prev_term:
                        set_idx = i
                        break
            self.ui.cbHocKy.setCurrentIndex(set_idx)
            self.ui.cbHocKy.blockSignals(False)
            hk_t, nam_t = self._current_term()
            mon_rows, lop_rows = self._lecturer_scope_for_term(hk_t, nam_t)
            self._fill_lecturer_mon_lop_combos(mon_rows, lop_rows)
            self.ui.cbBaoCaoHocKy.clear()
            self.ui.cbBaoCaoHocKy.addItem("HK1 — 2024-2025", (1, "2024-2025"))
            self.ui.cbBaoCaoHocKy.addItem("HK2 — 2024-2025", (2, "2024-2025"))
            self.ui.cbTrangThaiSV.clear()
            self.ui.cbTrangThaiSV.addItem("Tất cả trạng thái", "all")
            self.ui.cbTrangThaiSV.addItem("Đã có điểm", "done")
            self.ui.cbTrangThaiSV.addItem("Chưa nhập", "missing")
            self.render_overview()
            self.filter_students()
            self.render_bao_cao_tab()
            self.render_ho_so_tab()
        except Exception as e:
            print("Lỗi tải dữ liệu giảng viên:", e)

    def _current_term(self):
        if self.ui.cbHocKy.count() <= 0:
            return 1, "2024-2025"
        term_data = self.ui.cbHocKy.currentData()
        if isinstance(term_data, tuple) and len(term_data) == 2:
            return int(term_data[0]), str(term_data[1])
        label = self.ui.cbHocKy.currentText().strip()
        hoc_ky = 1 if "1" in label else 2
        nam_hoc = "2024-2025"
        return hoc_ky, nam_hoc

    def render_overview(self):
        hk, nam = self._current_term()
        term_label = self.ui.cbHocKy.currentText()
        if hasattr(self.ui, "infoBanner"):
            self.ui.infoBanner.setText(
                f"{term_label}: Bạn chỉ thấy dữ liệu theo môn/lớp được phân công (học kỳ đang chọn)."
            )
        pcs = []
        if table_exists("PHAN_CONG"):
            clause = self._phan_cong_trang_thai_clause()
            pcs = fetch_all(
                f"""
                SELECT p.MaMon, COALESCE(m.TenMon, p.MaMon), COALESCE(TRIM(p.Lop), '')
                FROM PHAN_CONG p
                LEFT JOIN MON_HOC m ON m.MaMon = p.MaMon
                WHERE p.MaGV = ? AND p.HocKy = ? AND p.NamHoc = ?
                {clause}
                ORDER BY p.MaMon, p.Lop
                """,
                (self.username, hk, nam),
            )
        mon_codes = []
        seen_m = set()
        for r in pcs:
            if r[0] not in seen_m:
                seen_m.add(r[0])
                mon_codes.append(r[0])
        lops = sorted({str(r[2]).strip() for r in pcs if str(r[2]).strip()})
        mon_count = len(mon_codes)
        class_count = len(lops)
        if lops:
            ph = ",".join("?" * len(lops))
            cnt_sv = fetch_all(
                f"SELECT COUNT(DISTINCT MSSV) FROM SINH_VIEN WHERE Lop IN ({ph})",
                tuple(lops),
            )
            total_students = int(cnt_sv[0][0]) if cnt_sv else 0
        else:
            total_students = 0
        chua_nhap = 0
        for ma_mon, _ten, lop_raw in pcs:
            lop = str(lop_raw).strip()
            if not lop:
                continue
            miss = fetch_all(
                """
                SELECT COUNT(*)
                FROM SINH_VIEN s
                WHERE s.Lop = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM DIEM d
                    WHERE d.MSSV = s.MSSV AND d.MaMon = ?
                      AND d.HocKy = ? AND d.NamHoc = ?
                      AND d.DTB IS NOT NULL
                  )
                """,
                (lop, ma_mon, hk, nam),
            )
            chua_nhap += int(miss[0][0]) if miss else 0
        self.ui.cardSoLop.setText(f"Lớp phụ trách\n{class_count}")
        self.ui.cardSoMon.setText(f"Môn được dạy\n{mon_count}")
        self.ui.cardTongSV.setText(f"Sinh viên tổng\n{total_students}")
        self.ui.cardChuaNhap.setText(f"Chưa nhập điểm\n{chua_nhap}")
        phan_cong_table = self.ui.tbPhanCong
        phan_cong_table.setRowCount(0)
        for idx, (ma_mon, ten_mon, lop_raw) in enumerate(pcs):
            lop = str(lop_raw).strip() or "—"
            phan_cong_table.insertRow(idx)
            phan_cong_table.setItem(idx, 0, QTableWidgetItem(f"{ma_mon} — {ten_mon}"))
            phan_cong_table.setItem(idx, 1, QTableWidgetItem(lop))
            phan_cong_table.setItem(idx, 2, QTableWidgetItem(f"HK{hk} — {nam}"))
            st_txt = "—"
            if lop != "—":
                tot = fetch_all("SELECT COUNT(*) FROM SINH_VIEN WHERE Lop = ?", (lop,))
                n_tot = int(tot[0][0]) if tot else 0
                ok = fetch_all(
                    """
                    SELECT COUNT(*)
                    FROM SINH_VIEN s
                    WHERE s.Lop = ? AND EXISTS (
                      SELECT 1 FROM DIEM d WHERE d.MSSV = s.MSSV AND d.MaMon = ?
                        AND d.HocKy = ? AND d.NamHoc = ? AND d.DTB IS NOT NULL
                    )
                    """,
                    (lop, ma_mon, hk, nam),
                )
                n_ok = int(ok[0][0]) if ok else 0
                if n_tot == 0:
                    st_txt = "Chưa có SV"
                elif n_ok >= n_tot:
                    st_txt = "Đã nhập đủ"
                elif n_ok > 0:
                    st_txt = f"Mới nhập {n_ok}/{n_tot}"
                else:
                    st_txt = "Chưa nhập"
            phan_cong_table.setItem(idx, 3, QTableWidgetItem(st_txt))
        viec_table = self.ui.tbViecCanLam
        viec_table.setRowCount(0)
        todo_rows = []
        for ma_mon, ten_mon, lop_raw in pcs:
            lop = str(lop_raw).strip()
            if not lop:
                continue
            miss = fetch_all(
                """
                SELECT COUNT(*)
                FROM SINH_VIEN s
                WHERE s.Lop = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM DIEM d
                    WHERE d.MSSV = s.MSSV AND d.MaMon = ?
                      AND d.HocKy = ? AND d.NamHoc = ?
                      AND d.DTB IS NOT NULL
                  )
                """,
                (lop, ma_mon, hk, nam),
            )
            nmiss = int(miss[0][0]) if miss else 0
            if nmiss > 0:
                todo_rows.append(
                    (f"Chưa nhập điểm — {ten_mon} · {lop}", f"{nmiss} sinh viên"),
                )
        if not todo_rows:
            todo_rows.append(("Không có việc khẩn — điểm đã nhập đủ theo phân công", "—"))
        for idx, (noi_dung, nhac_han) in enumerate(todo_rows[:8]):
            viec_table.insertRow(idx)
            viec_table.setItem(idx, 0, QTableWidgetItem(noi_dung))
            viec_table.setItem(idx, 1, QTableWidgetItem(nhac_han))

    def render_students(self, rows_with_scores):
        self.ui.tbSinhVien.setRowCount(0)
        for row_num, row_data in enumerate(rows_with_scores):
            self.ui.tbSinhVien.insertRow(row_num)
            for col_num, data in enumerate(row_data):
                if col_num == 8:
                    mssv = str(row_data[0])
                    ho_ten = str(row_data[1])
                    lop = str(row_data[2])
                    aw = QWidget()
                    al = QHBoxLayout(aw)
                    al.setContentsMargins(2, 2, 2, 2)
                    al.setSpacing(4)
                    btn_edit = QPushButton("Sửa")
                    btn_del = QPushButton("Xóa")
                    for b in (btn_edit, btn_del):
                        b.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_edit.clicked.connect(
                        lambda _=False, m=mssv, h=ho_ten, l=lop: self.edit_student(m, h, l)
                    )
                    btn_del.clicked.connect(lambda _=False, m=mssv: self.delete_student(m))
                    al.addWidget(btn_edit)
                    al.addWidget(btn_del)
                    self.ui.tbSinhVien.setCellWidget(row_num, col_num, aw)
                elif col_num == 7:
                    item = QTableWidgetItem(str(data))
                    try:
                        dtb_val = float(data)
                        if dtb_val < 4:
                            item.setForeground(QBrush(QColor("#b91c1c")))
                        elif dtb_val < 7:
                            item.setForeground(QBrush(QColor("#8b5e00")))
                        else:
                            item.setForeground(QBrush(QColor("#155e75")))
                    except Exception:
                        pass
                    self.ui.tbSinhVien.setItem(row_num, col_num, item)
                else:
                    self.ui.tbSinhVien.setItem(row_num, col_num, QTableWidgetItem(str(data)))

    def filter_students(self, keyword=""):
        key = keyword.strip().lower() if isinstance(keyword, str) else self.ui.txtTimSinhVien.text().strip().lower()
        selected_lop = self.ui.cbLopSV.currentData()
        selected_mon = self.ui.cbMonSV.currentData()
        selected_status = self.ui.cbTrangThaiSV.currentData()
        hk, nam = self._current_term()
        score_map = {}
        try:
            rows = fetch_all(
                "SELECT MSSV, MaMon, CC, GK, CK, DTB FROM DIEM WHERE HocKy = ? AND NamHoc = ?",
                (hk, nam),
            )
            for mssv, ma_mon, cc, gk, ck, dtb in rows:
                score_map.setdefault(mssv, {})
                score_map[mssv][ma_mon] = (cc, gk, ck, dtb)
        except Exception:
            pass
        filtered = []
        count_done = 0
        count_missing = 0
        count_fail = 0
        for mssv, ho_ten, lop, *_ in self.all_students:
            mon_scores = score_map.get(mssv, {})
            if key and key not in str(mssv).lower() and key not in str(ho_ten).lower():
                continue
            if selected_lop and lop != selected_lop:
                continue
            if selected_mon:
                # Luôn liệt kê SV được phân công (lớp/môn); điểm có thì hiện, chưa nhập thì "—".
                if selected_mon in mon_scores:
                    cc, gk, ck, dtb = mon_scores[selected_mon]
                else:
                    cc = gk = ck = dtb = None
            else:
                cc = gk = ck = dtb = None
                if mon_scores:
                    first = next(iter(mon_scores.values()))
                    cc, gk, ck, dtb = first
            has_score = dtb is not None
            if selected_status == "done" and not has_score:
                continue
            if selected_status == "missing" and has_score:
                continue
            if has_score:
                count_done += 1
                try:
                    if float(dtb) < 4:
                        count_fail += 1
                except (TypeError, ValueError):
                    pass
            else:
                count_missing += 1
            email = f"{str(mssv).lower()}@abc.edu.vn"
            filtered.append(
                (
                    mssv,
                    ho_ten,
                    lop,
                    email,
                    f"{cc:.1f}" if cc is not None else "—",
                    f"{gk:.1f}" if gk is not None else "—",
                    f"{ck:.1f}" if ck is not None else "—",
                    f"{dtb:.2f}" if dtb is not None else "—",
                    "Xem",
                )
            )
        self.render_students(filtered)
        self.ui.cardTongSv.setText(f"Tổng SV\n{len(filtered)}")
        self.ui.cardDaCoDiem.setText(f"Đã có điểm\n{count_done}")
        self.ui.cardChuaNhapSv.setText(f"Chưa nhập\n{count_missing}")
        self.ui.cardRotMon.setText(f"Rớt môn\n{count_fail}")

    def add_student(self):
        mssv, ok = QInputDialog.getText(self, "Thêm sinh viên", "MSSV:")
        if not ok or not mssv.strip():
            return
        mssv = mssv.strip()
        if fetch_all("SELECT 1 FROM TAI_KHOAN WHERE TenDangNhap = ?", (mssv,)):
            QMessageBox.warning(self, "Trùng MSSV", f"Tài khoản {mssv} đã tồn tại.")
            return
        ho_ten, ok = QInputDialog.getText(self, "Thêm sinh viên", "Họ tên:")
        if not ok or not ho_ten.strip():
            return
        lop, ok = QInputDialog.getText(self, "Thêm sinh viên", "Lớp:")
        if not ok or not lop.strip():
            return
        lop = lop.strip()
        default_pwd = "12345678"
        try:
            ensure_danh_muc_lop_table()
            execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (lop,))
            execute_query(
                """
                INSERT INTO TAI_KHOAN
                    (TenDangNhap, MatKhau, VaiTro, TrangThai, SoLanSaiMK, TaoLuc, CapNhatLuc)
                VALUES (?, ?, 'Sinh viên', 'HOAT_DONG', 0, datetime('now', 'localtime'), datetime('now', 'localtime'))
                """,
                (mssv, hash_password(default_pwd)),
            )
            execute_query(
                "INSERT INTO SINH_VIEN (MSSV, HoTen, Lop, GPA10, GPA4, XepLoai) VALUES (?, ?, ?, 0, 0, 'Chưa có')",
                (mssv, ho_ten.strip(), lop),
            )
            self.load_dashboard_data()
            QMessageBox.information(
                self,
                "Thành công",
                f"Đã thêm sinh viên {mssv}.\nMật khẩu mặc định: {default_pwd}",
            )
            log_event(self.username, "Giảng viên", "Quản trị", f"Thêm sinh viên {mssv}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thêm được sinh viên: {e}")

    def edit_student(self, mssv, ho_ten, lop):
        ho_moi, ok = QInputDialog.getText(self, "Sửa sinh viên", f"Họ tên ({mssv}):", text=ho_ten)
        if not ok or not ho_moi.strip():
            return
        lop_moi, ok = QInputDialog.getText(self, "Sửa sinh viên", "Lớp:", text=lop)
        if not ok or not lop_moi.strip():
            return
        try:
            ensure_danh_muc_lop_table()
            execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (lop_moi.strip(),))
            execute_query(
                "UPDATE SINH_VIEN SET HoTen = ?, Lop = ? WHERE MSSV = ?",
                (ho_moi.strip(), lop_moi.strip(), mssv),
            )
            self.load_dashboard_data()
            QMessageBox.information(self, "Thành công", "Đã cập nhật hồ sơ sinh viên.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật được: {e}")

    def delete_student(self, mssv):
        ans = QMessageBox.question(
            self,
            "Xóa sinh viên",
            f"Xóa sinh viên {mssv} và toàn bộ điểm liên quan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            execute_query("DELETE FROM TAI_KHOAN WHERE TenDangNhap = ?", (mssv,))
            self.load_dashboard_data()
            log_event(self.username, "Giảng viên", "Quản trị", f"Xóa sinh viên {mssv}")
            QMessageBox.information(self, "Đã xóa", f"Đã xóa sinh viên {mssv}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xóa được: {e}")

    def load_score_table(self):
        table = self.ui.tbNhapDiem
        table.setRowCount(0)
        selected_lop = self.ui.cbLopNhap.currentData() or ""
        selected_mon = self.ui.cbMonNhap.currentData() or ""
        hoc_ky, nam_hoc = self._current_term()
        allowed_students = [(str(m), str(h), str(l)) for m, h, l, *_ in self.all_students]
        if selected_lop:
            allowed_students = [r for r in allowed_students if r[2] == str(selected_lop)]
        allowed_ids = {r[0] for r in allowed_students}
        self._scores_locked = False
        if selected_mon:
            scope_sql = ""
            scope_params = []
            if selected_lop:
                scope_sql = " AND MSSV IN (SELECT MSSV FROM SINH_VIEN WHERE Lop = ?) "
                scope_params.append(selected_lop)
            base_params = [selected_mon, hoc_ky, nam_hoc] + scope_params
            unpub_rows = fetch_all(
                f"""
                SELECT COUNT(*)
                FROM DIEM
                WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
                  AND COALESCE(DaKhoa, 0) = 0 AND DTB IS NOT NULL
                  {scope_sql}
                """,
                tuple(base_params),
            )
            pub_rows = fetch_all(
                f"""
                SELECT COUNT(*)
                FROM DIEM
                WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
                  AND COALESCE(DaKhoa, 0) = 1
                  {scope_sql}
                """,
                tuple(base_params),
            )
            unpub_cnt = int(unpub_rows[0][0]) if unpub_rows else 0
            pub_cnt = int(pub_rows[0][0]) if pub_rows else 0
            self._scores_locked = pub_cnt > 0 and unpub_cnt == 0
        self.ui.btnLuuDiem.setEnabled(not self._scores_locked)
        self.ui.btnHuyThayDoi.setEnabled(not self._scores_locked)
        btn_publish = getattr(self.ui, "btnNopKhoaDiem", None)
        if btn_publish is not None:
            draft_cnt = 0
            if selected_mon:
                scope_sql = ""
                scope_params = []
                if selected_lop:
                    scope_sql = " AND MSSV IN (SELECT MSSV FROM SINH_VIEN WHERE Lop = ?) "
                    scope_params.append(selected_lop)
                draft_row = fetch_all(
                    f"""
                    SELECT COUNT(*)
                    FROM DIEM
                    WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
                      AND COALESCE(DaKhoa, 0) = 0 AND DTB IS NOT NULL
                      {scope_sql}
                    """,
                    tuple([selected_mon, hoc_ky, nam_hoc] + scope_params),
                )
                draft_cnt = int(draft_row[0][0]) if draft_row else 0
            btn_publish.setEnabled(not self._scores_locked and draft_cnt > 0)
        lock_lbl = getattr(self.ui, "lblLockNotice", None)
        if lock_lbl is not None:
            if self._scores_locked:
                lock_lbl.setText("Điểm đã công bố — sinh viên đang xem được.")
            else:
                lock_lbl.setText("Lưu điểm trước, sau đó bấm «Công bố điểm» để sinh viên xem.")
        if not selected_mon:
            self._all_score_rows = []
            for mssv, ho_ten, lop in allowed_students:
                self._all_score_rows.append((mssv, ho_ten, ""))
        else:
            query = """
                SELECT s.MSSV, s.HoTen, s.Lop, d.CC, d.GK, d.CK, d.DTB
                FROM SINH_VIEN s
                LEFT JOIN DIEM d
                    ON d.MSSV = s.MSSV
                    AND d.MaMon = ?
                    AND d.HocKy = ?
                    AND d.NamHoc = ?
                ORDER BY s.MSSV
            """
            self._all_score_rows = fetch_all(query, (selected_mon, hoc_ky, nam_hoc))
            # Chỉ giữ sinh viên trong phạm vi môn/lớp được phân công cho giảng viên.
            self._all_score_rows = [row for row in self._all_score_rows if str(row[0]) in allowed_ids]
        for i, row in enumerate(self._all_score_rows):
            table.insertRow(i)
            mssv, ho_ten = row[0], row[1]
            table.setItem(i, 0, QTableWidgetItem(str(mssv)))
            table.setItem(i, 1, QTableWidgetItem(str(ho_ten)))
            cc = row[3] if len(row) > 3 else None
            gk = row[4] if len(row) > 4 else None
            ck = row[5] if len(row) > 5 else None
            dtb = row[6] if len(row) > 6 else None
            for col, score in ((2, cc), (3, gk), (4, ck)):
                editor = QLineEdit("" if score is None else f"{float(score):.1f}")
                editor.setObjectName("scoreInput")
                editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
                editor.setPlaceholderText("—")
                editor.setEnabled(not self._scores_locked)
                editor.textChanged.connect(lambda _t, r=i: self._update_score_row_preview(r))
                table.setCellWidget(i, col, editor)
            dtb_item = QTableWidgetItem("" if dtb is None else f"{float(dtb):.2f}")
            if dtb is not None:
                dtb_val = float(dtb)
                if dtb_val < 4:
                    dtb_item.setForeground(QBrush(QColor("#b91c1c")))
                elif dtb_val < 7:
                    dtb_item.setForeground(QBrush(QColor("#8b5e00")))
                else:
                    dtb_item.setForeground(QBrush(QColor("#155e75")))
            table.setItem(i, 5, dtb_item)
            xep_loai = _hoc_luc_tu_gpa10(float(dtb))[0] if dtb is not None else "Chưa nhập"
            table.setCellWidget(i, 6, self._badge_label_text(xep_loai))
            if dtb is not None:
                if self._scores_locked:
                    status_text = "Đã công bố"
                else:
                    row_pub = fetch_all(
                        """
                        SELECT COALESCE(DaKhoa, 0) FROM DIEM
                        WHERE MSSV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ?
                        """,
                        (mssv, selected_mon, hoc_ky, nam_hoc),
                    )
                    status_text = "Đã công bố" if row_pub and int(row_pub[0][0]) == 1 else "Chưa công bố"
            else:
                status_text = "Thiếu điểm"
            table.setCellWidget(i, 7, self._status_label(status_text))
        self.load_attendance_history()

    def _read_score_row(self, row):
        table = self.ui.tbNhapDiem
        values = []
        for col in (2, 3, 4):
            widget = table.cellWidget(row, col)
            text = widget.text().strip() if isinstance(widget, QLineEdit) else ""
            if not text:
                values.append(None)
                continue
            try:
                val = float(text)
                if val < 0 or val > 10:
                    return None
                values.append(val)
            except Exception:
                return None
        return values

    def _update_score_row_preview(self, row):
        table = self.ui.tbNhapDiem
        values = self._read_score_row(row)
        if values is None:
            table.setItem(row, 5, QTableWidgetItem("—"))
            table.setCellWidget(row, 6, self._badge_label_text("Chưa nhập"))
            table.setCellWidget(row, 7, self._status_label("Thiếu điểm"))
            return
        if any(v is None for v in values):
            table.setItem(row, 5, QTableWidgetItem("—"))
            table.setCellWidget(row, 6, self._badge_label_text("Chưa nhập"))
            table.setCellWidget(row, 7, self._status_label("Thiếu điểm"))
            return
        cc, gk, ck = values
        dtb = round(cc * 0.1 + gk * 0.3 + ck * 0.6, 2)
        item = QTableWidgetItem(f"{dtb:.2f}")
        if dtb < 4:
            item.setForeground(QBrush(QColor("#b91c1c")))
        elif dtb < 7:
            item.setForeground(QBrush(QColor("#8b5e00")))
        else:
            item.setForeground(QBrush(QColor("#155e75")))
        table.setItem(row, 5, item)
        table.setCellWidget(row, 6, self._badge_label_text(_hoc_luc_tu_gpa10(dtb)[0]))
        table.setCellWidget(row, 7, self._status_label("Chưa lưu"))

    def _badge_label_text(self, text):
        lb = QLabel(text)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color_map = {
            "Xuất sắc": ("#dcfce7", "#166534"),
            "Giỏi": ("#e0f2fe", "#0c4a6e"),
            "Khá": ("#fef9c3", "#854d0e"),
            "Trung bình": ("#fef3c7", "#92400e"),
            "Yếu / Kém": ("#fee2e2", "#991b1b"),
            "Chưa nhập": ("#f3f4f6", "#374151"),
        }
        bg, fg = color_map.get(text, ("#f3f4f6", "#374151"))
        lb.setStyleSheet(
            f"background:{bg};color:{fg};padding:4px 10px;border-radius:10px;font-weight:600;font-size:12px;"
        )
        return lb

    def _status_label(self, text):
        lb = QLabel(text)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if text in ("Đã lưu", "Đã khóa"):
            lb.setStyleSheet("color:#166534;font-weight:600;")
        elif text == "Thiếu điểm":
            lb.setStyleSheet("color:#92400e;font-weight:600;")
        else:
            lb.setStyleSheet("color:#991b1b;font-weight:600;")
        return lb

    def save_scores_from_table(self):
        if self._scores_locked:
            QMessageBox.warning(
                self,
                "Đã công bố",
                "Điểm môn này đã được công bố. Sinh viên đang xem — không thể chỉnh sửa thêm.",
            )
            return
        selected_mon = self.ui.cbMonNhap.currentData()
        selected_lop = self.ui.cbLopNhap.currentData()
        if not selected_mon:
            QMessageBox.information(self, "Thiếu môn", "Vui lòng chọn môn trước khi lưu điểm.")
            return
        hoc_ky, nam_hoc = self._current_term()
        table = self.ui.tbNhapDiem
        saved = 0
        skipped_empty = 0
        skipped_invalid = 0
        for row in range(table.rowCount()):
            mssv_item = table.item(row, 0)
            if mssv_item is None:
                continue
            mssv = mssv_item.text().strip()
            try:
                cc_widget = table.cellWidget(row, 2)
                gk_widget = table.cellWidget(row, 3)
                ck_widget = table.cellWidget(row, 4)
                cc_text = cc_widget.text().strip() if isinstance(cc_widget, QLineEdit) else ""
                gk_text = gk_widget.text().strip() if isinstance(gk_widget, QLineEdit) else ""
                ck_text = ck_widget.text().strip() if isinstance(ck_widget, QLineEdit) else ""
                if not cc_text and not gk_text and not ck_text:
                    skipped_empty += 1
                    continue
                cc = float(cc_text) if cc_text else None
                gk = float(gk_text) if gk_text else None
                ck = float(ck_text) if ck_text else None
                vals = [v for v in (cc, gk, ck) if v is not None]
                if vals and (min(vals) < 0 or max(vals) > 10):
                    raise ValueError("Điểm phải trong khoảng 0-10")
            except Exception:
                skipped_invalid += 1
                continue
            cur = fetch_all(
                """
                SELECT CC, GK, CK, COALESCE(DaKhoa, 0)
                FROM DIEM
                WHERE MSSV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ?
                """,
                (mssv, selected_mon, hoc_ky, nam_hoc),
            )
            old_cc = old_gk = old_ck = None
            da_khoa = 0
            if cur:
                old_cc, old_gk, old_ck, da_khoa = cur[0]
            if int(da_khoa) == 1:
                continue
            merged_cc = cc if cc is not None else old_cc
            merged_gk = gk if gk is not None else old_gk
            merged_ck = ck if ck is not None else old_ck
            if merged_cc is not None and merged_gk is not None and merged_ck is not None:
                dtb = round(float(merged_cc) * 0.1 + float(merged_gk) * 0.3 + float(merged_ck) * 0.6, 2)
            else:
                dtb = None
            execute_query(
                "DELETE FROM DIEM WHERE MSSV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ? AND COALESCE(DaKhoa, 0) = 0",
                (mssv, selected_mon, hoc_ky, nam_hoc),
            )
            execute_query(
                "INSERT INTO DIEM (MSSV, MaMon, HocKy, NamHoc, CC, GK, CK, DTB, DaKhoa, NguoiNhap) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (mssv, selected_mon, hoc_ky, nam_hoc, merged_cc, merged_gk, merged_ck, dtb, self.username),
            )
            if dtb is not None:
                table.setItem(row, 5, QTableWidgetItem(f"{dtb:.2f}"))
                table.setCellWidget(row, 6, self._badge_label_text(_hoc_luc_tu_gpa10(dtb)[0]))
            else:
                table.setItem(row, 5, QTableWidgetItem("—"))
                table.setCellWidget(row, 6, self._badge_label_text("Chưa nhập"))
            table.setCellWidget(row, 7, self._status_label("Đã lưu"))
            self._update_student_gpa(mssv)
            saved += 1
        if saved <= 0:
            QMessageBox.warning(
                self,
                "Chưa lưu được",
                "Không có dòng hợp lệ để lưu.\n"
                f"- Chưa nhập ô điểm nào: {skipped_empty} dòng\n"
                f"- Điểm không hợp lệ (ngoài 0-10/sai định dạng): {skipped_invalid} dòng\n\n"
                "Vui lòng chọn môn cụ thể rồi nhập ít nhất một cột điểm (CC/GK/CK).",
            )
            return
        log_event(self.username, "Giảng viên", "Điểm số", f"Lưu điểm {selected_mon} HK{hoc_ky}/{nam_hoc} ({saved} dòng)")
        self.load_dashboard_data()
        # Giữ nguyên bộ lọc ở tab Nhập điểm để không tạo cảm giác "mất điểm" sau khi lưu.
        idx_mn = self.ui.cbMonNhap.findData(selected_mon)
        if idx_mn >= 0:
            self.ui.cbMonNhap.setCurrentIndex(idx_mn)
        idx_ln = self.ui.cbLopNhap.findData(selected_lop)
        if idx_ln >= 0:
            self.ui.cbLopNhap.setCurrentIndex(idx_ln)
        # Đồng bộ bộ lọc sang tab Danh sách SV để thấy ngay điểm vừa lưu.
        idx_m = self.ui.cbMonSV.findData(selected_mon)
        if idx_m >= 0:
            self.ui.cbMonSV.setCurrentIndex(idx_m)
        idx_l = self.ui.cbLopSV.findData(selected_lop)
        if idx_l >= 0:
            self.ui.cbLopSV.setCurrentIndex(idx_l)
        self.load_score_table()
        self.filter_students()
        QMessageBox.information(self, "Đã lưu", f"Đã lưu {saved} dòng điểm.")

    def _update_student_gpa(self, mssv):
        try:
            sync_student_gpa_record(mssv, fetch_all, execute_query)
        except Exception:
            return

    def submit_and_lock_scores(self):
        selected_mon = self.ui.cbMonNhap.currentData()
        selected_lop = self.ui.cbLopNhap.currentData() or ""
        hoc_ky, nam_hoc = self._current_term()
        if not selected_mon:
            QMessageBox.information(self, "Thiếu môn", "Vui lòng chọn môn trước khi công bố điểm.")
            return
        pending = fetch_all(
            """
            SELECT COUNT(*)
            FROM DIEM
            WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
              AND COALESCE(DaKhoa, 0) = 0 AND DTB IS NOT NULL
            """,
            (selected_mon, hoc_ky, nam_hoc),
        )
        pending_cnt = int(pending[0][0]) if pending else 0
        if pending_cnt <= 0:
            QMessageBox.information(
                self,
                "Chưa có điểm",
                "Chưa có điểm đã nhập để công bố.\nVui lòng lưu điểm trước khi công bố.",
            )
            return
        lop_note = f" — lớp {selected_lop}" if selected_lop else ""
        ans = QMessageBox.question(
            self,
            "Công bố điểm",
            f"Công bố điểm môn {selected_mon}{lop_note} (HK{hoc_ky}/{nam_hoc})?\n\n"
            f"Sẽ công bố {pending_cnt} bản ghi điểm.\n"
            "Sau khi công bố, sinh viên mới xem được và bạn không chỉnh sửa được nữa.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        if selected_lop:
            execute_query(
                """
                UPDATE DIEM
                SET DaKhoa = 1, LanCapNhatCuoi = datetime('now', 'localtime')
                WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
                  AND COALESCE(DaKhoa, 0) = 0 AND DTB IS NOT NULL
                  AND MSSV IN (SELECT MSSV FROM SINH_VIEN WHERE Lop = ?)
                """,
                (selected_mon, hoc_ky, nam_hoc, selected_lop),
            )
        else:
            execute_query(
                """
                UPDATE DIEM
                SET DaKhoa = 1, LanCapNhatCuoi = datetime('now', 'localtime')
                WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
                  AND COALESCE(DaKhoa, 0) = 0 AND DTB IS NOT NULL
                """,
                (selected_mon, hoc_ky, nam_hoc),
            )
        self._scores_locked = True
        self.ui.btnLuuDiem.setEnabled(False)
        self.ui.btnHuyThayDoi.setEnabled(False)
        btn_publish = getattr(self.ui, "btnNopKhoaDiem", None)
        if btn_publish is not None:
            btn_publish.setEnabled(False)
        log_event(
            self.username,
            "Giảng viên",
            "Điểm số",
            f"Công bố điểm {selected_mon} HK{hoc_ky}/{nam_hoc} ({pending_cnt} dòng)",
        )
        if selected_lop:
            for (mssv,) in fetch_all(
                "SELECT MSSV FROM SINH_VIEN WHERE Lop = ?", (selected_lop,)
            ):
                sync_student_gpa_record(mssv, fetch_all, execute_query)
        else:
            for (mssv,) in fetch_all(
                """
                SELECT DISTINCT MSSV FROM DIEM
                WHERE MaMon = ? AND HocKy = ? AND NamHoc = ?
                """,
                (selected_mon, hoc_ky, nam_hoc),
            ):
                sync_student_gpa_record(mssv, fetch_all, execute_query)
        self.load_score_table()
        QMessageBox.information(
            self,
            "Đã công bố",
            f"Đã công bố {pending_cnt} bản ghi điểm.\nSinh viên có thể xem điểm môn này trên cổng sinh viên.",
        )

    def _lecturer_bao_cao_diem_rows(self, hoc_ky, nam_hoc, selected_lop, selected_mon):
        where = " WHERE d.HocKy = ? AND d.NamHoc = ? "
        params = [hoc_ky, nam_hoc]
        if selected_lop:
            where += " AND s.Lop = ? "
            params.append(selected_lop)
        if selected_mon:
            where += " AND d.MaMon = ? "
            params.append(selected_mon)
        return fetch_all(
            f"""
            SELECT s.MSSV, s.HoTen, s.Lop, d.MaMon, d.DTB
            FROM DIEM d
            JOIN SINH_VIEN s ON s.MSSV = d.MSSV
            {where}
            ORDER BY s.Lop, s.MSSV, d.MaMon
            """,
            tuple(params),
        )

    def render_bao_cao_tab(self):
        hoc_ky, nam_hoc = self.ui.cbBaoCaoHocKy.currentData() or (1, "2024-2025")
        selected_lop = self.ui.cbBaoCaoLop.currentData() or ""
        selected_mon = self.ui.cbBaoCaoMon.currentData() or ""
        rows = self._lecturer_bao_cao_diem_rows(hoc_ky, nam_hoc, selected_lop, selected_mon)
        clean_rows = []
        for r in rows:
            try:
                dtb_val = float(r[4])
            except (TypeError, ValueError):
                continue
            clean_rows.append((r[0], r[1], r[2], r[3], dtb_val))
        total = len(clean_rows)
        uniq_sv = len({r[0] for r in clean_rows}) if clean_rows else 0
        if hasattr(self.ui, "lblBaoCaoScope"):
            lop_txt = selected_lop or "tất cả lớp"
            mon_txt = selected_mon or "tất cả môn"
            self.ui.lblBaoCaoScope.setText(
                f"HK{hoc_ky} — {nam_hoc} · Lớp: {lop_txt} · Môn: {mon_txt} · "
                f"Dữ liệu điểm theo bộ lọc hiện tại ({uniq_sv} SV, {total} dòng điểm)."
            )
        if total == 0:
            self.ui.cardBaoCaoTongSv.setText("Tổng hợp\n0 SV · 0 điểm")
            self.ui.cardBaoCaoTiLeDau.setText("Tỉ lệ đậu\n0%")
            self.ui.cardBaoCaoDtbCao.setText("ĐTB cao nhất\n0.00")
            self.ui.cardBaoCaoCanChuY.setText("Cần chú ý\n0")
            for tb in (self.ui.tbBaoCaoTheoLop, self.ui.tbBaoCaoDtbLop, self.ui.tbBaoCaoPhanBo, self.ui.tbBaoCaoCanhBao, self.ui.tbBaoCaoXuat):
                tb.setRowCount(0)
            if getattr(self, "_bao_cao_chart", None):
                self._bao_cao_chart.set_distribution([])
            return

        passed = [r for r in clean_rows if r[4] >= 4.0]
        warnings = [r for r in clean_rows if r[4] < 4.0]
        self.ui.cardBaoCaoTongSv.setText(f"Tổng hợp\n{uniq_sv} SV\n{total} dòng điểm")
        pct_dau = round(len(passed) * 100 / total)
        self.ui.cardBaoCaoTiLeDau.setText(f"Tỉ lệ đậu\n{pct_dau}%")
        self.ui.cardBaoCaoTiLeDau.setToolTip(
            f"Tính trên {total} dòng điểm (theo ĐTB từng môn, ngưỡng đậu ≥ 4)."
        )
        self.ui.cardBaoCaoDtbCao.setText(f"ĐTB cao nhất\n{max(r[4] for r in clean_rows):.2f}")
        self.ui.cardBaoCaoCanChuY.setText(f"Cần chú ý\n{len(warnings)}")
        self.ui.cardBaoCaoCanChuY.setToolTip(f"Số dòng có ĐTB dưới 4 trong {total} bản ghi hiện tại.")

        by_lop = {}
        for _mssv, _ho_ten, lop, _ma, dtb in clean_rows:
            by_lop.setdefault(lop, []).append(dtb)
        tb_lop = self.ui.tbBaoCaoTheoLop
        tb_lop.setRowCount(0)
        for i, (lop, arr) in enumerate(sorted(by_lop.items())):
            tb_lop.insertRow(i)
            rate = round(sum(1 for v in arr if v >= 4.0) * 100 / len(arr))
            tb_lop.setItem(i, 0, QTableWidgetItem(lop))
            tb_lop.setItem(i, 1, QTableWidgetItem(f"{rate}%"))

        by_lop_mon = {}
        for _mssv, _ho_ten, lop, ma, dtb in clean_rows:
            key = f"{ma}/{lop}"
            by_lop_mon.setdefault(key, []).append(dtb)
        tb_dtb = self.ui.tbBaoCaoDtbLop
        tb_dtb.setRowCount(0)
        for i, (key, arr) in enumerate(sorted(by_lop_mon.items())[:8]):
            tb_dtb.insertRow(i)
            tb_dtb.setItem(i, 0, QTableWidgetItem(key))
            tb_dtb.setItem(i, 1, QTableWidgetItem(f"{sum(arr)/len(arr):.2f}"))

        bins = {"Xuất sắc (>=8.5)": 0, "Giỏi (7.0-8.4)": 0, "Khá (5.5-6.9)": 0, "Trung bình (4-5.4)": 0, "Yếu/Kém (<4.0)": 0}
        for *_a, dtb in clean_rows:
            g = dtb
            if g >= 8.5:
                bins["Xuất sắc (>=8.5)"] += 1
            elif g >= 7.0:
                bins["Giỏi (7.0-8.4)"] += 1
            elif g >= 5.5:
                bins["Khá (5.5-6.9)"] += 1
            elif g >= 4.0:
                bins["Trung bình (4-5.4)"] += 1
            else:
                bins["Yếu/Kém (<4.0)"] += 1
        tb_pb = self.ui.tbBaoCaoPhanBo
        tb_pb.setRowCount(0)
        for i, (label, cnt) in enumerate(bins.items()):
            tb_pb.insertRow(i)
            tb_pb.setItem(i, 0, QTableWidgetItem(label))
            tb_pb.setItem(i, 1, QTableWidgetItem(f"{round(cnt * 100 / total)}%"))

        tb_warn = self.ui.tbBaoCaoCanhBao
        tb_warn.setRowCount(0)
        # Hiển thị toàn bộ dòng điểm (sắp ĐTB tăng dần), không chỉ SV rớt — tránh bảng trống khi 100% đậu.
        detail_limit = 50
        ranked = sorted(clean_rows, key=lambda x: x[4])
        for i, (mssv, ho_ten, lop, ma, dtb) in enumerate(ranked[:detail_limit]):
            tb_warn.insertRow(i)
            c0 = QTableWidgetItem(f"{ho_ten}\n{mssv}")
            c0.setToolTip(f"Lớp {lop}")
            tb_warn.setItem(i, 0, c0)
            tb_warn.setItem(i, 1, QTableWidgetItem(str(ma)))
            c2 = QTableWidgetItem(f"{dtb:.2f}")
            if dtb < 4:
                c2.setForeground(QBrush(QColor("#b91c1c")))
            tb_warn.setItem(i, 2, c2)
        if len(ranked) > detail_limit:
            r = tb_warn.rowCount()
            tb_warn.insertRow(r)
            tb_warn.setItem(r, 0, QTableWidgetItem(f"… và {len(ranked) - detail_limit} dòng khác"))
            tb_warn.setSpan(r, 0, 1, 3)

        tb_xuat = self.ui.tbBaoCaoXuat
        tb_xuat.setRowCount(0)
        for i, lop in enumerate(sorted(by_lop.keys())[:6]):
            tb_xuat.insertRow(i)
            tb_xuat.setItem(i, 0, QTableWidgetItem(f"Bảng điểm lớp {lop}\nHK{hoc_ky} {nam_hoc}"))
            btn_ex = QPushButton("Excel")
            btn_pdf = QPushButton("PDF")
            btn_ex.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
            lop_val = str(lop)
            btn_ex.clicked.connect(lambda _=False, lv=lop_val: self._export_lecturer_bao_cao_lop(lv, "excel"))
            btn_pdf.clicked.connect(lambda _=False, lv=lop_val: self._export_lecturer_bao_cao_lop(lv, "pdf"))
            tb_xuat.setCellWidget(i, 1, btn_ex)
            tb_xuat.setCellWidget(i, 2, btn_pdf)
        if getattr(self, "_bao_cao_chart", None):
            self._bao_cao_chart.set_distribution([r[4] for r in clean_rows])

    def _export_lecturer_bao_cao(self, kind: str):
        hoc_ky, nam_hoc = self.ui.cbBaoCaoHocKy.currentData() or (1, "2024-2025")
        selected_lop = self.ui.cbBaoCaoLop.currentData() or ""
        selected_mon = self.ui.cbBaoCaoMon.currentData() or ""
        rows = self._lecturer_bao_cao_diem_rows(hoc_ky, nam_hoc, selected_lop, selected_mon)
        if not rows:
            QMessageBox.information(self, "Không có dữ liệu", "Không có điểm phù hợp bộ lọc để xuất.")
            return
        hdr = ["MSSV", "Họ tên", "Lớp", "Mã môn", "ĐTB"]
        body = [[r[0], r[1], r[2], r[3], r[4]] for r in rows]
        scope = f"HK{hoc_ky} — {nam_hoc}"
        if selected_lop:
            scope += f" — Lớp {selected_lop}"
        if selected_mon:
            scope += f" — Môn {selected_mon}"
        title = f"Báo cáo điểm — {scope}"
        stem = f"bao_cao_GV_{self.username}_HK{hoc_ky}_{nam_hoc}"
        base = Path(__file__).resolve().parent
        if kind == "excel":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu Excel",
                str(base / f"{stem}.xlsx"),
                "Excel (*.xlsx);;CSV (*.csv)",
            )
            if not path:
                return
            k, err = export_to_excel(path, stem[:31], hdr, body)
            if err:
                QMessageBox.warning(self, "Lỗi", err)
                return
            QMessageBox.information(
                self,
                "Đã xuất",
                "Đã lưu file Excel." if k == "xlsx" else "Đã lưu CSV (UTF-8, mở bằng Excel). Cài openpyxl: pip install openpyxl",
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu PDF",
                str(base / f"{stem}.pdf"),
                "PDF (*.pdf)",
            )
            if not path:
                return
            err = export_to_pdf(path, title, hdr, body)
            if err:
                QMessageBox.warning(self, "Không xuất được PDF", err)
                return
            QMessageBox.information(self, "Đã xuất", "Đã lưu file PDF.")

    def _export_lecturer_bao_cao_lop(self, lop: str, kind: str):
        hoc_ky, nam_hoc = self.ui.cbBaoCaoHocKy.currentData() or (1, "2024-2025")
        selected_mon = self.ui.cbBaoCaoMon.currentData() or ""
        rows = self._lecturer_bao_cao_diem_rows(hoc_ky, nam_hoc, lop, selected_mon)
        if not rows:
            QMessageBox.information(self, "Không có dữ liệu", f"Không có điểm lớp « {lop} » để xuất.")
            return
        hdr = ["MSSV", "Họ tên", "Lớp", "Mã môn", "ĐTB"]
        body = [[r[0], r[1], r[2], r[3], r[4]] for r in rows]
        title = f"Bảng điểm lớp {lop} — HK{hoc_ky} {nam_hoc}"
        stem = f"diem_lop_{lop}_HK{hoc_ky}_{nam_hoc}"
        base = Path(__file__).resolve().parent
        if kind == "excel":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu Excel",
                str(base / f"{stem}.xlsx"),
                "Excel (*.xlsx);;CSV (*.csv)",
            )
            if not path:
                return
            k, err = export_to_excel(path, stem[:31], hdr, body)
            if err:
                QMessageBox.warning(self, "Lỗi", err)
                return
            QMessageBox.information(
                self,
                "Đã xuất",
                "Đã lưu file Excel." if k == "xlsx" else "Đã lưu CSV (UTF-8).",
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu PDF",
                str(base / f"{stem}.pdf"),
                "PDF (*.pdf)",
            )
            if not path:
                return
            err = export_to_pdf(path, title, hdr, body)
            if err:
                QMessageBox.warning(self, "Không xuất được PDF", err)
                return
            QMessageBox.information(self, "Đã xuất", "Đã lưu file PDF.")

    def _lecturer_sv_list_export_rows(self):
        key = self.ui.txtTimSinhVien.text().strip().lower()
        selected_lop = self.ui.cbLopSV.currentData()
        selected_mon = self.ui.cbMonSV.currentData()
        selected_status = self.ui.cbTrangThaiSV.currentData()
        hk, nam = self._current_term()
        score_map = {}
        try:
            rows_d = fetch_all(
                "SELECT MSSV, MaMon, CC, GK, CK, DTB FROM DIEM WHERE HocKy = ? AND NamHoc = ?",
                (hk, nam),
            )
            for mssv, ma_mon, cc, gk, ck, dtb in rows_d:
                score_map.setdefault(mssv, {})
                score_map[mssv][ma_mon] = (cc, gk, ck, dtb)
        except Exception:
            pass
        out = []
        for mssv, ho_ten, lop, *_ in self.all_students:
            mon_scores = score_map.get(mssv, {})
            if key and key not in str(mssv).lower() and key not in str(ho_ten).lower():
                continue
            if selected_lop and lop != selected_lop:
                continue
            if selected_mon:
                if selected_mon in mon_scores:
                    cc, gk, ck, dtb = mon_scores[selected_mon]
                else:
                    cc = gk = ck = dtb = None
            else:
                cc = gk = ck = dtb = None
                if mon_scores:
                    first = next(iter(mon_scores.values()))
                    cc, gk, ck, dtb = first
            has_score = dtb is not None
            if selected_status == "done" and not has_score:
                continue
            if selected_status == "missing" and has_score:
                continue
            out.append(
                [
                    mssv,
                    ho_ten,
                    lop,
                    f"{str(mssv).lower()}@abc.edu.vn",
                    f"{cc:.1f}" if cc is not None else "",
                    f"{gk:.1f}" if gk is not None else "",
                    f"{ck:.1f}" if ck is not None else "",
                    f"{dtb:.2f}" if dtb is not None else "",
                ]
            )
        return out

    def _export_lecturer_sv_list_dialog(self):
        fmt, ok = QInputDialog.getItem(
            self,
            "Xuất danh sách sinh viên",
            "Chọn định dạng:",
            ["Excel", "PDF"],
            0,
            False,
        )
        if not ok:
            return
        self._export_lecturer_sv_list("excel" if fmt == "Excel" else "pdf")

    def _export_lecturer_sv_list(self, kind: str):
        body = self._lecturer_sv_list_export_rows()
        if not body:
            QMessageBox.information(self, "Không có dữ liệu", "Danh sách đang trống theo bộ lọc hiện tại.")
            return
        hdr = ["MSSV", "Họ tên", "Lớp", "Email", "CC", "GK", "CK", "ĐTB"]
        hk, nam = self._current_term()
        title = f"Danh sách sinh viên — HK{hk} — {nam}"
        stem = f"danh_sach_SV_GV_{self.username}_HK{hk}_{nam}"
        base = Path(__file__).resolve().parent
        if kind == "excel":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu Excel",
                str(base / f"{stem}.xlsx"),
                "Excel (*.xlsx);;CSV (*.csv)",
            )
            if not path:
                return
            k, err = export_to_excel(path, stem[:31], hdr, body)
            if err:
                QMessageBox.warning(self, "Lỗi", err)
                return
            QMessageBox.information(
                self,
                "Đã xuất",
                "Đã lưu file Excel." if k == "xlsx" else "Đã lưu CSV (UTF-8).",
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu PDF",
                str(base / f"{stem}.pdf"),
                "PDF (*.pdf)",
            )
            if not path:
                return
            err = export_to_pdf(path, title, hdr, body)
            if err:
                QMessageBox.warning(self, "Không xuất được PDF", err)
                return
            QMessageBox.information(self, "Đã xuất", "Đã lưu file PDF.")

    def _initials(self, name):
        parts = [p for p in str(name).split() if p]
        if not parts:
            return "GV"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def render_ho_so_tab(self):
        gv = []
        if table_exists("GIANG_VIEN"):
            try:
                gv = fetch_all("SELECT MaGV, HoTen, Khoa FROM GIANG_VIEN WHERE MaGV = ?", (self.username,))
            except Exception:
                gv = []
        if gv:
            ma_gv, ho_ten, khoa = gv[0]
        else:
            ma_gv, ho_ten, khoa = self.username, self.username, "Công nghệ thông tin"
        email = f"{str(ma_gv).lower()}@abc.edu.vn"
        self.ui.lblAvatarHoSo.setText(self._initials(ho_ten))
        self.ui.lblHoSoName.setText(f"Th.S {ho_ten}" if "Th.S" not in ho_ten else ho_ten)
        self.ui.lblHoSoMeta.setText(f"{ma_gv} · Khoa {khoa} · {email}")

        rows = [
            ("Mã giảng viên", ma_gv),
            ("Họ và tên", ho_ten),
            ("Học hàm / học vị", "Thạc sĩ"),
            ("Ngày sinh", "20/05/1985"),
            ("Giới tính", "Nam"),
            ("Khoa", khoa),
            ("Email trường", email),
            ("Số điện thoại", "0912 345 678"),
            ("Trạng thái TK", "Đang hoạt động"),
        ]
        tb_info = self.ui.tbThongTinGV
        tb_info.setRowCount(0)
        tb_info.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tb_info.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i, (k, v) in enumerate(rows):
            tb_info.insertRow(i)
            tb_info.setItem(i, 0, QTableWidgetItem(k))
            tb_info.setItem(i, 1, QTableWidgetItem(v))

        tb_pc = self.ui.tbPhanCongHoSo
        tb_pc.setRowCount(0)
        try:
            pc_rows = fetch_all(
                """
                SELECT COALESCE(m.TenMon, p.MaMon), p.MaMon, p.HocKy, p.NamHoc
                FROM PHAN_CONG p
                LEFT JOIN MON_HOC m ON m.MaMon = p.MaMon
                WHERE p.MaGV = ?
                ORDER BY p.MaMon
                """,
                (ma_gv,),
            )
        except Exception:
            pc_rows = []
        if not pc_rows:
            pc_rows = [("Lập trình Python", "CS301", 1, "2024-25"), ("CTDL & Giải thuật", "CS302", 1, "2024-25"), ("Kiến trúc máy tính", "CS401", 1, "2024-25")]
        for i, (ten_mon, ma_mon, hk, nam) in enumerate(pc_rows):
            tb_pc.insertRow(i)
            tb_pc.setItem(i, 0, QTableWidgetItem(f"{ten_mon} ({ma_mon})"))
            tb_pc.setItem(i, 1, QTableWidgetItem(f"HK{hk} / {nam}"))
        tb_pc.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tb_pc.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    def _update_lecturer_password_strength(self, text=""):
        pwd = text if isinstance(text, str) else self.ui.txtMkMoiGV.text().strip()
        if not pwd:
            self.ui.lblMkStrength.setText("Độ mạnh: —")
            return
        score = 0
        if len(pwd) >= 8:
            score += 1
        if any(c.islower() for c in pwd):
            score += 1
        if any(c.isupper() for c in pwd):
            score += 1
        if any(c.isdigit() for c in pwd):
            score += 1
        if any(not c.isalnum() for c in pwd):
            score += 1
        if score <= 2:
            self.ui.lblMkStrength.setText("Độ mạnh: Yếu")
        elif score <= 3:
            self.ui.lblMkStrength.setText("Độ mạnh: Trung bình — thêm ký tự đặc biệt để mạnh hơn")
        else:
            self.ui.lblMkStrength.setText("Độ mạnh: Mạnh")

    def _change_lecturer_password(self):
        old_pwd = self.ui.txtMkHienTaiGV.text().strip()
        new_pwd = self.ui.txtMkMoiGV.text().strip()
        confirm_pwd = self.ui.txtNhapLaiMkGV.text().strip()
        if not old_pwd or not new_pwd or not confirm_pwd:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ các trường mật khẩu.")
            return
        if len(new_pwd) < 8:
            QMessageBox.warning(self, "Mật khẩu yếu", "Mật khẩu mới phải có ít nhất 8 ký tự.")
            return
        if new_pwd != confirm_pwd:
            QMessageBox.warning(self, "Không khớp", "Xác nhận mật khẩu mới không trùng khớp.")
            return
        if not TaiKhoanModel.auth(self.username, old_pwd):
            QMessageBox.warning(self, "Sai mật khẩu", "Mật khẩu hiện tại chưa chính xác.")
            return
        try:
            TaiKhoanModel.update_password(self.username, new_pwd)
            self.ui.txtMkHienTaiGV.clear()
            self.ui.txtMkMoiGV.clear()
            self.ui.txtNhapLaiMkGV.clear()
            self._update_lecturer_password_strength("")
            log_event(self.username, "Giảng viên", "Quản trị", "Đổi mật khẩu")
            QMessageBox.information(self, "Thành công", "Đổi mật khẩu thành công.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không đổi được mật khẩu: {e}")


class AdminApp(QWidget):
    def __init__(self, username=""):
        super().__init__()
        self.username = username
        self.ui = Ui_AdminDashboard()
        self.ui.setupUi(self)
        self._stretch_admin_overview_tables()
        self._dm_catalog_view = "mon"
        self.ui.splitDmLopSv.setStretchFactor(0, 2)
        self.ui.splitDmLopSv.setStretchFactor(1, 3)
        if self.ui.cbSvQuanLyLop.count() == 0:
            self.ui.cbSvQuanLyLop.addItem("Tất cả lớp", "")
        self.ui.lblAccount.setText(self.username)
        self.ui.btnLogout.clicked.connect(self._logout_click)
        self._all_accounts = []
        self._wire_events()
        self._admin_bc_chart = GradeChartHost("Phân bố điểm toàn trường (đã công bố)")
        _configure_admin_bao_cao_page(self.ui, self._admin_bc_chart)
        self._load_overview()
        self._load_account_tab()

    def _logout_click(self):
        self._go_login_screen()

    def _go_login_screen(self):
        self.login_window = LoginApp()
        self.login_window.show()
        self.close()

    def _stretch_admin_overview_tables(self):
        exp = QSizePolicy.Policy.Expanding
        ui = self.ui
        if ui.rootLayout.count() >= 2:
            ui.rootLayout.setStretch(1, 1)
        ui.pages.setSizePolicy(exp, exp)
        pq = ui.pageTongQuanLayout
        if pq.count() >= 3:
            pq.setStretch(2, 1)
        for tbl in (ui.tbPhanBoTaiKhoan, ui.tbTienDoNhapDiem, ui.tbHoatDongGanDay):
            tbl.setSizePolicy(exp, exp)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        ui.framePhanBoLayout.setStretch(1, 1)
        ui.frameTienDoLayout.setStretch(1, 1)
        ui.frameHoatDongLayout.setStretch(1, 1)
        for i in range(ui.panelsLayout.count()):
            ui.panelsLayout.setStretch(i, 1)

    def _show_dm_catalog(self, key):
        sw = getattr(self.ui, "swDmCatalog", None)
        if sw is None:
            return
        ft = getattr(self.ui, "frameDmLopToolbar", None)
        if ft is not None:
            ft.setVisible(key == "lophoc")
        if key == "khoa":
            sw.setCurrentIndex(1)
            self._dm_catalog_view = "khoa"
            self._load_khoa_catalog_tab()
            return
        if key == "lophoc":
            sw.setCurrentIndex(2)
            self._dm_catalog_view = "lophoc"
            self._load_lop_catalog_tab()
            return
        if key == "namhoc":
            sw.setCurrentIndex(3)
            self._dm_catalog_view = "namhoc"
            self._load_catalog_tab()
            return
        sw.setCurrentIndex(0)
        self._dm_catalog_view = "mon"
        self._load_catalog_tab()

    def _admin_khoa_ma_list(self):
        ensure_khoa_master_table()
        if not table_exists("KHOA"):
            return []
        return [r[0] for r in fetch_all("SELECT MaKhoa FROM KHOA ORDER BY MaKhoa")]

    def _admin_lop_ma_list(self):
        ensure_danh_muc_lop_table()
        s = set()
        if table_exists("DANH_MUC_LOP"):
            try:
                for (ml,) in fetch_all("SELECT MaLop FROM DANH_MUC_LOP ORDER BY MaLop"):
                    s.add(str(ml).strip())
            except Exception:
                pass
        if table_exists("SINH_VIEN"):
            try:
                for (lop,) in fetch_all(
                    "SELECT DISTINCT trim(Lop) FROM SINH_VIEN WHERE Lop IS NOT NULL AND trim(Lop) <> ''"
                ):
                    if lop:
                        s.add(str(lop).strip())
            except Exception:
                pass
        return sorted(s)

    def _pick_khoa_ma_dialog(self, title, label, current=""):
        ensure_khoa_master_table()
        if not table_exists("KHOA"):
            t, ok = QInputDialog.getText(
                self, title, label + " (mã khoa, vd: CNTT):", text=str(current or "CNTT")
            )
            return t.strip() if ok and t.strip() else None
        rows = fetch_all("SELECT MaKhoa, TenKhoa FROM KHOA ORDER BY MaKhoa")
        if not rows:
            t, ok = QInputDialog.getText(
                self, title, label + " (mã khoa, vd: CNTT):", text=str(current or "CNTT")
            )
            return t.strip() if ok and t.strip() else None
        labels = [f"{ma} — {ten}" for ma, ten in rows]
        codes = [str(ma) for ma, _ten in rows]
        cur = str(current or "").strip()
        idx = codes.index(cur) if cur in codes else 0
        pick, ok = QInputDialog.getItem(self, title, label, labels, idx, False)
        if not ok or pick is None:
            return None
        ps = str(pick)
        try:
            j = labels.index(ps)
        except ValueError:
            j = 0
        return codes[j]

    def _pick_khoa_ma_optional_dialog(self, title, label, current=""):
        """Chọn mã khoa hoặc để trống; Cancel → None (caller có thể hủy thao tác)."""
        ensure_khoa_master_table()
        cur = str(current or "").strip()
        if not table_exists("KHOA"):
            t, ok = QInputDialog.getText(
                self,
                title,
                label + " (mã khoa, để trống nếu không gán):",
                text=cur,
            )
            if not ok:
                return None
            return t.strip()
        rows = fetch_all("SELECT MaKhoa, TenKhoa FROM KHOA ORDER BY MaKhoa")
        if not rows:
            t, ok = QInputDialog.getText(
                self,
                title,
                label + " (mã khoa, để trống nếu không gán):",
                text=cur,
            )
            if not ok:
                return None
            return t.strip()
        labels = ["(Không chọn khoa)"] + [f"{ma} — {ten}" for ma, ten in rows]
        codes = [""] + [str(ma) for ma, _ten in rows]
        try:
            idx = codes.index(cur) if cur in codes else 0
        except ValueError:
            idx = 0
        pick, ok = QInputDialog.getItem(self, title, label, labels, idx, False)
        if not ok:
            return None
        ps = str(pick)
        try:
            j = labels.index(ps)
        except ValueError:
            j = 0
        return codes[j]

    def _pick_lop_ma_dialog(self, title, label, current=""):
        ensure_danh_muc_lop_table()
        codes = self._admin_lop_ma_list()
        extra = "— Nhập mã lớp khác…"
        cur = str(current or "").strip()
        if not codes:
            t, ok = QInputDialog.getText(self, title, label + " (mã lớp):", text=cur or "CNTT14.C.1")
            return t.strip() if ok and t.strip() else None
        labels = list(codes) + [extra]
        if cur and cur in codes:
            idx = codes.index(cur)
        elif cur:
            idx = len(labels) - 1
        else:
            idx = 0
        pick, ok = QInputDialog.getItem(self, title, label, labels, idx, False)
        if not ok or pick is None:
            return None
        ps = str(pick)
        if ps == extra:
            t, ok2 = QInputDialog.getText(self, title, "Mã lớp:", text=cur)
            return t.strip() if ok2 and t.strip() else None
        return ps.strip()

    def _load_lop_catalog_tab(self):
        ensure_danh_muc_lop_table()
        self.ui.tbDmLop.setRowCount(0)
        by_lop = {}
        if table_exists("DANH_MUC_LOP"):
            try:
                for (ml,) in fetch_all("SELECT MaLop FROM DANH_MUC_LOP ORDER BY MaLop"):
                    by_lop[str(ml)] = 0
            except Exception:
                pass
        if table_exists("SINH_VIEN"):
            try:
                for lop, cnt in fetch_all(
                    """
                    SELECT Lop, COUNT(*)
                    FROM SINH_VIEN
                    WHERE Lop IS NOT NULL AND trim(Lop) <> ''
                    GROUP BY Lop
                    ORDER BY Lop
                    """
                ):
                    by_lop[str(lop)] = int(cnt)
            except Exception:
                pass
        for i, lop in enumerate(sorted(by_lop.keys())):
            self.ui.tbDmLop.insertRow(i)
            self.ui.tbDmLop.setItem(i, 0, QTableWidgetItem(str(lop)))
            self.ui.tbDmLop.setItem(i, 1, QTableWidgetItem(str(by_lop[lop])))
            aw = QWidget()
            al = QHBoxLayout(aw)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(6)
            btn_del = QPushButton("Xóa")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.clicked.connect(lambda _=False, m=str(lop): self._delete_lop_catalog_row(m))
            al.addWidget(btn_del)
            al.addStretch(1)
            self.ui.tbDmLop.setCellWidget(i, 2, aw)
        self.ui.tbDmLop.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ui.tbDmLop.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        cb = self.ui.cbSvQuanLyLop
        if cb is not None:
            prev = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("Tất cả lớp", "")
            for lop in sorted(by_lop.keys()):
                cb.addItem(f"{lop}  ({by_lop[lop]} SV)", str(lop))
            if prev:
                ix = cb.findData(prev)
                cb.setCurrentIndex(ix if ix >= 0 else 0)
            cb.blockSignals(False)
        self._load_sv_quan_ly_theo_lop_table()

    def _on_lop_catalog_row_selected(self):
        sel = self.ui.tbDmLop.selectionModel().selectedRows()
        if not sel:
            return
        it = self.ui.tbDmLop.item(sel[0].row(), 0)
        if not it:
            return
        ma = str(it.text()).strip()
        if not ma:
            return
        ix = self.ui.cbSvQuanLyLop.findData(ma)
        if ix < 0:
            return
        self.ui.cbSvQuanLyLop.blockSignals(True)
        self.ui.cbSvQuanLyLop.setCurrentIndex(ix)
        self.ui.cbSvQuanLyLop.blockSignals(False)
        self._load_sv_quan_ly_theo_lop_table()

    def _admin_role_for_login(self, ten_dang_nhap):
        try:
            r = fetch_all("SELECT VaiTro FROM TAI_KHOAN WHERE TenDangNhap = ?", (ten_dang_nhap,))
            if r:
                return str(r[0][0])
        except Exception:
            pass
        return "Sinh viên"

    def _load_sv_quan_ly_theo_lop_table(self):
        tb = getattr(self, "tbSvQuanLyLop", None)
        cb = self.ui.cbSvQuanLyLop
        if tb is None or cb is None or not table_exists("SINH_VIEN"):
            return
        lop_f = cb.currentData()
        lop_f = str(lop_f).strip() if lop_f else ""
        kw = self.ui.txtSvQuanLyTim.text().strip().lower()
        pat = f"%{kw}%" if kw else "%"
        tt_hoc_map = {
            "DANG_HOC": "Đang học",
            "BAO_LUU": "Bảo lưu",
            "TOT_NGHIEP": "Tốt nghiệp",
            "THOI_HOC": "Thôi học",
        }
        tb.setRowCount(0)
        try:
            if lop_f:
                rows = fetch_all(
                    """
                    SELECT s.MSSV, s.HoTen, s.Lop, COALESCE(TRIM(s.Khoa), ''),
                           COALESCE(s.TrangThai, 'DANG_HOC'), s.GPA10,
                           COALESCE(t.TrangThai, '')
                    FROM SINH_VIEN s
                    LEFT JOIN TAI_KHOAN t ON t.TenDangNhap = s.MSSV
                    WHERE s.Lop = ?
                      AND (LOWER(s.MSSV) LIKE ? OR LOWER(s.HoTen) LIKE ?)
                    ORDER BY s.MSSV
                    """,
                    (lop_f, pat, pat),
                )
            else:
                rows = fetch_all(
                    """
                    SELECT s.MSSV, s.HoTen, s.Lop, COALESCE(TRIM(s.Khoa), ''),
                           COALESCE(s.TrangThai, 'DANG_HOC'), s.GPA10,
                           COALESCE(t.TrangThai, '')
                    FROM SINH_VIEN s
                    LEFT JOIN TAI_KHOAN t ON t.TenDangNhap = s.MSSV
                    WHERE LOWER(s.MSSV) LIKE ? OR LOWER(s.HoTen) LIKE ?
                    ORDER BY s.Lop, s.MSSV
                    """,
                    (pat, pat),
                )
        except Exception:
            try:
                rows = fetch_all(
                    """
                    SELECT s.MSSV, s.HoTen, s.Lop, '', 'DANG_HOC', s.GPA10,
                           COALESCE(t.TrangThai, '')
                    FROM SINH_VIEN s
                    LEFT JOIN TAI_KHOAN t ON t.TenDangNhap = s.MSSV
                    WHERE (? = '' OR s.Lop = ?)
                      AND (LOWER(s.MSSV) LIKE ? OR LOWER(s.HoTen) LIKE ?)
                    ORDER BY s.Lop, s.MSSV
                    """,
                    (lop_f, lop_f, pat, pat),
                )
            except Exception:
                rows = []
        for i, row in enumerate(rows):
            mssv, ho_ten, lop, khoa, tt_hoc, gpa10, tt_tk = row
            tb.insertRow(i)
            tb.setItem(i, 0, QTableWidgetItem(str(mssv)))
            tb.setItem(i, 1, QTableWidgetItem(str(ho_ten)))
            tb.setItem(i, 2, QTableWidgetItem(str(lop)))
            tb.setItem(i, 3, QTableWidgetItem(str(khoa or "—")))
            tb.setItem(i, 4, QTableWidgetItem(tt_hoc_map.get(str(tt_hoc), str(tt_hoc or "—"))))
            gtxt = f"{float(gpa10):.2f}" if gpa10 is not None else "—"
            tb.setItem(i, 5, QTableWidgetItem(gtxt))
            ttk = str(tt_tk or "").upper()
            if not ttk:
                tb.setItem(i, 6, QTableWidgetItem("Chưa có TK"))
            elif ttk == "BI_KHOA":
                tb.setItem(i, 6, QTableWidgetItem("Bị khóa"))
            else:
                tb.setItem(i, 6, QTableWidgetItem("Hoạt động"))
            aw = QWidget()
            al = QHBoxLayout(aw)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(6)
            u = str(mssv)
            role = self._admin_role_for_login(u)
            btn_sua = QPushButton("Sửa hồ sơ")
            btn_sua.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_sua.clicked.connect(lambda _=False, usr=u, rr=role: self._edit_account_menu(usr, rr))
            btn_tk = QPushButton("Tài khoản…")
            btn_tk.setToolTip("Khóa / reset mật khẩu / xóa — chuyển sang tab Tài khoản hoặc dùng trực tiếp sau này")
            btn_tk.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_tk.clicked.connect(lambda _=False, usr=u: self._switch_admin_page_and_focus_account(usr))
            al.addWidget(btn_sua)
            al.addWidget(btn_tk)
            al.addStretch(1)
            tb.setCellWidget(i, 7, aw)
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tb.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        tb.setColumnWidth(7, 220)

    def _switch_admin_page_and_focus_account(self, username):
        self._switch_admin_page("tai_khoan")
        self.ui.txtAccSearch.setText(str(username))
        self._filter_account_table()

    def _fill_hoc_ky_table(self, tb_hk):
        if tb_hk is None:
            return
        tb_hk.setRowCount(0)
        hk_rows = (
            fetch_all(
                """
                SELECT HocKy, NamHoc, COALESCE(TenHienThi, 'HK' || HocKy || ' — ' || NamHoc), COALESCE(TrangThai, 'DANG_DIEN_RA')
                FROM HOC_KY
                ORDER BY NamHoc DESC, HocKy ASC
                """
            )
            if table_exists("HOC_KY")
            else []
        )
        status_map = {
            "DANG_DIEN_RA": "Đang diễn ra",
            "DA_KET_THUC": "Đã kết thúc",
            "CHUA_BAT_DAU": "Chưa bắt đầu",
        }
        for i, (hk, nam, name, status_key) in enumerate(hk_rows):
            tb_hk.insertRow(i)
            tb_hk.setItem(i, 0, QTableWidgetItem(name))
            tb_hk.setItem(i, 1, QTableWidgetItem(status_map.get(status_key, status_key)))
            hk_actions = QWidget()
            hal = QHBoxLayout(hk_actions)
            hal.setContentsMargins(2, 2, 2, 2)
            hal.setSpacing(6)
            btn_edit_hk = QPushButton("Sửa")
            btn_del_hk = QPushButton("Xóa")
            for b in (btn_edit_hk, btn_del_hk):
                b.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit_hk.clicked.connect(lambda _=False, h=hk, n=nam, s=status_key: self._edit_term_from_admin(h, n, s))
            btn_del_hk.clicked.connect(lambda _=False, h=hk, n=nam: self._delete_term_from_admin(h, n))
            hal.addWidget(btn_edit_hk)
            hal.addWidget(btn_del_hk)
            hal.addStretch(1)
            tb_hk.setCellWidget(i, 2, hk_actions)
        tb_hk.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tb_hk.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    def _load_khoa_catalog_tab(self):
        ensure_khoa_master_table()
        self.ui.tbDmKhoa.setRowCount(0)
        if not table_exists("KHOA"):
            return
        rows = fetch_all("SELECT MaKhoa, TenKhoa FROM KHOA ORDER BY MaKhoa")
        for i, (ma, ten) in enumerate(rows):
            self.ui.tbDmKhoa.insertRow(i)
            self.ui.tbDmKhoa.setItem(i, 0, QTableWidgetItem(str(ma)))
            self.ui.tbDmKhoa.setItem(i, 1, QTableWidgetItem(str(ten)))
            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(0, 0, 0, 0)
            b_edit = QPushButton("Sửa tên")
            b_del = QPushButton("Xóa")
            b_edit.clicked.connect(lambda _=False, m=ma, t=ten: self._edit_khoa_catalog_row(m, t))
            b_del.clicked.connect(lambda _=False, m=ma: self._delete_khoa_catalog_row(m))
            al.addWidget(b_edit)
            al.addWidget(b_del)
            self.ui.tbDmKhoa.setCellWidget(i, 2, actions)
        self.ui.tbDmKhoa.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ui.tbDmKhoa.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    def _add_khoa_from_admin(self):
        ensure_khoa_master_table()
        if not table_exists("KHOA"):
            QMessageBox.warning(self, "Thiếu bảng", "CSDL chưa có bảng KHOA.")
            return
        ma, ok = QInputDialog.getText(self, "Thêm khoa", "Mã khoa (viết tắt, không dấu cách, vd: QTKD):")
        if not ok or not ma.strip():
            return
        ma = ma.strip()
        ten, ok = QInputDialog.getText(self, "Thêm khoa", "Tên đầy đủ của khoa:")
        if not ok or not ten.strip():
            return
        try:
            execute_query("INSERT INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (ma, ten.strip()))
            self._load_khoa_catalog_tab()
            self._load_account_tab()
            if self.ui.pages.currentWidget() is self.ui.pagePhanCong:
                self._load_assignment_tab()
            log_event(self.username, "Admin", "Quản trị", f"Thêm danh mục khoa {ma}")
            QMessageBox.information(self, "Thành công", f"Đã thêm khoa « {ma} ».")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thêm được khoa (mã có thể đã tồn tại): {e}")

    def _edit_khoa_catalog_row(self, ma_khoa, ten_hien_tai):
        ten, ok = QInputDialog.getText(self, "Sửa khoa", f"Tên hiển thị cho « {ma_khoa} »:", text=str(ten_hien_tai))
        if not ok or not ten.strip():
            return
        try:
            execute_query("UPDATE KHOA SET TenKhoa = ? WHERE MaKhoa = ?", (ten.strip(), ma_khoa))
            self._load_khoa_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Cập nhật tên khoa {ma_khoa}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật được: {e}")

    def _delete_khoa_catalog_row(self, ma_khoa):
        try:
            n_gv = fetch_all("SELECT COUNT(*) FROM GIANG_VIEN WHERE Khoa = ?", (ma_khoa,))
            cnt = int(n_gv[0][0]) if n_gv else 0
        except Exception:
            cnt = 0
        if cnt:
            QMessageBox.warning(
                self,
                "Không xóa được",
                f"Đang có {cnt} giảng viên gán khoa « {ma_khoa} ». Hãy đổi khoa trong Tài khoản (Sửa → Hồ sơ) trước.",
            )
            return
        if QMessageBox.question(
            self,
            "Xác nhận",
            f"Xóa khoa « {ma_khoa} » khỏi danh mục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            execute_query("DELETE FROM KHOA WHERE MaKhoa = ?", (ma_khoa,))
            self._load_khoa_catalog_tab()
            self._load_account_tab()
            if self.ui.pages.currentWidget() is self.ui.pagePhanCong:
                self._load_assignment_tab()
            log_event(self.username, "Admin", "Quản trị", f"Xóa danh mục khoa {ma_khoa}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xóa được: {e}")

    def _add_danh_muc_lop_from_accounts(self):
        ensure_danh_muc_lop_table()
        if not table_exists("DANH_MUC_LOP"):
            QMessageBox.warning(self, "Thiếu bảng", "CSDL chưa có bảng DANH_MUC_LOP.")
            return
        ma, ok = QInputDialog.getText(self, "Thêm lớp", "Mã lớp (vd: CNTT15.A.1):")
        if not ok or not ma.strip():
            return
        ma = ma.strip()
        try:
            execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (ma,))
            self._load_account_tab()
            if self.ui.pages.currentWidget() is self.ui.pagePhanCong:
                self._load_assignment_tab()
            if getattr(self, "_dm_catalog_view", "mon") == "lophoc":
                self._load_lop_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Thêm danh mục lớp {ma}")
            QMessageBox.information(self, "Thành công", f"Đã thêm lớp « {ma} ».")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thêm được lớp: {e}")

    def _edit_account_menu(self, username, current_role):
        opts = ["Hồ sơ (tên, lớp, khoa)", "Đổi vai trò"]
        sel, ok = QInputDialog.getItem(
            self,
            "Sửa tài khoản",
            f"Chọn thao tác cho {username}:",
            opts,
            0,
            False,
        )
        if not ok:
            return
        if str(sel).startswith("Hồ sơ"):
            self._edit_user_profile(username, current_role)
        else:
            self._edit_account(username, current_role)

    def _edit_user_profile(self, username, current_role):
        if role_is_admin(current_role):
            QMessageBox.information(
                self,
                "Hồ sơ",
                "Tài khoản quản trị không có hồ sơ riêng trong CSDL. Chỉ có thể đổi vai trò / mật khẩu / khóa.",
            )
            return
        if role_is_giang_vien(current_role):
            if not table_exists("GIANG_VIEN"):
                return
            row = fetch_all("SELECT HoTen, Khoa FROM GIANG_VIEN WHERE MaGV = ?", (username,))
            if not row:
                try:
                    execute_query(
                        "INSERT OR IGNORE INTO GIANG_VIEN (MaGV, HoTen, Khoa) VALUES (?, ?, ?)",
                        (username, username, "CNTT"),
                    )
                    row = fetch_all("SELECT HoTen, Khoa FROM GIANG_VIEN WHERE MaGV = ?", (username,))
                except Exception as e:
                    QMessageBox.warning(self, "Thiếu hồ sơ", f"Chưa có và không tạo được GIANG_VIEN: {e}")
                    return
            if not row:
                QMessageBox.warning(self, "Thiếu hồ sơ", "Chưa có bản ghi GIANG_VIEN cho tài khoản này.")
                return
            ho_ten, khoa = row[0]
            ht, ok = QInputDialog.getText(self, "Hồ sơ giảng viên", "Họ tên:", text=str(ho_ten))
            if not ok or not ht.strip():
                return
            k_ma = self._pick_khoa_ma_dialog("Hồ sơ giảng viên", "Khoa (mã):", current=str(khoa or ""))
            if k_ma is None:
                k_ma = str(khoa or "").strip() or "CNTT"
            try:
                execute_query("UPDATE GIANG_VIEN SET HoTen = ?, Khoa = ? WHERE MaGV = ?", (ht.strip(), k_ma, username))
                try:
                    execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (k_ma, k_ma))
                except Exception:
                    pass
                self._load_account_tab()
                log_event(self.username, "Admin", "Quản trị", f"Cập nhật hồ sơ GV {username}")
                QMessageBox.information(self, "Thành công", "Đã cập nhật hồ sơ giảng viên.")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không lưu được: {e}")
            return
        if not role_is_sinh_vien(current_role):
            QMessageBox.information(self, "Hồ sơ", "Chưa hỗ trợ sửa hồ sơ cho vai trò này.")
            return
        if not table_exists("SINH_VIEN"):
            return
        try:
            row = fetch_all(
                "SELECT HoTen, Lop, COALESCE(trim(Khoa), '') FROM SINH_VIEN WHERE MSSV = ?",
                (username,),
            )
        except Exception:
            row = fetch_all("SELECT HoTen, Lop FROM SINH_VIEN WHERE MSSV = ?", (username,))
            row = [(r[0], r[1], "") for r in row] if row else []
        if not row:
            QMessageBox.warning(self, "Thiếu hồ sơ", "Chưa có bản ghi SINH_VIEN cho tài khoản này.")
            return
        ho_ten, lop, sk = row[0]
        ht, ok = QInputDialog.getText(self, "Hồ sơ sinh viên", "Họ tên:", text=str(ho_ten))
        if not ok or not ht.strip():
            return
        lop_moi = self._pick_lop_ma_dialog("Hồ sơ sinh viên", "Lớp:", current=str(lop or ""))
        if lop_moi is None:
            return
        k_ma = self._pick_khoa_ma_optional_dialog(
            "Hồ sơ sinh viên", "Khoa (mã):", current=str(sk or "")
        )
        if k_ma is None:
            return
        try:
            try:
                execute_query(
                    "UPDATE SINH_VIEN SET HoTen = ?, Lop = ?, Khoa = ? WHERE MSSV = ?",
                    (ht.strip(), lop_moi, k_ma if k_ma else None, username),
                )
            except Exception:
                execute_query(
                    "UPDATE SINH_VIEN SET HoTen = ?, Lop = ? WHERE MSSV = ?",
                    (ht.strip(), lop_moi, username),
                )
            try:
                execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (lop_moi,))
            except Exception:
                pass
            if k_ma:
                try:
                    execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (k_ma, k_ma))
                except Exception:
                    pass
            self._load_account_tab()
            if self.ui.pages.currentWidget() is self.ui.pagePhanCong:
                self._load_assignment_tab()
            if getattr(self, "_dm_catalog_view", "") == "lophoc":
                self._load_lop_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Cập nhật hồ sơ SV {username}")
            QMessageBox.information(self, "Thành công", "Đã cập nhật hồ sơ sinh viên.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không lưu được: {e}")

    def _wire_events(self):
        self.ui.pages.currentChanged.connect(self._on_admin_tab_changed)
        self.ui.btnXuLyNgay.clicked.connect(self._overview_xu_ly_ngay)
        self.ui.btnTaoTaiKhoan.clicked.connect(self._create_account_from_admin)
        self.ui.btnMoKhoaTk.clicked.connect(lambda: self._switch_admin_page("tai_khoan"))
        self.ui.btnResetMk.clicked.connect(lambda: self._switch_admin_page("tai_khoan"))
        self.ui.btnImportExcel.clicked.connect(self._import_students_excel_from_admin)
        self.ui.btnAccCreate.clicked.connect(self._create_account_from_admin)
        self.ui.btnAccImport.clicked.connect(self._import_students_excel_from_admin)
        self.ui.txtAccSearch.textChanged.connect(self._filter_account_table)
        self.ui.cbAccRole.currentIndexChanged.connect(self._filter_account_table)
        self.ui.cbAccStatus.currentIndexChanged.connect(self._filter_account_table)
        self.ui.cbAccKhoa.currentIndexChanged.connect(self._filter_account_table)
        self.ui.btnDmThemLop.clicked.connect(self._add_danh_muc_lop_from_accounts)
        self.ui.pillAll.clicked.connect(lambda: self._set_account_filter_pill("all"))
        self.ui.pillAdmin.clicked.connect(lambda: self._set_account_filter_pill("admin"))
        self.ui.pillGV.clicked.connect(lambda: self._set_account_filter_pill("gv"))
        self.ui.pillSV.clicked.connect(lambda: self._set_account_filter_pill("sv"))
        self.ui.pillLocked.clicked.connect(lambda: self._set_account_filter_pill("locked"))
        self.ui.lstGiangVienPc.currentRowChanged.connect(self._load_assignment_for_selected_lecturer)
        self.ui.cbPcKhoa.currentIndexChanged.connect(self._apply_pc_khoa_filter)
        self.ui.cbPcHocKy.currentIndexChanged.connect(self._load_assignment_for_selected_lecturer)
        self.ui.btnPcThem.clicked.connect(self._add_assignment_for_selected)
        self.ui.btnThemPhanCongTop.clicked.connect(self._add_assignment_for_selected)
        self.ui.btnDmThemMon.clicked.connect(self._add_subject_from_admin)
        self.ui.btnDmThemHocKy.clicked.connect(self._add_term_from_admin)
        self.ui.btnDmMonHoc.clicked.connect(lambda: self._show_dm_catalog("mon"))
        self.ui.btnDmNamHoc.clicked.connect(lambda: self._show_dm_catalog("namhoc"))
        self.ui.btnDmLopHoc.clicked.connect(lambda: self._show_dm_catalog("lophoc"))
        self.ui.btnDmKhoa.clicked.connect(lambda: self._show_dm_catalog("khoa"))
        self.ui.btnDmThemKhoa.clicked.connect(self._add_khoa_from_admin)
        self.ui.btnDmThemHocKyPage.clicked.connect(self._add_term_from_admin)
        self.ui.btnDmLopLamMoi.clicked.connect(self._load_lop_catalog_tab)
        self.ui.btnDmSvLopLamMoi.clicked.connect(self._load_lop_catalog_tab)
        self.ui.tbDmLop.itemSelectionChanged.connect(self._on_lop_catalog_row_selected)
        self.ui.cbSvQuanLyLop.currentIndexChanged.connect(self._load_sv_quan_ly_theo_lop_table)
        self.ui.txtSvQuanLyTim.textChanged.connect(self._load_sv_quan_ly_theo_lop_table)
        self.ui.btnDmTuyChinhHeSo.clicked.connect(self._customize_mon_he_so_from_admin)
        self.ui.cbBcHocKy.currentIndexChanged.connect(self._load_admin_report_tab)
        self.ui.cbBcKhoa.currentIndexChanged.connect(self._load_admin_report_tab)
        self.ui.cbBcLop.currentIndexChanged.connect(self._load_admin_report_tab)
        self.ui.cbBcMon.currentIndexChanged.connect(self._load_admin_report_tab)
        self.ui.btnBcExcel.clicked.connect(lambda: self._export_admin_bao_cao("excel"))
        self.ui.btnBcPdf.clicked.connect(lambda: self._export_admin_bao_cao("pdf"))
        self.ui.txtLogSearch.textChanged.connect(self._filter_system_logs)
        self.ui.cbLogType.currentIndexChanged.connect(self._filter_system_logs)
        self.ui.cbLogRole.currentIndexChanged.connect(self._filter_system_logs)
        self.ui.cbLogTime.currentIndexChanged.connect(self._filter_system_logs)

    def _switch_admin_page(self, page):
        if page == "tai_khoan":
            self.ui.pages.setCurrentWidget(self.ui.pageTaiKhoan)
            self._load_account_tab()
        elif page == "phan_cong":
            self.ui.pages.setCurrentWidget(self.ui.pagePhanCong)
            self._load_assignment_tab()
        elif page == "danh_muc":
            self.ui.pages.setCurrentWidget(self.ui.pageDanhMuc)
            self._load_catalog_tab()
            ft = getattr(self.ui, "frameDmLopToolbar", None)
            if ft is not None:
                ft.setVisible(getattr(self, "_dm_catalog_view", "mon") == "lophoc")
        elif page == "bao_cao_admin":
            self.ui.pages.setCurrentWidget(self.ui.pageBaoCaoAdmin)
            self._load_admin_report_tab()
        elif page == "log_system":
            self.ui.pages.setCurrentWidget(self.ui.pageLogSystem)
            self._load_system_logs()
        else:
            self.ui.pages.setCurrentWidget(self.ui.pageTongQuan)
            self._load_overview()

    def _on_admin_tab_changed(self, _index):
        current = self.ui.pages.currentWidget()
        ft = getattr(self.ui, "frameDmLopToolbar", None)
        if ft is not None and current is not self.ui.pageDanhMuc:
            ft.setVisible(False)
        if current is self.ui.pageTaiKhoan:
            self._load_account_tab()
        elif current is self.ui.pagePhanCong:
            self._load_assignment_tab()
        elif current is self.ui.pageDanhMuc:
            self._load_catalog_tab()
            if ft is not None:
                ft.setVisible(getattr(self, "_dm_catalog_view", "mon") == "lophoc")
        elif current is self.ui.pageBaoCaoAdmin:
            self._load_admin_report_tab()
        elif current is self.ui.pageLogSystem:
            self._load_system_logs()
        else:
            self._load_overview()

    def _overview_xu_ly_ngay(self):
        target = getattr(self, "_overview_xu_ly_target", "tai_khoan")
        self._switch_admin_page(target)

    def _load_overview(self):
        try:
            accounts = fetch_all(
                "SELECT TenDangNhap, VaiTro, COALESCE(TrangThai, 'HOAT_DONG') FROM TAI_KHOAN"
            )
            total_acc = len(accounts)
            total_sv = len(fetch_all("SELECT MSSV FROM SINH_VIEN")) if table_exists("SINH_VIEN") else 0
            total_gv = len(fetch_all("SELECT MaGV FROM GIANG_VIEN")) if table_exists("GIANG_VIEN") else 0
            locked = 0
            if table_exists("TAI_KHOAN"):
                locked = len([row for row in accounts if str(row[2]).upper() == "BI_KHOA"])
            self.ui.cardTongTaiKhoan.setText(f"Tổng tài khoản\n{total_acc}")
            self.ui.cardSinhVien.setText(f"Sinh viên\n{total_sv}")
            self.ui.cardGiangVien.setText(f"Giảng viên\n{total_gv}")
            self.ui.cardBiKhoa.setText(f"Tài khoản bị khóa\n{locked}")

            n_lock_pw = 0
            n_lock_khac = 0
            if table_exists("TAI_KHOAN"):
                try:
                    n_lock_pw = int(
                        fetch_all(
                            """
                            SELECT COUNT(*) FROM TAI_KHOAN
                            WHERE TrangThai = 'BI_KHOA' AND COALESCE(SoLanSaiMK, 0) >= 5
                            """
                        )[0][0]
                    )
                    n_lock_khac = int(
                        fetch_all(
                            """
                            SELECT COUNT(*) FROM TAI_KHOAN
                            WHERE TrangThai = 'BI_KHOA' AND COALESCE(SoLanSaiMK, 0) < 5
                            """
                        )[0][0]
                    )
                except Exception:
                    n_lock_pw = n_lock_khac = 0

            term_row = _admin_active_hoc_ky_row()
            gv_chua_nhap = 0
            term_label = ""
            deadline_part = ""
            if term_row:
                hk, nam, ngay_kt = term_row
                term_label = f"HK{hk} — {nam}"
                dleft = _days_from_today_date_str(ngay_kt)
                if dleft is not None:
                    if dleft < 0:
                        deadline_part = f"hạn nhập điểm đã qua {abs(dleft)} ngày"
                    elif dleft == 0:
                        deadline_part = "hạn nhập điểm hôm nay"
                    else:
                        deadline_part = f"deadline còn {dleft} ngày"
                else:
                    deadline_part = "chưa gắn ngày kết thúc cho học kỳ"
                if table_exists("PHAN_CONG") and table_exists("SINH_VIEN") and table_exists("DIEM"):
                    try:
                        gv_chua_nhap = int(
                            fetch_all(
                                """
                                SELECT COUNT(DISTINCT p.MaGV)
                                FROM PHAN_CONG p
                                WHERE p.TrangThai = 'DANG_DAY'
                                  AND p.HocKy = ? AND p.NamHoc = ?
                                  AND p.Lop IS NOT NULL AND TRIM(p.Lop) != ''
                                  AND EXISTS (
                                    SELECT 1 FROM SINH_VIEN s
                                    WHERE s.Lop = p.Lop
                                    AND NOT EXISTS (
                                      SELECT 1 FROM DIEM d
                                      WHERE d.MSSV = s.MSSV AND d.MaMon = p.MaMon
                                        AND d.HocKy = p.HocKy AND d.NamHoc = p.NamHoc
                                        AND d.DTB IS NOT NULL
                                    )
                                  )
                                """,
                                (hk, nam),
                            )[0][0]
                        )
                    except Exception as e:
                        print("Lỗi đếm GV chưa nhập điểm:", e)
                        gv_chua_nhap = 0

            alert_parts = []
            if n_lock_pw:
                alert_parts.append(f"{n_lock_pw} tài khoản bị khóa do nhập sai mật khẩu 5 lần")
            if n_lock_khac:
                alert_parts.append(
                    f"{n_lock_khac} tài khoản đang bị khóa (không do sai mật khẩu 5 lần — thủ công hoặc trước đó)"
                )
            if gv_chua_nhap and term_label:
                alert_parts.append(
                    f"{gv_chua_nhap} giảng viên còn lớp/môn chưa nhập đủ điểm ({term_label})"
                    + (f", {deadline_part}" if deadline_part else "")
                )
            if not alert_parts:
                self.ui.lblAlert.setText(
                    "Không có cảnh báo — không có tài khoản khóa do sai mật khẩu; "
                    "phân công theo học kỳ hiện tại đã nhập đủ điểm (theo dữ liệu lớp)."
                )
            else:
                self.ui.lblAlert.setText(" · ".join(alert_parts))

            has_lock = n_lock_pw + n_lock_khac > 0
            if has_lock and gv_chua_nhap:
                self._overview_xu_ly_target = "tai_khoan"
            elif has_lock:
                self._overview_xu_ly_target = "tai_khoan"
            elif gv_chua_nhap:
                self._overview_xu_ly_target = "phan_cong"
            else:
                self._overview_xu_ly_target = "tai_khoan"
            self.ui.btnXuLyNgay.setVisible(bool(has_lock or gv_chua_nhap))

            tb_pb = self.ui.tbPhanBoTaiKhoan
            tb_pb.setRowCount(0)
            admin_cnt = len([1 for _u, v, _s in accounts if role_is_admin(v)])
            gv_cnt = len([1 for _u, v, _s in accounts if role_is_giang_vien(v)])
            sv_cnt = len([1 for _u, v, _s in accounts if role_is_sinh_vien(v)])
            pb_rows = [("Quản trị viên", admin_cnt), ("Giảng viên", gv_cnt), ("Sinh viên", sv_cnt), ("Bị khóa", locked)]
            for i, (name, val) in enumerate(pb_rows):
                tb_pb.insertRow(i)
                tb_pb.setItem(i, 0, QTableWidgetItem(name))
                tb_pb.setItem(i, 1, QTableWidgetItem(str(val)))

            tb_td = self.ui.tbTienDoNhapDiem
            tb_td.setRowCount(0)
            if table_exists("DIEM"):
                progress = fetch_all(
                    """
                    SELECT d.MaMon || '/' || COALESCE(s.Lop, 'N/A') AS LopMon,
                           ROUND(AVG(CASE WHEN d.DTB IS NOT NULL THEN 100 ELSE 0 END), 0)
                    FROM DIEM d
                    LEFT JOIN SINH_VIEN s ON s.MSSV = d.MSSV
                    GROUP BY d.MaMon, s.Lop
                    ORDER BY d.MaMon
                    LIMIT 8
                    """
                )
            else:
                progress = []
            if not progress:
                tb_td.insertRow(0)
                tb_td.setItem(0, 0, QTableWidgetItem("—"))
                tb_td.setItem(0, 1, QTableWidgetItem("Chưa có dữ liệu điểm"))
            else:
                for i, (lop_mon, pct) in enumerate(progress):
                    tb_td.insertRow(i)
                    pe = int(pct) if pct is not None else 0
                    label = "Đã khóa" if pe >= 95 else ("Chưa nhập" if pe == 0 else f"{pe}% nhập")
                    tb_td.setItem(i, 0, QTableWidgetItem(str(lop_mon)))
                    tb_td.setItem(i, 1, QTableWidgetItem(label))

            tb_hd = self.ui.tbHoatDongGanDay
            tb_hd.setRowCount(0)
            events = []
            if table_exists("NHAT_KY_HE_THONG"):
                try:
                    events = fetch_all(
                        """
                        SELECT NoiDung, ThoiGian
                        FROM NHAT_KY_HE_THONG
                        ORDER BY Id DESC
                        LIMIT 8
                        """
                    )
                except Exception:
                    events = []
            if not events:
                tb_hd.insertRow(0)
                tb_hd.setItem(0, 0, QTableWidgetItem("Chưa có sự kiện trong nhật ký hệ thống"))
                tb_hd.setItem(0, 1, QTableWidgetItem("—"))
            else:
                for i, (event, at) in enumerate(events):
                    tb_hd.insertRow(i)
                    tb_hd.setItem(i, 0, QTableWidgetItem(str(event) if event else ""))
                    tb_hd.setItem(i, 1, QTableWidgetItem(str(at) if at else ""))
        except Exception as e:
            print("Lỗi tải tổng quan admin:", e)

    def _ho_ten_hien_thi_admin(self, username):
        try:
            if table_exists("SINH_VIEN"):
                r = fetch_all("SELECT HoTen, Lop FROM SINH_VIEN WHERE MSSV = ?", (username,))
                if r:
                    return r[0][0], r[0][1]
        except Exception:
            pass
        try:
            if table_exists("GIANG_VIEN"):
                r = fetch_all("SELECT HoTen, Khoa FROM GIANG_VIEN WHERE MaGV = ?", (username,))
                if r:
                    return r[0][0], r[0][1]
        except Exception:
            pass
        return username, "—"

    def _load_account_tab(self):
        try:
            self._all_accounts = fetch_all(
                "SELECT TenDangNhap, VaiTro, COALESCE(TrangThai, 'HOAT_DONG') FROM TAI_KHOAN"
            )
        except Exception:
            try:
                self._all_accounts = fetch_all("SELECT TenDangNhap, VaiTro, 'HOAT_DONG' FROM TAI_KHOAN")
            except Exception:
                self._all_accounts = []
        ensure_khoa_master_table()
        ensure_danh_muc_lop_table()
        khoa_values = set()
        if table_exists("KHOA"):
            try:
                for (km,) in fetch_all("SELECT MaKhoa FROM KHOA ORDER BY MaKhoa"):
                    khoa_values.add(str(km))
            except Exception:
                pass
        if table_exists("GIANG_VIEN"):
            try:
                for (k,) in fetch_all("SELECT DISTINCT trim(Khoa) FROM GIANG_VIEN WHERE Khoa IS NOT NULL AND trim(Khoa) <> ''"):
                    khoa_values.add(str(k))
            except Exception:
                pass
        self.ui.cbAccKhoa.blockSignals(True)
        self.ui.cbAccKhoa.clear()
        self.ui.cbAccKhoa.addItem("Tất cả khoa")
        for khoa in sorted(khoa_values):
            self.ui.cbAccKhoa.addItem(khoa)
        self.ui.cbAccKhoa.blockSignals(False)
        self._set_account_filter_pill("all")

    def _import_students_excel_from_admin(self):
        """Import danh sách sinh viên từ Excel/CSV (tab Tài khoản Admin)."""
        self._switch_admin_page("tai_khoan")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import danh sách sinh viên",
            "",
            "Excel (*.xlsx);;CSV (*.csv);;Tất cả (*.*)",
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        raw = []
        try:
            if ext == ".csv":
                with open(path, newline="", encoding="utf-8-sig") as f:
                    raw = list(csv.reader(f))
            elif ext == ".xlsx":
                try:
                    import openpyxl
                except ImportError:
                    QMessageBox.warning(
                        self,
                        "Thiếu openpyxl",
                        "Để đọc file .xlsx, cài: pip install openpyxl\n"
                        "Hoặc lưu file dạng CSV (UTF-8) và chọn lại.",
                    )
                    return
                wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
                ws = wb.active
                raw = [list(r) for r in ws.iter_rows(values_only=True)]
                wb.close()
            else:
                QMessageBox.warning(self, "Định dạng", "Chỉ hỗ trợ file .xlsx hoặc .csv.")
                return
        except Exception as e:
            QMessageBox.warning(self, "Không đọc được file", str(e))
            return
        if not raw:
            QMessageBox.warning(self, "File rỗng", "Không có dòng dữ liệu.")
            return
        start = 1 if _import_sv_row_is_header(raw[0]) else 0
        if start >= len(raw):
            QMessageBox.warning(self, "File rỗng", "Chỉ có dòng tiêu đề, không có sinh viên.")
            return
        cmap = None
        vaitro_ix = None
        if start == 1:
            cmap = _import_sv_header_column_map(raw[0])
            if cmap["mssv"] is None or cmap["hoten"] is None or cmap["lop"] is None:
                QMessageBox.warning(
                    self,
                    "Thiếu cột",
                    "Dòng đầu là tiêu đề nhưng không nhận đủ cột bắt buộc: «Mã/MSSV», «Họ tên», «Lớp».\n"
                    "Đặt đúng tên cột hoặc dùng file gọn 5 cột: MSSV | Họ tên | Lớp | Khoa | Mật khẩu.",
                )
                return
            for i, cell in enumerate(raw[0]):
                if _import_sv_col_key(cell) in ("vaitro", "role", "phanquyen"):
                    vaitro_ix = i
                    break

        def _cell(row, field):
            if cmap is not None:
                ix = cmap.get(field)
                if ix is not None and ix < len(row):
                    return _import_sv_cell_str(row, ix)
                return ""
            legacy = {"mssv": 0, "hoten": 1, "lop": 2, "khoa": 3, "matkhau": 4}
            return _import_sv_cell_str(row, legacy[field])

        if not table_exists("TAI_KHOAN") or not table_exists("SINH_VIEN"):
            QMessageBox.warning(self, "CSDL", "Thiếu bảng TAI_KHOAN hoặc SINH_VIEN.")
            return
        ensure_danh_muc_lop_table()
        ensure_khoa_master_table()
        sv_cols = {str(r[1]) for r in fetch_all("PRAGMA table_info(SINH_VIEN)")}
        has_khoa = "Khoa" in sv_cols
        default_pw = "12345678"
        added = 0
        skipped_dup = 0
        skipped_bad = 0
        errors = []
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        cur = conn.cursor()
        for ri in range(start, len(raw)):
            row = raw[ri]
            if not row or not any(str(c).strip() for c in row if c is not None):
                continue
            if vaitro_ix is not None and vaitro_ix < len(row):
                rv = normalize_role_text(_import_sv_cell_str(row, vaitro_ix))
                if rv and "sinhvien" not in rv.replace(" ", ""):
                    skipped_bad += 1
                    errors.append(f"Dòng {ri + 1}: bỏ qua (vai trò không phải Sinh viên).")
                    continue
            mssv = _cell(row, "mssv")
            ho_ten = _cell(row, "hoten")
            lop = _cell(row, "lop")
            khoa = _cell(row, "khoa")
            pwd_in = _cell(row, "matkhau")
            if not mssv or not ho_ten or not lop:
                skipped_bad += 1
                errors.append(f"Dòng {ri + 1}: thiếu MSSV, họ tên hoặc lớp.")
                continue
            pwd = pwd_in if pwd_in else default_pw
            if len(pwd) < 8:
                skipped_bad += 1
                errors.append(f"Dòng {ri + 1} ({mssv}): mật khẩu phải ≥ 8 ký tự hoặc để trống.")
                continue
            cur.execute("SELECT 1 FROM TAI_KHOAN WHERE TenDangNhap = ?", (mssv,))
            if cur.fetchone():
                skipped_dup += 1
                continue
            try:
                cur.execute("BEGIN")
                cur.execute(
                    """
                    INSERT INTO TAI_KHOAN
                        (TenDangNhap, MatKhau, VaiTro, TrangThai, SoLanSaiMK, TaoLuc, CapNhatLuc)
                    VALUES
                        (?, ?, 'Sinh viên', 'HOAT_DONG', 0, datetime('now', 'localtime'), datetime('now', 'localtime'))
                    """,
                    (mssv, hash_password(pwd)),
                )
                cur.execute("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (lop,))
                if khoa and has_khoa:
                    cur.execute("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (khoa, khoa))
                    cur.execute(
                        """
                        INSERT INTO SINH_VIEN (MSSV, HoTen, Lop, Khoa, GPA10, GPA4, XepLoai)
                        VALUES (?, ?, ?, ?, 0, 0, 'Chưa có')
                        """,
                        (mssv, ho_ten, lop, khoa),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO SINH_VIEN (MSSV, HoTen, Lop, GPA10, GPA4, XepLoai)
                        VALUES (?, ?, ?, 0, 0, 'Chưa có')
                        """,
                        (mssv, ho_ten, lop),
                    )
                conn.commit()
                added += 1
            except Exception as e:
                conn.rollback()
                skipped_bad += 1
                errors.append(f"Dòng {ri + 1} ({mssv}): {e}")
        conn.close()
        self._load_account_tab()
        self._load_overview()
        try:
            log_event(
                self.username,
                "Admin",
                "Quản trị",
                f"Import sinh viên: thêm {added}, trùng {skipped_dup}, lỗi/thiếu {skipped_bad}",
            )
        except Exception:
            pass
        detail = (
            f"Đã thêm: {added}\n"
            f"Bỏ qua (đã có tài khoản): {skipped_dup}\n"
            f"Dòng không hợp lệ / lỗi: {skipped_bad}\n\n"
            "File có tiêu đề: nhận các cột Mã/MSSV, Họ tên, Lớp, Khoa (tuỳ chọn), Mật khẩu (tuỳ chọn); "
            "có thể thêm Email, Vai trò, Trạng thái (chỉ import dòng Vai trò = Sinh viên).\n"
            f"File không tiêu đề: 5 cột A–E = MSSV | Họ tên | Lớp | Khoa | Mật khẩu (mật khẩu trống = {default_pw})."
        )
        if errors:
            detail += "\n\n" + "\n".join(errors[:12])
            if len(errors) > 12:
                detail += f"\n… và {len(errors) - 12} lỗi khác."
        QMessageBox.information(self, "Import sinh viên", detail)

    def _create_account_from_admin(self):
        self._switch_admin_page("tai_khoan")
        username, ok = QInputDialog.getText(self, "Tạo tài khoản", "Tên đăng nhập:")
        if not ok or not username.strip():
            return
        username = username.strip()
        existed = fetch_all("SELECT 1 FROM TAI_KHOAN WHERE TenDangNhap = ?", (username,))
        if existed:
            QMessageBox.warning(self, "Trùng tài khoản", f"Tên đăng nhập {username} đã tồn tại.")
            return

        password, ok = QInputDialog.getText(
            self,
            "Tạo tài khoản",
            f"Mật khẩu cho {username}:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        password = password.strip()
        if len(password) < 8:
            QMessageBox.warning(self, "Mật khẩu yếu", "Mật khẩu phải có ít nhất 8 ký tự.")
            return

        roles = ["Admin", "Giảng viên", "Sinh viên"]
        role, ok = QInputDialog.getItem(self, "Tạo tài khoản", "Vai trò:", roles, 2, False)
        if not ok:
            return

        try:
            execute_query(
                """
                INSERT INTO TAI_KHOAN
                    (TenDangNhap, MatKhau, VaiTro, TrangThai, SoLanSaiMK, TaoLuc, CapNhatLuc)
                VALUES
                    (?, ?, ?, 'HOAT_DONG', 0, datetime('now', 'localtime'), datetime('now', 'localtime'))
                """,
                (username, hash_password(password), role),
            )
            if role == "Giảng viên" and table_exists("GIANG_VIEN"):
                ensure_khoa_master_table()
                ho_ten, ok = QInputDialog.getText(self, "Hồ sơ giảng viên", "Họ tên giảng viên:")
                if not ok or not ho_ten.strip():
                    ho_ten = username
                khoa = self._pick_khoa_ma_dialog("Hồ sơ giảng viên", "Khoa:", current="CNTT")
                if khoa is None:
                    khoa = "CNTT"
                execute_query(
                    "INSERT OR IGNORE INTO GIANG_VIEN (MaGV, HoTen, Khoa) VALUES (?, ?, ?)",
                    (username, ho_ten.strip(), khoa.strip()),
                )
                try:
                    execute_query(
                        "INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)",
                        (khoa.strip(), khoa.strip()),
                    )
                except Exception:
                    pass
            elif role == "Sinh viên" and table_exists("SINH_VIEN"):
                ensure_danh_muc_lop_table()
                ensure_khoa_master_table()
                ho_ten, ok = QInputDialog.getText(self, "Hồ sơ sinh viên", "Họ tên sinh viên:")
                if not ok or not ho_ten.strip():
                    ho_ten = username
                lop = self._pick_lop_ma_dialog("Hồ sơ sinh viên", "Lớp:", current="CNTT14.C.1")
                if lop is None:
                    lop = "CNTT14.C.1"
                k_sv_opt = self._pick_khoa_ma_optional_dialog(
                    "Hồ sơ sinh viên", "Khoa (tùy chọn):", current=""
                )
                k_sv = "" if k_sv_opt is None else k_sv_opt
                try:
                    execute_query("INSERT OR IGNORE INTO DANH_MUC_LOP (MaLop) VALUES (?)", (lop,))
                except Exception:
                    pass
                try:
                    if k_sv:
                        execute_query(
                            """
                            INSERT OR IGNORE INTO SINH_VIEN
                                (MSSV, HoTen, Lop, Khoa, GPA10, GPA4, XepLoai)
                            VALUES
                                (?, ?, ?, ?, 0, 0, 'Chưa có')
                            """,
                            (username, ho_ten.strip(), lop, k_sv),
                        )
                    else:
                        execute_query(
                            """
                            INSERT OR IGNORE INTO SINH_VIEN
                                (MSSV, HoTen, Lop, GPA10, GPA4, XepLoai)
                            VALUES
                                (?, ?, ?, 0, 0, 'Chưa có')
                            """,
                            (username, ho_ten.strip(), lop),
                        )
                except Exception:
                    execute_query(
                        """
                        INSERT OR IGNORE INTO SINH_VIEN
                            (MSSV, HoTen, Lop, GPA10, GPA4, XepLoai)
                        VALUES
                            (?, ?, ?, 0, 0, 'Chưa có')
                        """,
                        (username, ho_ten.strip(), lop),
                    )
                if k_sv:
                    try:
                        execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (k_sv, k_sv))
                    except Exception:
                        pass
            self._load_account_tab()
            self._load_overview()
            log_event(self.username, "Admin", "Quản trị", f"Tạo tài khoản {username} ({role})")
            QMessageBox.information(self, "Thành công", f"Đã tạo tài khoản {username}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không tạo được tài khoản: {e}")

    def _load_assignment_tab(self):
        gv_rows = []
        if table_exists("GIANG_VIEN"):
            try:
                gv_rows = fetch_all("SELECT MaGV, HoTen, COALESCE(Khoa, 'CNTT') FROM GIANG_VIEN ORDER BY MaGV")
            except Exception:
                gv_rows = []
        if not gv_rows:
            try:
                acc = fetch_all("SELECT TenDangNhap FROM TAI_KHOAN WHERE VaiTro LIKE '%Giảng%'")
                gv_rows = [(u, u, "CNTT") for (u,) in acc]
            except Exception:
                gv_rows = []
        self._pc_gv_all = gv_rows

        prev_khoa = self.ui.cbPcKhoa.currentText()
        self.ui.cbPcKhoa.blockSignals(True)
        self.ui.cbPcKhoa.clear()
        self.ui.cbPcKhoa.addItem("Tất cả khoa")
        khoa_set = {str(k) for _m, _t, k in gv_rows if k}
        ensure_khoa_master_table()
        if table_exists("KHOA"):
            try:
                for (km,) in fetch_all("SELECT MaKhoa FROM KHOA ORDER BY MaKhoa"):
                    khoa_set.add(str(km))
            except Exception:
                pass
        for khoa in sorted(khoa_set):
            self.ui.cbPcKhoa.addItem(khoa)
        k_idx = self.ui.cbPcKhoa.findText(prev_khoa)
        self.ui.cbPcKhoa.setCurrentIndex(k_idx if k_idx >= 0 else 0)
        self.ui.cbPcKhoa.blockSignals(False)

        prev_hk = self.ui.cbPcHocKy.currentData()
        hk_rows = (
            fetch_all(
                """
                SELECT HocKy, NamHoc, COALESCE(TenHienThi, 'HK' || HocKy || '/' || NamHoc)
                FROM HOC_KY
                ORDER BY NamHoc DESC, HocKy ASC
                """
            )
            if table_exists("HOC_KY")
            else []
        )
        self.ui.cbPcHocKy.blockSignals(True)
        self.ui.cbPcHocKy.clear()
        if hk_rows:
            for hk, nam, label in hk_rows:
                self.ui.cbPcHocKy.addItem(str(label), (int(hk), str(nam)))
        else:
            self.ui.cbPcHocKy.addItem("HK1 — 2024-2025", (1, "2024-2025"))
            self.ui.cbPcHocKy.addItem("HK2 — 2024-2025", (2, "2024-2025"))
        if prev_hk is not None:
            for i in range(self.ui.cbPcHocKy.count()):
                if self.ui.cbPcHocKy.itemData(i) == prev_hk:
                    self.ui.cbPcHocKy.setCurrentIndex(i)
                    break
        if self.ui.cbPcHocKy.currentIndex() < 0 and self.ui.cbPcHocKy.count():
            self.ui.cbPcHocKy.setCurrentIndex(0)
        self.ui.cbPcHocKy.blockSignals(False)

        self._apply_pc_khoa_filter()

        self.ui.cbPcMon.clear()
        self.ui.cbPcMon.addItem("Chọn môn học...", "")
        if table_exists("MON_HOC"):
            for ma, ten, *_ in fetch_all("SELECT MaMon, COALESCE(TenMon, MaMon), 0 FROM MON_HOC ORDER BY MaMon"):
                self.ui.cbPcMon.addItem(f"{ten} ({ma})", ma)

        self.ui.cbPcLop.clear()
        self.ui.cbPcLop.addItem("Chọn lớp...", "")
        seen_lop = set()
        if table_exists("SINH_VIEN"):
            for (lop,) in fetch_all("SELECT DISTINCT Lop FROM SINH_VIEN WHERE Lop IS NOT NULL AND Lop <> '' ORDER BY Lop"):
                seen_lop.add(str(lop))
                self.ui.cbPcLop.addItem(lop, lop)
        ensure_danh_muc_lop_table()
        if table_exists("DANH_MUC_LOP"):
            try:
                for (ml,) in fetch_all("SELECT MaLop FROM DANH_MUC_LOP ORDER BY MaLop"):
                    if str(ml) not in seen_lop:
                        self.ui.cbPcLop.addItem(str(ml), str(ml))
            except Exception:
                pass
        self.ui.cbPcHocKyThem.clear()
        hk_rows = fetch_all(
            """
            SELECT HocKy, NamHoc, COALESCE(TenHienThi, 'HK' || HocKy || '/' || NamHoc)
            FROM HOC_KY
            ORDER BY NamHoc DESC, HocKy ASC
            """
        ) if table_exists("HOC_KY") else []
        if hk_rows:
            for hk, nam, label in hk_rows:
                self.ui.cbPcHocKyThem.addItem(str(label), (int(hk), str(nam)))
        else:
            self.ui.cbPcHocKyThem.addItem("HK1/2024-2025", (1, "2024-2025"))
            self.ui.cbPcHocKyThem.addItem("HK2/2024-2025", (2, "2024-2025"))
    def _apply_pc_khoa_filter(self):
        gv_all = getattr(self, "_pc_gv_all", [])
        self.ui.lstGiangVienPc.blockSignals(True)
        self.ui.lstGiangVienPc.clear()
        khoa_sel = self.ui.cbPcKhoa.currentText()
        if self.ui.cbPcKhoa.currentIndex() <= 0 or khoa_sel == "Tất cả khoa":
            filtered = list(gv_all)
        else:
            filtered = [(m, t, k) for m, t, k in gv_all if str(k) == khoa_sel]
        for ma, ten, khoa in filtered:
            self.ui.lstGiangVienPc.addItem(f"{ten} ({ma}) — Khoa {khoa}")
        self._pc_gv_rows = filtered
        self.ui.lstGiangVienPc.blockSignals(False)
        if filtered:
            self.ui.lstGiangVienPc.setCurrentRow(0)
        else:
            self._load_assignment_for_selected_lecturer()

    def _selected_gv_code(self):
        idx = self.ui.lstGiangVienPc.currentRow()
        if idx < 0 or idx >= len(getattr(self, "_pc_gv_rows", [])):
            return None
        return self._pc_gv_rows[idx][0]

    def _pc_selected_term(self):
        term = self.ui.cbPcHocKy.currentData()
        if not isinstance(term, (tuple, list)) or len(term) < 2:
            return None
        hk, nam_hoc = int(term[0]), str(term[1])
        if isinstance(nam_hoc, str) and len(nam_hoc) == 7 and nam_hoc[4] == "-":
            head = nam_hoc[:4]
            tail = nam_hoc[-2:]
            if tail.isdigit():
                nam_hoc = f"{head}-20{tail}"
        return hk, nam_hoc

    def _load_assignment_for_selected_lecturer(self, _row=None):
        ma_gv = self._selected_gv_code()
        table = self.ui.tbPhanCongChiTiet
        table.setRowCount(0)
        if not ma_gv:
            return
        term = self._pc_selected_term()
        if table_exists("PHAN_CONG"):
            if term:
                hk_f, nam_f = term
                rows = fetch_all(
                    """
                    SELECT COALESCE(m.TenMon, p.MaMon), p.MaMon, p.HocKy, p.NamHoc, COALESCE(p.Lop, '')
                    FROM PHAN_CONG p
                    LEFT JOIN MON_HOC m ON m.MaMon = p.MaMon
                    WHERE p.MaGV = ? AND p.HocKy = ? AND p.NamHoc = ?
                    ORDER BY p.MaMon
                    """,
                    (ma_gv, hk_f, nam_f),
                )
            else:
                rows = fetch_all(
                    """
                    SELECT COALESCE(m.TenMon, p.MaMon), p.MaMon, p.HocKy, p.NamHoc, COALESCE(p.Lop, '')
                    FROM PHAN_CONG p
                    LEFT JOIN MON_HOC m ON m.MaMon = p.MaMon
                    WHERE p.MaGV = ?
                    ORDER BY p.MaMon
                    """,
                    (ma_gv,),
                )
        else:
            rows = []
        for i, (ten_mon, ma_mon, hk, nam, _lop) in enumerate(rows):
            table.insertRow(i)
            mon_lop = f"{ten_mon} ({ma_mon})"
            if str(_lop).strip():
                mon_lop = f"{mon_lop} / {_lop}"
            table.setItem(i, 0, QTableWidgetItem(mon_lop))
            table.setItem(i, 1, QTableWidgetItem(f"HK{hk}/{nam}"))
            btn = QPushButton("Thu hồi")
            btn.clicked.connect(
                lambda _=False, m=ma_mon, h=hk, n=nam, l=_lop, g=ma_gv: self._revoke_assignment(g, m, h, n, l)
            )
            table.setCellWidget(i, 2, btn)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    def _add_assignment_for_selected(self):
        ma_gv = self._selected_gv_code()
        if not ma_gv:
            QMessageBox.information(self, "Chọn giảng viên", "Vui lòng chọn giảng viên bên trái.")
            return
        ma_mon = self.ui.cbPcMon.currentData()
        lop = self.ui.cbPcLop.currentData()
        term = self.ui.cbPcHocKyThem.currentData()
        if not ma_mon or not lop:
            QMessageBox.information(self, "Thiếu dữ liệu", "Vui lòng chọn môn học và lớp.")
            return
        hoc_ky, nam_hoc = term if isinstance(term, tuple) else (1, "2024-2025")
        # Chuẩn hóa format năm học cũ dạng 2024-25 -> 2024-2025 để qua FK HOC_KY.
        if isinstance(nam_hoc, str) and len(nam_hoc) == 7 and nam_hoc[4] == "-":
            head = nam_hoc[:4]
            tail = nam_hoc[-2:]
            if tail.isdigit():
                nam_hoc = f"{head}-20{tail}"
        hk_ok = fetch_all("SELECT 1 FROM HOC_KY WHERE HocKy = ? AND NamHoc = ?", (hoc_ky, nam_hoc))
        if not hk_ok:
            QMessageBox.warning(
                self,
                "Thiếu học kỳ",
                f"Chưa có học kỳ HK{hoc_ky}/{nam_hoc} trong danh mục. Vui lòng thêm ở tab Danh mục trước.",
            )
            return
        if not table_exists("PHAN_CONG"):
            QMessageBox.warning(self, "Thiếu bảng", "CSDL chưa có bảng PHAN_CONG.")
            return
        try:
            execute_query(
                "INSERT INTO PHAN_CONG (MaGV, MaMon, Lop, HocKy, NamHoc) VALUES (?, ?, ?, ?, ?)",
                (ma_gv, ma_mon, lop, hoc_ky, nam_hoc),
            )
            self._load_assignment_for_selected_lecturer()
            log_event(self.username, "Admin", "Quản trị", f"Phân công {ma_gv} dạy {ma_mon}/{lop} HK{hoc_ky}/{nam_hoc}")
            QMessageBox.information(self, "Thành công", f"Đã phân công {ma_mon} cho {ma_gv}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thêm được phân công: {e}")

    def _revoke_assignment(self, ma_gv, ma_mon, hoc_ky, nam_hoc, lop=""):
        try:
            if str(lop).strip():
                execute_query(
                    "DELETE FROM PHAN_CONG WHERE MaGV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ? AND Lop = ?",
                    (ma_gv, ma_mon, hoc_ky, nam_hoc, lop),
                )
            else:
                execute_query(
                    "DELETE FROM PHAN_CONG WHERE MaGV = ? AND MaMon = ? AND HocKy = ? AND NamHoc = ? AND (Lop IS NULL OR Lop = '')",
                    (ma_gv, ma_mon, hoc_ky, nam_hoc),
                )
            self._load_assignment_for_selected_lecturer()
            log_event(self.username, "Admin", "Quản trị", f"Thu hồi phân công {ma_gv} {ma_mon}/{lop} HK{hoc_ky}/{nam_hoc}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thu hồi được phân công: {e}")

    def _load_catalog_tab(self):
        tb_mon = self.ui.tbDmMonHoc
        tb_mon.setRowCount(0)
        mon_rows = []
        if table_exists("MON_HOC"):
            try:
                mon_rows = fetch_all(
                    """
                    SELECT MaMon, COALESCE(TenMon, MaMon), COALESCE(SoTinChi, 3), COALESCE(KhoaPhuTrach, '')
                    FROM MON_HOC
                    ORDER BY MaMon
                    """
                )
            except Exception:
                try:
                    mon_rows = fetch_all("SELECT MaMon, COALESCE(TenMon, MaMon), COALESCE(SoTinChi, 3) FROM MON_HOC ORDER BY MaMon")
                    mon_rows = [(a, b, c, "") for a, b, c in mon_rows]
                except Exception:
                    mon_rows = []
        for i, row in enumerate(mon_rows):
            ma, ten, tc = row[0], row[1], row[2]
            kfac = str(row[3]).strip() if len(row) > 3 else ""
            disp_k = kfac if kfac else "—"
            tb_mon.insertRow(i)
            tb_mon.setItem(i, 0, QTableWidgetItem(str(ma)))
            tb_mon.setItem(i, 1, QTableWidgetItem(str(ten)))
            tb_mon.setItem(i, 2, QTableWidgetItem(str(tc)))
            tb_mon.setItem(i, 3, QTableWidgetItem(disp_k))
            action = QWidget()
            lay = QHBoxLayout(action)
            lay.setContentsMargins(0, 0, 0, 0)
            btn_edit = QPushButton("Sửa")
            btn_delete = QPushButton("Xóa")
            btn_edit.clicked.connect(lambda _=False, m=ma, t=ten, c=tc, k=kfac: self._edit_subject_from_admin(m, t, c, k))
            btn_delete.clicked.connect(lambda _=False, m=ma: self._delete_subject_from_admin(m))
            lay.addWidget(btn_edit)
            lay.addWidget(btn_delete)
            tb_mon.setCellWidget(i, 4, action)
        tb_mon.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tb_mon.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self._fill_hoc_ky_table(self.ui.tbDmHocKy)
        self._fill_hoc_ky_table(self.ui.tbDmHocKyPage)

        v = getattr(self, "_dm_catalog_view", "mon")
        if v == "khoa":
            self._load_khoa_catalog_tab()
        elif v == "lophoc":
            self._load_lop_catalog_tab()

    def _customize_mon_he_so_from_admin(self):
        if not table_exists("MON_HOC"):
            QMessageBox.warning(self, "Thiếu bảng", "CSDL chưa có bảng MON_HOC.")
            return
        rows = fetch_all(
            """
            SELECT MaMon, COALESCE(TenMon, MaMon), HeSoCC, HeSoGK, HeSoCK
            FROM MON_HOC ORDER BY MaMon
            """
        )
        if not rows:
            QMessageBox.information(self, "Danh mục môn", "Chưa có môn học để cấu hình hệ số.")
            return
        labels = [
            f"{ma} — {ten}  (CC:{float(cc):.2f} · GK:{float(gk):.2f} · CK:{float(ck):.2f})"
            for ma, ten, cc, gk, ck in rows
        ]
        codes = [str(r[0]) for r in rows]
        pick, ok = QInputDialog.getItem(
            self, "Hệ số điểm thành phần", "Chọn môn học:", labels, 0, False
        )
        if not ok or pick is None:
            return
        try:
            idx = labels.index(str(pick))
        except ValueError:
            idx = 0
        ma_mon = codes[idx]
        cur = rows[idx]
        cc, ok = QInputDialog.getDouble(
            self, "Hệ số CC", f"Chuyên cần ({ma_mon}):", float(cur[2] or 0.1), 0.0, 1.0, 2
        )
        if not ok:
            return
        gk, ok = QInputDialog.getDouble(
            self, "Hệ số GK", f"Giữa kỳ ({ma_mon}):", float(cur[3] or 0.3), 0.0, 1.0, 2
        )
        if not ok:
            return
        ck, ok = QInputDialog.getDouble(
            self, "Hệ số CK", f"Cuối kỳ ({ma_mon}):", float(cur[4] or 0.6), 0.0, 1.0, 2
        )
        if not ok:
            return
        total = round(cc + gk + ck, 2)
        if abs(total - 1.0) > 0.02:
            QMessageBox.warning(
                self,
                "Hệ số không hợp lệ",
                f"Tổng hệ số phải bằng 1.0 (hiện tại: {total:.2f}).",
            )
            return
        try:
            execute_query(
                "UPDATE MON_HOC SET HeSoCC = ?, HeSoGK = ?, HeSoCK = ? WHERE MaMon = ?",
                (cc, gk, ck, ma_mon),
            )
            self._load_catalog_tab()
            log_event(
                self.username,
                "Admin",
                "Quản trị",
                f"Cập nhật hệ số môn {ma_mon}: CC={cc} GK={gk} CK={ck}",
            )
            QMessageBox.information(self, "Thành công", f"Đã cập nhật hệ số cho môn {ma_mon}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật được hệ số: {e}")

    def _add_subject_from_admin(self):
        ma, ok = QInputDialog.getText(self, "Thêm môn học", "Mã môn:")
        if not ok or not ma.strip():
            return
        ten, ok = QInputDialog.getText(self, "Thêm môn học", "Tên môn:")
        if not ok or not ten.strip():
            return
        tc, ok = QInputDialog.getInt(self, "Thêm môn học", "Số tín chỉ:", 3, 1, 10, 1)
        if not ok:
            return
        k_ma = self._pick_khoa_ma_dialog("Thêm môn học", "Khoa phụ trách môn (mã):")
        if k_ma is None:
            return
        if not table_exists("MON_HOC"):
            QMessageBox.warning(self, "Thiếu bảng", "CSDL chưa có bảng MON_HOC.")
            return
        try:
            try:
                execute_query(
                    "INSERT INTO MON_HOC (MaMon, TenMon, SoTinChi, KhoaPhuTrach) VALUES (?, ?, ?, ?)",
                    (ma.strip(), ten.strip(), tc, k_ma),
                )
            except Exception:
                try:
                    execute_query("ALTER TABLE MON_HOC ADD COLUMN KhoaPhuTrach TEXT")
                    execute_query(
                        "INSERT INTO MON_HOC (MaMon, TenMon, SoTinChi, KhoaPhuTrach) VALUES (?, ?, ?, ?)",
                        (ma.strip(), ten.strip(), tc, k_ma),
                    )
                except Exception:
                    execute_query("INSERT INTO MON_HOC (MaMon, TenMon, SoTinChi) VALUES (?, ?, ?)", (ma.strip(), ten.strip(), tc))
            try:
                execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (k_ma, k_ma))
            except Exception:
                pass
            self._load_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Thêm môn học {ma.strip()}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thêm được môn học: {e}")

    def _add_term_from_admin(self):
        hk, ok = QInputDialog.getInt(self, "Thêm học kỳ", "Học kỳ (1-3):", 1, 1, 3, 1)
        if not ok:
            return
        nam_hoc, ok = QInputDialog.getText(self, "Thêm học kỳ", "Năm học (vd: 2024-2025):")
        if not ok or not nam_hoc.strip():
            return
        status_options = ["DANG_DIEN_RA", "CHUA_BAT_DAU", "DA_KET_THUC"]
        trang_thai, ok = QInputDialog.getItem(self, "Thêm học kỳ", "Trạng thái:", status_options, 1, False)
        if not ok:
            return
        ten_hien_thi = f"HK{hk} — {nam_hoc.strip()}"
        try:
            execute_query(
                """
                INSERT INTO HOC_KY (HocKy, NamHoc, TenHienThi, TrangThai)
                VALUES (?, ?, ?, ?)
                """,
                (hk, nam_hoc.strip(), ten_hien_thi, trang_thai),
            )
            self._load_catalog_tab()
            log_event(self.username, "Admin", "Hệ thống", f"Tạo học kỳ {ten_hien_thi}")
            QMessageBox.information(self, "Thành công", "Đã thêm học kỳ.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thêm được học kỳ: {e}")

    def _edit_subject_from_admin(self, ma_mon, ten_mon, so_tin_chi, khoa_phu_trach=""):
        ten_moi, ok = QInputDialog.getText(self, "Sửa môn học", f"Tên môn ({ma_mon}):", text=str(ten_mon))
        if not ok or not ten_moi.strip():
            return
        tc_moi, ok = QInputDialog.getInt(self, "Sửa môn học", "Số tín chỉ:", int(so_tin_chi or 3), 1, 10, 1)
        if not ok:
            return
        k_ma = self._pick_khoa_ma_dialog("Sửa môn học", "Khoa phụ trách (mã):", current=str(khoa_phu_trach or ""))
        if k_ma is None:
            return
        try:
            try:
                execute_query(
                    "UPDATE MON_HOC SET TenMon = ?, SoTinChi = ?, KhoaPhuTrach = ? WHERE MaMon = ?",
                    (ten_moi.strip(), tc_moi, k_ma, ma_mon),
                )
            except Exception:
                try:
                    execute_query("ALTER TABLE MON_HOC ADD COLUMN KhoaPhuTrach TEXT")
                    execute_query(
                        "UPDATE MON_HOC SET TenMon = ?, SoTinChi = ?, KhoaPhuTrach = ? WHERE MaMon = ?",
                        (ten_moi.strip(), tc_moi, k_ma, ma_mon),
                    )
                except Exception:
                    execute_query(
                        "UPDATE MON_HOC SET TenMon = ?, SoTinChi = ? WHERE MaMon = ?",
                        (ten_moi.strip(), tc_moi, ma_mon),
                    )
            try:
                execute_query("INSERT OR IGNORE INTO KHOA (MaKhoa, TenKhoa) VALUES (?, ?)", (k_ma, k_ma))
            except Exception:
                pass
            self._load_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Cập nhật môn học {ma_mon}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật được môn học: {e}")

    def _delete_subject_from_admin(self, ma_mon):
        ok = QMessageBox.question(
            self,
            "Xóa môn học",
            f"Bạn có chắc muốn xóa môn {ma_mon}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            execute_query("DELETE FROM MON_HOC WHERE MaMon = ?", (ma_mon,))
            self._load_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Xóa môn học {ma_mon}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xóa được môn học: {e}")

    def _edit_term_from_admin(self, hoc_ky, nam_hoc, current_status):
        status_options = ["DANG_DIEN_RA", "CHUA_BAT_DAU", "DA_KET_THUC"]
        idx = status_options.index(current_status) if current_status in status_options else 0
        status_new, ok = QInputDialog.getItem(self, "Sửa học kỳ", f"Trạng thái HK{hoc_ky}/{nam_hoc}:", status_options, idx, False)
        if not ok:
            return
        try:
            execute_query(
                "UPDATE HOC_KY SET TrangThai = ? WHERE HocKy = ? AND NamHoc = ?",
                (status_new, hoc_ky, nam_hoc),
            )
            self._load_catalog_tab()
            log_event(self.username, "Admin", "Hệ thống", f"Cập nhật học kỳ HK{hoc_ky}/{nam_hoc} -> {status_new}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật được học kỳ: {e}")

    def _delete_term_from_admin(self, hoc_ky, nam_hoc):
        hk = int(hoc_ky)
        nam = str(nam_hoc).strip()
        nd = np = 0
        if table_exists("DIEM"):
            try:
                nd = int(fetch_all("SELECT COUNT(*) FROM DIEM WHERE HocKy = ? AND NamHoc = ?", (hk, nam))[0][0])
            except Exception:
                nd = 0
        if table_exists("PHAN_CONG"):
            try:
                np = int(
                    fetch_all("SELECT COUNT(*) FROM PHAN_CONG WHERE HocKy = ? AND NamHoc = ?", (hk, nam))[0][0]
                )
            except Exception:
                np = 0
        if nd or np:
            QMessageBox.warning(
                self,
                "Không xóa được",
                f"Học kỳ « HK{hk} / {nam} » đang có {nd} bản ghi điểm và {np} phân công. "
                "Cần xóa hoặc chuyển dữ liệu liên quan trước.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Xác nhận",
                f"Xóa học kỳ « HK{hk} — {nam} » khỏi danh mục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            execute_query("DELETE FROM HOC_KY WHERE HocKy = ? AND NamHoc = ?", (hk, nam))
            self._load_catalog_tab()
            self._load_overview()
            log_event(self.username, "Admin", "Hệ thống", f"Xóa học kỳ HK{hk}/{nam}")
            QMessageBox.information(self, "Đã xóa", f"Đã xóa học kỳ HK{hk} / {nam}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xóa được học kỳ: {e}")

    def _delete_lop_catalog_row(self, ma_lop):
        ma = str(ma_lop).strip()
        if not ma:
            return
        if table_exists("SINH_VIEN"):
            try:
                ns = int(fetch_all("SELECT COUNT(*) FROM SINH_VIEN WHERE Lop = ?", (ma,))[0][0])
            except Exception:
                ns = 0
            if ns > 0:
                QMessageBox.warning(
                    self,
                    "Không xóa được",
                    f"Đang có {ns} sinh viên thuộc lớp « {ma} ». Hãy đổi lớp tại tab Tài khoản (Sửa → Hồ sơ) trước.",
                )
                return
        if table_exists("PHAN_CONG"):
            try:
                npc = int(fetch_all("SELECT COUNT(*) FROM PHAN_CONG WHERE Lop = ?", (ma,))[0][0])
            except Exception:
                npc = 0
            if npc > 0:
                QMessageBox.warning(
                    self,
                    "Không xóa được",
                    f"Đang có {npc} phân công gắn lớp « {ma} ». Hãy xóa hoặc sửa phân công (tab Phân công GV) trước.",
                )
                return
        if not table_exists("DANH_MUC_LOP"):
            QMessageBox.warning(self, "Thiếu bảng", "CSDL chưa có bảng DANH_MUC_LOP.")
            return
        existed = fetch_all("SELECT 1 FROM DANH_MUC_LOP WHERE MaLop = ?", (ma,))
        if not existed:
            QMessageBox.information(
                self,
                "Không có trong danh mục",
                f"Mã « {ma} » chỉ hiển thị theo dữ liệu sinh viên — không có dòng riêng trong DANH_MUC_LOP để xóa.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Xác nhận",
                f"Xóa mã lớp « {ma} » khỏi danh mục (chỉ khi không còn SV / phân công)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            execute_query("DELETE FROM DANH_MUC_LOP WHERE MaLop = ?", (ma,))
            self._load_lop_catalog_tab()
            self._load_account_tab()
            log_event(self.username, "Admin", "Quản trị", f"Xóa danh mục lớp {ma}")
            QMessageBox.information(self, "Đã xóa", f"Đã xóa mã lớp « {ma} ».")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xóa được mã lớp: {e}")

    def _admin_bao_cao_export_rows(self):
        where = []
        params = []
        lop = self.ui.cbBcLop.currentData()
        mon = self.ui.cbBcMon.currentData()
        if lop:
            where.append("s.Lop = ?")
            params.append(lop)
        if mon:
            where.append("d.MaMon = ?")
            params.append(mon)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        if not table_exists("DIEM"):
            return []
        return fetch_all(
            f"""
            SELECT s.MSSV, s.HoTen, s.Lop, d.MaMon, d.DTB
            FROM DIEM d
            JOIN SINH_VIEN s ON s.MSSV = d.MSSV
            {cond}
            ORDER BY s.Lop, s.MSSV, d.MaMon
            """,
            tuple(params),
        )

    def _export_admin_bao_cao(self, kind: str, banner_title: str = ""):
        rows = self._admin_bao_cao_export_rows()
        if not rows:
            QMessageBox.information(self, "Không có dữ liệu", "Không có bản ghi điểm phù hợp bộ lọc.")
            return
        hdr = ["MSSV", "Họ tên", "Lớp", "Mã môn", "ĐTB"]
        body = [[r[0], r[1], r[2], r[3], r[4]] for r in rows]
        title = (banner_title or "Báo cáo điểm").strip() + " — Quản trị"
        stem = "bao_cao_admin_diem"
        base = Path(__file__).resolve().parent
        if kind == "excel":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu Excel",
                str(base / f"{stem}.xlsx"),
                "Excel (*.xlsx);;CSV (*.csv)",
            )
            if not path:
                return
            k, err = export_to_excel(path, stem[:31], hdr, body)
            if err:
                QMessageBox.warning(self, "Lỗi", err)
                return
            QMessageBox.information(
                self,
                "Đã xuất",
                "Đã lưu file Excel." if k == "xlsx" else "Đã lưu CSV (UTF-8).",
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu PDF",
                str(base / f"{stem}.pdf"),
                "PDF (*.pdf)",
            )
            if not path:
                return
            err = export_to_pdf(path, title, hdr, body)
            if err:
                QMessageBox.warning(self, "Không xuất được PDF", err)
                return
            QMessageBox.information(self, "Đã xuất", "Đã lưu file PDF.")

    def _load_admin_report_tab(self, *_args):
        if getattr(self, "_loading_admin_report", False):
            return
        self._loading_admin_report = True
        try:
            if self.ui.cbBcKhoa.count() <= 1:
                self.ui.cbBcKhoa.blockSignals(True)
                self.ui.cbBcKhoa.clear()
                self.ui.cbBcKhoa.addItem("Tất cả khoa", "")
                ensure_khoa_master_table()
                if table_exists("KHOA"):
                    for ma_k, ten_k in fetch_all(
                        "SELECT MaKhoa, TenKhoa FROM KHOA ORDER BY MaKhoa"
                    ):
                        self.ui.cbBcKhoa.addItem(f"{ma_k} — {ten_k}", str(ma_k))
                self.ui.cbBcKhoa.blockSignals(False)
            if self.ui.cbBcLop.count() <= 1:
                self.ui.cbBcLop.blockSignals(True)
                self.ui.cbBcLop.clear()
                self.ui.cbBcLop.addItem("Tất cả lớp", "")
                if table_exists("SINH_VIEN"):
                    for (lop,) in fetch_all("SELECT DISTINCT Lop FROM SINH_VIEN WHERE Lop IS NOT NULL AND Lop<>'' ORDER BY Lop"):
                        self.ui.cbBcLop.addItem(lop, lop)
                self.ui.cbBcLop.blockSignals(False)
            if self.ui.cbBcMon.count() <= 1:
                self.ui.cbBcMon.blockSignals(True)
                self.ui.cbBcMon.clear()
                self.ui.cbBcMon.addItem("Tất cả môn", "")
                if table_exists("MON_HOC"):
                    for ma, ten, *_ in fetch_all("SELECT MaMon, COALESCE(TenMon, MaMon), 0 FROM MON_HOC ORDER BY MaMon"):
                        self.ui.cbBcMon.addItem(f"{ma} — {ten}", ma)
                self.ui.cbBcMon.blockSignals(False)

            where = ["COALESCE(d.DaKhoa, 0) = 1", "d.DTB IS NOT NULL"]
            params = []
            lop = self.ui.cbBcLop.currentData()
            mon = self.ui.cbBcMon.currentData()
            khoa_ma = self.ui.cbBcKhoa.currentData()
            if lop:
                where.append("s.Lop = ?")
                params.append(lop)
            if mon:
                where.append("d.MaMon = ?")
                params.append(mon)
            if khoa_ma:
                where.append("COALESCE(trim(s.Khoa), '') = ?")
                params.append(str(khoa_ma))
            cond = " WHERE " + " AND ".join(where)
            rows = fetch_all(
                f"""
                SELECT s.MSSV, s.Lop, d.MaMon, d.DTB, COALESCE(trim(s.Khoa), '')
                FROM DIEM d
                JOIN SINH_VIEN s ON s.MSSV = d.MSSV
                {cond}
                """,
                tuple(params),
            ) if table_exists("DIEM") else []
            clean_rows = []
            for r in rows:
                try:
                    dtb_val = float(r[3])
                except (TypeError, ValueError):
                    continue
                clean_rows.append((r[0], r[1], r[2], dtb_val))
            total = len(clean_rows)
            if not total:
                self.ui.cardBcTongSv.setText("Tổng sinh viên\n0")
                self.ui.cardBcTyLeDau.setText("Tỉ lệ đậu toàn trường\n0%")
                self.ui.cardBcGpaTb.setText("GPA trung bình\n0.00")
                self.ui.cardBcMonRot.setText("Môn có tỉ lệ rớt cao nhất\n—")
                for tb in (self.ui.tbBcTheoLop, self.ui.tbBcPhanBo, self.ui.tbBcKhoa, self.ui.tbBcXuat):
                    tb.setRowCount(0)
                if getattr(self, "_admin_bc_chart", None):
                    self._admin_bc_chart.set_distribution([])
                return

            passed = [r for r in clean_rows if r[3] >= 4.0]
            gpa_avg = sum(r[3] for r in clean_rows) / total
            by_mon = {}
            for _mssv, _lop, ma, dtb in clean_rows:
                by_mon.setdefault(ma, []).append(dtb)
            worst_mon = max(by_mon.items(), key=lambda kv: sum(1 for v in kv[1] if v < 4.0) / len(kv[1]))
            worst_rate = round(sum(1 for v in worst_mon[1] if v < 4.0) * 100 / len(worst_mon[1]))
            self.ui.cardBcTongSv.setText(f"Tổng sinh viên\n{total}")
            self.ui.cardBcTyLeDau.setText(f"Tỉ lệ đậu toàn trường\n{round(len(passed) * 100 / total)}%")
            self.ui.cardBcGpaTb.setText(f"GPA trung bình\n{gpa_avg:.2f}")
            self.ui.cardBcMonRot.setText(f"Môn có tỉ lệ rớt cao nhất\n{worst_mon[0]} ({worst_rate}%)")

            tb_lop = self.ui.tbBcTheoLop
            tb_lop.setRowCount(0)
            by_lop = {}
            for _mssv, lop_name, _ma, dtb in clean_rows:
                by_lop.setdefault(lop_name, []).append(dtb)
            for i, (lop_name, vals) in enumerate(sorted(by_lop.items())[:8]):
                tb_lop.insertRow(i)
                tb_lop.setItem(i, 0, QTableWidgetItem(lop_name))
                tb_lop.setItem(i, 1, QTableWidgetItem(f"{round(sum(1 for v in vals if v>=4.0)*100/len(vals))}%"))

            tb_pb = self.ui.tbBcPhanBo
            tb_pb.setRowCount(0)
            bins = {"Xuất sắc (>=8.5)": 0, "Giỏi (7.0 - 8.4)": 0, "Khá (5.5 - 6.9)": 0, "Trung bình (4.0 - 5.4)": 0, "Yếu / Kém (< 4.0)": 0}
            for *_a, dtb in clean_rows:
                g = dtb
                if g >= 8.5:
                    bins["Xuất sắc (>=8.5)"] += 1
                elif g >= 7.0:
                    bins["Giỏi (7.0 - 8.4)"] += 1
                elif g >= 5.5:
                    bins["Khá (5.5 - 6.9)"] += 1
                elif g >= 4.0:
                    bins["Trung bình (4.0 - 5.4)"] += 1
                else:
                    bins["Yếu / Kém (< 4.0)"] += 1
            for i, (name, cnt) in enumerate(bins.items()):
                tb_pb.insertRow(i)
                tb_pb.setItem(i, 0, QTableWidgetItem(name))
                tb_pb.setItem(i, 1, QTableWidgetItem(f"{round(cnt*100/total)}%"))

            tb_khoa = self.ui.tbBcKhoa
            tb_khoa.setRowCount(0)
            khoa_d = _fetch_khoa_display_map()
            by_khoa = {}
            for _mssv, _lop, _ma, dtb, k_raw in rows:
                k_key = str(k_raw or "").strip() or "—"
                disp = _khoa_display_name(k_key, khoa_d) if k_key != "—" else "Chưa gán khoa"
                by_khoa.setdefault(disp, []).append(float(dtb))
            for i, (k_name, vals) in enumerate(sorted(by_khoa.items())):
                tb_khoa.insertRow(i)
                tb_khoa.setItem(i, 0, QTableWidgetItem(k_name))
                tb_khoa.setItem(i, 1, QTableWidgetItem(f"{sum(vals) / len(vals):.2f}"))
            if getattr(self, "_admin_bc_chart", None):
                self._admin_bc_chart.set_distribution([r[3] for r in clean_rows])

            tb_xuat = self.ui.tbBcXuat
            tb_xuat.setRowCount(0)
            xuat_rows = [
                "Bảng điểm toàn trường",
                "Báo cáo theo khoa CNTT",
                "Báo cáo theo khoa Toán",
                "Thống kê tỉ lệ đậu/rớt",
                "Danh sách SV cần chú ý",
            ]
            for i, title in enumerate(xuat_rows):
                tb_xuat.insertRow(i)
                tb_xuat.setItem(i, 0, QTableWidgetItem(title))
                btn_ex = QPushButton("Excel")
                btn_pdf = QPushButton("PDF")
                btn_ex.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_ex.clicked.connect(lambda _=False, t=title: self._export_admin_bao_cao("excel", t))
                btn_pdf.clicked.connect(lambda _=False, t=title: self._export_admin_bao_cao("pdf", t))
                tb_xuat.setCellWidget(i, 1, btn_ex)
                tb_xuat.setCellWidget(i, 2, btn_pdf)
        finally:
            self._loading_admin_report = False

    def _load_system_logs(self):
        if table_exists("NHAT_KY_HE_THONG"):
            self._all_system_logs = fetch_all(
                """
                SELECT COALESCE(ThoiGian, datetime('now', 'localtime')),
                       COALESCE(TenDangNhap, 'system'),
                       COALESCE(NoiDung, ''),
                       COALESCE(DiaChiIP, 'local'),
                       COALESCE(LoaiSuKien, 'Hệ thống'),
                       COALESCE(VaiTro, 'Admin')
                FROM NHAT_KY_HE_THONG
                ORDER BY ThoiGian DESC, Id DESC
                LIMIT 500
                """
            )
        else:
            self._all_system_logs = []
        self.ui.cbLogType.blockSignals(True)
        self.ui.cbLogType.clear()
        self.ui.cbLogType.addItems(["Tất cả loại", "Login OK", "Login Fail", "Khóa TK", "Điểm số", "Quản trị", "Hệ thống"])
        self.ui.cbLogType.blockSignals(False)
        self.ui.cbLogRole.blockSignals(True)
        self.ui.cbLogRole.clear()
        self.ui.cbLogRole.addItems(["Tất cả vai trò", "Admin", "Giảng viên", "Sinh viên"])
        self.ui.cbLogRole.blockSignals(False)
        self.ui.cbLogTime.blockSignals(True)
        self.ui.cbLogTime.clear()
        self.ui.cbLogTime.addItems(["Hôm nay", "7 ngày qua", "Tất cả"])
        self.ui.cbLogTime.blockSignals(False)
        self._filter_system_logs()

    def _filter_system_logs(self, *_args):
        rows = getattr(self, "_all_system_logs", [])
        keyword = self.ui.txtLogSearch.text().strip().lower()
        type_filter = self.ui.cbLogType.currentText().strip()
        role_filter = self.ui.cbLogRole.currentText().strip()
        time_filter = self.ui.cbLogTime.currentText().strip()
        filtered = []
        for row in rows:
            t, user, action, ip, typ, role = row
            if keyword and keyword not in user.lower() and keyword not in action.lower():
                continue
            if type_filter != "Tất cả loại" and typ != type_filter:
                continue
            if role_filter != "Tất cả vai trò" and role != role_filter:
                continue
            date_ok = True
            if time_filter != "Tất cả":
                date_ok = False
                try:
                    ts = str(t)
                    dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                    now = datetime.now()
                    if time_filter == "Hôm nay":
                        date_ok = dt.date() == now.date()
                    elif time_filter == "7 ngày qua":
                        date_ok = dt >= (now - timedelta(days=7))
                except Exception:
                    date_ok = time_filter == "Tất cả"
            if not date_ok:
                continue
            filtered.append(row)
        tb = self.ui.tbLogSystem
        tb.setRowCount(0)
        for i, (t, user, action, ip, typ, _role) in enumerate(filtered):
            tb.insertRow(i)
            tb.setItem(i, 0, QTableWidgetItem(t))
            tb.setItem(i, 1, QTableWidgetItem(user))
            tb.setItem(i, 2, QTableWidgetItem(action))
            tb.setItem(i, 3, QTableWidgetItem(ip))
            tb.setItem(i, 4, QTableWidgetItem(typ))
        tb.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tb.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        today_date = datetime.now().date()
        today = []
        for r in rows:
            try:
                dt = datetime.strptime(str(r[0])[:19], "%Y-%m-%d %H:%M:%S")
                if dt.date() == today_date:
                    today.append(r)
            except Exception:
                continue
        ok = [r for r in today if r[4] == "Login OK"]
        fail = [r for r in today if r[4] == "Login Fail"]
        lock = [r for r in today if r[4] == "Khóa TK"]
        score = [r for r in today if r[4] == "Điểm số"]
        self.ui.cardLogTong.setText(f"Tổng sự kiện hôm nay\n{len(today)}")
        self.ui.cardLogOk.setText(f"Đăng nhập thành công\n{len(ok)}")
        self.ui.cardLogFail.setText(f"Đăng nhập thất bại\n{len(fail)}")
        self.ui.cardLogLock.setText(f"Tài khoản bị khóa\n{len(lock)}")
        self.ui.cardLogScore.setText(f"Thao tác điểm\n{len(score)}")

    def _set_account_filter_pill(self, pill):
        self._account_pill = pill
        self._filter_account_table()

    def _filter_account_table(self):
        keyword = self.ui.txtAccSearch.text().strip().lower()
        role_filter = self.ui.cbAccRole.currentText().strip().lower()
        status_filter = self.ui.cbAccStatus.currentText().strip().lower()
        khoa_filter = self.ui.cbAccKhoa.currentText().strip()

        khoa_d = _fetch_khoa_display_map()

        sv_map = {}
        if table_exists("SINH_VIEN"):
            try:
                for r in fetch_all("SELECT MSSV, HoTen, Lop, COALESCE(trim(Khoa), '') FROM SINH_VIEN"):
                    sv_map[r[0]] = (r[1], r[2], r[3])
            except Exception:
                try:
                    for r in fetch_all("SELECT MSSV, HoTen, Lop FROM SINH_VIEN"):
                        sv_map[r[0]] = (r[1], r[2], "")
                except Exception:
                    pass

        gv_map = {}
        if table_exists("GIANG_VIEN"):
            try:
                for r in fetch_all("SELECT MaGV, HoTen, Khoa FROM GIANG_VIEN"):
                    gv_map[r[0]] = (r[1], str(r[2] or "").strip())
            except Exception:
                pass

        table = self.ui.tbAccounts
        table.setRowCount(0)
        cnt_admin = cnt_gv = cnt_sv = cnt_locked = 0
        cnt_all = 0
        for row in self._all_accounts:
            user = row[0]
            role = row[1] if len(row) > 1 else "Sinh viên"
            trang_thai = row[2] if len(row) > 2 else "HOAT_DONG"
            khoa_raw_tip = ""
            if role_is_sinh_vien(role) and user in sv_map:
                ho_ten, sv_lop, sv_k = sv_map[user]
                sv_k = str(sv_k or "").strip()
                sv_lop = str(sv_lop or "").strip()
                khoa_raw_tip = sv_k
                disp_khoa = _khoa_display_name(sv_k, khoa_d)
                disp_lop = sv_lop if sv_lop else "—"
            elif role_is_giang_vien(role) and user in gv_map:
                ho_ten, gv_k = gv_map[user]
                gv_k = str(gv_k or "").strip()
                khoa_raw_tip = gv_k
                disp_khoa = _khoa_display_name(gv_k, khoa_d)
                disp_lop = "—"
            else:
                ho_ten, extra = self._ho_ten_hien_thi_admin(user)
                ex = str(extra).strip() if extra is not None else ""
                disp_khoa = "—"
                disp_lop = "—"
                if role_is_giang_vien(role) and ex and ex != "—":
                    khoa_raw_tip = ex
                    disp_khoa = _khoa_display_name(ex, khoa_d)
                elif role_is_sinh_vien(role) and ex and ex != "—":
                    disp_lop = ex
            email = f"{str(user).lower()}@abc.edu.vn"
            locked = str(trang_thai).upper() == "BI_KHOA"
            status_text = "Bị khóa" if locked else "Hoạt động"
            if role_is_admin(role):
                cnt_admin += 1
            elif role_is_giang_vien(role):
                cnt_gv += 1
            else:
                cnt_sv += 1
            if locked:
                cnt_locked += 1
            cnt_all += 1
            if keyword and keyword not in str(user).lower() and keyword not in str(ho_ten).lower() and keyword not in email.lower() and keyword not in str(disp_khoa).lower() and keyword not in str(disp_lop).lower():
                continue
            if role_filter != "tất cả vai trò":
                if role_filter == "admin" and not role_is_admin(role):
                    continue
                if role_filter == "giảng viên" and not role_is_giang_vien(role):
                    continue
                if role_filter == "sinh viên" and not role_is_sinh_vien(role):
                    continue
            if status_filter == "hoạt động" and locked:
                continue
            if status_filter == "bị khóa" and not locked:
                continue
            if khoa_filter != "Tất cả khoa":
                ok_k = False
                fk = _khoa_canonical_key(khoa_filter, khoa_d) or khoa_filter
                if role_is_admin(role):
                    ok_k = False
                elif role_is_giang_vien(role) and user in gv_map:
                    gvk = str(gv_map[user][1] or "").strip()
                    ok_k = (
                        _khoa_canonical_key(gvk, khoa_d) == fk
                        or gvk == khoa_filter
                        or _khoa_display_name(gvk, khoa_d) == khoa_filter
                    )
                elif role_is_sinh_vien(role):
                    sl = sv_map.get(user)
                    if sl:
                        _ht, lop, sk = sl
                        sk = str(sk or "").strip()
                        ok_k = (
                            _khoa_canonical_key(sk, khoa_d) == fk
                            or sk == khoa_filter
                            or _khoa_display_name(sk, khoa_d) == khoa_filter
                            or (not sk and str(lop or "").upper().startswith(khoa_filter.upper()))
                        )
                if not ok_k:
                    continue
            if getattr(self, "_account_pill", "all") == "admin" and not role_is_admin(role):
                continue
            if getattr(self, "_account_pill", "all") == "gv" and not role_is_giang_vien(role):
                continue
            if getattr(self, "_account_pill", "all") == "sv" and not role_is_sinh_vien(role):
                continue
            if getattr(self, "_account_pill", "all") == "locked" and not locked:
                continue
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(str(user)))
            table.setItem(r, 1, QTableWidgetItem(str(ho_ten)))
            table.setItem(r, 2, QTableWidgetItem(str(role)))
            table.setItem(r, 3, QTableWidgetItem(email))
            it_khoa = QTableWidgetItem(str(disp_khoa))
            if disp_khoa not in ("—", "") and khoa_raw_tip and table_exists("KHOA"):
                ck = _khoa_canonical_key(khoa_raw_tip, khoa_d) or khoa_raw_tip
                if ck and str(disp_khoa) != ck:
                    it_khoa.setToolTip(f"Mã khoa: {ck}")
            table.setItem(r, 4, it_khoa)
            table.setItem(r, 5, QTableWidgetItem(str(disp_lop)))
            table.setItem(r, 6, QTableWidgetItem(status_text))
            row_actions = QWidget()
            row_layout = QHBoxLayout(row_actions)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(8)
            btn_edit = QPushButton("Sửa")
            btn_toggle = QPushButton("Mở khóa" if locked else "Khóa")
            btn_reset = QPushButton("Reset MK")
            btn_xoa = QPushButton("Xóa")
            btn_edit.setToolTip("Sửa hồ sơ (tên, lớp, khoa) hoặc đổi vai trò")
            btn_toggle.setToolTip("Khóa hoặc mở khóa đăng nhập tài khoản này")
            btn_reset.setToolTip("Đặt mật khẩu mới cho tài khoản")
            btn_xoa.setToolTip("Xóa vĩnh viễn tài khoản và hồ sơ liên quan (SV/GV) trong CSDL")
            for b in (btn_edit, btn_toggle, btn_reset, btn_xoa):
                b.setMinimumHeight(28)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.clicked.connect(lambda _=False, u=user, rr=role: self._edit_account_menu(u, rr))
            btn_toggle.clicked.connect(lambda _=False, u=user, lk=locked: self._toggle_account_lock(u, lk))
            btn_reset.clicked.connect(lambda _=False, u=user: self._reset_account_password(u))
            btn_xoa.clicked.connect(lambda _=False, u=user, rr=role: self._delete_account(u, rr))
            row_layout.addWidget(btn_edit)
            row_layout.addWidget(btn_toggle)
            row_layout.addWidget(btn_reset)
            row_layout.addWidget(btn_xoa)
            row_layout.addStretch(1)
            table.setCellWidget(r, 7, row_actions)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(7, 340)
        self.ui.pillAll.setText(f"Tất cả ({cnt_all})")
        self.ui.pillAdmin.setText(f"Admin ({cnt_admin})")
        self.ui.pillGV.setText(f"Giảng viên ({cnt_gv})")
        self.ui.pillSV.setText(f"Sinh viên ({cnt_sv})")
        self.ui.pillLocked.setText(f"Bị khóa ({cnt_locked})")

    def _edit_account(self, username, current_role):
        roles = ["Admin", "Giảng viên", "Sinh viên"]
        idx = roles.index(current_role) if current_role in roles else 2
        role, ok = QInputDialog.getItem(
            self,
            "Sửa vai trò",
            f"Vai trò mới cho {username}:",
            roles,
            idx,
            False,
        )
        if not ok:
            return
        if username == self.username and role != "Admin":
            QMessageBox.warning(self, "Không hợp lệ", "Bạn không thể tự gỡ quyền Admin của mình.")
            return
        try:
            execute_query("UPDATE TAI_KHOAN SET VaiTro = ?, CapNhatLuc = datetime('now', 'localtime') WHERE TenDangNhap = ?", (role, username))
            self._load_account_tab()
            self._load_overview()
            log_event(self.username, "Admin", "Quản trị", f"Cập nhật vai trò {username} -> {role}")
            QMessageBox.information(self, "Thành công", f"Đã cập nhật vai trò cho {username}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật được vai trò: {e}")

    def _toggle_account_lock(self, username, is_locked):
        if username == self.username and is_locked:
            QMessageBox.warning(self, "Không hợp lệ", "Bạn không thể tự khóa tài khoản đang đăng nhập.")
            return
        new_status = "HOAT_DONG" if is_locked else "BI_KHOA"
        try:
            execute_query(
                "UPDATE TAI_KHOAN SET TrangThai = ?, SoLanSaiMK = CASE WHEN ? = 'HOAT_DONG' THEN 0 ELSE SoLanSaiMK END, CapNhatLuc = datetime('now', 'localtime') WHERE TenDangNhap = ?",
                (new_status, new_status, username),
            )
            self._load_account_tab()
            self._load_overview()
            log_event(self.username, "Admin", "Khóa TK", f"{'Mở khóa' if is_locked else 'Khóa'} tài khoản {username}")
            QMessageBox.information(
                self,
                "Thành công",
                f"Đã {'mở khóa' if is_locked else 'khóa'} tài khoản {username}.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không cập nhật trạng thái tài khoản: {e}")

    def _reset_account_password(self, username):
        new_pwd, ok = QInputDialog.getText(
            self,
            "Reset mật khẩu",
            f"Mật khẩu mới cho {username}:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        new_pwd = new_pwd.strip()
        if len(new_pwd) < 8:
            QMessageBox.warning(self, "Mật khẩu yếu", "Mật khẩu phải có ít nhất 8 ký tự.")
            return
        try:
            execute_query(
                "UPDATE TAI_KHOAN SET MatKhau = ?, SoLanSaiMK = 0, TrangThai = 'HOAT_DONG', CapNhatLuc = datetime('now', 'localtime') WHERE TenDangNhap = ?",
                (hash_password(new_pwd), username),
            )
            self._load_account_tab()
            log_event(self.username, "Admin", "Quản trị", f"Reset mật khẩu tài khoản {username}")
            QMessageBox.information(self, "Thành công", f"Đã reset mật khẩu cho {username}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không reset được mật khẩu: {e}")

    def _purge_admin_user_related_rows(self, username):
        """Xóa dữ liệu gắn với tài khoản (điểm, phân công, hồ sơ SV/GV) trước khi xóa TAI_KHOAN.
        Cần cho CSDL cũ không CASCADE hoặc hồ sơ SINH_VIEN tồn tại khi không còn tài khoản."""
        u = str(username).strip()
        if not u:
            return
        if table_exists("DIEM_DANH"):
            try:
                execute_query("DELETE FROM DIEM_DANH WHERE MSSV = ?", (u,))
            except Exception:
                pass
        if table_exists("DIEM"):
            try:
                execute_query("DELETE FROM DIEM WHERE MSSV = ?", (u,))
            except Exception:
                pass
            try:
                execute_query("UPDATE DIEM SET NguoiNhap = NULL WHERE NguoiNhap = ?", (u,))
            except Exception:
                pass
        if table_exists("PHAN_CONG"):
            try:
                execute_query("DELETE FROM PHAN_CONG WHERE MaGV = ?", (u,))
            except Exception:
                pass
        if table_exists("GIANG_VIEN"):
            try:
                execute_query("DELETE FROM GIANG_VIEN WHERE MaGV = ?", (u,))
            except Exception:
                pass
        if table_exists("SINH_VIEN"):
            try:
                execute_query("DELETE FROM SINH_VIEN WHERE MSSV = ?", (u,))
            except Exception:
                pass

    def _delete_account(self, username, role):
        if username == self.username:
            QMessageBox.warning(self, "Không thể xóa", "Bạn không thể xóa tài khoản đang đăng nhập.")
            return
        if role_is_admin(role):
            others = [u for u, v, _s in self._all_accounts if role_is_admin(v) and u != username]
            if not others:
                QMessageBox.warning(
                    self,
                    "Không thể xóa",
                    "Phải còn ít nhất một tài khoản Quản trị viên.",
                )
                return
        tip = (
            "Sẽ xóa luôn: điểm / điểm danh (nếu có), phân công GV, hồ sơ sinh viên hoặc giảng viên "
            "trùng mã với tài khoản này — danh sách lớp trong Danh mục cập nhật theo dữ liệu còn lại."
        )
        if (
            QMessageBox.question(
                self,
                "Xác nhận xóa",
                f"Xóa vĩnh viễn tài khoản « {username} »?\n\n{tip}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._purge_admin_user_related_rows(username)
            execute_query("DELETE FROM TAI_KHOAN WHERE TenDangNhap = ?", (username,))
            self._load_account_tab()
            self._load_overview()
            if self.ui.pages.currentWidget() is self.ui.pagePhanCong:
                self._load_assignment_tab()
            self._load_lop_catalog_tab()
            log_event(self.username, "Admin", "Quản trị", f"Xóa tài khoản {username}")
            QMessageBox.information(self, "Đã xóa", f"Đã xóa tài khoản « {username} » và dữ liệu liên quan.")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Lỗi",
                f"Không xóa được (kiểm tra ràng buộc CSDL, ví dụ môn học đang tham chiếu): {e}",
            )


class LoginApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Login()
        self.ui.setupUi(self)
        self.selected_role = None
        self.ui.rootLoginLayout.setStretch(0, 1)
        self.ui.rootLoginLayout.setStretch(1, 1)
        self._setup_login_left_background()
        self._load_login_brand_logo()
        self.ui.lblBrandTitle.setStyleSheet(
            "font-family: Georgia, 'Times New Roman', serif; letter-spacing: 0.02em;"
        )
        self.ui.btnDangNhap.clicked.connect(self.dang_nhap)
        self.ui.txtTaiKhoan.returnPressed.connect(self.dang_nhap)
        self.ui.txtMatKhau.returnPressed.connect(self.dang_nhap)
        self.ui.btnToggleMatKhau.toggled.connect(self._toggle_login_password_visible)
        self.ui.txtMatKhau.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.ui.txtTaiKhoan.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.ui.btnQuanTri.clicked.connect(lambda: self._set_selected_role("admin"))
        self.ui.btnGiangVien.clicked.connect(lambda: self._set_selected_role("giang vien"))
        self.ui.btnSinhVien.clicked.connect(lambda: self._set_selected_role("sinh vien"))
        self.ui.label_3.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ui.label_3.mousePressEvent = lambda _e: self._on_login_forgot_password_click()
        self._set_selected_role("sinh vien")

    def _setup_login_left_background(self):
        """Ảnh nền toàn panel trái + lớp phủ tối để chữ đọc được (assets/login_bg_left.png)."""
        root = Path(__file__).resolve().parent
        bg_path = root / "assets" / "login_bg_left.png"
        if not bg_path.is_file():
            self.ui.leftBranding.setStyleSheet(
                self.ui.leftBranding.styleSheet().replace(
                    "background-color: transparent;",
                    "background-color: #0d1b2a;",
                )
            )
            return
        pix = QPixmap(str(bg_path))
        if pix.isNull():
            return
        self._login_bg_pix = pix
        self._login_bg_label = QLabel(self.ui.leftBranding)
        self._login_bg_label.setObjectName("loginBgImage")
        self._login_bg_label.lower()

        self._login_bg_overlay = QFrame(self.ui.leftBranding)
        self._login_bg_overlay.setObjectName("loginBgOverlay")
        self._login_bg_overlay.setStyleSheet(
            "QFrame#loginBgOverlay { background-color: rgba(13, 27, 42, 0.55); border: none; }"
        )

        self.ui.leftBranding.installEventFilter(self)
        self._sync_login_left_background_geometry()

        for w in self.ui.leftBranding.findChildren(QWidget):
            if w is self._login_bg_label or w is self._login_bg_overlay:
                continue
            w.raise_()

    def eventFilter(self, watched, event):
        if watched is self.ui.leftBranding and event.type() == QEvent.Type.Resize:
            self._sync_login_left_background_geometry()
        return super().eventFilter(watched, event)

    def _sync_login_left_background_geometry(self):
        if not getattr(self, "_login_bg_label", None):
            return
        r = self.ui.leftBranding.rect()
        self._login_bg_label.setGeometry(r)
        self._login_bg_overlay.setGeometry(r)
        if getattr(self, "_login_bg_pix", None) and not self._login_bg_pix.isNull():
            scaled = self._login_bg_pix.scaled(
                r.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._login_bg_label.setPixmap(scaled)

    def _load_login_brand_logo(self):
        root = Path(__file__).resolve().parent
        logo_px = 88
        dpr = max(1.0, float(self.devicePixelRatio()))
        for name in ("assets/logo_eaut.png", "logo.png"):
            p = (root / name).resolve()
            if p.is_file():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    side = int(round(logo_px * dpr))
                    scaled = pix.scaled(
                        side,
                        side,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    scaled.setDevicePixelRatio(dpr)
                    self.ui.lblLogoLeft.setPixmap(scaled)
                    self.ui.lblLogoLeft.setMinimumSize(logo_px, logo_px)
                    self.ui.lblLogoLeft.setMaximumSize(logo_px, logo_px)
                break

    def _on_login_forgot_password_click(self):
        QMessageBox.information(
            self,
            "Quên mật khẩu",
            "Vui lòng liên hệ quản trị hệ thống hoặc phòng Đào tạo để được cấp lại mật khẩu.",
        )

    def _toggle_login_password_visible(self, visible):
        if visible:
            self.ui.txtMatKhau.setEchoMode(QLineEdit.EchoMode.Normal)
            self.ui.btnToggleMatKhau.setText("Ẩn")
        else:
            self.ui.txtMatKhau.setEchoMode(QLineEdit.EchoMode.Password)
            self.ui.btnToggleMatKhau.setText("Hiện")

    @staticmethod
    def _normalize_login_text(text):
        """Chuẩn hóa chuỗi đăng nhập: bỏ khoảng trắng thừa, ký tự ẩn do bộ gõ tiếng Việt."""
        if text is None:
            return ""
        s = unicodedata.normalize("NFC", str(text).strip())
        cleaned = []
        for ch in s:
            cat = unicodedata.category(ch)
            if cat in ("Cf", "Mn"):  # định dạng / dấu rời (IME)
                continue
            if ch.isspace() and not cleaned:
                continue
            cleaned.append(ch)
        return "".join(cleaned).strip()

    def _apply_role_button_style(self):
        active_style = (
            "QPushButton { background-color: #e5e7eb; color: #0f172a; "
            "border: 1px solid #cbd5e1; border-radius: 10px; font-weight: 600; font-size: 13px; }"
        )
        default_style = (
            "QPushButton { background-color: #ffffff; color: #475569; "
            "border: 1px solid #e2e8f0; border-radius: 10px; font-weight: 600; font-size: 13px; }"
            "QPushButton:hover { background-color: #f8fafc; border-color: #cbd5e1; }"
        )
        self.ui.btnQuanTri.setStyleSheet(active_style if self.selected_role == "admin" else default_style)
        self.ui.btnGiangVien.setStyleSheet(active_style if self.selected_role == "giang vien" else default_style)
        self.ui.btnSinhVien.setStyleSheet(active_style if self.selected_role == "sinh vien" else default_style)

    def _set_selected_role(self, role):
        self.selected_role = role
        self._apply_role_button_style()

    @staticmethod
    def _normalize_role(role_text):
        if role_text is None:
            return ""
        text = str(role_text).strip().lower()
        # Loại dấu tiếng Việt để so khớp ổn định hơn.
        return "".join(
            ch
            for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        ).replace("đ", "d")

    def _open_window_by_role(self, role, username):
        normalized = self._normalize_role(role)
        if "admin" in normalized or "quan tri" in normalized:
            self.next_window = AdminApp(username)
        elif "giang vien" in normalized:
            self.next_window = LecturerApp(username)
        elif "sinh vien" in normalized or "sinhvien" in normalized:
            self.next_window = StudentApp(username)
        else:
            QMessageBox.warning(self, "Vai trò không hợp lệ", f"Không nhận diện được vai trò: {role}")
            return
        self.next_window.show()
        self.close()

    def dang_nhap(self):
        tk = self._normalize_login_text(self.ui.txtTaiKhoan.text())
        mk = self._normalize_login_text(self.ui.txtMatKhau.text())
        if not tk or not mk:
            self.ui.lblTrangThai.setText("Vui lòng nhập tài khoản và mật khẩu.")
            self.ui.lblTrangThai.setStyleSheet("color: red;")
            return
        try:
            account_rows = fetch_all(
                "SELECT TenDangNhap, VaiTro, COALESCE(TrangThai, 'HOAT_DONG'), COALESCE(SoLanSaiMK, 0) FROM TAI_KHOAN WHERE TenDangNhap = ?",
                (tk,),
            )
            if not account_rows:
                self.ui.lblTrangThai.setText("Sai tài khoản hoặc mật khẩu!")
                self.ui.lblTrangThai.setStyleSheet("color: red;")
                return
            _u, role_raw, status_raw, fail_count = account_rows[0]
            if str(status_raw).upper() == "BI_KHOA":
                self.ui.lblTrangThai.setText("Tài khoản đang bị khóa. Vui lòng liên hệ quản trị viên.")
                self.ui.lblTrangThai.setStyleSheet("color: red;")
                log_event(tk, role_raw, "Khóa TK", "Đăng nhập thất bại do tài khoản bị khóa")
                return

            auth_row = fetch_all(
                """
                SELECT VaiTro, COALESCE(TrangThai, 'HOAT_DONG'), MatKhau
                FROM TAI_KHOAN WHERE TenDangNhap = ?
                """,
                (tk,),
            )
            if auth_row and verify_password(mk, auth_row[0][2]):
                db_role, db_status = auth_row[0][0], auth_row[0][1]
                if str(db_status).upper() == "BI_KHOA":
                    self.ui.lblTrangThai.setText("Tài khoản đang bị khóa. Vui lòng liên hệ quản trị viên.")
                    self.ui.lblTrangThai.setStyleSheet("color: red;")
                    log_event(tk, db_role, "Khóa TK", "Đăng nhập thất bại do tài khoản bị khóa")
                    return
                db_norm = self._normalize_role(db_role)
                # Nếu người dùng có chọn nút vai trò thì kiểm tra nhất quán trước khi vào màn hình.
                if self.selected_role == "admin" and "admin" not in db_norm and "quan tri" not in db_norm:
                    self.ui.lblTrangThai.setText(
                        f"Sai vai trò: tài khoản «{tk}» là «{role_raw}». Hãy bấm nút Cán bộ."
                    )
                    self.ui.lblTrangThai.setStyleSheet("color: red;")
                    return
                if self.selected_role == "giang vien" and "giang vien" not in db_norm:
                    self.ui.lblTrangThai.setText(
                        f"Sai vai trò: tài khoản «{tk}» là «{role_raw}». Hãy bấm nút Giảng viên."
                    )
                    self.ui.lblTrangThai.setStyleSheet("color: red;")
                    return
                if self.selected_role == "sinh vien" and "sinh vien" not in db_norm and "sinhvien" not in db_norm:
                    self.ui.lblTrangThai.setText(
                        f"Sai vai trò: tài khoản «{tk}» là «{role_raw}». "
                        "Hãy bấm đúng nút Sinh viên / Giảng viên / Cán bộ."
                    )
                    self.ui.lblTrangThai.setStyleSheet("color: red;")
                    return

                self.ui.lblTrangThai.setText("Đăng nhập thành công!")
                self.ui.lblTrangThai.setStyleSheet("color: green;")
                execute_query(
                    """
                    UPDATE TAI_KHOAN
                    SET SoLanSaiMK = 0, LanDangNhapCuoi = datetime('now', 'localtime'),
                        CapNhatLuc = datetime('now', 'localtime')
                    WHERE TenDangNhap = ?
                    """,
                    (tk,),
                )
                log_event(tk, db_role, "Login OK", "Đăng nhập thành công")
                self._open_window_by_role(db_role, tk)
            else:
                next_fail = int(fail_count or 0) + 1
                if next_fail >= 5:
                    execute_query(
                        """
                        UPDATE TAI_KHOAN
                        SET SoLanSaiMK = ?, TrangThai = 'BI_KHOA', CapNhatLuc = datetime('now', 'localtime')
                        WHERE TenDangNhap = ?
                        """,
                        (next_fail, tk),
                    )
                    log_event(tk, role_raw, "Khóa TK", "Tài khoản bị khóa do nhập sai mật khẩu 5 lần")
                    self.ui.lblTrangThai.setText("Tài khoản đã bị khóa do nhập sai mật khẩu nhiều lần.")
                else:
                    execute_query(
                        "UPDATE TAI_KHOAN SET SoLanSaiMK = ?, CapNhatLuc = datetime('now', 'localtime') WHERE TenDangNhap = ?",
                        (next_fail, tk),
                    )
                    log_event(tk, role_raw, "Login Fail", f"Sai mật khẩu lần {next_fail}/5")
                    self.ui.lblTrangThai.setText("Sai tài khoản hoặc mật khẩu!")
                self.ui.lblTrangThai.setStyleSheet("color: red;")
        except Exception as e:
            self.ui.lblTrangThai.setText("Lỗi kết nối dữ liệu.")
            self.ui.lblTrangThai.setStyleSheet("color: red;")
            print("Lỗi khi đăng nhập:", e)


if __name__ == "__main__":
    bootstrap_database()
    app = QApplication(sys.argv)
    window = LoginApp()
    window.show()
    sys.exit(app.exec())
