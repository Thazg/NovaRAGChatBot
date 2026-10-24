# Sửa các phát hiện R1–R6 — 23/10/2026

Phạm vi là working tree trên HEAD `805233e0e2cf3b92facacf809e6eff86515c136b`. Giữ nguyên các thay đổi trước đó; không commit, push, deploy hoặc chạy migration trên dữ liệu thật. Đây là follow-up của `PORTFOLIO_REAUDIT_2026-10-23.md`; báo cáo audit cũ giữ nguyên làm lịch sử.

## Thay đổi

| Phát hiện | Kết quả sửa |
| --- | --- |
| R1 — migration xóa bản gốc local | Hydration không còn unlink file vắng trên remote. Distributed reindex dừng trước khi publish nếu còn file chưa migrate. Có CLI migration tường minh: giữ bản gốc, retry được, merge tên hiển thị, bỏ qua tombstone và không ghi đè object khác nội dung. |
| R2 — xóa dở vẫn searchable, retry 404 | Lưu barrier theo storage ID trước mọi thao tác phá hủy. Retrieval cache, direct index loading, summary, listing, persist và reindex đều tôn trọng barrier. DELETE nhận lại ID đã đánh dấu xóa để hoàn tất cleanup; clear-all giữ barrier. Lỗi persist/index hoặc xóa remote vẫn chặn retrieval. Lỗi ghi barrier không xóa upload. Nhánh B2 có/không Redis đều báo lỗi khi remote delete thất bại. |
| R3 — packing bỏ mất evidence | Ưu tiên giữ nguyên chunk; mặc định tăng giới hạn passage lên 2.400 ký tự, tổng context 10.000 và Ollama context 8.192. Khi bị giới hạn, chọn cửa sổ liên tục theo query và thu hẹp khoảng dòng. Prompt và SSE dùng cùng hàm, cùng query. Thêm gate retention sau packing, tách khỏi page Hit@5. |
| R4 — listing thiếu file trên replica khác | Luôn merge local/remote theo storage ID, lọc barrier, giữ size/chunk counts/tên hiển thị. Distributed listing thất bại không giả thành danh sách rỗng. |
| R5 — mapping dòng gần bậc hai | Binary search vào các line intervals đã sắp xếp; chỉ duyệt interval giao với từ. Giữ nguyên offsets cho overlap và từ nối qua hai dòng PDF. Có kiểm tra số lần truy cập interval và đối chiếu với reference exhaustive. |
| R6 — Copy/Share mất source | Dùng formatter chung cho hiển thị, clipboard, native Share và conversation TXT export; thay ID hợp lệ bằng filename/page/line. Không thêm link/viewer. Account JSON vẫn giữ message gốc và evidence metadata để bảo toàn dữ liệu cấu trúc. |

## Kiểm chứng

- Full backend suite với coverage: **114 passed**, **68,14%**, floor 64% giữ nguyên; 147,71 giây. Còn một deprecation warning đã có từ Starlette/httpx.
- Sau đó bổ sung kiểm tra B2 không Redis và sửa điều kiện báo lỗi của remote delete: **23 targeted tests passed**, gồm lifecycle, chunking và revision tests. Tổng số backend cases hiện tại là 115; lần full coverage ở trên chạy trước khi thêm case B2 không Redis.
- Frontend unit: **7 passed**. Lint, TypeScript và production build đều qua.
- Chromium E2E: **11 passed**, gồm source sau reload, Copy, Share được mock và đọc nội dung file TXT export; mobile axe và visual regression vẫn qua. Không gửi câu trả lời ra dịch vụ chia sẻ bên ngoài.
- Rebuild offline: **10 PDF / 549 chunks / 100 queries**. SHA-256 corpus sinh lại khớp report evaluation.
- Offline evaluation CLI: tất cả ngưỡng pass. **Hit@5 74/90 (0,8222)**, **MRR 0,5544**; retrieval P50 **3,53 ms**, P95 **6,43 ms** trên máy local. Loại trừ HTTP, remote revision sync và generation.
- Verbatim evidence retention: **58/58 (100%)**, trước đó 40/58. 90 câu answerable có 58 câu chứa nguyên văn span annotate trong chunks truy xuất. Đây không phải generated-answer accuracy; runtime không đọc annotations để chọn đoạn.
- Synthetic TXT mapping: 500 dòng ~0,0033 s; 1.000 ~0,0057 s; 2.000 ~0,0129 s; 10.000 ~0,0664 s. Số đo phụ thuộc máy; regression test dùng số lần truy cập interval để tránh deadline dễ flaky.

Các test failure/migration/deletion chạy trên thư mục tạm và storage adapters. Giữ bản gốc local duy nhất, migration retry/conflict, lỗi publish barrier, lỗi persist index, lỗi remote delete, clear-all retry, cache cũ, reader trên local disk khác và job bị trễ đều có kiểm tra. Kiểm chứng này không thay thế staging Redis/RQ/B2 thật.

## Khi áp dụng sau này

Làm theo `PRODUCTION_PERSISTENCE.md`: dừng writes và drain jobs, backup, chạy migration cho từng account từ host giữ originals, rồi reindex và xác minh trước khi mở traffic. Không xóa local originals chỉ vì B2 listing trống. Không xóa barrier file trong cleanup; storage IDs đã xóa không được tái sử dụng. Snapshot cũ vẫn theo chính sách retention/GC chưa tự động của hệ thống.

Nếu deployment đang override `MAX_CHUNK_CHARS=1000` hoặc `MAX_CONTEXT_CHARS=6000`, cần cập nhật rõ ràng; default mới không ghi đè biến môi trường. Character budget không phải token count chính xác cho mọi ngôn ngữ/model.

Abstention vẫn **0/10**; chưa chạy generated-answer evaluation bằng provider thật hoặc staging distributed thật. Các sửa này hoàn tất R1–R6 trong phạm vi local, chưa đủ để đổi mô tả thành production-ready.
