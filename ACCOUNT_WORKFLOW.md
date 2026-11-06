# Tài khoản và phân việc trong Blacklist Studio

## Admin bắt đầu

1. Mở web. Tài khoản admin là `STUDIO_USERNAME` (mặc định `admin`); mã đăng nhập là `STUDIO_PASSWORD` hiện có trong Environment trên Render. Đây là mã riêng của admin, không dùng làm mã chung cho nhóm.
2. Vào Giám sát & chia việc → Tạo tài khoản thành viên. Điền tài khoản (3–40 chữ thường/số/`_.-`) và tên hiển thị. App sinh mã riêng, chỉ hiển thị lần tạo/cấp mã thành công. Gửi riêng **tài khoản + mã** cho đúng người; app không tự nhắn cho thành viên.
3. Thêm/import dữ liệu tại Quản lý bình luận. Chọn người nhận việc, nhập số câu tối đa/người (0 là chia hết), xem trước rồi xác nhận. Mỗi bình luận chỉ thuộc một người tại một thời điểm. Những câu đã giao hoặc đang được giữ không bị chia chồng.
4. Thành viên đăng nhập, thấy phần việc riêng và số bình luận còn lại, nhận câu tiếp theo, lưu liên tục. Có thể chọn gửi thêm nháp blacklist khi lưu câu vi phạm. Thành viên không có quyền import, xem kho của người khác, xuất SQL hoặc bật luật.
5. Admin xem tiến độ/lịch sử, mở từng lượt để kiểm tra. Có nút Nhãn đạt hoặc Trả lại để sửa; khi trả lại cần ghi lý do. Câu quay về hàng đợi của thành viên, lịch sử nhãn cũ được giữ.

## Quản lý thông tin

- Sửa tên hiển thị/tài khoản: lịch sử vẫn gắn UID cũ. Đổi tài khoản sinh mã mới. Các phiên đăng nhập hiện tại của thành viên kết thúc.
- Cấp mã mới: mã cũ không dùng được, phiên cũ bị thu hồi. Không có nút xem lại mã cũ vì server chỉ giữ hash.
- Khóa/mở khóa: giữ nguyên tài khoản và dữ liệu. Mở khóa không tự phát mã mới; có thể cấp mã mới nếu cần.
- Xóa: thu hồi truy cập và đưa tài khoản vào trạng thái đã xóa, giữ lịch sử; các phần chưa hoàn thành về kho để admin chia lại. Khôi phục cấp mã mới, tài khoản vẫn có cùng UID. Tên tài khoản đã xóa được giữ để tránh nhầm người.
- Thu hồi chưa làm: thu hồi phần pending không có lượt giữ còn hạn, giữ các câu đã xong. Nếu câu cần sửa đã có nhãn thì quay về kho với cờ cần gán lại.
- Bình luận: admin có thể thêm, sửa, xóa và khôi phục. Xóa đưa vào lưu trữ, không hủy nhãn/lịch sử. Đổi nội dung một mẫu đã có nhãn tạo mẫu thay thế; nhãn cũ không tự áp vào nội dung mới. Sửa khi có người đang xử lý bị chặn để tránh mất thao tác.
- Blacklist: thành viên gửi nháp từ câu vi phạm thuộc phần mình; admin xem, sửa, kiểm tra các ví dụ và bật/tắt luật.

## Đọc các số liệu giám sát

| Số liệu | Ý nghĩa |
| --- | --- |
| Đã giao / đã xong / còn lại | Số bình luận trong phần việc hiện tại, không tính bản đã lưu trữ |
| Lượt lưu | Tổng các lần gán nhãn/sửa nhãn của tài khoản; khác số bình luận duy nhất |
| Trung vị/câu | Trung vị thời gian mở câu của tối đa 200 lượt có số đo gần nhất |
| Mở câu | Thời gian từ server cấp lượt hiện tại đến khi server nhận nhãn; có thể gồm nghỉ/mất mạng, không gồm thời gian backup sau lưu |
| Hoạt động ≈ | Ước tính từ heartbeat lúc trang hiển thị/có focus; có khoảng trống và có thể bị thao túng từ trình duyệt |
| Lượt nhanh | Thời gian mở câu dưới ngưỡng tại lúc lưu; mặc định 5 giây, admin chỉnh 1–120 giây |

Cảnh báo nhanh hỗ trợ chọn mẫu rà soát, không tự kết luận gán bừa hoặc tự phạt. Ngưỡng mới chỉ áp dụng cho lần lưu tiếp theo; các bản ghi cũ giữ ngưỡng cũ. Nhãn từ trước nâng cấp không có user_id/thời gian sẽ hiển thị chưa có số đo, không gán thời gian giả.

Admin có thể lọc theo người hoặc chỉ lượt nhanh, phân trang lịch sử, đọc toàn câu/ngữ cảnh, 9 nhãn, lý do và bằng chứng trước khi xác nhận đạt hay trả lại. Mở màn kiểm tra không chiếm lượt hoặc thay đổi đồng hồ của thành viên.

## Backup và khởi động lại

Tài khoản, mã hash, phần việc, nhãn, thời gian, kết quả kiểm tra và dữ liệu lưu trữ đều nằm trong SQLite snapshot. Session đăng nhập bị loại khỏi snapshot; sau restart người dùng đăng nhập lại bằng mã hiện có. Backup cần repo private và token Render theo [BACKUP_SETUP.md](BACKUP_SETUP.md). Nếu Git backup chưa cấu hình, Render Free có thể làm mất cả tài khoản và phần việc khi mất ổ tạm.
