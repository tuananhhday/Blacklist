# Blacklist Studio

Không gian gán nhãn bình luận tiếng Việt cho nhóm nhỏ, chạy Python standard library trên Render Free. Giao diện màu dịu với bạn mây hoạt hình, chế độ tập trung, phản hồi khi lưu và tùy chọn tắt chuyển động. Tôn trọng `prefers-reduced-motion` của thiết bị.

## Bắt đầu

Render → New → Blueprint → kết nối `tuananhhday/Blacklist`, nhánh `main`, file `render.yaml`. Đặt `STUDIO_PASSWORD`; username mặc định `admin`. Gói Free không gắn disk. Lệnh build/start và `/health` đã có trong Blueprint.

**Bật sao lưu theo [BACKUP_SETUP.md](BACKUP_SETUP.md) trước khi dùng dữ liệu cần giữ.** Repo backup phải private và Render phải có `GITHUB_BACKUP_TOKEN`; chỉ push mã nguồn chưa làm tính năng backup hoạt động. Dữ liệu phiên bản cũ cần tải bản sao trước khi deploy bản mới.

Chạy local: `python app.py`, mở `http://localhost:8765`. Có thể đặt `STUDIO_DATA` và `STUDIO_EXPORTS`; trên Render mặc định dùng thư mục tạm `/tmp/blacklist-studio/`.

## Gán nhãn liên tục

1. Mỗi người nhập tên người gán nhãn. Bấm nhận bình luận tiếp theo; server giữ riêng mẫu này 180 giây và gia hạn mỗi 30 giây khi còn kết nối. Người khác nhận câu khác.
2. Chọn Có / Không / Chưa kiểm tra ở từng nhóm. Một câu có thể có nhiều nhóm vi phạm. Phím `1–9` bật/tắt nhãn Có; `N` xác nhận các nhóm còn lại không vi phạm; `U` chọn Cần xem lại; `F` bật chế độ tập trung. Phím tắt không chạy khi đang gõ trong trường nhập liệu.
3. Chọn kết luận rồi Lưu & tiếp theo (`Ctrl/Cmd + Enter`). Server kiểm tra lượt giữ và phiên bản nhãn; gửi lại cùng thao tác không tạo lần duyệt trùng. Nút Bỏ qua chuyển sang mẫu khác, giữ nháp cũ.
4. Bằng chứng, hành vi và ghi chú ở phần thu gọn, không bắt buộc. Bỏ trống ghi chú sẽ lưu tóm tắt kết luận và nhãn đã chọn. Có thể hoàn tác thao tác chọn nhãn trước khi lưu.
5. Nhãn chưa kiểm tra vẫn là `null`, xuất với `label_mask=0`; không tự đổi thành Không. Thao tác xác nhận các nhóm còn lại là hành động rõ ràng của người duyệt.

Tên người duyệt là tự khai; web dùng Basic Auth chung. Giữ mẫu ngăn hai phiên cùng sửa một câu, không thay thế hệ thống tài khoản riêng. Chỉ chạy một instance; xem giới hạn backup và lưu trữ trong tài liệu thiết lập.

## Nhập mẫu từ file

Thêm mẫu → Nhập từ file → chọn một hoặc nhiều CSV, JSON, JSONL, TXT → Xem trước → Nhập vào hàng đợi. Tối đa 5 MB mỗi file và 5.000 câu mỗi lượt; gửi từng lô 50 câu và hiển thị tiến độ. Có thể thử lại phần còn lại khi mất mạng; nội dung và ngữ cảnh trùng được bỏ qua bằng fingerprint có UNIQUE trong SQL.

- TXT: mỗi dòng một bình luận.
- JSON: mảng chuỗi hoặc object; cũng nhận object có `samples` hay `comments`.
- CSV/JSON/JSONL: tự nhận cột `text`, `comment`, `content`, `body`, hoặc nhập tên cột riêng. Các trường tùy chọn: `context`, `source`, `synthetic`. Source thiếu dùng tên file; synthetic thiếu dùng checkbox dữ liệu mô phỏng (mặc định không chọn). Nếu đã có synthetic thì phải là true/false.
- Nhãn sẵn trong file không tự trở thành nhãn chuẩn. Mỗi nội dung tối đa 20.000 ký tự.

## SQL và backup

`sql/schema.sql`: mẫu, lịch sử nhãn, luật và lịch sử luật. `sql/003_collaboration.sql`: lượt giữ mẫu, bản nháp, phiên bản kho và biên nhận chống lưu trùng. Migration chạy tự động, giữ nguyên bảng và dữ liệu cũ. Ghi dùng transaction `BEGIN IMMEDIATE`; SQLite WAL cho phép đọc khi có nhiều người thao tác. Database vẫn là SQLite, không phải MySQL.

Nháp giữ trên thiết bị, tự gửi lên server; server thử backup Git mỗi 20 giây và sau thao tác lưu chính. Nếu Git chưa đồng bộ, bản nhãn vừa lưu vẫn giữ thêm trên thiết bị. Giao diện hiển thị riêng trạng thái nháp và Git. Có nút Sao lưu Git ngay và Tải nháp trên thiết bị.

Git lưu snapshot `snapshots/latest.sqlite3.gz` trong repo private riêng; khôi phục tự động nếu Render mất database. Không thể cam kết mọi ký tự đã lên Git khi mạng/server chết đột ngột; xem trạng thái đồng bộ và giữ bản tải về.

## Blacklist và xuất dữ liệu

Luật có thể tạo từ mẫu vi phạm đã lưu hoặc tạo thủ công. Nháp không được đưa vào blacklist đang bật. Muốn bật luật cần mẫu khớp và mẫu đối chiếu, các kiểm tra đều đạt. Luật chỉ chuyển duyệt, không tự xóa/chặn.

Nhập blacklist JSON (`rules` hoặc mảng luật), CSV (`name,category,kind,pattern,reason`) hoặc TXT (mỗi dòng một nguyên câu). Mọi luật nhập thành nháp; mục trùng được bỏ qua. Tối đa 1.000 luật/lượt, file dưới 1,9 MB. Các nhóm dùng mã trong `sql/002_categories.sql`.

- `blacklist.json`: chỉ luật đang bật.
- `blacklist_drafts.json`: toàn bộ luật, gồm nháp và đã tắt.
- `training_data.jsonl`: mẫu đã kết luận, nhãn và label_mask; chưa chia train/test.
- `backup.sql`: toàn bộ SQLite gồm lịch sử và bản nháp. Không upload SQL qua web.

Phục hồi SQL thủ công: dừng app, giữ bản database cũ, tạo SQLite mới và chạy nội dung SQL từ bản sao tin cậy, kiểm tra rồi thay file. Không chạy SQL vào kho đang có dữ liệu. Không xóa disk/dữ liệu bản cũ trước khi xác nhận bản phục hồi.

## Kiểm tra

```sh
python -m unittest -v test_app test_render test_collaboration
node --check static/app.js
node test_ui.cjs
```

Backend kiểm tra workflow, Basic Auth, rollback, chống trùng, nhiều người nhận đồng thời, hết lượt, backup/restore và từ chối repo public/xung đột remote. Kiểm thử Node dùng DOM giả lập cho parser file, nháp, hoàn tác, giảm chuyển động và gửi lại sau khi server đổi phiên; không thay thế kiểm tra bố cục trên trình duyệt.
