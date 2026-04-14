 Phần Mềm Quản Lý Điểm Đại Học

 SQLite. Hệ thống hỗ trợ 2 vai trò người dùng:
| Vai trò             | Mô tả                                                        |
|  - Giảng viên       | Toàn quyền: quản lý sinh viên, môn học, nhập điểm, thống kê. |
|  - Sinh viên        | Chỉ xem: tra cứu điểm cá nhân, GPA, xếp loại.                |

- Tính Năng Chính
 Giảng Viên:

 - Quản lý sinh viên (thêm, sửa, xóa, tìm kiếm)
 - Quản lý môn học (mã môn, tên môn, số tín chỉ, học kỳ)
 - Nhập & sửa điểm (chuyên cần, giữa kỳ, cuối kỳ)
 - Tự động tính điểm trung bình & xếp loại
 - Thống kê biểu đồ phân bố điểm
 - Xuất báo cáo ra file Excel / PDF
 - Quản lý tài khoản giảng viên & sinh viên

 Sinh Viên:

 - Xem điểm từng môn theo học kỳ
 - Xem GPA tích lũy (thang 4 & thang 10)
 - Xem xếp loại học lực
 - Tra cứu & lọc bảng điểm
 - Đổi mật khẩu cá nhân


- Công Thức Tính Điểm

| Điểm Trung Bình | Xếp Loại   | GPA (Thang 4) |
|  ≥ 8.5          | Xuất sắc   | 4.0           |
|  7.0 – 8.4      | Giỏi       | 3.0 – 3.9     |
|  5.5 – 6.9      | Khá        | 2.0 – 2.9     |
|  4.0 – 5.4      | Trung bình | 1.0 – 1.9     |
|  < 4.0          | Yếu / Kém  | 0.0           |

🛠 Công Nghệ Sử Dụng
Ngôn ngữ: Python
Giao diện: QTDesigner
Cơ sở dữ liệu:** SQLite3
