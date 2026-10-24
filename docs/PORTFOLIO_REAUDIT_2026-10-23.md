# Audit lại working tree — 23/10/2026

> Follow-up cùng ngày: R1–R6 đã được sửa và kiểm thử local; xem `PORTFOLIO_FIXES_2026-10-23.md`. Nội dung dưới đây giữ nguyên thời điểm phát hiện, không phải trạng thái sau sửa.

## Kết luận

Repo tiến bộ về tính nhất quán của retrieval, source page/line và xử lý stream bị ngắt. Tuy nhiên, kết luận trước đó rằng cả 5 nhóm lỗi đã hoàn tất còn quá sớm: các nhánh migration/deletion vẫn có thể mất dữ liệu hoặc giữ nội dung đã yêu cầu xóa trong index.

Nên tiếp tục giữ dự án làm case study full-stack/RAG. Chưa nên giới thiệu là hệ thống production đã được kiểm chứng. Ưu tiên sửa hai lỗi P1 trước khi nâng cấp hạ tầng hoặc dùng tài liệu quan trọng.

Phạm vi: working tree chưa commit trên HEAD `805233e0e2cf3b92facacf809e6eff86515c136b`, gồm các sửa đổi ngày 18/10. Audit này không sửa mã nguồn, không commit, push hoặc deploy. Các phép thử gây lỗi chạy trong thư mục tạm do audit tạo, dùng storage stub; không tác động upload thật hoặc tài khoản live.

## Kết quả kiểm tra lại

| Kiểm tra | Kết quả ngày 23/10 |
| --- | --- |
| Backend tests | 102 passed, 1 warning; 78,12 giây |
| Frontend unit tests | 6 passed |
| Chromium E2E | 11 passed; 46,6 giây |
| Lint, TypeScript, production build | Qua |
| Coverage | Không chạy lại; 66,15% là kết quả kiểm tra ngày 18/10 |
| Provider generation / Redis-RQ-B2 thật | Không chạy trong audit này |

Các test hiện tại chưa bao phủ những nhánh lỗi dưới đây. Phép đo retrieval bổ sung dùng corpus đã sinh và production retrieval function, không gọi LLM.

## Phát hiện theo ưu tiên

### R1 — P1: reindex khi chuyển từ local sang distributed có thể xóa upload gốc

Vị trí: `backend/api/routes/documents.py:278–282`.

Khi `REDIS_URL` có giá trị, `_restore_remote_uploads()` lấy danh sách object từ B2 rồi xóa mọi file local không có tên trong danh sách đó. Code chưa phân biệt file cache đã bị xóa trên remote với tài liệu local chưa từng được migrate.

**Đã tái hiện:** tạo `only-local-copy.txt`, chuyển sang distributed mode với một B2 prefix trống hợp lệ, gọi `_restore_remote_uploads()`. File local không còn tồn tại sau lời gọi. Đây không phải trường hợp B2 mất kết nối: một listing trống thành công cũng đủ kích hoạt.

Test `test_distributed_reindex_cannot_restore_deleted_local_uploads` đang kỳ vọng xóa cache cũ, nhưng thiếu trường hợp local-to-distributed migration. Hai trạng thái có cùng biểu hiện “file local không có trên remote” nên không thể suy ra quyền xóa chỉ từ listing.

**Hướng sửa:** tách migration khỏi cache reconciliation; không xóa tài liệu chưa xác nhận đã migrate. Dùng manifest/tombstone có trạng thái rõ ràng hoặc bỏ file không còn active khỏi lần reindex mà vẫn giữ bản local cho đến khi có chính sách cleanup an toàn. Thêm test giữ được bản local duy nhất khi B2 còn trống.

### R2 — P1: delete thất bại ở bước lưu index không thể hoàn tất bằng retry

Vị trí: `backend/api/routes/documents.py:504–530`.

Delete xóa upload và manifest trước, sau đó mới persist index đã bỏ tài liệu. Nếu persist thất bại, revision cũ vẫn active. Lần gọi lại thấy upload đã mất và remote delete trả false nên kết thúc bằng 404 trước khi dọn index.

**Đã tái hiện bằng fault injection:**

```text
DELETE lần đầu: 500 (giả lập lỗi đĩa ở store.persist)
Upload trên đĩa: đã bị xóa
DELETE retry: 404
retrieve_context("confidential budget"): vẫn trả nội dung secret.txt
```

API không báo delete thành công giả, nhưng hệ thống rơi vào trạng thái xóa dở, retry thông thường không sửa được. Người dùng phải chủ động full reindex mới có thể dọn phần còn lại.

**Hướng sửa:** deletion phải idempotent cả khi physical file đã mất; giữ tombstone/pending deletion để retry có thể hoàn tất. Retrieval phải loại tài liệu đã được đánh dấu xóa. Kiểm thử lỗi publish snapshot, lỗi xóa remote và retry sau từng bước.

### R3 — P2: context packing làm mất bằng chứng mà retrieval đã tìm được

Vị trí: `backend/rag/prompts.py:105–107`; production evaluation bắt đầu ở `backend/evaluation/metrics.py:184`.

Chunk dùng 220 từ, nhưng prompt lấy tối đa 1.000 ký tự đầu của mỗi chunk. Evaluation chính chấm đúng trang trong retrieval, chưa gate việc span cần thiết còn tồn tại sau bước tạo context.

Phép đo trên cùng 90 câu answerable:

| Tín hiệu | Số câu |
| --- | ---: |
| Có trang đúng trong 5 kết quả | 74 |
| Có nguyên văn span được annotate trong các chunk truy xuất | 58 |
| Span đó còn trong context thật sau packing | 40 |
| Có span trước packing nhưng mất sau packing | 18 |

Ví dụ ID bị mất: `rag-001`, `rag-003`, `rag-007`, `dpr-003`, `colbert-002`, `colbert-003`.

Đây là kiểm tra span nguyên văn, không phải tỷ lệ answer đúng/sai. Những đoạn khác có thể diễn đạt cùng thông tin; không suy ra 40/90 là accuracy của LLM. Nhưng việc mất 18 span đã tìm được là một failure mode cụ thể chưa có gate.

**Hướng sửa:** chọn context theo token budget và giữ vùng quanh evidence phù hợp thay vì cắt đầu chunk cố định; bổ sung phép đo evidence retention sau packing và đánh giá generated answers. Tiếp tục gọi 82,22% là Hit@5 retrieval, không gọi là answer accuracy.

### R4 — P2: danh sách tài liệu bỏ sót upload từ replica khác

Vị trí: `backend/api/routes/documents.py:232–269`.

Chỉ list B2 nếu thư mục local không có tài liệu nào. Khi replica A có `first.txt` trên local, còn `second.txt` chỉ ở B2 do replica B nhận upload, A trả danh sách chỉ có `first.txt`, dù index hiện tại đã chứa cả hai.

**Đã tái hiện:** stub remote listing gồm hai file, tạo một file local và đặt chunk counts cho cả hai. `_list_upload_files()` chỉ trả `first.txt`.

**Hướng sửa:** trong distributed mode lấy document manifest/shared catalog làm nguồn chính, hoặc merge remote/local theo storage ID; local directory chỉ là cache. Thêm test hai replica với local caches khác nhau.

### R5 — P2: mapping dòng có độ phức tạp gần bậc hai trên file nhiều dòng

Vị trí: `backend/rag/chunking.py:67–73`.

Mỗi từ của mỗi chunk quét lại toàn bộ danh sách dòng của document. Với file TXT/Markdown dài, cả số từ lẫn số dòng tăng theo kích thước file, dẫn đến chi phí gần `O(words × lines)`.

Đo bằng dữ liệu tự tạo `short text line\n` trên máy audit:

| Dòng | Từ | Thời gian split_documents |
| ---: | ---: | ---: |
| 500 | 1.500 | 0,367 giây |
| 1.000 | 3.000 | 1,380 giây |
| 2.000 | 6.000 | 6,056 giây |

Thời gian phụ thuộc máy và tải nền; pattern tăng khoảng 4 lần khi gấp đôi số dòng phù hợp với vòng lặp hiện tại. File thử còn rất nhỏ so với giới hạn upload 25 MB. Local executor chỉ có hai worker nên các job kiểu này có thể chiếm hàng đợi lâu.

**Hướng sửa:** dùng sweep/two-pointer trên word offsets và line intervals, hoặc binary search vào line starts. Thêm performance regression với file nhiều dòng và budget parsing cho các loại text.

### R6 — P2: copy/share làm mất source page/line đang hiển thị

Vị trí: `frontend/src/components/chat/ChatBubble.tsx:45–46,67–72` và nút Copy trong cùng component.

UI render `citedContent` bằng cách thay `[E1]` thành filename/page/lines. Nhưng Copy và Share đều dùng `message.content` gốc. Người dùng nhìn thấy source đầy đủ, còn clipboard/share nhận ID nội bộ `[E1]` không đủ để đối chiếu bên ngoài ứng dụng.

Đây là phát hiện từ call sites trực tiếp; chưa thực hiện giao tiếp chia sẻ ra dịch vụ ngoài.

**Hướng sửa:** tách formatter plain text dùng chung cho render/copy/share/export, kèm metadata source. Không cần thêm link hoặc viewer; giữ đúng yêu cầu chỉ hiển thị vị trí nguồn.

## Những sửa đổi đã có tác dụng

- Parser, chunker và retrieval core đã dùng chung với evaluation. Việc còn thiếu gate context packing là bước sau retrieval, không phủ nhận sửa đổi này.
- Source page/line được tạo từ metadata trích xuất và giữ qua session reload. Kiểu source văn bản thuần đáp ứng yêu cầu hiện tại.
- Client không tự replay POST sau lỗi stream, và EOF thiếu `[DONE]` được coi là gián đoạn. Các kiểm thử này chạy lại đều qua.
- Revisioned snapshots giải quyết phần lớn lỗi reader dùng index cũ; vẫn cần hoàn thiện lifecycle delete/migration/document catalog và staging thật.
- README đã phân biệt hosted fallback với cấu hình distributed được hỗ trợ. Không xác minh lại trạng thái live deployment trong audit này.

## Đề xuất trước khi đưa làm dự án nổi bật

Sửa R1 và R2 trước. Tiếp theo làm evidence retention sau packing, document catalog dùng chung và mapping dòng tuyến tính. R6 là chỉnh sửa nhỏ nhưng ảnh hưởng trực tiếp workflow dùng câu trả lời có nguồn.

Abstention 0/10, chưa có generated-answer evaluation/staging distributed thật, cùng phần onboarding/visual polish vẫn là các giới hạn đã biết. Phù hợp để trình bày dưới dạng case study junior full-stack/RAG có giới hạn rõ ràng; chưa đủ bằng chứng cho tuyên bố production-ready.
