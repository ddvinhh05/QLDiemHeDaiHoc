1. Lớp TAI_KHOAN (Tài khoản)
Đây là lớp trung tâm dùng để xác thực và phân quyền người dùng.

Thuộc tính:
TenDangNhap (khóa chính)
MatKhau
VaiTro (Admin / GV / SV)
TrangThai (mặc định “HOAT_DONG”)
SoLanSaiMK
LanDangNhapCuoi
TaoLuc
Phương thức:
dangNhap(): kiểm tra đăng nhập
doiMatKhau(): đổi mật khẩu
Lớp này được kế thừa bởi GIANG_VIEN và SINH_VIEN.
2. Lớp NHAT_KY_HE_THONG (Nhật ký hệ thống)
Dùng để ghi lại các hoạt động trong hệ thống.
Thuộc tính:
Id (khóa chính, tự tăng)
ThoiGian
TenDangNhap (khóa ngoại)
VaiTro
LoaiSuKien
NoiDung
DiaChiIP
Phương thức:
ghiLog(): ghi lại log
Quan hệ: Một tài khoản có thể tạo nhiều bản ghi nhật ký (1 – 0..*).
3. Lớp GIANG_VIEN (Giảng viên)
Kế thừa từ TAI_KHOAN.
Thuộc tính:
MaGV (khóa chính, đồng thời là khóa ngoại tới tài khoản)
HoTen, Khoa, Email, SoDienThoai, TrangThai
Phương thức:
nhapDiem(): nhập điểm
xemDanhSachSV(): xem danh sách sinh viên
Quan hệ:
Một giảng viên có thể được phân công nhiều lớp/môn (1 – 0..* với PHAN_CONG).
4. Lớp SINH_VIEN (Sinh viên)
Cũng kế thừa từ TAI_KHOAN.
Thuộc tính:
MSSV (khóa chính, đồng thời là khóa ngoại)
HoTen, Lop, Khoa
TrangThai (mặc định “DANG_HOC”)
GPA10, GPA4
XepLoai
Phương thức:
xemBangDiem(): xem bảng điểm
tinhGPA(): tính điểm trung bình
Quan hệ:
Một sinh viên có nhiều bản ghi điểm (1 – 0..* với DIEM).
5. Lớp MON_HOC (Môn học)
Quản lý thông tin môn học.
Thuộc tính:
MaMon (khóa chính)
TenMon
SoTinChi
KhoaPhuTrach
HeSoCC, HeSoGK, HeSoCK (hệ số tính điểm)
Phương thức:
tinhDTB(cc, gk, ck): tính điểm trung bình
Quan hệ:
Một môn học có thể có nhiều điểm và nhiều phân công (1 – 0..*).
6. Lớp HOC_KY (Học kỳ)
Quản lý thông tin học kỳ.
Thuộc tính:
HocKy, NamHoc (cùng là khóa chính)
TenHienThi
TrangThai (mặc định “DANG_DIEN_RA”)
NgayBatDau, NgayKetThuc
Quan hệ:
Một học kỳ có nhiều bản ghi điểm và phân công (1 – 0..*).
7. Lớp PHAN_CONG (Phân công giảng dạy)
Liên kết giữa giảng viên, môn học và học kỳ.
Thuộc tính:
MaGV, MaMon, Lop, HocKy, NamHoc (đều là khóa chính/kết hợp và khóa ngoại)
TrangThai (mặc định “DANG_DAY”)
Quan hệ:
Một phân công thuộc về 1 giảng viên, 1 môn học và 1 học kỳ.
Dùng để xác định giảng viên nào dạy môn nào, lớp nào, trong học kỳ nào.
8. Lớp DIEM (Điểm)
Lưu điểm của sinh viên theo từng môn và học kỳ.
Thuộc tính:
MSSV, MaMon, HocKy, NamHoc (khóa chính kết hợp, đồng thời là khóa ngoại)
CC (chuyên cần), GK (giữa kỳ), CK (cuối kỳ)
DTB (tính tự động)
KetQua (thuộc tính ảo)
Phương thức:
khoaDiem(): khóa điểm
Quan hệ:
Mỗi bản ghi điểm gắn với 1 sinh viên, 1 môn học và 1 học kỳ.
Một sinh viên có nhiều điểm; một môn học và học kỳ cũng có nhiều bản ghi điểm.
Tổng kết quan hệ chính:
TAI_KHOAN là lớp cha của GIANG_VIEN và SINH_VIEN.
TAI_KHOAN liên kết với NHAT_KY_HE_THONG (1 – nhiều).
GIANG_VIEN ↔ PHAN_CONG ↔ MON_HOC ↔ HOC_KY (liên kết giảng dạy).
SINH_VIEN ↔ DIEM ↔ MON_HOC ↔ HOC_KY (quản lý điểm).