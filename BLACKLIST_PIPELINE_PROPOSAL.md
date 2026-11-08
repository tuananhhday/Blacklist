# Phương án đề xuất: biên soạn Blacklist cho luồng kiểm duyệt nhiều tầng

Luồng đã xác nhận với người dùng: **Blacklist → fastText → ViSoBERT/PhoBERT → kiểm tra chặn nhầm → người duyệt → sửa nhãn và cập nhật kho**. “ViPhoBERT” được người dùng đính chính là **ViSoBERT**.

Đây là đề xuất thiết kế, chưa triển khai các tầng mô hình hoặc chặn tự động. Chưa có số đo chất lượng hay độ trễ trên dữ liệu người dùng để khẳng định một checkpoint/ngưỡng là tối ưu thực nghiệm. Hai tài liệu nghiên cứu trước về ngữ cảnh và cách tính điểm là tài liệu tham khảo; phương án trong tài liệu này được ưu tiên vì bám sát luồng đã được xác nhận.

## 1. Quyết định chính

**Blacklist là kho dấu hiệu và luật có điều kiện được biên soạn, phục vụ xử lý nhanh các dạng đã biết. Kho ví dụ và dữ liệu gán nhãn cung cấp bằng chứng để kiểm định luật và huấn luyện các tầng sau.**

Không đưa một bộ cosine + mô hình ngữ cảnh lớn nữa vào đầu pipeline khi phía sau đã có fastText và BERT. Cosine có thể hỗ trợ tìm mẫu gần, phát hiện trùng và gợi ý gom mục trong công cụ biên soạn, xử lý theo lô khi cần.

Luật chỉ nhắc đến một chủ đề như “cá cược” thường phù hợp để báo hiệu. Luật có điều kiện đặc hiệu, đã qua kiểm định và được admin bật mới có quyền đề xuất chặn nhanh. Câu phụ thuộc ngữ cảnh khó tiếp tục đi xuống các mô hình.

## 2. Người dùng sẽ thao tác như thế nào?

### Màn Gán nhãn

- Đọc câu và chọn nhãn như hiện tại; câu hỏi ghi rõ “Có vi phạm về …?” để phân biệt với chỉ nhắc đến chủ đề.
- Lưu & tiếp theo; không phải điền mẫu luật, tên luật hoặc điểm cosine.
- Có nút sao **Đánh dấu để biên soạn** nếu thấy một dấu hiệu đáng giữ. Đây là dấu đánh dấu nguồn; thao tác này chưa tạo luật trong kho đang chạy.
- Bình luận được lưu trong kho dữ liệu đầy đủ dù không được đánh dấu. Người quản lý vẫn lọc dữ liệu đã duyệt để biên soạn sau.

### Màn Biên soạn Blacklist

Một câu mỗi lượt, với nhóm đã được lấy từ nhãn nguồn. Ba bước chính:

1. **Chọn dấu hiệu:** bôi đen hoặc chọn từ trong câu, bấm **Nội dung/đối tượng** hoặc **Hành vi**. Không yêu cầu nhập lại câu.
2. **Gom vào mục:** ứng dụng gợi ý mục liên quan đã có; chọn **Thêm vào mục này**. Nếu chưa có, chọn một hành vi ngắn, như Mời gọi/Mua bán/Đe dọa, để tạo mục mới. Tên tự sinh từ nhóm và hành vi; có thể sửa sau.
3. **Lưu & tiếp theo:** câu nguồn tự gắn vào phần ví dụ. Người biên soạn có thể bấm **Thêm ví dụ đối chiếu** từ danh sách các câu đã kiểm tra không vi phạm cùng nhóm. Chưa có đối chiếu vẫn được lưu nháp, nhưng chưa được bật chế độ chặn.

Khi chỉ có một cụm đặc hiệu hoặc một thực thể như URL/domain, dùng mẫu biên soạn tương ứng. Với các câu chỉ có giá trị làm ví dụ cho mô hình, cho **Giữ làm ví dụ** mà không ép tạo luật từ ngữ.

Ví dụ màn hình đề xuất:

```text
Nguồn #128 · Cờ bạc · Nhãn đã được duyệt
“Vào nhóm cá cược của tôi, đăng ký nhận thưởng ngay.”

Nội dung/đối tượng: [cá cược ×]
Hành vi:           [vào nhóm ×] [đăng ký nhận thưởng ×]

Đưa vào mục:       [Cờ bạc · Mời gọi tham gia]
                   Đã có mục này → bổ sung dấu hiệu và ví dụ

Hệ thống sẽ hiểu:
“Gặp dấu hiệu cá cược kèm lời mời tham gia trong phạm vi
đã cấu hình. Câu nghi cảnh báo/trích dẫn chuyển tầng sau.”

[Lưu & tiếp theo]  [Bỏ qua]  [Hoàn tác thao tác vừa chọn]
```

Người biên soạn dùng cụm chọn trên giao diện. Vai trò cụm, điều kiện và định dạng máy đọc được do hệ thống sinh theo mẫu đã định nghĩa; không yêu cầu viết JSON, SQL, regex, ngưỡng hay token gap.

### Màn Kho Blacklist

Nhóm theo hành vi, không tạo một mục độc lập cho mỗi bình luận:

```text
Cờ bạc
  Mời gọi tham gia
    Dấu hiệu: cá cược, cá độ, ...
    Hành vi: vào nhóm, đăng ký nhận thưởng, ...
    Ví dụ vi phạm và ví dụ đối chiếu
    Chế độ: Chỉ báo hiệu / Đề xuất chặn nhanh / Tạm tắt
    Phiên bản, người biên soạn, người duyệt, kết quả kiểm tra
```

Giao diện thường chỉ hiện nội dung, chế độ và các ví dụ. Cấu hình triển khai và số liệu nằm trong phần admin mở khi cần.

### Màn Chặn nhầm

Hiển thị câu gốc, ngữ cảnh, dấu hiệu đã khớp, mục gây đề xuất chặn và lý do hệ thống. Người duyệt chọn **Chặn đúng / Chặn nhầm / Chưa đủ thông tin**, sửa các nhóm cần sửa, rồi lưu. Phần còn lại tự được liên kết về nguồn.

Chặn nhầm từ một mục → gợi ý **Bổ sung làm đối chiếu cho mục đó**. Bỏ sót một dạng lặp rõ ràng → gợi ý **Biên soạn dấu hiệu mới**. Những ca khó chưa có luật rõ thì đi vào dữ liệu huấn luyện, không ép biến thành từ khóa.

## 3. Một mục trong kho chứa gì?

Ví dụ mục **Cờ bạc · Mời gọi tham gia**:

| Phần | Nội dung |
| --- | --- |
| Nhóm | Cờ bạc |
| Hành vi cần phát hiện | Mời gọi tham gia |
| Dấu hiệu nội dung/đối tượng | Những cụm đã biên soạn, ví dụ cá cược, cá độ |
| Dấu hiệu hành vi | Những lời mời đã biên soạn, ví dụ vào nhóm, đăng ký nhận thưởng |
| Điều kiện | Theo mẫu luật có phạm vi vế/câu và quan hệ phù hợp; không chỉ hai từ xuất hiện ở bất kỳ đâu |
| Ngữ cảnh chưa quyết định nhanh | Có dấu hiệu cảnh báo, phủ định, trích dẫn, pha trộn hoặc thiếu thông tin |
| Ví dụ vi phạm | Các câu đã duyệt cho thấy hành vi cần nhận diện |
| Ví dụ đối chiếu | Các câu dễ khớp cụm nhưng không vi phạm quy định đang xét |
| Chế độ vận hành | Chỉ báo hiệu / Đề xuất chặn nhanh / Tạm tắt |
| Quản lý | Người tạo, nguồn/phiên bản nhãn, lịch sử sửa, bản phát hành |

Một mục có thể có nhiều luật con và nhiều ví dụ. Không gộp các cách dùng khác ý định chỉ vì có cùng từ hoặc cosine cao. Mẫu đối chiếu chỉ có phạm vi quy tắc/nhóm liên quan, không phải whitelist cho toàn bình luận.

## 4. Blacklist xử lý thế nào ở tầng đầu?

### Đối sánh nhanh

- Xây chỉ mục cụm từ/biến thể đã duyệt, có thể dùng Aho–Corasick để tìm nhiều cụm trong một lần quét.
- Chuẩn hóa có phiên bản; giữ nguyên văn, dấu, phủ định, trích dẫn, ranh giới từ và ánh xạ vị trí bằng chứng.
- Xét điều kiện của luật trên đoạn liên quan. Cùng xuất hiện hai cụm chưa chứng minh chúng có quan hệ hoặc người viết đang kêu gọi.
- Dấu hiệu chỉ khớp sau phép chuẩn hóa mạnh/lách chữ, ngữ cảnh mâu thuẫn hoặc thiếu thông tin → báo hiệu/chuyển tầng sau. Không tự coi bỏ dấu và xóa dấu câu là đủ chắc để chặn.
- Trường hợp có thể là phủ định/trích dẫn có thể dùng dấu hiệu rẻ để nhận ra sự mơ hồ rồi chuyển mô hình; Blacklist không cần cố giải toàn bộ bài toán ngữ nghĩa.

### Đầu ra của tầng Blacklist

| Đầu ra nội bộ | Ý nghĩa |
| --- | --- |
| `BLOCK_CANDIDATE` | Luật đã phát hành ở chế độ chặn khớp đủ điều kiện; cần qua bộ kiểm tra chặn nhầm trước quyết định cuối |
| `FLAG_CONTINUE` | Có tín hiệu nhưng chưa đủ điều kiện; truyền các cụm và lý do sang fastText/BERT |
| `NO_MATCH_CONTINUE` | Không khớp luật; tiếp tục fastText, không suy ra câu an toàn |
| `STAGE_ERROR` | Tầng không đánh giá được; ghi lỗi và định tuyến kiểm tra tiếp, không ngụy trang thành kết quả an toàn |

Câu cảnh báo không phải ngoại lệ cho qua toàn bộ hệ thống. Ví dụ “Đừng tham gia cá cược” được chuyển xét tiếp theo quy định; “Đừng bỏ lỡ kèo ngon” cũng được xét tiếp nếu bộ luật chưa phân biệt chắc. Trường hợp rõ đã qua kiểm định mới đi nhánh đề xuất chặn nhanh.

## 5. Ghép đúng với fastText, ViSoBERT, PhoBERT

| Tầng | Vai trò đề xuất | Kết quả chuyển tiếp |
| --- | --- | --- |
| Blacklist | Các dạng đã biết, đối sánh rẻ, giải thích được bằng dấu hiệu | Đề xuất chặn hoặc chuyển tiếp kèm bằng chứng |
| fastText | Phân loại nhẹ dựa trên dữ liệu đã duyệt, giảm số ca phải chạy mô hình nặng khi chất lượng cho phép | Quyết định tạm theo từng nhóm hoặc chuyển xét sâu |
| ViSoBERT | Ứng viên mô hình chính để thử nghiệm cho bình luận mạng xã hội; cần fine-tune nhiệm vụ cụ thể | Điểm và nhóm nghi vi phạm theo ngữ cảnh |
| PhoBERT | Mô hình đối chiếu hoặc xử lý ca ViSoBERT chưa chắc, nếu đánh giá chứng minh có lợi | Bổ sung thông tin cho ca khó; bất đồng chuyển người duyệt |
| Kiểm tra chặn nhầm | Kiểm tra bằng chứng, phạm vi quy định, ngữ cảnh, bất đồng và điều kiện ra quyết định | BLOCK / ALLOW trong phạm vi đã xét / NEED_MORE / HUMAN_REVIEW |
| Người duyệt | Kết luận các ca còn thiếu hoặc mâu thuẫn, sửa nhãn và ghi lý do | Nhãn chuẩn và phản hồi để sửa dữ liệu/luật |

Khuyến nghị thử ViSoBERT như ứng viên chính vì mô hình được nghiên cứu cho tiếng Việt mạng xã hội. Không kết luận nó tốt hơn PhoBERT cho 9 nhóm hiện tại khi chưa thử. Không mặc định chạy cả hai BERT cho mọi câu; đánh giá phương án dùng PhoBERT cho ca khó để tránh tăng chi phí mà không tăng chất lượng.

Checkpoint nền như `uitnlp/visobert` và `vinai/phobert-base` chưa tự trở thành bộ kiểm duyệt có 9 nhãn chỉ bằng cách tải về. Cần đầu phân loại/fine-tuning phù hợp, dữ liệu nhãn thống nhất và ngưỡng đã được kiểm định. PhoBERT yêu cầu tiền xử lý phân đoạn từ theo hướng dẫn; không mặc định dùng chung chuỗi xử lý của ViSoBERT.

### Định tuyến để vừa nhanh vừa giữ tầng kiểm tra chặn nhầm

Luồng nghiệp vụ vẫn theo thứ tự người dùng đưa. Có nhánh ngắn cho ca rõ khi đã đo chất lượng:

1. Blacklist đề xuất chặn rõ → bộ kiểm tra chặn nhầm. Nếu đủ điều kiện, giữ khỏi hiển thị mà có thể bỏ qua các mô hình nặng.
2. Blacklist chỉ báo hiệu/không khớp → fastText. Ca chưa chắc, mâu thuẫn hoặc chưa đủ các nhóm bắt buộc → ViSoBERT; PhoBERT xử lý bổ sung khi cấu hình yêu cầu.
3. Mọi đề xuất chặn, dù bắt đầu ở tầng nào, đều qua kiểm tra chặn nhầm trước khi chốt. Tầng này nhận bằng chứng từ các tầng đã chạy, không chỉ một số phần trăm.
4. Nếu nhánh ngắn cần thêm ngữ cảnh, tiếp tục tầng chưa chạy; nếu đã dùng hết các tầng vẫn chưa đủ thì chuyển người duyệt. Lưu các tầng đã chạy để tránh vòng lặp gọi lại cùng mô hình.
5. Khi một nghi vấn của nhóm A được gỡ, còn nhóm khác chưa xét thì tiếp tục đánh giá; không tự cho phép cả câu. Khi đã xác nhận một nhóm cần chặn, có thể chặn bình luận nhưng các nhóm chưa xét vẫn giữ trạng thái chưa xét.

Ngưỡng cắt sớm và ngưỡng chặn phải đo trên **toàn pipeline** và dữ liệu còn lại sau tầng trước. Không cộng hoặc nhân xác suất các mô hình như những bằng chứng độc lập; không lấy đa số phiếu làm bằng chứng đủ chắc vì các mô hình có thể cùng mắc một lỗi.

## 6. Vòng phản hồi phải đi về đúng nơi

Luồng cập nhật đề xuất:

```text
Người duyệt sửa/xác nhận nhãn
    → kho dữ liệu đã duyệt để huấn luyện/đánh giá
    → nếu có dấu hiệu tái sử dụng: mục chờ biên soạn
    → nếu chặn nhầm: ví dụ đối chiếu gắn đúng mục gây lỗi
    → admin kiểm tra thay đổi và phát hành bản Blacklist mới
```

Không phải mọi bình luận vừa xác nhận vi phạm đều tạo luật mới. Dạng lặp đặc hiệu có thể trở thành luật; ca phụ thuộc ngữ cảnh trở thành dữ liệu cho fastText/BERT và mẫu kiểm tra.

Không tự thêm từ “đừng”, “không”, “cảnh báo” vào một whitelist toàn cục để chữa chặn nhầm. Cần sửa điều kiện của đúng mục hoặc chuyển mục về chỉ báo hiệu. Câu bị chặn cần giữ nguyên văn, nguồn quyết định và phiên bản để có thể khôi phục khi bắt nhầm.

## 7. Chuẩn dữ liệu cho cả chuỗi

Một dữ liệu gốc, nhiều định dạng xuất tự động. Người dùng không điền schema mô hình trên giao diện.

Các trường chính: ID bình luận, nguyên văn, ngữ cảnh/ID câu cha khi có, 9 nhãn 0/1/null, label_mask, phiên bản nhãn và quy định, các đoạn bằng chứng theo nhóm, người duyệt, trạng thái kiểm tra và nguồn thu thập.

`1 = đã xác nhận vi phạm`, `0 = đã kiểm tra không vi phạm`, `null = chưa đủ thông tin/chưa kiểm tra`. Không biến null thành 0; không tự coi nhãn chủ đề của một dataset khác là nhãn vi phạm.

- **Xuất luật tầng đầu:** JSON có schema/version, nhóm, điều kiện, chế độ, bằng chứng và thông tin phát hành; khác dữ liệu train.
- **Xuất train fastText:** với nhãn còn thiếu, giai đoạn đầu dùng một bài toán nhị phân theo nhóm và chỉ lấy câu có mask=1 cho nhóm đó. Có thể dùng multi-label OVA với tập đã có đủ nhãn, nhưng không nạp dữ liệu thiếu nhãn như thể mọi nhãn vắng là âm tính.
- **Xuất train ViSoBERT/PhoBERT:** JSONL giữ nhãn/mask và nguyên văn/ngữ cảnh; áp dụng bộ tiền xử lý phù hợp từng model. Các mục ngữ cảnh/hành vi là nhãn phụ khi đã được duyệt và có định nghĩa nhất quán.
- **Xuất kiểm tra chặn nhầm:** các câu đối chiếu, phủ định, trích dẫn, câu hỗn hợp và các quyết định đã bị người duyệt sửa.

Nhãn mô hình gợi ý phải lưu tách khỏi nhãn người đã duyệt. Bộ test độc lập phải giữ riêng; các câu gần trùng/chiến dịch cần nằm cùng nhóm chia tập để tránh rò rỉ. Kiểm thử hồi quy các ví dụ đã thấy là cần thiết nhưng không thay thế phép đo trên dữ liệu chưa dùng để biên soạn.

## 8. SQL mở rộng dự kiến

Giữ dữ liệu gốc và lịch sử hiện tại. Không đồng nhất một dòng reviews với một dòng luật.

| Thành phần | Vai trò |
| --- | --- |
| `reviews` và chi tiết bằng chứng theo nhóm | Nhãn và lịch sử sửa; bằng chứng có thể có nhiều đoạn |
| `blacklist_items` | Mục biên soạn theo nhóm/hành vi, một mục có nhiều ví dụ và luật con |
| `blacklist_rule_versions` | Điều kiện thực thi và chế độ theo từng phiên bản, bản nháp tách bản đang chạy |
| `blacklist_terms` | Các cụm/biến thể và vai trò trong một phiên bản luật |
| `blacklist_examples` | Ví dụ vi phạm, đối chiếu hoặc chưa rõ, liên kết nguồn và phiên bản nhãn |
| `moderation_events` | Bằng chứng từng tầng, mô hình/điểm, trạng thái tạm và quyết định cuối |
| `review_feedback` | Kết luận sửa, nguyên nhân chặn nhầm/bỏ sót và người duyệt |
| `blacklist_releases` | Danh sách phiên bản luật được phát hành cùng nhau, hash, cấu hình chuẩn hóa, kết quả đánh giá và bản trước để quay lại |

Đây là thiết kế dữ liệu chưa được migration. Dấu đánh dấu nguồn hoặc mẫu đối chiếu cần có bảng riêng phù hợp, không tiếp tục dùng `rules(kind=exact)` để giả lập mọi loại bản ghi.

## 9. Điều kiện để dùng nhanh và ổn định

- Chỉ có tác vụ lưu nhỏ trong nút Lưu & tiếp theo; xác nhận khi database commit. Backup, xuất kho, biên dịch chỉ mục và train mô hình chạy riêng.
- Nhiều người lấy câu biên soạn phải có lượt giữ riêng, tự lưu nháp và kiểm tra phiên bản khi cập nhật cùng một mục; không làm mất phần chọn nếu người khác vừa thêm ví dụ.
- Gợi ý dùng mục có sẵn trước khi tạo mới. Chuẩn hóa và khóa chống trùng theo nguồn/phiên bản/đoạn/mục; không gộp các ý định trái nhau.
- Thao tác chính có hoàn tác; xóa là lưu trữ; khôi phục giữ đúng lịch sử. Phát hành một mục là thao tác riêng của admin.
- Có bản phát hành bất biến để engine nhận biết chính xác luật đang dùng; thay chỉ mục khi sẵn sàng, giữ bản trước để quay lại. Sửa nhãn nguồn cần đánh dấu lại các mục phụ thuộc.
- Render Free phục vụ ứng dụng biên soạn; không mặc định đặt cả fastText, ViSoBERT, PhoBERT và tiến trình backup trong cùng instance đó. Nơi chạy suy luận cần được đo/tách riêng. Công cụ biên soạn vẫn dùng được khi chưa có mô hình AI gợi ý.

## 10. Thứ tự triển khai được đề xuất

1. **Làm đúng luồng biên soạn:** đánh dấu nguồn, chọn cụm, gom mục, ví dụ đối chiếu, màn kiểm tra diễn giải bằng tiếng Việt. Giữ phần gán nhãn nhẹ.
2. **Sinh luật và xuất được kho:** mẫu điều kiện có phạm vi, JSON có phiên bản, chạy thử trên ví dụ và dữ liệu độc lập. Mặc định chỉ báo hiệu.
3. **Ghép tầng Blacklist:** chạy theo dõi kết quả, đo khớp đúng/khớp nhầm/bỏ sót và độ trễ; cho admin bật chặn nhanh những mục đạt yêu cầu.
4. **Ghép mô hình và vòng phản hồi:** xuất đúng dữ liệu fastText/ViSoBERT/PhoBERT, kiểm tra chặn nhầm, tiếp nhận sửa nhãn và phát hành lại kho.

Mỗi mục không cần nhiều biểu mẫu. Tuy nhiên, đủ một ví dụ vi phạm và một ví dụ đối chiếu chỉ giúp kiểm tra biên soạn cơ bản; nó chưa chứng minh chất lượng chặn thực tế. Ngưỡng, chế độ cắt sớm và quyền chặn phải dựa trên phép đo theo từng nhóm và cả pipeline.

## Nguồn nghiên cứu chính

- [fastText: Text classification](https://fasttext.cc/docs/en/supervised-tutorial.html): n-gram, phân loại nhiều nhãn và OVA. Cách bảo toàn mask và xuất từng nhóm là đề xuất để phù hợp dữ liệu hiện có.
- [ViSoBERT, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.315/): mô hình được nghiên cứu cho tiếng Việt mạng xã hội; không phải số đo cho dự án này.
- [ViSoBERT model card](https://huggingface.co/uitnlp/visobert): checkpoint nền; cần nhiệm vụ/đầu phân loại phù hợp.
- [VinAIResearch: PhoBERT](https://github.com/VinAIResearch/PhoBERT): checkpoint và yêu cầu phân đoạn từ.
- [pyahocorasick](https://pyahocorasick.readthedocs.io/en/latest/): tìm nhiều cụm trong một lần quét; thư viện đối sánh không tự hiểu phủ định hay ý định.
- [Prodigy: Text classification](https://prodi.gy/docs/text-classification): chọn ví dụ bằng pattern và thao tác xác nhận/từ chối làm cơ sở tham khảo UX; không yêu cầu đổi công cụ hoặc mua Prodigy.
- [HateCheck, ACL 2021](https://aclanthology.org/2021.acl-long.4/): kiểm thử theo chức năng cho các điểm dễ nhầm; không chứng minh chất lượng kiểm duyệt tiếng Việt của dự án.
- [scikit-learn: Tuning decision thresholds](https://scikit-learn.org/stable/modules/classification_threshold.html): kiểm định ngưỡng riêng với dữ liệu học mô hình.

Luồng tác nghiệp, các màn hình, SQL, chế độ luật và định tuyến trong tài liệu là đề xuất thiết kế cho yêu cầu đã xác nhận. Chưa triển khai hoặc benchmark toàn pipeline.
