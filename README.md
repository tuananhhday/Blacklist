# Blacklist Studio — Render

Web tiếng Việt để nhập thông tin, gán nhãn thủ công, nhập và xuất blacklist. Database bắt đầu trống. Không cần Python trên máy của người dùng: Python chạy trên Render.

## Triển khai
1. Giải nén. Đưa NỘI DUNG thư mục này lên root một repository GitHub riêng (app.py và render.yaml ở root).
2. Render → New → Blueprint → kết nối repository đó. Render đọc render.yaml.
3. Đặt STUDIO_PASSWORD là mật khẩu mạnh, riêng cho công cụ này. Username mặc định admin; có thể đổi STUDIO_USERNAME.
4. Xem chi phí gói web trả phí và disk trong Render rồi triển khai. Không dùng Free với SQLite để lưu lâu dài.
5. Mở URL HTTPS Render cấp. Trình duyệt hỏi tên và mật khẩu; nhập admin và STUDIO_PASSWORD. Điền tên người thao tác ở thanh trái.

Nếu tạo Web Service thủ công: runtime Python; build `python -m compileall -q app.py`; start `python app.py`; health `/health`; đặt biến môi trường và disk giống render.yaml. Root Directory để trống nếu app.py ở root. Chỉ một instance, một tiến trình. Không dùng Static Site.

## Thao tác
- “Thêm mẫu”: nhập câu, ngữ cảnh, nguồn, đánh dấu tự viết hay thực tế; lưu vào kho.
- Đọc mẫu, chọn 9 nhãn 0/1/chưa kiểm tra, bằng chứng, hành vi, kết luận và lý do; lưu. Nhãn chưa kiểm tra không thành 0.
- Tạo blacklist từ câu vi phạm đã lưu hoặc tạo mục thủ công. Nháp không nằm trong blacklist đang bật.
- “Dữ liệu & xuất file” → Nhập blacklist có sẵn → chọn file → Xem trước → Nhập vào kho. JSON xuất từ bản local cũ dùng được. Mục trùng theo loại + nhóm + điều kiện được bỏ qua. Tất cả nhập thành nháp, không ghi đè mục cũ hay bật theo file.
- JSON: object có rules hoặc mảng luật, mỗi luật gồm name, category, kind, config, tests (tùy chọn), reason (tùy chọn). Kiểu exact/url/domain dùng config.pattern; combined dùng config.topic/behavior/context là danh sách chuỗi. Category dùng mã trong sql/002_categories.sql.
- CSV: name,category,kind,pattern,reason; chỉ dùng exact/url/domain. Xem examples/blacklist_import.csv. TXT: mỗi dòng một NGUYÊN CÂU; chọn nhóm mặc định trước. Từ đơn trong TXT cũng chỉ khớp toàn câu, không trở thành luật chứa từ.
- File nhập tối đa 1.000 mục / khoảng 1,9 MB. Không nhập SQL qua web.
- Mở Kho blacklist, chọn luật, thêm ví dụ cần bắt và ví dụ đối chiếu, chạy thử rồi chọn Đang bật và lưu. Luật chỉ chuyển duyệt, không tự chặn.
- “Tải blacklist”: chỉ luật đang bật; “Tải toàn bộ luật”: cả nháp/đã tắt. Có thể tải lại để chuyển kho giữa hai bản.
- Tải training_data.jsonl và backup.sql để sao lưu. SQL là SQLite, không phải MySQL. Hướng dẫn phục hồi bên dưới.

## Lưu trữ và sao lưu
SQLite tại /var/data/database/studio.sqlite3; file xuất tại /var/data/exports. Disk phải gắn ở /var/data. Filesystem mặc định của Render mất thay đổi khi restart/redeploy. Persistent disk là tài nguyên trả phí. Không tắt/xóa disk khi đổi bản deploy. Chỉ dữ liệu bên dưới mount path được giữ. Xuất backup.sql định kỳ về máy; xóa service/disk có thể mất dữ liệu.

Phục hồi backup.sql: dừng server, giữ bản sao database cũ, dùng Python/SQLite tạo database MỚI và executescript nội dung SQL, kiểm tra rồi thay studio.sqlite3. Không chạy vào database đang có dữ liệu. Không có giao diện upload SQL vì SQL thực thi có thể sửa/xóa toàn kho.

## Phạm vi
Công cụ nhóm nhỏ dùng một tài khoản chung qua HTTPS Basic Auth. Tên người duyệt là tự khai, chưa phải danh tính đã xác thực riêng. Không có phân quyền theo người, SSO hay xử lý lượng truy cập lớn. Health không trả dữ liệu; mọi trang, API và file xuất còn lại cần mật khẩu khi cấu hình. Render từ chối khởi động nếu thiếu mật khẩu. Không tải Windows portable lên Render.

## Kiểm tra
`python -m unittest -v test_app.py test_render.py`

Tài liệu Render: https://render.com/docs/disks và https://render.com/docs/blueprint-spec
