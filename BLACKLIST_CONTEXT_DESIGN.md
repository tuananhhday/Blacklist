# Thiết kế kho Blacklist theo hành vi và ngữ cảnh

**Cập nhật yêu cầu:** người dùng đã xác nhận luồng Blacklist → fastText → ViSoBERT/PhoBERT → kiểm tra chặn nhầm → người duyệt. Ưu tiên [phương án biên soạn kho và tích hợp pipeline](BLACKLIST_PIPELINE_PROPOSAL.md). Tài liệu dưới đây giữ làm nghiên cứu nền; không cần đặt toàn bộ bộ phân loại cosine/ngữ cảnh vào tầng Blacklist đầu tiên.

Đây là đề xuất kiến trúc dựa trên mã hiện tại và tài liệu nghiên cứu. Chưa bổ sung mô hình embedding hay bộ phân loại vào ứng dụng, chưa đo chất lượng mô hình trên dữ liệu người dùng. Các câu minh họa bên dưới là dữ liệu tự tạo. PR tối ưu tốc độ lưu vẫn là một thay đổi riêng.

## 1. Định nghĩa đúng nhãn

Mục tiêu là nhận diện **vi phạm một quy định trong ngữ cảnh**, không chỉ nhận diện từ thuộc chủ đề. Ví dụ dưới đây giả định quy định cần bắt lời mời/quảng bá cờ bạc, còn cảnh báo hoặc thảo luận trung lập không vi phạm chỉ vì nhắc đến cờ bạc.

| Bình luận | Chủ đề | Hành vi trong câu | Kết luận mong muốn |
| --- | --- | --- | --- |
| Vào nhóm cá cược, đăng ký nhận thưởng. | Cờ bạc | Mời gọi/quảng bá | Vi phạm |
| Đừng tham gia nhóm cá cược, dễ mất tiền. | Cờ bạc | Cảnh báo/phản đối | Không vi phạm quy định mời gọi |
| Đừng bỏ lỡ kèo ngon, tham gia nhóm cá độ ngay. | Cờ bạc | Mời gọi; từ “đừng” phủ định việc bỏ lỡ | Vi phạm |
| Không cần vốn, vào nhóm cá độ nhận thưởng. | Cờ bạc | Mời gọi; từ “không” nói về điều kiện vốn | Vi phạm |
| Nó nhắn “vào nhóm cá cược”, tôi đã báo cáo rồi. | Cờ bạc | Trích dẫn để tố cáo | Không tự coi là lời mời của người viết |
| Cờ bạc là gì? | Cờ bạc | Hỏi đáp | Không vi phạm chỉ vì đề cập chủ đề |
| Tôi phản đối cá cược. Nhưng ai muốn chơi thì nhắn tôi. | Cờ bạc | Vừa phản đối vừa mời gọi | Có dấu hiệu vi phạm ở vế sau; xét quy định hoặc chuyển duyệt |
| Vào nhóm này nhé. | Chưa đủ thông tin | Lời mời thiếu đối tượng | Cần ngữ cảnh trước đó |

Giao diện gán nhãn nên ghi rõ “Có vi phạm về cờ bạc?” để tránh hiểu nhãn là “Có nói tới cờ bạc?”. Giữ ý nghĩa `1 = đã xác nhận vi phạm`, `0 = đã kiểm tra không vi phạm`, `null = chưa kiểm tra/chưa đủ kết luận`. Không tự suy ra ý nghĩa nhãn trong file Parquet nếu chưa có định nghĩa của bộ dữ liệu đó.

Một bình luận có thể có nhiều nhóm và nhiều hành vi. Hành vi và bằng chứng phải gắn với từng nhóm/đoạn; một trường intent chung cho toàn bình luận không đủ cho câu pha trộn nhiều ngữ cảnh.

## 2. Cosine similarity làm được gì?

Biến văn bản thành vector `a`, `b`, rồi tính:

`cosine(a,b) = sum(a[i] * b[i]) / (sqrt(sum(a[i]^2)) * sqrt(sum(b[i]^2)))`

Với vector khác không, kết quả thuộc [-1, 1]. Với các vector đã chuẩn hóa độ dài bằng 1, có thể dùng tích vô hướng. Đây là điểm gần nhau trong không gian biểu diễn, không phải xác suất vi phạm.

Hai cách tạo vector cần phân biệt:

- **Đếm từ / TF-IDF:** chủ yếu đo từ và cụm từ cùng xuất hiện. Nhanh, hữu ích làm baseline hoặc tìm câu lặp. Các đặc trưng ký tự giúp tìm biến thể cách viết nhưng vẫn không tự hiểu ý định.
- **Embedding đa ngữ:** học biểu diễn để tìm cách diễn đạt gần nghĩa, hữu ích khi người viết thay từ. Chất lượng phụ thuộc mô hình, ngôn ngữ và dữ liệu huấn luyện; phủ định, trích dẫn và mỉa mai vẫn có thể gây nhầm.

Phép tính minh họa đã kiểm tra bằng đếm từ:

- A: “Đừng tham gia nhóm cá cược”
- B: “Hãy tham gia nhóm cá cược”
- Mỗi câu có 6 từ, chung 5 từ, cosine đếm từ = 5/6 ≈ **0,8333**.

Hai ý định trái nhau vẫn có điểm cao. Đây là ví dụ đếm từ, **không phải số đo embedding của E5 hoặc một mô hình đã chạy trên dữ liệu thực**.

Không đặt quy tắc “cosine > 0,8 thì vi phạm”. Ngưỡng phải được kiểm định theo mô hình, nhóm và mục tiêu vận hành. Model card E5 còn nêu rằng điểm cosine thường tập trung khoảng 0,7–1,0; vì vậy 0,8 càng không có nghĩa là xác suất vi phạm 80%.

## 3. Kho cần chứa cả mẫu vi phạm và mẫu đối chiếu

Đơn vị quản lý là **một quy tắc/hành vi cần nhận diện**, có nhiều ví dụ liên kết. Ví dụ quy tắc: “Mời gọi tham gia cờ bạc”.

| Thành phần | Nội dung ví dụ |
| --- | --- |
| Nhóm | Cờ bạc |
| Hành vi cần bắt | Mời tham gia, quảng bá, hướng dẫn đăng ký trong phạm vi quy định |
| Dấu hiệu chủ đề | cá cược, cá độ và các biến thể đã được duyệt |
| Dấu hiệu hành vi | vào nhóm, đăng ký, nhận thưởng và các cách diễn đạt tương đương |
| Mẫu vi phạm | Các lời mời thật, nhiều cách viết |
| Mẫu đối chiếu | Cảnh báo, tố cáo, hỏi đáp, đưa tin, trích dẫn có ngữ cảnh rõ |
| Mẫu dễ nhầm | “Đừng bỏ lỡ…”, “Không cần vốn…” và câu vừa cảnh báo vừa mời gọi |
| Bằng chứng | Đoạn nguyên văn, vị trí trong câu, vế liên quan |
| Nguồn | Bình luận đầy đủ, ngữ cảnh, phiên bản nhãn, người duyệt |
| Quản lý | Nháp/đã duyệt/đã thay thế, phiên bản quy định và lịch sử sửa |

Mẫu đối chiếu chỉ mô tả trường hợp không vi phạm của một quy tắc. Nó không trở thành danh sách cho phép toàn bộ bình luận. Một câu được phép nhắc đến cờ bạc vẫn có thể vi phạm nhóm xúc phạm hoặc chứa lời mời ở vế khác.

Câu nguồn đầy đủ được giữ làm bằng chứng, phục vụ tìm mẫu và huấn luyện. Việc lưu câu nguồn không có nghĩa câu đó trở thành điều kiện chặn nguyên văn. Đoạn được bôi đen cũng chưa tự trở thành từ khóa chặn ở mọi ngữ cảnh.

Không biến toàn bộ 296.466 bình luận thành 296.466 luật. Giữ kho dữ liệu gán nhãn đầy đủ, rồi chọn các mẫu đại diện đã duyệt cho từng hành vi. Gộp các câu gần nhau phải xét nhãn và ý định; không tự gộp câu cảnh báo với câu mời gọi chỉ vì cosine cao.

## 4. Luồng nhận diện được đề xuất

1. **Chuẩn hóa có giữ thông tin:** Unicode NFC, khoảng trắng; lưu cả nguyên văn. Giữ dấu tiếng Việt, từ phủ định, dấu câu, URL và vị trí bằng chứng. Biến thể không dấu/lách chữ là tín hiệu bổ sung, không thay thế bản gốc.
2. **Lấy đoạn và ngữ cảnh:** xét câu/vế xung quanh dấu hiệu, lời trích dẫn và tác giả phát ngôn. Khi cần, lấy cả câu trước/sau hoặc bình luận cha. Không chỉ đưa cụm đã bôi đen cho mô hình.
3. **Tìm ứng viên:** kết hợp tìm từ/cụm/ký tự và tìm embedding bằng cosine. Lấy một tập nhỏ mẫu vi phạm lẫn mẫu đối chiếu, chẳng hạn top 10–20 để thử nghiệm. Không bắt buộc có từ khóa trước mới cho tìm ngữ nghĩa, vì sẽ bỏ sót cách nói tránh.
4. **Xét hành vi/ngữ cảnh:** dùng bộ phân loại hoặc mô hình so cặp đã được đánh giá cho nhiệm vụ này. Các nhãn gồm mời gọi, mua bán, đe dọa, cảnh báo, trích dẫn, hỏi đáp, hỗn hợp/chưa rõ, tùy quy định từng nhóm. Một reranker chỉ học mức độ liên quan trong tìm kiếm chưa đủ để kết luận vi phạm.
5. **Đề xuất có giải thích:** trả nhóm, hành vi, đoạn bằng chứng, nguồn quy tắc và mẫu đối chiếu gần nhất. Trạng thái gồm nghi vi phạm, chưa thấy bằng chứng vi phạm, cần người duyệt. Nếu cả mẫu vi phạm lẫn đối chiếu đều gần, ưu tiên kiểm tra thêm.
6. **Phản hồi admin:** admin chấp nhận/sửa/trả lại. Lưu thành phiên bản mới; nhãn cũ không bị xóa. Phiên bản nhãn nguồn thay đổi thì các mẫu, index hoặc luật phụ thuộc cần được đánh dấu kiểm tra lại.

Mô hình retrieve-and-rerank là cơ sở cho bước tìm và đọc lại ứng viên. Phần quyết định vi phạm là thiết kế bổ sung theo quy định, không phải tính năng tự có của cosine hoặc mọi cross-encoder.

## 5. Giao diện gán nhãn nên hoạt động thế nào?

Màn gán nhãn vẫn ưu tiên đọc và kết luận. Khi giữ một mẫu tham chiếu:

- Kết luận vi phạm → gợi ý **Giữ làm mẫu vi phạm**.
- Kết luận không vi phạm nhưng cùng chủ đề → cho **Giữ làm mẫu đối chiếu**.
- Thiếu ngữ cảnh → giữ vào mục **Cần kiểm tra**, chưa dùng làm mẫu chuẩn.

Tên mẫu, nhóm gợi ý và nguồn lấy sẵn. Bôi đen là tùy chọn. Admin vào kho để chọn hành vi, ghép các ví dụ vào cùng một quy tắc và duyệt. Máy có thể gợi ý nhóm/cụm/hành vi, người duyệt xác nhận trước khi đưa vào kho chuẩn.

Màn thử quy tắc cần hiển thị song song: câu đang thử, đoạn nghi vấn, lý do gợi ý, các mẫu vi phạm gần và các mẫu đối chiếu gần. Tránh chỉ hiện một điểm phần trăm dễ bị hiểu là xác suất vi phạm.

## 6. Chênh lệch với SQL và engine hiện tại

Hiện `app.py:evaluate` có `exact`, `combined`, `url`, `domain`. `combined` tìm cụm chủ đề và hành vi trong cùng câu rồi đánh dấu cần xem ngữ cảnh nếu gặp một cụm cấu hình. Đây là luật từ ngữ, chưa có embeddings, cosine search hoặc bộ phân loại ý định.

`reviews.intent`/`evidence` hiện thuộc toàn lượt duyệt. `rules` liên kết một bình luận nguồn; đề xuất tự động hiện chỉ nhận kết quả VIOLATION và khởi tạo kiểu exact. Vì vậy bản hiện tại chưa biểu diễn đầy đủ các mẫu đối chiếu và nhiều hành vi trong một câu.

Đề xuất mở rộng theo hướng giữ dữ liệu cũ:

| Bảng mới dự kiến | Dữ liệu chính |
| --- | --- |
| `review_category_details` | review_id, category, intent, target, evidence_start/end, evidence_text, context_note; cho nhiều đoạn trên một nhóm |
| `rule_cases` | rule_id, source_review_id, category, vai trò positive/counterexample/uncertain, snapshot câu/ngữ cảnh/đoạn, người duyệt, trạng thái, policy_version |
| `case_embeddings` | case_id, content_hash, model_id, model_revision, số chiều, cách chuẩn hóa/prefix, vị trí vector hoặc BLOB |
| `model_evaluations` | phiên bản mô hình/index/quy định, định danh bộ kiểm thử, ngưỡng từng nhóm và số liệu đánh giá |

`rules` tiếp tục mô tả quy tắc và trạng thái; `rule_cases` cho phép một quy tắc có nhiều mẫu vi phạm và nhiều mẫu đối chiếu. Các bảng này là đề xuất, chưa được migration vào database. Không trộn vector từ hai model/revision khác nhau trong cùng phép so sánh.

## 7. Cách kiểm định trước khi dùng tự động

- Thu thập cả câu vi phạm, câu trung lập và các cặp chỉ khác một vế phủ định/ngữ cảnh. Dữ liệu tự tạo giúp kiểm tra lỗi cụ thể nhưng phải có bộ thực tế đã được admin duyệt.
- Tách train/validation/test theo nhóm câu gần trùng, chiến dịch, nguồn hoặc thời gian phù hợp. Không để cùng mẫu quảng cáo chỉ đổi vài ký tự nằm ở cả tập train và test.
- Đo precision (các câu bị gắn cờ có đúng không), recall (bỏ sót bao nhiêu), tỷ lệ bắt nhầm câu cảnh báo/trích dẫn và tỷ lệ phải chuyển người duyệt, theo từng nhóm.
- Chọn ngưỡng trên validation, kiểm tra một lần trên test riêng. Không lấy điểm cosine hoặc output mô hình chưa hiệu chỉnh làm xác suất.
- Chạy chế độ gợi ý trước: đối chiếu kết quả với admin, chưa tự thay nhãn hoặc bật luật. Số lượt có dữ liệu quá ít phải báo rõ, không kết luận đã có độ chính xác cao.
- Bộ hồi quy phải có đủ “đừng tham gia”, “đừng bỏ lỡ”, “không cần vốn”, trích dẫn để tố cáo, hỗn hợp hai vế, nói tránh, không dấu/lách chữ và thiếu bình luận cha.

## 8. Phương án phù hợp Render Free

Render hiện công bố gói web Free có 512 MB RAM và 0,1 CPU. Nếu giữ 296.466 vector 384 chiều dạng float32, riêng ma trận thô đã chiếm **455.371.776 byte, khoảng 455 MB thập phân / 434 MiB**. Chưa tính model, index tìm kiếm, Python, PyArrow và database. Vì vậy không nên nạp toàn bộ encoder và ma trận này vào cùng tiến trình gán nhãn hiện tại.

Lộ trình đề xuất:

1. **Trước mắt:** sửa cấu trúc mẫu vi phạm/đối chiếu, hướng dẫn nhãn và màn kiểm tra ngữ cảnh. Dùng luật cụm từ và baseline nhẹ để gợi ý; giữ lưu nhãn độc lập với suy luận AI.
2. **Thử nghiệm theo lô:** trên máy cá nhân hoặc notebook, so sánh baseline TF-IDF ký tự/từ với mô hình đa ngữ như `intfloat/multilingual-e5-small`. Mô hình này cho vector 384 chiều; cần tuân theo prefix/chuẩn hóa của model card. Đo trên dữ liệu tiếng Việt đã duyệt trước khi chọn.
3. **Web đọc gợi ý đã tính:** với các bình luận có sẵn trong kho, có thể tính ứng viên trước rồi lưu kết quả để web hiển thị nhanh. Chọn một tập mẫu đại diện thay vì coi mọi câu là luật.
4. **Nếu cần nhận diện câu mới tức thời:** câu mới vẫn phải được mã hóa, dù vector kho đã tính sẵn. Cần benchmark mô hình lượng tử hóa hoặc tách nơi chạy suy luận; việc chỉ thêm cosine vào web không giải quyết chi phí này. Notebook miễn phí không được mặc định là dịch vụ chạy 24/7.

Không đưa việc tạo embedding, huấn luyện hoặc quét cả kho vào nút Lưu & tiếp theo. Vector/index là dữ liệu có thể tái tạo theo phiên bản; cần cân nhắc lưu riêng vì snapshot Git hiện giới hạn 20 MB nén.

## Nguồn chính

1. [Sentence Transformers: Semantic Textual Similarity](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) — embeddings, các phép đo và cosine.
2. [Sentence Transformers: Retrieve & Re-Rank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) — tìm ứng viên trước, đánh giá lại tập nhỏ sau.
3. [Multilingual E5 small: model card](https://huggingface.co/intfloat/multilingual-e5-small) — 384 chiều, prefix, chuẩn hóa, giới hạn token và đặc điểm phân bố điểm cosine. Đây là một ứng viên thử nghiệm, không phải kết quả chứng minh cho nhiệm vụ kiểm duyệt tiếng Việt.
4. [Petcu et al., EMNLP 2025: A Comprehensive Taxonomy of Negation for NLP and Neural Retrievers](https://aclanthology.org/2025.findings-emnlp.839/) — các giới hạn của mô hình truy hồi với phủ định; không được suy ra độ lỗi cụ thể trên dữ liệu người dùng.
5. [Render: Compute Plans](https://render.com/docs/compute-plans) — giới hạn CPU/RAM của gói Free được đối chiếu khi viết tài liệu.

Pipeline kiểm duyệt, SQL mở rộng và lộ trình vận hành trong tài liệu này là đề xuất cho dự án, không phải một hệ thống đã được triển khai hoặc benchmark ngữ nghĩa.
