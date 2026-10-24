# Các sửa đổi sau audit — 18/10/2026

## Phạm vi và thứ tự thực hiện

1. Sửa hoàn tất/gián đoạn SSE và tránh tự replay POST tạo thêm lượt hỏi.
2. Dùng chung parser, chunker và retrieval entry point giữa ứng dụng và evaluation.
3. Hiển thị source dạng văn bản thuần: tên file, trang và dòng theo yêu cầu người dùng.
4. Đồng bộ index giữa API/worker bằng snapshot có phiên bản và kiểm tra lưu bền vững.
5. Chỉnh README/runbook theo cấu hình đã quan sát và chạy kiểm thử hồi quy.

Không commit, push hoặc deploy. Bản audit ngày 16/10 được giữ làm ghi nhận lịch sử.

## Kết quả triển khai

### Retrieval và evaluation

- Cả upload và corpus builder dùng `load_pdf` và `split_documents`: chunk 220 từ, overlap 40 từ, giữ ranh giới trang.
- Runtime và CI dùng `retrieve_from_store`; bỏ bước lọc/sắp xếp từ khóa riêng vốn làm runtime lệch benchmark.
- Chọn tối đa K passages với tính đa dạng theo trang PDF; cache được kiểm tra sau khi resolve revision hiện tại.
- `results.json` ghi primary method, entry point, corpus SHA-256 và phạm vi latency. Benchmark neural lịch sử được ghi rõ là chưa chạy lại.
- Benchmark sau sửa: Hit@5 **0.8222 (74/90)**, MRR@5 **0.5544**, P50 **3.92 ms**, P95 **13.97 ms** cho warm retrieval, không gồm HTTP/revision sync/LLM. Các ngưỡng chất lượng hiện có được giữ nguyên. Abstention 0/10 vẫn là hạn chế công khai, nằm ngoài 5 nhóm sửa lần này.

### Source theo trang và dòng

- Citation hiển thị như `(Source: report.pdf · Page 4 · Lines 12–18)`.
- Page và line đến từ parser/chunker, không lấy số do LLM tự viết. LLM dùng evidence IDs và frontend thay bằng vị trí do backend cung cấp.
- Số dòng bắt đầu từ 1 trên từng trang PDF theo văn bản trích xuất, gồm các dòng trống. Chuẩn hóa khoảng trắng, ligature và nối từ ngắt dòng vẫn giữ mapping về dòng gốc.
- File văn bản có số dòng theo nội dung trích xuất; không tạo số trang khi không có thông tin trang. Legacy index thiếu vị trí sẽ được ghi rõ cần reindex.
- Phạm vi dòng được thu hẹp khi context bị cắt ngắn. Evidence được lưu cùng answer để source còn nguyên sau reload.
- Không có link citation, popup evidence hoặc endpoint phục vụ PDF gốc.

### Streaming

- Chỉ `[DONE]` mới xác nhận hoàn tất; EOF, lỗi protocol và provider stream bị cắt đều được báo gián đoạn.
- Client không tự gửi lại chat POST sau lỗi mạng. UI cho regenerate chủ động; backend giữ user turn hiện tại.
- Regenerate không xóa answer của câu hỏi trước nếu POST mới chưa từng tới server.
- Server lưu answer và evidence trước khi phát `[DONE]`; answer bị ngắt được đánh dấu incomplete. Provider errors không còn được trả như answer token thành công.

### Index và worker

- Mỗi lần lưu tạo snapshot immutable, kèm SHA-256 cho từng artifact. Chỉ publish `current.json` sau khi tất cả artifact lưu thành công.
- Reader kiểm tra revision trước cache hit và xác minh checksum khi hydrate snapshot; lỗi storage không bị hiểu thành knowledge base rỗng.
- Writer tải bản mới dưới khóa mutation dùng chung cho add/delete/reindex. Writer cũ bị từ chối thay thế revision mới.
- Clear index publish revision rỗng để các host khác không hồi sinh cache cũ. Job đã xếp hàng kiểm tra upload còn tồn tại trước khi index.
- Runbook mô tả retention của snapshot cũ và các bước staging cần chạy trước khi bật distributed mode.

### Tài liệu triển khai

- README tách cấu hình live demo đã quan sát ngày 16/10 (local JSON/memory/thread pool) với adapter PostgreSQL/Redis/B2 mà repo hỗ trợ.
- Nêu rõ Blueprint không tự provision worker/database và không gọi số đo retrieval là latency của toàn bộ chat.

## Kiểm chứng và giới hạn

- Backend: 102 tests qua; coverage 66,15%, vượt floor 64% với phạm vi đo được giữ nguyên.
- SSE/source unit tests: 6 tests qua.
- E2E: 11/11 Chromium tests qua, gồm source page/line trên mobile, không có link/popup, session reload và regenerate sau gián đoạn. Lint, TypeScript và production build đều qua.
- Có test qua process riêng và thư mục index riêng với filesystem object-store adapter; có fault injection cho durable upload/read, checksum và stale writer.
- Chưa chạy staging với Redis/RQ/B2 thật hoặc live LLM generation. Không thay đổi cấu hình demo đang chạy.

Sau khi chạy phiên bản mới, dùng **Reindex** cho tài liệu cũ để sinh metadata trang/dòng. Hội thoại lịch sử không có evidence vẫn đọc được, nhưng không thể bổ sung vị trí nguồn một cách hồi tố.
