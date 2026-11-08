# Cách tính để tự động chặn dựa trên kho Blacklist

**Cập nhật yêu cầu:** với chuỗi Blacklist → fastText → ViSoBERT/PhoBERT → kiểm tra chặn nhầm, ưu tiên [phương án tích hợp pipeline](BLACKLIST_PIPELINE_PROPOSAL.md). Các công thức dưới đây là nghiên cứu tham khảo cho việc tính điểm/chọn hành động; không phải yêu cầu đưa một bộ phân loại lớn bổ sung vào tầng Blacklist đầu tiên.

Đây là phương án đề xuất cho dự án. Chưa huấn luyện, hiệu chỉnh xác suất hoặc kiểm định trên dữ liệu người dùng; chưa bật chặn trong ứng dụng. Những con số minh họa bên dưới là bài toán số học giả định, không phải độ chính xác hoặc điểm mô hình đo được. Có thể đọc phần cấu trúc kho trong [BLACKLIST_CONTEXT_DESIGN.md](BLACKLIST_CONTEXT_DESIGN.md).

## 1. Đầu vào phải mô tả hành vi cần chặn

Ví dụ quy tắc CB-01: **Mời gọi tham gia cờ bạc**. Kho tham chiếu của quy tắc gồm:

- P: các mẫu vi phạm đã được admin duyệt, như lời mời tham gia và đăng ký nhận thưởng.
- N: các mẫu đối chiếu đã được duyệt, như cảnh báo, tố cáo và hỏi đáp.
- Các ca khó: “đừng tham gia”, “đừng bỏ lỡ”, “không cần vốn”, trích dẫn và câu có hai vế trái ý.

Cả P và N giữ câu nguồn, ngữ cảnh và đoạn đặc trưng. N chỉ là đối chiếu của quy tắc này, không miễn trừ toàn câu khỏi các quy tắc khác. Mẫu chưa duyệt không được tự đưa vào kho đang dùng để chặn.

## 2. Tính bằng chứng tương đồng

Với bình luận x, xét các vế/đoạn z kèm ngữ cảnh liên quan. Chuẩn hóa Unicode, giữ dấu, phủ định, dấu trích dẫn và nguyên văn. Tính vector bằng cùng một model, revision và cách xử lý đầu vào.

`sim(z,e) = dot(v_z, v_e) / (norm(v_z) * norm(v_e))`

Lấy các mẫu gần bằng tìm cụm/ký tự và cosine. Ví dụ các đặc trưng cho nhóm c:

`s_pos = mean(top-k sim(z,p), p thuộc P_c)`

`s_neg = mean(top-k sim(z,n), n thuộc N_c)`

`margin = s_pos - s_neg`

k là tham số phải chọn trên validation. Dùng tối đa số mẫu có sẵn và lưu số lượng hỗ trợ; thiếu mẫu không được coi điểm vắng mặt là 0 để tự tin chặn. Các mẫu gần trùng từ cùng một chiến dịch cần được khử trùng hoặc giảm trọng số để một bản quảng cáo lặp hàng nghìn lần không lấn át kết quả.

Ba giá trị này là **đặc trưng**, không phải xác suất. Cả s_pos và s_neg cao cho thấy cần phân biệt ngữ cảnh, không mặc định chỉ lấy mẫu có điểm cao nhất.

Một baseline khác là kNN có trọng số khoảng cách. Ví dụ tự thiết kế trọng số theo cosine:

`w_i = exp((sim_i - max_sim) / temperature)`

`vote = sum(w_i * y_i) / sum(w_i)`

Trong đó y_i là 1/0 ở các mẫu đã duyệt. temperature phải được kiểm định. vote vẫn chỉ là điểm bỏ phiếu thô; tập tham chiếu lệch lớp, mẫu trùng và các câu rất xa kho đều có thể làm nó sai. Không dùng nó trực tiếp làm xác suất chặn.

Tìm mẫu có thể dùng cả embedding và từ/cụm; không đặt điều kiện phải có đúng từ “cá cược” trước mọi tìm kiếm, vì sẽ bỏ sót cách nói tránh.

## 3. Tính điểm hành vi và điểm vi phạm

Tạo vector đặc trưng F cho bình luận, theo từng nhóm vi phạm, gồm:

- s_pos, s_neg, margin và mức hỗ trợ của các mẫu đã duyệt.
- Từ/cụm hoặc n-gram ký tự trong bình luận và đoạn liên quan.
- Bằng chứng chủ đề và hành vi cùng nói về một đối tượng trong một vế.
- Lời kêu gọi/đăng ký/mua bán, URL hoặc thông tin liên hệ trong phạm vi quy định.
- Phạm vi phủ định: phủ định việc tham gia hay phủ định việc bỏ lỡ/cần vốn?
- Ai đang phát ngôn: lời mời của người viết hay lời trích dẫn để phản đối?
- Câu hỗn hợp, thiếu bình luận cha hoặc thiếu thông tin để kết luận.

Những đặc trưng về phủ định và tác giả phát ngôn phải được trích bằng quy tắc có phạm vi rõ hoặc mô hình đã huấn luyện. Không thể chỉ dò sự xuất hiện của “đừng”, “không”, dấu ngoặc kép rồi coi như đã hiểu ngữ cảnh.

Baseline dễ triển khai là logistic regression dùng đặc trưng n-gram kết hợp đặc trưng từ kho:

`r_c(x) = b_c + sum_j(w_cj * F_j(x))`

`p_raw_c(x) = 1 / (1 + exp(-r_c(x)))`

Các hệ số b, w được **học từ nhãn đã duyệt** bằng tối ưu log loss có regularization; không tự đặt “cosine 50%, từ khóa 30%, ngữ cảnh 20%”. Các điểm tương quan cũng không được nhân như các xác suất độc lập.

Sau đó hiệu chỉnh điểm trên dữ liệu tách riêng:

`p_c(x) = calibrator_c(r_c(x))`

Có thể thử sigmoid hoặc isotonic tùy lượng dữ liệu. Đánh giá reliability theo nhóm điểm và bối cảnh. Nếu chưa có mô hình và calibrator đạt yêu cầu thì output vẫn là điểm gợi ý, chưa có xác suất đáng tin để bật chặn.

Logistic n-gram là baseline hiệu quả để đo mốc chất lượng; nó không bảo đảm hiểu được mọi câu phủ định. Khi cần nâng chất lượng, thử bộ phân loại ngữ cảnh mạnh hơn nhưng vẫn giữ quy trình hiệu chỉnh và kiểm định. Cosine tiếp tục phục vụ lấy mẫu và giải thích nguồn.

Nên dự đoán và hiệu chỉnh ở **cấp bình luận theo từng nhóm**. Nếu quét nhiều đoạn rồi lấy điểm lớn nhất, phải kiểm định/hiệu chỉnh điểm tổng hợp đó; không tự coi max của các xác suất đoạn là xác suất bình luận. Tương tự, không tính `1 - product(1-p_c)` để gộp các nhóm nếu chưa chứng minh giả định độc lập.

## 4. Cách tính quyết định BLOCK / REVIEW / ALLOW

Một mô hình điểm tốt và một ngưỡng phù hợp là hai việc khác nhau. Giả sử p là xác suất vi phạm đã hiệu chỉnh cho một nhóm, xét ba chi phí:

- C_FP: thiệt hại của chặn nhầm câu không vi phạm.
- C_FN: thiệt hại của để lọt một câu vi phạm.
- C_R: công sức và độ trễ của một lượt người duyệt.

Trong mô hình minh họa giả định người duyệt quyết định đúng và các quyết định đúng có chi phí 0:

`L_block = (1-p) * C_FP`

`L_allow = p * C_FN`

`L_review = C_R`

Chọn hành động có tổn thất kỳ vọng nhỏ nhất. Khi bằng nhau, ưu tiên REVIEW.

### Ví dụ tính số

Giả sử C_FP = 20, C_FN = 1, C_R = 0,2 theo đơn vị quy ước, không phải tiền. Các p dưới đây cũng giả định, không được gán cho một câu thật khi chưa chạy mô hình:

| p giả định | L_block | L_allow | L_review | Hành động có chi phí nhỏ nhất |
| --- | ---: | ---: | ---: | --- |
| 0,995 | 0,100 | 0,995 | 0,200 | BLOCK |
| 0,940 | 1,200 | 0,940 | 0,200 | REVIEW |
| 0,030 | 19,400 | 0,030 | 0,200 | ALLOW |

Với đúng các chi phí minh họa này:

- p > 0,99 → BLOCK.
- p < 0,20 → ALLOW đối với nhóm đang xét.
- Còn lại → REVIEW.

Nếu chỉ có BLOCK/ALLOW, ngưỡng tối ưu theo mô hình chi phí đơn giản là `C_FP / (C_FP + C_FN)`, ở ví dụ này là 20/21 ≈ 0,9524. Thêm lựa chọn REVIEW tạo vùng dành cho người duyệt, nên ngưỡng chặn cao hơn trong ví dụ.

Đây là cách **suy ra ngưỡng từ yêu cầu vận hành**, không phải đề xuất đặt mặc định 0,99 cho dự án. Người duyệt thực tế có sai số; khi ước lượng được, chi phí review cần cộng thêm lỗi của người duyệt. Năng lực xử lý hàng đợi cũng cần được đo.

Các điều kiện vận hành vẫn áp dụng: thiếu ngữ cảnh, nhóm chưa có đủ mẫu, ngoài phạm vi đã kiểm định, phiên bản mô hình/kho không khớp hoặc nguồn nhãn đang bị trả sửa → chưa tự động chặn bằng điểm đó. Một từ phủ định xuất hiện không phải điều kiện tự động ALLOW.

Tính riêng từng nhóm. Bình luận bị BLOCK nếu có nhóm đã đạt điều kiện BLOCK; nếu không có BLOCK mà còn nhóm cần xem thì REVIEW; chỉ ALLOW khi các nhóm bắt buộc theo quy định đã được đánh giá và đều cho phép. Nhóm chưa đánh giá phải được ghi rõ, không biến thành “an toàn toàn bộ”.

## 5. Chọn ngưỡng theo kết quả kiểm thử thực tế

Nếu admin muốn kiểm soát trực tiếp tỷ lệ chặn nhầm, có thể chọn ngưỡng theo precision thay cho đặt chi phí chủ quan:

`precision_block(t) = TP(t) / (TP(t) + FP(t))`

`recall_block(t) = TP(t) / (TP(t) + FN(t))`

Trong đó TP là câu vi phạm bị chặn đúng, FP là câu không vi phạm bị chặn nhầm. Khi chỉ đo nhánh tự chặn, các câu vi phạm được chuyển duyệt cũng chưa tính là đã chặn tự động; cần báo riêng kết quả nhánh duyệt và độ trễ.

Ví dụ mục tiêu do admin lựa chọn là precision nhánh chặn ≥ 99,5%. Thử các ngưỡng trên validation, chọn ngưỡng có recall cao nhất trong các ngưỡng đủ điều kiện precision, số mẫu hỗ trợ và giới hạn bắt nhầm theo từng loại ngữ cảnh. Sau đó xác nhận một lần trên bộ test độc lập.

Không chọn ngưỡng và công bố chất lượng trên cùng một tập. Cần tách bộ tham chiếu/huấn luyện, bộ hiệu chỉnh và chọn ngưỡng, bộ test cuối. Có thể dùng cross-validation đúng cách khi ít dữ liệu. Các câu gần trùng phải nằm cùng một nhóm chia tập để tránh rò rỉ.

### Vì sao không chỉ nhìn “100 câu thử đều đúng”?

Nếu n câu bị chặn được lấy mẫu đại diện, độc lập, và cả n đều đúng, cận dưới exact một phía ở mức tin cậy 95% cho precision là:

`lower = 0.05 ** (1/n)`

- 100/100 đúng → cận dưới khoảng **97,05%**.
- 600/600 đúng → cận dưới khoảng **99,502%**.

Đây là suy luận nhị thức với các giả định lấy mẫu cụ thể; không bảo đảm tỷ lệ trong dữ liệu tương lai khi phân bố thay đổi. Có lỗi thì phải dùng khoảng tin cậy tổng quát thay vì công thức riêng cho 0 lỗi. Hàng trăm bản sao của cùng một câu không được coi là hàng trăm phép kiểm tra độc lập.

Mục tiêu 99,5% chỉ là ví dụ, chưa được người dùng chốt và chưa được dự án đạt. Cần kiểm tra nhánh chặn theo từng nhóm và cả quyết định cuối của toàn hệ thống, vì một trong nhiều nhóm bắt nhầm cũng có thể khiến cả bình luận bị chặn.

## 6. Các phép thử bắt buộc về ngữ cảnh

Với quy định cấm mời gọi cờ bạc:

| Câu thử tự tạo | Kết quả cần hệ thống học/được kiểm định |
| --- | --- |
| Vào nhóm cá cược đăng ký nhận thưởng. | BLOCK nếu đủ điều kiện vận hành và điểm đạt ngưỡng |
| Đừng tham gia nhóm cá cược. | ALLOW đối với quy định mời gọi nếu ngữ cảnh đầy đủ |
| Đừng bỏ lỡ kèo ngon, vào nhóm cá cược ngay. | Không được miễn vì chữ “đừng”; xét lời mời thật |
| Không cần vốn, tham gia nhóm cá độ nhận thưởng. | Không được miễn vì chữ “không” |
| Nó nhắn “vào nhóm cá cược”, tôi đã báo cáo. | Phân biệt lời trích dẫn tố cáo với lời mời của người viết |
| Tôi phản đối cá cược. Ai muốn chơi thì nhắn tôi. | Không để vế phản đối miễn trừ lời mời ở vế sau |
| Tham gia nhóm này đi. | REVIEW nếu thiếu thông tin nhóm nói về gì |

Những dòng này là yêu cầu kiểm thử, không phải kết quả đã chạy. Cần bổ sung câu thực tế, nói tránh, lỗi chính tả, mỉa mai và các nhóm khác. Cách kiểm thử theo chức năng như HateCheck giúp tìm lỗi bị che khuất khi chỉ xem điểm trung bình, nhưng benchmark của lĩnh vực khác không chứng minh chất lượng cờ bạc tiếng Việt.

## 7. Quy tắc chắc chắn và cách triển khai

Có thể có nhánh quy tắc rõ ràng được admin duyệt và bật chế độ chặn: ví dụ một điều kiện có chủ đề, hành vi và phạm vi phát ngôn được định nghĩa cụ thể. Các quy tắc này cũng phải kiểm định trên câu thực tế và mẫu đối chiếu. Không tự nâng mọi từ khóa, domain hoặc nguyên câu trích dẫn thành lệnh chặn vô điều kiện.

Để chặn bình luận thực tế, nơi tiếp nhận bình luận phải gọi bộ đánh giá trước khi hiển thị. Output cần ghi:

`decision, category, rule_id, evidence_span, score_type, calibrated_score (nếu có), policy_version, model_version, index_version, audit_id`

BLOCK nên có nghĩa giữ bình luận khỏi hiển thị trong trạng thái có thể kiểm tra và khôi phục. Lưu nguyên văn, lý do và phiên bản quyết định để admin xử lý bắt nhầm; không xóa sạch bằng chứng. REVIEW và ALLOW cũng cần lưu phạm vi nhóm đã xét.

Hệ thống hiện tại chỉ phát tín hiệu REVIEW. Chuyển sang BLOCK cần bổ sung chế độ luật, dữ liệu đối chiếu, bộ tính điểm/hiệu chỉnh, ngưỡng theo nhóm và điểm tích hợp chặn. Những điều này chưa được triển khai trong tài liệu này.

Với Render Free, khuyến nghị huấn luyện và tính embedding theo lô bên ngoài đường lưu nhãn. Bắt đầu bằng mô hình gọn và các đặc trưng từ kho; chỉ dùng encoder lớn thời gian thực sau khi đo tài nguyên hoặc tách nơi suy luận. Web lưu nhãn không nên chờ tính lại cả kho.

## Nguồn nghiên cứu

- [scikit-learn: Nearest Neighbors](https://scikit-learn.org/stable/modules/neighbors.html) — phân loại theo các mẫu gần và trọng số khoảng cách. Công thức softmax cosine nêu trong tài liệu là lựa chọn baseline đề xuất, không phải mặc định của sklearn.
- [scikit-learn: Logistic regression](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression) — hàm logistic và tối ưu log loss có regularization.
- [scikit-learn: Probability calibration](https://scikit-learn.org/stable/modules/calibration.html) — hiệu chỉnh điểm và yêu cầu dữ liệu độc lập.
- [scikit-learn: Tuning the decision threshold](https://scikit-learn.org/stable/modules/classification_threshold.html) — tách dự đoán điểm khỏi quyết định và chọn ngưỡng trên dữ liệu phù hợp.
- [scikit-learn: Precision-Recall](https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html) — định nghĩa và quan hệ precision/recall.
- [NIST: Exact binomial confidence limits](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm) — cơ sở thống kê khoảng tin cậy cho tỷ lệ.
- [HateCheck, ACL 2021](https://aclanthology.org/2021.acl-long.4/) — kiểm thử theo chức năng để phát hiện giới hạn mô hình kiểm duyệt.

Các đặc trưng dựa trên kho, quy tắc ba hành động, chi phí minh họa và cách ghép vào ứng dụng là đề xuất thiết kế; không được trình bày như chất lượng thực nghiệm của dự án.
