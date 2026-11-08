# Gán nhãn, biên soạn Blacklist và thử bình luận

Đăng nhập bằng tài khoản và mã do admin cấp. Web có hai việc riêng: **Phần việc** để gán nhãn và **Biên soạn kho** để tạo các mục Blacklist. **Thử bình luận** dùng chính các mục đã phát hành để kiểm tra một câu bạn nhập.

## Thử nhanh khi chưa có dữ liệu

Admin có thể bắt đầu bằng bộ ví dụ tự tạo:

1. Vào **Biên soạn kho**, bấm **Điền bộ ví dụ demo**. Nút này chỉ điền bản đang soạn, chưa ghi database hoặc thay đổi kho đang dùng.
2. Đọc các cụm và câu ví dụ. Bấm **Kiểm tra ví dụ**, rồi **Lưu nháp & tiếp theo** nếu muốn giữ mục.
3. Mở lại mục, vào **Tên mục & kiểu nhận diện**. Chọn **Chỉ báo hiệu** hoặc **Đề xuất chặn** ở phần dành cho admin, rồi bấm **Kiểm tra & phát hành**.
4. Vào **Thử bình luận** hoặc mở đường dẫn `/demo` trên cùng web. Chọn **Kho đã phát hành**, nhập câu và bấm **Kiểm tra bình luận**.

Các nút Mời gọi, Cảnh báo, Trích dẫn và Hai vế trái ý chỉ điền câu mô phỏng. Bạn có thể sửa câu trước khi kiểm tra.

## 1. Gán nhãn và đánh dấu nguồn

Trong **Phần việc**, đọc bình luận, chọn nhãn và kết luận rồi bấm **Lưu & tiếp theo**. Một câu có thể vi phạm nhiều nhóm. `Chưa kiểm tra` được giữ riêng, không tự đổi thành `Không`.

Nếu có câu đặc trưng, tích **Đánh dấu để biên soạn** trước khi lưu. Câu đó trở thành nguồn để chọn cụm ở màn biên soạn; chưa tạo hoặc bật luật. Câu đã kiểm tra không vi phạm cũng có thể được đánh dấu để dùng làm đối chiếu.

Thành viên chỉ truy cập nguồn trong phần việc được giao. Admin xem được dữ liệu tổng. Việc lưu nhãn không cần chờ xuất lại toàn bộ kho hoặc GitHub; trạng thái Git backup được hiển thị riêng.

## 2. Tạo một mục từ câu đã gán nhãn

Vào **Biên soạn kho**:

1. Chọn câu ở danh sách **Nguồn đã gắn nhãn**. Có thể lọc nhóm, kết luận hoặc **Chỉ câu đã đánh dấu biên soạn**.
2. Bôi đen cụm trong câu rồi bấm **＋ Nội dung / đối tượng** hoặc **＋ Hành vi**. Cũng có thể nhập một cụm vào ô tương ứng và bấm `＋`.
3. Ở **Đưa vào mục**, chọn mục đã có để bổ sung hoặc tạo mục mới. Chọn hành vi như Mời gọi, Quảng bá hoặc Mua bán; tên mục được gợi ý từ nhóm và hành vi.
4. Đọc phần **Hệ thống sẽ hiểu**, bổ sung các ví dụ rồi bấm **Lưu nháp & tiếp theo**.

Ví dụ mục **Cờ bạc · Mời gọi tham gia** có nội dung `cá cược`, hành vi `vào nhóm`. Các cụm chỉ là dấu hiệu để máy xét trong ngữ cảnh; toàn câu được giữ làm ví dụ nguồn.

Để thêm câu dễ chặn nhầm, bấm **＋ Thêm ví dụ**, chọn **Ví dụ đối chiếu** và kết quả mong muốn:

| Câu minh họa | Kết quả mong muốn |
| --- | --- |
| Vào nhóm cá cược để đăng ký nhận thưởng. | Khớp đủ điều kiện — `MATCH` |
| Đừng tham gia nhóm cá cược. | Cần xét tiếp — `REVIEW` |
| Chúc bạn một ngày tốt lành. | Không khớp — `NO_MATCH` |

`MATCH` kiểm tra việc nhận diện dấu hiệu. Mục đang ở chế độ **Chỉ báo hiệu** vẫn trả kết quả chuyển xét tiếp khi chạy demo. Câu cảnh báo, phủ định hoặc trích dẫn có thể trả `REVIEW`; không phải cứ là ví dụ đối chiếu thì bắt buộc `NO_MATCH`.

## 3. Nháp, phát hành và tạm tắt

| Trạng thái/thao tác | Ý nghĩa |
| --- | --- |
| **Lưu nháp** | Giữ phần đang biên soạn, chưa đưa bản sửa vào kho demo đang dùng |
| **Kiểm tra ví dụ** | So kết quả thực tế với kết quả mong muốn của các ví dụ |
| **Kiểm tra & phát hành** | Admin kiểm tra rồi đưa phiên bản này vào kho đang dùng |
| **Tạm tắt / Lưu trữ** | Admin dừng sử dụng mục trong kho demo |
| **Đưa về nháp** | Mở lại mục để biên soạn; kiểm tra và phát hành lại khi muốn dùng |

Thành viên tạo và sửa nháp của mình; admin mới có quyền phát hành, bật chế độ chặn, tạm tắt hoặc lưu trữ. Khi bạn lưu thay đổi thành nháp của một mục đã phát hành, phiên bản đã phát hành trước đó vẫn được dùng. Xem thông báo phiên bản trong trình soạn để biết bản nào đang chạy.

Phát hành cần có ví dụ khớp và ví dụ không khớp đạt kiểm tra. Đây là kiểm tra cơ bản của mục, chưa chứng minh độ chính xác trên dữ liệu thực tế. Nếu nhãn nguồn đã đổi, bị trả sửa hoặc nguồn được lưu trữ, hệ thống cần kiểm tra lại mục liên quan trước khi dựa vào nó để chặn.

## 4. Đọc kết quả demo

Trong **Thử bình luận**, chọn đúng phạm vi:

- **Kho đã phát hành:** kiểm tra các phiên bản đang dùng. Các nháp chưa phát hành không ảnh hưởng kết quả.
- **Mục đang biên soạn:** thử bản trong trình soạn, kể cả khi chưa phát hành. Có thể mở bằng **Thử một bình luận với bản đang soạn →**.

Kết quả hiển thị câu nhập, cụm đã khớp, tên mục, lý do và phạm vi đang thử:

| Kết quả | Cách hiểu |
| --- | --- |
| `BLOCK` | Có mục đủ điều kiện trong chế độ chặn của phạm vi đang thử |
| `REVIEW` | Có dấu hiệu nhưng mục chỉ báo hiệu, hoặc ngữ cảnh còn mơ hồ; cần chuyển xét tiếp |
| `NO_MATCH` | Kho đang xét chưa khớp mục nào; chưa có nghĩa câu an toàn |

Demo hiện thực thi tầng Blacklist. fastText, ViSoBERT/PhoBERT và quy trình người duyệt nhiều tầng chưa được tích hợp. Kết quả demo chưa phải lệnh xóa hay chặn bình luận trên một hệ thống bên ngoài. Câu mới không khớp phải đi tiếp các tầng sau trong luồng kiểm duyệt đã thiết kế.

## 5. Xuất kho và giữ dữ liệu

Admin dùng **Xuất kho có phiên bản** trong phần Kho Blacklist để tải `blacklist_pack.json`, định dạng kho mới `schema_version: 2`. Muốn nhập lại file này, dùng **Nhập kho JSON** trong cùng phần Kho Blacklist. File pack mới khác `blacklist.json` của phần luật cũ; không đưa nó vào trình nhập luật cũ ở trang Nhập & xuất dữ liệu.

Các mục nhập được đưa về nháp và chế độ chỉ báo hiệu để kiểm tra trước khi phát hành. Liên kết nguồn của database khác không được giả làm nguồn đã xác minh trên database hiện tại. Với phần đang soạn chưa lưu, dùng **Tải nháp biên soạn** để giữ thêm một bản trên máy.

Đối với bản sao toàn bộ dữ liệu, vào **Nhập & xuất dữ liệu → Tải bản sao SQL**. `backup.sql` giữ database gồm nhãn, lịch sử và kho mới; file pack chỉ phục vụ chuyển kho Blacklist.

Trước khi cập nhật Render Free đang có dữ liệu, tải bản sao SQL và pack kho về máy. Repo `backup-blacklist` hiện được kiểm tra là public, trong khi ứng dụng chỉ sao lưu Git vào repo private. Chỉ dựa vào tự khôi phục khi đã chuyển repo phù hợp, cấu hình token trên Render và thấy **Git backup: đã đồng bộ**. Không gửi token hoặc mã đăng nhập trong chat.

Sau khi bản cập nhật được triển khai trên đúng service/nhánh, đăng nhập lại khi cần và mở `/demo` để thử. Tài liệu này không xác nhận dịch vụ Render đã được deploy hoặc backup đã hoạt động.

### Dành cho người tích hợp

Admin có thể nhập pack v2 qua `POST /api/studio/import` với body `{"pack": <nội dung pack>}` và session/CSRF hợp lệ. Không gửi pack v2 vào trình nhập luật cũ. API nhập luôn tạo nháp; dùng giao diện kiểm tra rồi phát hành.
