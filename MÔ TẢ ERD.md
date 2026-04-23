
MÔ TẢ SƠ ĐỒ ERD (Entity-Relationship Diagram) — Hệ Thống Quản Lý Điểm
I. TỔNG QUAN

Sơ đồ ERD của hệ thống Quản Lý Điểm mô tả cấu trúc cơ sở dữ liệu quan hệ với 8 bảng (thực thể) chính. Sơ đồ tập trung vào các khóa chính, khóa ngoại và các ràng buộc dữ liệu giữa các bảng, phản ánh trực tiếp cách dữ liệu được lưu trữ và liên kết trong cơ sở dữ liệu.
II. MÔ TẢ CÁC THỰC THỂ VÀ THUỘC TÍNH

1. Bảng TAI_KHOAN
Bảng TAI_KHOAN là bảng trung tâm lưu thông tin xác thực của toàn bộ người dùng trong hệ thống.
 Khóa chính là TenDangNhap kiểu TEXT. Các cột dữ liệu gồm MatKhau kiểu TEXT, VaiTro kiểu TEXT nhận một trong ba giá trị Admin, GV hoặc SV, TrangThai kiểu TEXT có giá trị mặc định 'HOAT_DONG', SoLanSaiMK kiểu INTEGER có giá trị mặc định 0, LanDangNhapCuoi kiểu TEXT, và TaoLuc kiểu TEXT. Bảng này không có khóa ngoại vì là bảng gốc của hệ thống.

2. Bảng GIANG_VIEN
Bảng GIANG_VIEN lưu thông tin chi tiết của giảng viên. Khóa chính đồng thời là khóa ngoại MaGV kiểu TEXT tham chiếu đến TenDangNhap trong bảng TAI_KHOAN, thể hiện quan hệ một-một giữa tài khoản và giảng viên. Các cột còn lại gồm HoTen, Khoa, Email, SoDienThoai và TrangThai, tất cả đều kiểu TEXT.

3. Bảng SINH_VIEN
Bảng SINH_VIEN lưu thông tin chi tiết của sinh viên. Khóa chính đồng thời là khóa ngoại MSSV kiểu TEXT tham chiếu đến TenDangNhap trong bảng TAI_KHOAN. Các cột dữ liệu gồm HoTen kiểu TEXT, Lop kiểu TEXT, Khoa kiểu TEXT, TrangThai kiểu TEXT mặc định 'DANG_HOC', GPA10 kiểu REAL mặc định 0, GPA4 kiểu REAL mặc định 0, và XepLoai kiểu TEXT.

4. Bảng MON_HOC
Bảng MON_HOC lưu danh mục các môn học. Khóa chính là MaMon kiểu TEXT. Các cột dữ liệu gồm TenMon kiểu TEXT, SoTinChi kiểu INTEGER, KhoaPhuTrach kiểu TEXT, HeSoCC kiểu REAL mặc định 0.1, HeSoGK kiểu REAL mặc định 0.3, và HeSoCK kiểu REAL mặc định 0.6. Tổng ba hệ số luôn bằng 1.0, đảm bảo tính toán điểm trung bình chính xác.

5. Bảng HOC_KY
Bảng HOC_KY lưu thông tin các học kỳ. Khóa chính là tổ hợp hai cột HocKy kiểu INTEGER (chỉ nhận giá trị 1, 2 hoặc 3) và NamHoc kiểu TEXT. Các cột dữ liệu gồm TenHienThi kiểu TEXT, TrangThai kiểu TEXT mặc định 'DANG_DIEN_RA', NgayBatDau kiểu TEXT, và NgayKetThuc kiểu TEXT. Bảng này không có khóa ngoại.

6. Bảng PHAN_CONG
Bảng PHAN_CONG là bảng trung gian giải quyết quan hệ nhiều-nhiều giữa giảng viên, môn học và học kỳ. Khóa chính là tổ hợp năm cột: MaGV kiểu TEXT là khóa ngoại tham chiếu bảng GIANG_VIEN, MaMon kiểu TEXT là khóa ngoại tham chiếu bảng MON_HOC, Lop kiểu TEXT, HocKy kiểu INTEGER là khóa ngoại tham chiếu bảng HOC_KY, và NamHoc kiểu TEXT là khóa ngoại tham chiếu bảng HOC_KY. Cột dữ liệu bổ sung là TrangThai kiểu TEXT mặc định 'DANG_DAY'.

7. Bảng DIEM
Bảng DIEM là bảng trung gian giải quyết quan hệ nhiều-nhiều giữa sinh viên, môn học và học kỳ. Khóa chính là tổ hợp bốn cột: MSSV kiểu TEXT là khóa ngoại tham chiếu bảng SINH_VIEN, MaMon kiểu TEXT là khóa ngoại tham chiếu bảng MON_HOC, HocKy kiểu INTEGER là khóa ngoại tham chiếu bảng HOC_KY, và NamHoc kiểu TEXT là khóa ngoại tham chiếu bảng HOC_KY. Các cột điểm gồm CC kiểu REAL ràng buộc từ 0 đến 10, GK kiểu REAL ràng buộc từ 0 đến 10, CK kiểu REAL ràng buộc từ 0 đến 10. Cột DTB kiểu REAL được ghi chú là auto trigger, tức là giá trị này tự động được tính lại thông qua trigger của cơ sở dữ liệu mỗi khi CC, GK hoặc CK thay đổi. Cột KetQua kiểu TEXT được đánh dấu VIRTUAL, nghĩa là đây là cột ảo được tính toán động, không chiếm dung lượng lưu trữ thực tế.

8. Bảng NHAT_KY_HE_THONG
Bảng NHAT_KY_HE_THONG lưu lịch sử hoạt động của người dùng trong hệ thống. Khóa chính là Id kiểu INTEGER tự động tăng (AUTO INCREMENT). Các cột dữ liệu gồm ThoiGian kiểu TEXT, TenDangNhap kiểu TEXT là khóa ngoại tham chiếu bảng TAI_KHOAN, VaiTro kiểu TEXT, LoaiSuKien kiểu TEXT, NoiDung kiểu TEXT, và DiaChiIP kiểu TEXT.

III. CÁC MỐI QUAN HỆ TRONG ERD

- Quan hệ giữa TAI_KHOAN và GIANG_VIEN là quan hệ một-một, trong đó một bản ghi TAI_KHOAN tương ứng với đúng một bản ghi GIANG_VIEN thông qua khóa ngoại MaGV. Tương tự, quan hệ giữa TAI_KHOAN và SINH_VIEN cũng là một-một thông qua khóa ngoại MSSV.

- Quan hệ giữa TAI_KHOAN và NHAT_KY_HE_THONG là một-nhiều: một tài khoản có thể có từ không đến nhiều bản ghi nhật ký, liên kết qua khóa ngoại TenDangNhap trong bảng NHAT_KY_HE_THONG.

- Quan hệ giữa GIANG_VIEN và PHAN_CONG là một-nhiều: một giảng viên có thể được phân công nhiều lần, liên kết qua khóa ngoại MaGV.

- Quan hệ giữa MON_HOC và PHAN_CONG là một-nhiều: một môn học có thể xuất hiện trong nhiều phân công, liên kết qua khóa ngoại MaMon.

- Quan hệ giữa HOC_KY và PHAN_CONG là một-nhiều: một học kỳ có thể chứa nhiều phân công, liên kết qua tổ hợp khóa ngoại HocKy và NamHoc.

- Quan hệ giữa SINH_VIEN và DIEM là một-nhiều: một sinh viên có nhiều bản ghi điểm tương ứng với các môn học khác nhau qua các học kỳ khác nhau, liên kết qua khóa ngoại MSSV.

- Quan hệ giữa MON_HOC và DIEM là một-nhiều: một môn học có thể có nhiều bản ghi điểm từ nhiều sinh viên, liên kết qua khóa ngoại MaMon.

- Quan hệ giữa HOC_KY và DIEM là một-nhiều: một học kỳ chứa nhiều bản ghi điểm, liên kết qua tổ hợp khóa ngoại HocKy và NamHoc.

IV. ĐẶC ĐIỂM KỸ THUẬT CỦA ERD

- Về thiết kế khóa chính, hệ thống sử dụng hai dạng: khóa đơn cho các bảng độc lập như TAI_KHOAN, MON_HOC, NHAT_KY_HE_THONG, và khóa tổ hợp cho các bảng trung gian như PHAN_CONG với năm cột và DIEM với bốn cột.

- Về ràng buộc dữ liệu, các cột điểm CC, GK, CK được ràng buộc trong khoảng từ 0 đến 10. Cột HocKy chỉ nhận một trong ba giá trị 1, 2 hoặc 3. Cột VaiTro trong TAI_KHOAN chỉ nhận một trong ba giá trị Admin, GV hoặc SV.

- Về tính toán tự động, DTB được tính tự động qua trigger khi dữ liệu điểm thay đổi, đảm bảo tính toàn vẹn dữ liệu. KetQua là cột ảo được tính từ DTB mà không lưu trực tiếp, tiết kiệm dung lượng lưu trữ.

- Về tính toàn vẹn tham chiếu, toàn bộ khóa ngoại trong hệ thống đều đảm bảo tính toàn vẹn tham chiếu, nghĩa là không thể tạo bản ghi điểm cho sinh viên hoặc môn học không tồn tại, không thể phân công giảng viên không có trong hệ thống, và không thể ghi nhật ký cho tài khoản không tồn tại.