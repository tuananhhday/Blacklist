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

Hướng dẫn tài khoản: [ACCOUNT_WORKFLOW.md](ACCOUNT_WORKFLOW.md). Hướng dẫn chọn từ → thử câu → bật vào kho: [STUDIO_GUIDE.md](STUDIO_GUIDE.md).

## Gán nhãn liên tục

1. Mỗi người đăng nhập bằng tài khoản và mã do admin cấp. Bấm nhận bình luận tiếp theo trong phần được giao; server giữ riêng mẫu này 180 giây và gia hạn mỗi 30 giây khi còn kết nối. Người khác nhận câu khác.
2. Chọn Có / Không / Chưa kiểm tra ở từng nhóm. Một câu có thể có nhiều nhóm vi phạm. Phím `1–9` bật/tắt nhãn Có; `N` xác nhận các nhóm còn lại không vi phạm; `U` chọn Cần xem lại; `F` bật chế độ tập trung. Phím tắt không chạy khi đang gõ trong trường nhập liệu.
3. Chọn kết luận rồi Lưu & tiếp theo (`Ctrl/Cmd + Enter`). Server kiểm tra lượt giữ và phiên bản nhãn; gửi lại cùng thao tác không tạo lần duyệt trùng. Nút Bỏ qua chuyển sang mẫu khác, giữ nháp cũ.
4. Có thể tích **Gửi câu này sang kho Blacklist** cho câu đặc trưng hoặc câu dễ chặn nhầm, rồi **Lưu & tiếp theo**. Đây là gửi câu mẫu vào Kho Blacklist, chưa tạo hoặc bật cách chặn. Bôi đen đoạn đáng chú ý là tùy chọn và được giữ làm gợi ý.
5. Nhãn chưa kiểm tra vẫn là `null`, xuất với `label_mask=0`; không tự đổi thành Không. Thao tác xác nhận các nhóm còn lại là hành động rõ ràng của người duyệt.

Danh tính người duyệt lấy từ tài khoản đã xác thực; không nhận tên hay user_id tự khai từ trình duyệt. Giữ mẫu ngăn hai phiên cùng sửa một câu. Chỉ chạy một instance; xem giới hạn backup và lưu trữ trong tài liệu thiết lập.

## Nhập mẫu từ file

Thêm mẫu → Nhập từ file → chọn file. Với CSV/JSON/JSONL/TXT: Xem trước → Nhập vào hàng đợi. Với Parquet: file tự mở thành bảng → bấm tiêu đề cột bình luận → Nhập toàn bộ. CSV/JSON/JSONL/TXT tối đa 5 MB mỗi file và 5.000 câu mỗi lượt; gửi từng lô 50 câu và hiển thị tiến độ. Parquet tối đa 256 MiB, một file mỗi lượt; chọn cột bằng click và nhập toàn bộ file bằng một lần bấm. Không cần gõ tên cột hoặc chia số dòng thủ công. Có thể thử lại phần còn lại khi mất mạng; nội dung và ngữ cảnh trùng được bỏ qua bằng fingerprint có UNIQUE trong SQL.

- Parquet (`.parquet`, `.pq`): chọn file để tự mở bảng xem trước 8 dòng; bấm tiêu đề cột hoặc ô trong cột văn bản. App tự gợi ý cột phổ biến; có thể đổi bằng click. Nút **Nhập toàn bộ N dòng** nằm ngay phía trên bảng và giữ hiện khi cuộn hộp nhập. Hai nút **Xem cột bên trái/phải** cuộn ngang bảng; file trên 20 cột có thể chuyển tiếp sang nhóm cột khác. Bấm cột số/nhãn để xem nhưng không đổi cột bình luận đang chọn; ví dụ chọn `text`, còn `SEXUAL`, `HATE SPEECH` là cột nhãn. Nhập toàn bộ chạy một job trên server, không gửi từng nhóm dữ liệu qua trình duyệt. Context/source/synthetic là tùy chọn thu gọn, có thể bỏ qua. Không tự áp dụng nhãn trong file.
- Server đọc theo lô nhỏ, lưu SQLite theo checkpoint nhưng đây chỉ là cách xử lý bên trong: người dùng không phải chia đợt. Có thanh tiến độ, số thêm/trùng/bỏ qua và Tạm dừng/Tiếp tục. Đóng hộp hoặc đóng trình duyệt không dừng job khi server vẫn chạy; mở Nhập từ file để theo dõi tiếp. Nếu server restart mất file tạm, chọn lại đúng file/cột: app nhận diện SHA-256 và tiếp tục checkpoint đã lưu nếu database/backup còn. Tạm dừng có thể hoàn thành lô đang xử lý trước khi dừng.
- Dòng trống/nội dung trên 20.000 ký tự được đếm và bỏ qua. File gốc được giữ tạm ngoài database, không đẩy file thô lên Git. Tất cả mẫu của file thuộc một đợt nhập để hoàn tác; job phải dừng xong trước khi hoàn tác. Chỉ admin được mở/nhập file; API vẫn kiểm tra session và CSRF.
- TXT: mỗi dòng một bình luận.
- JSON: mảng chuỗi hoặc object; cũng nhận object có `samples` hay `comments`.
- CSV/JSON/JSONL: tự nhận cột `text`, `comment`, `content`, `body`, hoặc nhập tên cột riêng. Các trường tùy chọn: `context`, `source`, `synthetic`. Source thiếu dùng tên file; synthetic thiếu dùng checkbox dữ liệu mô phỏng (mặc định không chọn). Nếu đã có synthetic thì phải là true/false.
- Nhãn sẵn trong file không tự trở thành nhãn chuẩn. Mỗi nội dung tối đa 20.000 ký tự.

## Sửa, xóa và hoàn tác dữ liệu vừa nhập

Mỗi lần thêm mẫu hoặc nhập file có mã đợt riêng; các lô của cùng file Parquet được gom vào một đợt, không giới hạn 5.000 dòng cho thao tác Nhập toàn bộ. Khi nhập xong, có nút **Hoàn tác đợt này** ngay trong hộp nhập và thanh **Hoàn tác đợt vừa thêm** trên trang.

Admin → Giám sát & chia việc → Quản lý bình luận → **Lịch sử nhập** hiển thị nguồn, thời gian, người tạo, số câu mới/trùng và số đang hiển thị. Bấm **Xem dữ liệu** để lọc đúng đợt rồi sửa/xóa từng câu. Bấm **Hoàn tác** để ẩn cả đợt nhập nhầm, hoặc **Khôi phục** để đưa về trạng thái trước khi hoàn tác.

Hoàn tác chỉ tác động những ID mới do đợt đó tạo ra; mẫu cũ bị bỏ qua do trùng không được liên kết vào đợt và không bị xóa. Lần khôi phục chỉ mở lại những mẫu do chính lần hoàn tác ấy ẩn; không mở lại các mẫu đã bị xóa riêng trước đó. Bản thay thế khi sửa nội dung mẫu đã gán nhãn cũng được liên kết vào đợt gốc để hoàn tác đầy đủ. Nhãn/lịch sử/phần việc vẫn được giữ trong SQL, không xóa cứng.

Nếu có mẫu đang được giữ hoặc luật blacklist đang bật từ đợt đó, server chặn hoàn tác để admin kiểm tra trước; toàn bộ thao tác là một transaction, không hoàn tác một nửa. Lịch sử đợt chỉ có cho dữ liệu nhập từ bản cập nhật này; dữ liệu cũ vẫn sửa/xóa/khôi phục theo từng mẫu. Các bảng `sql/005_import_history.sql` nằm trong snapshot backup như dữ liệu khác.

## SQL và backup

`sql/schema.sql`: mẫu, lịch sử nhãn, luật và lịch sử luật. `sql/003_collaboration.sql`: lượt giữ mẫu, bản nháp, phiên bản kho và biên nhận chống lưu trùng. `sql/004_accounts.sql` và migration trong accounts.py: tài khoản, session, chia việc, thời gian xử lý và kiểm tra chất lượng. `sql/008_blacklist_studio.sql`: các mục mới, ví dụ, phiên bản, bản đang phát hành, đánh dấu nguồn và nháp biên soạn. `sql/007_blacklist_proposals.sql` và migration trong accounts.py (tương thích luật cũ): bằng chứng, hành vi, ảnh chụp nhãn nguồn và khóa chống gửi nháp trùng. Bản ghi cũ giữ nguyên, không gán tài khoản hoặc thời gian giả cho dữ liệu trước nâng cấp. Migration chạy tự động, giữ nguyên bảng và dữ liệu cũ. Ghi dùng transaction `BEGIN IMMEDIATE`; SQLite WAL cho phép đọc khi có nhiều người thao tác. Database vẫn là SQLite, không phải MySQL.

Nháp giữ trên thiết bị và tự gửi lên server. Lưu nhãn xác nhận ngay sau khi database commit; không chờ xuất SQL, nén snapshot hoặc GitHub. Một worker riêng gom backup, thử cách nhau khoảng 20 giây, không giữ khóa ghi trong lúc chờ mạng. Khi Git chậm/lỗi, thời gian đồng bộ có thể dài hơn. Nút Sao lưu Git ngay chủ động chờ GitHub xác nhận nhưng không khóa người khác lưu nhãn. Nếu Git chưa đồng bộ, bản nhãn vừa lưu vẫn giữ thêm trên thiết bị. Giao diện hiển thị riêng trạng thái nháp và Git. Có nút Sao lưu Git ngay và Tải nháp trên thiết bị.

Git lưu snapshot `snapshots/latest.sqlite3.gz` trong repo private riêng; khôi phục tự động nếu Render mất database. Không thể cam kết mọi ký tự đã lên Git khi mạng/server chết đột ngột; xem trạng thái đồng bộ và giữ bản tải về.

## Kho Blacklist và thử bình luận

Bản mới có đánh dấu chữ trên câu: tím là nội dung, cam là hành động, vàng là dấu tránh chặn nhầm. Bấm từ đầu và từ cuối để chọn đoạn, rồi dùng các đoạn đó làm điều kiện. Trường hợp câu và vị trí nguyên văn được lưu trong `annotation_json` (migration thêm cột, giữ dữ liệu cũ); `config.cautions` làm câu có dấu hiệu liên quan chuyển người xem, không tự cho qua. Có lọc câu theo trường hợp; [hướng dẫn đánh dấu](STUDIO_GUIDE.md).

Mở **Kho Blacklist** hoặc `/studio`. Lần đầu, bấm **Điền mẫu cờ bạc** để có sẵn từ cần tìm và ba câu mẫu. Bấm **Thử các câu mẫu**, đọc **Bạn muốn / Khi bật chặn**. Admin chọn **Bật chặn** hoặc **Chỉ nhắc người duyệt**, rồi **Kiểm tra & bật vào kho**. [Hướng dẫn dùng từng bước](STUDIO_GUIDE.md).

Ví dụ: “Vào nhóm cá cược nhận thưởng” cần **Chặn**; “Đừng tham gia nhóm cá cược” cần **Cần người xem**; “Chúc mọi người vui vẻ” cần **Cho đi tiếp** qua bước Blacklist. Web không yêu cầu người dùng chọn mã kỹ thuật hay viết ví dụ theo một cú pháp riêng. Ví dụ là bài thử, không tự huấn luyện mô hình.

Từ dữ liệu thật: chọn một câu đã gán nhãn, lấy từ về nội dung và lời mời/hành động làm dấu hiệu. Câu gốc giữ làm ví dụ có nguồn và phiên bản nhãn. Thành viên tạo/sửa nháp của mình; admin mới được bật vào kho. Kiểm tra câu mẫu mô phỏng chế độ bật chặn; demo tuân theo chế độ thực tế của từng mục. Câu phủ định/trích dẫn/pha trộn được chuyển người xem, không tự cho phép chỉ vì có chữ “đừng”.

Bản nháp sửa sau khi bật không đổi phiên bản đang chạy. Tắt/lưu trữ dừng dùng mục; khôi phục về nháp cần kiểm tra và bật lại. Nhãn nguồn bị sửa/trả lại hoặc bình luận bị lưu trữ khiến mục liên quan chuyển người xem để kiểm tra lại. Kiểm tra vài câu mẫu chưa chứng minh độ chính xác trên dữ liệu thực tế.

Mở **Thử bình luận** hoặc `/demo` để thử kho SQL dùng chung; có thể chọn thử riêng bản nháp. `/sandbox/` là phòng thử độc lập dùng kho mẫu hoặc JSON nhập vào, lưu cục bộ trong trình duyệt. fastText, ViSoBERT/PhoBERT và hệ thống chặn bình luận bên ngoài chưa được tích hợp. **Cho đi tiếp** chỉ nghĩa là qua bước Blacklist để tới các bước sau.

Admin nhập/xuất kho bằng `blacklist_pack.json`, `schema_version: 2`. File giữ bản đang sửa và các phiên bản đang chạy. Nhập lại tạo nháp/chỉ nhắc người duyệt, bỏ liên kết nguồn ngoại lai; admin cần kiểm tra và bật lại. Không nhập pack v2 qua trình nhập luật cũ.

Các API luật cũ vẫn giữ để dữ liệu trước nâng cấp không mất. Tệp cũ `blacklist.json` và `blacklist_drafts.json` là định dạng của engine trước, action REVIEW; chúng không thay cho pack v2.

- `blacklist_pack.json`: kho mới có phiên bản, dùng chuyển dữ liệu biên soạn/kiểm tra.
- `training_data.jsonl`: mẫu đã kết luận, nhãn và label_mask; chưa chia train/test.
- `backup.sql`: toàn bộ SQLite gồm tài khoản, nguồn, nhãn, các kho cũ/mới, lịch sử và nháp. Không upload SQL qua web.

Phục hồi SQL thủ công: dừng app, giữ bản database cũ, tạo SQLite mới và chạy nội dung SQL từ bản sao tin cậy, kiểm tra rồi thay file. Không chạy SQL vào kho đang có dữ liệu. Không xóa dữ liệu bản cũ trước khi xác nhận bản phục hồi.

## Kiểm tra

```sh
python -m unittest -v test_app test_render test_collaboration test_accounts test_parquet test_native_parquet test_import_history test_blacklist_workflow test_fast_save test_context_rules test_studio_http test_marking
node --check static/app.js
node --check static/admin.js
node --check static/parquet.js
node --check static/studio.js
node test_ui.cjs
node test_studio_ui.cjs
node test_sandbox.cjs
node test_sandbox_ui.cjs
```

Backend kiểm tra workflow, đăng nhập và phân quyền, rollback, chống trùng, nhiều người nhận đồng thời, hết lượt, backup/restore và từ chối repo public/xung đột remote. Kiểm thử Node dùng DOM giả lập cho parser file, nháp, hoàn tác, giảm chuyển động và gửi lại sau khi server đổi phiên; không thay thế kiểm tra bố cục trên trình duyệt. test_parquet tạo file thật Snappy/Zstd/gzip, kiểm tra tải file hơn 32 MiB qua HTTP, chọn phạm vi dòng và chống trùng; không đưa dữ liệu khách hàng vào Git.

Nhận câu trả kèm nội dung trong cùng response; sau khi lưu không chờ tải lại toàn bộ workspace mới hiện câu tiếp theo. Danh sách bình luận dùng phân trang 100 mẫu/lần và số đếm tổng riêng, để không tải cả kho lớn vào RAM/trình duyệt. Nhận mẫu tiếp theo vẫn lấy đúng mẫu được server giao dù mẫu nằm ngoài trang hiện tại. Các file xuất chỉ được tạo khi tải, mỗi lần tạo đúng file yêu cầu từ một snapshot đọc nhất quán rồi gửi theo stream; không xuất lại cả kho sau từng nhãn hoặc khi khởi động. Xuất SQL/training chạy streaming; job Parquet không tái tạo toàn bộ file xuất sau mỗi lô. Backup snapshot được nén/giải nén theo stream; Git vẫn có giới hạn snapshot nén 20 MB và hiển thị trạng thái khi chưa đồng bộ.
