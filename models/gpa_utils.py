"""Tính GPA tích lũy theo tín chỉ, chỉ từ điểm đã công bố (DaKhoa = 1)."""


def hoc_luc_tu_gpa10(gpa10):
    g = float(gpa10 or 0)
    if g >= 8.5:
        return "Xuất sắc", 1
    if g >= 7.0:
        return "Giỏi", 2
    if g >= 5.5:
        return "Khá", 3
    if g >= 4.0:
        return "Trung bình", 4
    return "Yếu / Kém", 5


def compute_published_gpa(mssv, fetch_all_fn):
    """
    GPA10 = Σ(ĐTB × tín chỉ) / Σ(tín chỉ) với điểm đã khóa/công bố.
    Trả về (gpa10, gpa4, xep_loai, so_mon).
    """
    try:
        rows = fetch_all_fn(
            """
            SELECT d.DTB, COALESCE(m.SoTinChi, 3)
            FROM DIEM d
            LEFT JOIN MON_HOC m ON m.MaMon = d.MaMon
            WHERE d.MSSV = ?
              AND COALESCE(d.DaKhoa, 0) = 1
              AND d.DTB IS NOT NULL
            """,
            (mssv,),
        )
    except Exception:
        return 0.0, 0.0, "Chưa có", 0
    if not rows:
        return 0.0, 0.0, "Chưa có", 0
    total_tc = 0
    weighted = 0.0
    for dtb, tc in rows:
        try:
            t = int(tc or 3)
            d = float(dtb)
        except (TypeError, ValueError):
            continue
        if t <= 0:
            continue
        total_tc += t
        weighted += d * t
    if total_tc <= 0:
        return 0.0, 0.0, "Chưa có", 0
    gpa10 = round(weighted / total_tc, 2)
    gpa4 = round(gpa10 * 0.4, 2)
    return gpa10, gpa4, hoc_luc_tu_gpa10(gpa10)[0], len(rows)


def sync_student_gpa_record(mssv, fetch_all_fn, execute_query_fn):
    gpa10, gpa4, xep, _n = compute_published_gpa(mssv, fetch_all_fn)
    execute_query_fn(
        "UPDATE SINH_VIEN SET GPA10 = ?, GPA4 = ?, XepLoai = ? WHERE MSSV = ?",
        (gpa10, gpa4, xep, mssv),
    )


def recalc_all_student_gpa(fetch_all_fn, execute_query_fn):
    if not fetch_all_fn:
        return
    try:
        rows = fetch_all_fn("SELECT MSSV FROM SINH_VIEN")
    except Exception:
        return
    for (mssv,) in rows:
        sync_student_gpa_record(mssv, fetch_all_fn, execute_query_fn)
