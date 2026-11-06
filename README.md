# Blacklist Studio

Không gian gán nhãn bình luận tiếng Việt cho nhóm nhỏ, chạy Python và PyArrow trên Render Free. Giao diện màu dịu với bạn mây hoạt hình, chế độ tập trung, phản hồi khi lưu và tùy chọn tắt chuyển động. Tôn trọng `prefers-reduced-motion` của thiết bị.

## Bắt đầu

Render → New → Blueprint → kết nối `tuananhhday/Blacklist`, nhánh `main`, file `render.yaml`. Đặt `STUDIO_PASSWORD`; username mặc định `admin`. Gói Free không gắn disk. Lệnh build/start và `/health` đã có trong Blueprint. Build mới cài `requirements.txt` để đọc Parquet bằng PyArrow.

**Bật sao lưu theo [BACKUP_SETUP.md](BACKUP_SETUP.md) trước khi dùng dữ liệu cần giữ.** Repo backup phải private và Render phải có `GITHUB_BACKUP_TOKEN`; chỉ push mã nguồn chưa làm tính năng backup hoạt động. Dữ liệu phiên bản cũ cần tải bản sao trước khi deploy bản mới.

Chạy local: cài `python -m pip install -r requirements.txt`, đặt `STUDIO_PASSWORD` rồi chạy `python app.py`, mở `http://localhost:8765`. Có thể đặt `STUDIO_DATA` và `STUDIO_EXPORTS`; trên Render mặc định dùng thư mục tạm `/tmp/blacklist-studio/`.

## Tài khoản, phân quyền & chia phần

Đăng nhập ngay trên trang web, không còn hộp Basic Auth chung. Admin dùng tài khoản `STUDIO_USERNAME` (mặc định `admin`) và mã `STUDIO_PASSWORD` đang đặt trên Render; giữ mã admin riêng. Admin tạo tài khoản thành viên và mã riêng gắn đúng tên. Không có tự đăng ký hoặc tự cấp quyền admin.

Admin vào **Giám sát & chia việc** để tạo/sửa/khóa/xóa/khôi phục tài khoản, cấp lại mã, import dữ liệu, xem trước số câu chia cho từng người rồi xác nhận. Thành viên chỉ thấy và sửa phần đã giao, được gửi nháp blacklist; admin mới được bật/tắt luật, xem dữ liệu tổng và xuất database. Quyền được kiểm tra ở server cho từng API.

Mã thành viên chỉ hiện một lần; server lưu PBKDF2 có salt. Cấp lại mã, đổi thông tin hoặc thu hồi quyền kết thúc các phiên của thành viên. Cookie HttpOnly/SameSite, CSRF theo session; mã truy cập và cookie đăng nhập không được ghi plaintext vào backup Git. User/nhãn/phần việc được lưu trong SQLite và nằm trong snapshot private; session không phục hồi sau restart.

Màn giám sát có tiến độ từng người, số bình luận hoàn thành tách khỏi tổng lượt lưu, thời gian trung vị trên tối đa 200 lượt gần nhất, lịch sử chi tiết và bộ lọc lượt nhanh. Ngưỡng mặc định dưới 5 giây, admin chỉnh được. Thời gian mở câu được đo bằng đồng hồ server; hoạt động là ước tính theo heartbeat, không phải bằng chứng đọc hiểu. Cảnh báo chỉ để rà soát. Có thể xác nhận nhãn đạt hoặc ghi lý do và trả lại phần việc cần sửa. Lượt sửa tạo revision mới, không tăng số bình luận hoàn thành.

Admin sửa/xóa/khôi phục bình luận ở mục Quản lý bình luận. Mẫu đang có lượt giữ phải chờ xử lý xong. Xóa là lưu trữ, không xóa lịch sử. Nếu đổi nội dung/ngữ cảnh mẫu đã có nhãn, app lưu bản cũ và tạo mẫu thay thế cần gán nhãn lại. Luật blacklist liên quan được giữ để admin kiểm tra riêng. Tài khoản xóa có thể khôi phục; lịch sử gắn UID cố định qua các lần đổi tên.

Hướng dẫn thao tác: [ACCOUNT_WORKFLOW.md](ACCOUNT_WORKFLOW.md).

## Gán nhãn liên tục

1. Mỗi người đăng nhập bằng tài khoản và mã do admin cấp. Bấm nhận bình luận tiếp theo trong phần được giao; server giữ riêng mẫu này 180 giây và gia hạn mỗi 30 giây khi còn kết nối. Người khác nhận câu khác.
2. Chọn Có / Không / Chưa kiểm tra ở từng nhóm. Một câu có thể có nhiều nhóm vi phạm. Phím `1–9` bật/tắt nhãn Có; `N` xác nhận các nhóm còn lại không vi phạm; `U` chọn Cần xem lại; `F` bật chế độ tập trung. Phím tắt không chạy khi đang gõ trong trường nhập liệu.
3. Chọn kết luận rồi Lưu & tiếp theo (`Ctrl/Cmd + Enter`). Server kiểm tra lượt giữ và phiên bản nhãn; gửi lại cùng thao tác không tạo lần duyệt trùng. Nút Bỏ qua chuyển sang mẫu khác, giữ nháp cũ.
4. Bằng chứng, hành vi và ghi chú ở phần thu gọn, không bắt buộc. Bỏ trống ghi chú sẽ lưu tóm tắt kết luận và nhãn đã chọn. Có thể hoàn tác thao tác chọn nhãn trước khi lưu.
5. Nhãn chưa kiểm tra vẫn là `null`, xuất với `label_mask=0`; không tự đổi thành Không. Thao tác xác nhận các nhóm còn lại là hành động rõ ràng của người duyệt.

Danh tính người duyệt lấy từ tài khoản đã xác thực; không nhận tên hay user_id tự khai từ trình duyệt. Giữ mẫu ngăn hai phiên cùng sửa một câu. Chỉ chạy một instance; xem giới hạn backup và lưu trữ trong tài liệu thiết lập.

## Nhập mẫu từ file

Thêm mẫu → Nhập từ file → chọn CSV, JSON, JSONL, TXT hoặc một file Parquet → Xem trước → Nhập vào hàng đợi. CSV/JSON/JSONL/TXT tối đa 5 MB mỗi file và 5.000 câu mỗi lượt; gửi từng lô 50 câu và hiển thị tiến độ. Parquet tối đa 256 MiB, một file mỗi lượt; tải theo khối 1 MiB rồi chọn cột và phạm vi tối đa 5.000 dòng/đợt. Có thể thử lại phần còn lại khi mất mạng; nội dung và ngữ cảnh trùng được bỏ qua bằng fingerprint có UNIQUE trong SQL.

- Parquet (`.parquet`, `.pq`): tải file, xem tên/kiểu cột và tổng số dòng; chọn cột bình luận. Tự gợi ý text/comment/content/body/review/sentence và một số tên phổ biến, không phân biệt hoa thường. Có thể chọn thêm cột context, source, synthetic. Đọc các cột được chọn theo batch, hỗ trợ codec của PyArrow như Snappy/Zstandard/gzip. Chọn dòng bắt đầu tính từ 0 và số dòng (1–5.000); nhập xong tự chuyển ô bắt đầu sang đợt kế tiếp, file tạm được giữ 30 phút không hoạt động. Dòng trống/nội dung trên 20.000 ký tự được đếm và bỏ qua, cột không phải văn bản báo lỗi để chọn lại. Không tự áp dụng nhãn trong file.
- Parquet chỉ admin được tải/đọc, dùng session và CSRF như import thường. File gốc được giữ tạm ngoài database, không đẩy file thô lên Git; dữ liệu đã xác nhận nhập đi qua cùng cơ chế chống trùng và backup. File tạm mất khi Render restart thì tải lại; các mẫu đã nhập vẫn được kiểm tra trùng. Mỗi row group của các cột đã chọn tối đa 128 MiB giải nén để hạn chế RAM trên gói Free.
- TXT: mỗi dòng một bình luận.
- JSON: mảng chuỗi hoặc object; cũng nhận object có `samples` hay `comments`.
- CSV/JSON/JSONL: tự nhận cột `text`, `comment`, `content`, `body`, hoặc nhập tên cột riêng. Các trường tùy chọn: `context`, `source`, `synthetic`. Source thiếu dùng tên file; synthetic thiếu dùng checkbox dữ liệu mô phỏng (mặc định không chọn). Nếu đã có synthetic thì phải là true/false.
- Nhãn sẵn trong file không tự trở thành nhãn chuẩn. Mỗi nội dung tối đa 20.000 ký tự.

## Sửa, xóa và hoàn tác dữ liệu vừa nhập

Mỗi lần thêm mẫu hoặc nhập file có mã đợt riêng; các lô 50 câu của cùng file/phạm vi Parquet được gom vào một đợt. Khi nhập xong, có nút **Hoàn tác đợt này** ngay trong hộp nhập và thanh **Hoàn tác đợt vừa thêm** trên trang.

Admin → Giám sát & chia việc → Quản lý bình luận → **Lịch sử nhập** hiển thị nguồn, thời gian, người tạo, số câu mới/trùng và số đang hiển thị. Bấm **Xem dữ liệu** để lọc đúng đợt rồi sửa/xóa từng câu. Bấm **Hoàn tác** để ẩn cả đợt nhập nhầm, hoặc **Khôi phục** để đưa về trạng thái trước khi hoàn tác.

Hoàn tác chỉ tác động những ID mới do đợt đó tạo ra; mẫu cũ bị bỏ qua do trùng không được liên kết vào đợt và không bị xóa. Lần khôi phục chỉ mở lại những mẫu do chính lần hoàn tác ấy ẩn; không mở lại các mẫu đã bị xóa riêng trước đó. Bản thay thế khi sửa nội dung mẫu đã gán nhãn cũng được liên kết vào đợt gốc để hoàn tác đầy đủ. Nhãn/lịch sử/phần việc vẫn được giữ trong SQL, không xóa cứng.

Nếu có mẫu đang được giữ hoặc luật blacklist đang bật từ đợt đó, server chặn hoàn tác để admin kiểm tra trước; toàn bộ thao tác là một transaction, không hoàn tác một nửa. Lịch sử đợt chỉ có cho dữ liệu nhập từ bản cập nhật này; dữ liệu cũ vẫn sửa/xóa/khôi phục theo từng mẫu. Các bảng `sql/005_import_history.sql` nằm trong snapshot backup như dữ liệu khác.

## SQL và backup

`sql/schema.sql`: mẫu, lịch sử nhãn, luật và lịch sử luật. `sql/003_collaboration.sql`: lượt giữ mẫu, bản nháp, phiên bản kho và biên nhận chống lưu trùng. `sql/004_accounts.sql` và migration trong accounts.py: tài khoản, session, chia việc, thời gian xử lý và kiểm tra chất lượng. Bản ghi cũ giữ nguyên, không gán tài khoản hoặc thời gian giả cho dữ liệu trước nâng cấp. Migration chạy tự động, giữ nguyên bảng và dữ liệu cũ. Ghi dùng transaction `BEGIN IMMEDIATE`; SQLite WAL cho phép đọc khi có nhiều người thao tác. Database vẫn là SQLite, không phải MySQL.

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
python -m unittest -v test_app test_render test_collaboration test_accounts test_parquet test_import_history
node --check static/app.js
node --check static/admin.js
node --check static/parquet.js
node test_ui.cjs
```

Backend kiểm tra workflow, đăng nhập và phân quyền, rollback, chống trùng, nhiều người nhận đồng thời, hết lượt, backup/restore và từ chối repo public/xung đột remote. Kiểm thử Node dùng DOM giả lập cho parser file, nháp, hoàn tác, giảm chuyển động và gửi lại sau khi server đổi phiên; không thay thế kiểm tra bố cục trên trình duyệt. test_parquet tạo file thật Snappy/Zstd/gzip, kiểm tra tải file hơn 32 MiB qua HTTP, chọn phạm vi dòng và chống trùng; không đưa dữ liệu khách hàng vào Git.
