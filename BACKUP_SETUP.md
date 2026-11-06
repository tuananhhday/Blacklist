# Bật Git backup trên Render Free

Mã nguồn: `tuananhhday/Blacklist`. Dữ liệu: `tuananhhday/backup-blacklist`.

## Trước khi cập nhật bản đang chạy

Render Free có ổ tạm. Nếu đang có dữ liệu, tải `backup.sql` và toàn bộ blacklist từ bản đang chạy trước khi deploy. Phiên bản cũ chưa có cơ chế đẩy backup tự động. Không có cách bảo đảm lấy lại dữ liệu đã mất trước khi tính năng backup được cấu hình.

## Thiết lập một lần

1. Vào repo `backup-blacklist` → Settings → General → Danger Zone → Change repository visibility → Private. App kiểm tra trạng thái private trước mỗi lần gửi dữ liệu. Giữ repo backup riêng với repo mã nguồn để các commit backup không kích hoạt deploy.
2. GitHub → Settings tài khoản → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token. Resource owner: `tuananhhday`; Only select repositories: `backup-blacklist`; Repository permissions → Contents: Read and write. Chọn ngày hết hạn phù hợp và lưu nhắc gia hạn.
3. Render → service `blacklist-studio` → Environment. Đặt:

   | Key | Value |
   | --- | --- |
   | `GITHUB_BACKUP_REPO` | `tuananhhday/backup-blacklist` |
   | `GITHUB_BACKUP_BRANCH` | `main` |
   | `GITHUB_BACKUP_TOKEN` | Token vừa tạo, nhập trực tiếp trên Render |

   Không gửi token qua chat, không ghi vào Git hay file ZIP. Vẫn giữ `STUDIO_PASSWORD`.
4. Deploy bản cập nhật. Vào Nhập & xuất dữ liệu → Sao lưu Git ngay. Chỉ coi là đã sao lưu khi app hiện **Git backup: đã đồng bộ** và repo có `snapshots/latest.sqlite3.gz`.
5. Thử bằng một mẫu mô phỏng, lưu nhãn, xác nhận Git đã đồng bộ rồi redeploy. Mẫu phải xuất hiện trở lại. Không thử xóa dữ liệu thật để kiểm tra.

## App làm gì

- Mỗi lần nhập mẫu, lưu nhãn hoặc lưu luật: commit SQLite trước, sau đó thử đẩy snapshot Git. Response chỉ báo Git đã đồng bộ nếu GitHub xác nhận thành công.
- Khi đang gõ: giữ nháp trên thiết bị ngay; sau 1,6 giây ngừng thao tác gửi nháp lên server. Server gom thay đổi và thử backup mỗi 20 giây. Nhãn đã lưu mà Git chưa đồng bộ vẫn giữ thêm trên thiết bị.
- SQLite snapshot nhất quán được tạo bằng SQLite Backup API. Snapshot chứa mẫu, lịch sử nhãn, luật, bản nháp và mã chống gửi trùng. Lượt giữ mẫu không được phục hồi để tránh khóa người dùng sau restart.
- Khi Render khởi động mà database không còn: tải backup private, kiểm tra định dạng/integrity rồi khôi phục trước khi mở server. Nếu đã cấu hình backup mà GitHub lỗi, server dừng khởi động thay vì mở một kho trống rồi ghi đè backup.
- Lịch sử commit của repo giữ các phiên bản snapshot. Không tự xóa lịch sử backup. Token hết hạn hoặc repo chuyển public sẽ ngừng sao lưu và hiển thị lỗi.

## Giới hạn cần biết

Git là bản sao lưu, không phải database dùng chung giữa nhiều instance. Chỉ chạy **một instance, một tiến trình app**; nhiều trình duyệt có thể gán nhãn cùng lúc trên instance đó. Gói Free có thể ngủ; người dùng cần chờ lúc mở lại. GitHub có hạn mức API, nên phù hợp nhóm nhỏ và dữ liệu vừa phải. Snapshot nén tối đa 20 MB, phục hồi tối đa 100 MB giải nén.

Không hệ thống nào có thể đẩy dữ liệu mới lên Git khi server đã đứng hoàn toàn hoặc mạng đã mất. Ký tự chưa kịp gửi vẫn nằm trong bản nháp thiết bị nếu trình duyệt cho phép lưu; đừng xóa dữ liệu trình duyệt khi còn nháp. Dùng “Tải nháp trên thiết bị” để lấy JSON; file này có thể nhập lại các bình luận qua Nhập từ file, sau đó kiểm tra lại nhãn. Backup Git định kỳ có khoảng trễ; kiểm tra trạng thái trước khi redeploy hoặc kết thúc phiên.

Khi có dữ liệu SQLite cũ tại local nhưng Git có kho khác hoặc phiên bản mới hơn, app dừng để tránh ghi đè. Giữ cả hai bản để xử lý thủ công. Không chạy đồng thời hai bản service cùng ghi vào một repo backup.

Tài khoản và mã riêng do admin cấp được backup cùng database (mã chỉ lưu dạng hash có salt). Cookie session và bộ đếm đăng nhập sai được bỏ khỏi snapshot; mọi người đăng nhập lại sau khi khởi động lại. Mã admin lấy từ STUDIO_PASSWORD, không chia sẻ mã đó với thành viên.
