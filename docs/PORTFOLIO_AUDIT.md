# Audit portfolio — Nova

Ngày đánh giá: 16/10/2026. Commit được kiểm tra: `805233e0e2cf3b92facacf809e6eff86515c136b`.

## Kết luận

**Nên giữ và đưa vào portfolio sau một vòng hoàn thiện có trọng tâm. Chưa nên giới thiệu là một hệ thống production đã được chứng minh hoặc chọn làm dự án nổi bật nhất ở trạng thái hiện tại.**

Repo có nền tảng kỹ thuật thực chất: auth/session, kiểm soát upload, lưu hội thoại, job indexing, SSE, kiểm thử và dữ liệu đánh giá có provenance. Giá trị phù hợp nhất là một case study full-stack/RAG về quyết định kỹ thuật và cách đo chất lượng. Điểm yếu là các lớp benchmark, runtime, deployment và thông điệp sản phẩm chưa khớp nhau; trải nghiệm chưa làm bằng chứng truy xuất trở thành điểm nổi bật.

Với vị trí junior full-stack/backend, đây là dự án có chất liệu tốt để thảo luận sâu. Với vị trí tập trung RAG/AI engineering, cần ưu tiên tính đại diện của evaluation, khả năng từ chối khi thiếu bằng chứng và citation có thể kiểm tra. Với vị trí frontend/product, cần cải thiện luồng thử sản phẩm và chất lượng giao diện trước.

## Phạm vi và kết quả xác minh

| Kiểm tra | Kết quả thực chạy |
| --- | --- |
| `python -m pytest -q` | 90 passed, 1 warning; 71,85 giây |
| `npm run check` tại `frontend` | Lint, TypeScript và production build đều qua |
| `npm run e2e` tại `frontend` | 10/10 Chromium tests qua; 44,6 giây |
| Live frontend | Mở được màn hình đăng nhập |
| Live `/health/ready` | `ready: true`, provider Groq reachable; chế độ JSON/local worker |
| Diagnostic gọi `retrieve_context` với corpus benchmark | 69/90 câu answerable có trang đúng trong 5 trang đầu; 0/10 câu unanswerable được từ chối |
| Diagnostic SSE với lần reconnect trả lời khác prefix | Hàm resolve thành công nhưng chỉ giữ phần trả lời dang dở của lần đầu |

Build ban đầu bị sandbox chặn subprocess (`spawn EPERM`); chạy ngoài sandbox đã thành công. Không tính đây là lỗi repo. Coverage chưa chạy lại được vì Python hiện tại thiếu plugin `pytest-cov`; không xác nhận lại con số coverage bằng artifact cũ. Python trên máy là 3.11, khác Python 3.12 được ghi trong README/CI.

Playwright dùng API mock. Integration backend dùng upload/parser/index/retrieval thật với LLM adapter cố định. Những kiểm tra này có giá trị về wiring, nhưng không chứng minh chất lượng câu trả lời của provider thật. Không chạy provider-backed generation có tính phí, không đăng ký tài khoản demo, không thay đổi dữ liệu production, không chạy thử Redis/RQ nhiều host thật.

## Phát hiện cần sửa trước khi quảng bá mạnh

### A1 — Cao: benchmark chưa đại diện cho pipeline đang phục vụ người dùng

**Bằng chứng:**

- `backend/evaluation/arxiv_corpus/extract_corpus.py`: chuẩn hóa và chia từng trang PDF thành chunk 220 từ, overlap 40 từ; giữ metadata trang.
- `backend/rag/load.py:62`: gộp tất cả trang PDF thành một document.
- `backend/rag/chunking.py`: runtime mặc định chunk 1.000 từ, overlap 200 từ.
- `backend/evaluation/advanced_retrieval_eval.py:183`: benchmark BM25 trực tiếp, xếp hạng và khử trùng theo trang.
- `backend/rag/rag_chain.py`: runtime còn có lọc theo từ khóa, stemming, overview fallback, mở rộng phạm vi và sắp xếp lại.
- `backend/evaluation/metrics.py:251`: CI chọn `hybrid_rrf` proxy làm metric chính dù runtime mặc định BM25.

Diagnostic trong audit dựng `HybridVectorStore` từ chính corpus đã sinh, đặt `RETRIEVAL_MODE=bm25`, gọi `retrieve_context(query, user_id, top_k=5)` cho 100 câu, lấy 5 `evaluation_id` khác nhau đầu tiên. Kết quả **69/90 = 76,67%**, trong khi benchmark đã commit báo **74/90 = 82,22%**. Median thời gian diagnostic khoảng **206 ms** trên máy audit.

Đây là phép đo chẩn đoán trên chunk benchmark; chưa bao gồm parser/chunker runtime, HTTP, history hoặc LLM. Không coi nó là benchmark end-to-end mới, cũng không so trực tiếp latency với máy benchmark cũ. Nó chứng minh việc thêm runtime orchestration đã làm thay đổi kết quả ngay cả khi giữ corpus cố định.

**Ảnh hưởng:** không thể gắn trực tiếp 82,22% / 2,36 ms cho luồng chat production. Người phỏng vấn hỏi cách tái hiện từ upload đến answer sẽ gặp các pipeline khác nhau.

**Sửa:** dùng chung ingestion và retrieval entry point cho sản phẩm và evaluation; cho CI gate đúng production mode. Phân biệt latency retrieval, time to first token và thời gian hoàn tất answer. Giữ benchmark so sánh thuật toán nhưng ghi rõ phạm vi.

### A2 — Cao: citation hiện chủ yếu là văn bản do LLM tạo

`backend/rag/load.py:72` làm mất ranh giới trang. Prompt yêu cầu `(Source: file_name)` tại `backend/rag/prompts.py:12`; chat SSE không gửi danh sách evidence có ID/trang/snippet. `ChatBubble.tsx` render Markdown thông thường. Kiểu `RetrievedDocument` có trường `page`, `chunkId`, `content` nhưng không được dùng để hiển thị evidence trong luồng chat hiện tại.

**Ảnh hưởng:** người dùng thấy tên nguồn nhưng chưa kiểm tra nhanh được câu trả lời dựa trên đoạn nào, trang nào. Đây là thiếu hụt ở giá trị cốt lõi của ứng dụng RAG.

**Sửa:** giữ metadata trang khi ingest, gửi evidence có cấu trúc từ backend, ánh xạ citation ID với evidence hợp lệ, cho bấm mở đoạn trích/trang. Không giao quyền quyết định provenance hoàn toàn cho LLM.

### A3 — Cao: reconnect có thể kết thúc thành công với câu trả lời thiếu

Tại `frontend/src/services/api.ts:465`, trường hợp stream mới không khớp prefix cũ ném lỗi. Nhưng `catch` ngay sau đó bắt mọi lỗi và bỏ qua như JSON chưa hoàn chỉnh.

Đã tái hiện bằng cách transpile module TypeScript trong bộ nhớ và mock `fetch`:

1. Stream đầu phát `Original answer ` rồi gặp lỗi mạng.
2. Stream retry phát `Different answer with complete citation (Source: test.pdf)` rồi `[DONE]`.
3. Kết quả: hai request; UI callback chỉ nhận `Original answer `; Promise vẫn resolve.

Playwright hiện kiểm tra replay với nội dung giống nhau nên không bắt trường hợp này. Backend append user message cho mỗi POST ở `backend/api/routes/chat.py:186`, chưa có request ID/idempotency key; retry còn có nguy cơ lặp lượt hỏi trên server.

**Sửa:** chỉ catch lỗi parse tại phạm vi parse; phát lỗi protocol ra ngoài. Chọn chiến lược rõ ràng: resume theo event ID hoặc đánh dấu answer bị gián đoạn và cho regenerate. Dùng request ID để retry không tạo thêm lượt hội thoại.

### A4 — Cao khi bật worker riêng: index thiếu cơ chế đồng bộ phiên bản giữa các process

`backend/rag/rag_chain.py:8` giữ store theo user trong bộ nhớ không có kiểm tra revision. `reload_vector_store()` chỉ cập nhật process gọi nó. Job RQ gọi indexing ở process worker; API không nhận invalidation. `load_vector_store()` tại `backend/rag/vector_store.py:434` chỉ tải artifact B2 khi metadata local chưa tồn tại.

**Tình huống có thể xảy ra:** API đã cache index, worker thêm tài liệu, job báo hoàn tất nhưng API tiếp tục retrieve từ bản cũ. Với worker khác nhau và cache local cũ, khóa Redis chỉ tuần tự hóa thao tác; nó không làm snapshot trở nên mới. Có nguy cơ ghi đè index dựa trên snapshot lỗi thời. Delete route cũng chưa dùng cùng khóa mutation với indexing job.

`_upload_to_b2()` tại `backend/rag/vector_store.py:110` còn bỏ qua exception và không xử lý giá trị `False` của `upload_file()`: trạng thái job hoàn tất chưa bảo đảm artifact đã bền vững trên B2.

Đây là phát hiện từ đọc code, chưa được tái hiện bằng deployment Redis/B2 nhiều host trong audit.

**Sửa:** version index theo user, publish snapshot đã hoàn tất một cách atomic, kiểm tra version ở reader và tải đúng snapshot. Dùng cùng khóa cho add/delete/reindex; fail job khi durable persistence thất bại. Kiểm thử API và worker ở các process riêng.

### A5 — Vừa: abstention chưa được giải quyết, metric citation chưa đo live answer

Repo công khai đúng hạn chế **0/10 unanswerable**. Diagnostic runtime cũng không từ chối câu nào trong nhóm này. `RETRIEVAL_CONFIDENCE_THRESHOLD` hiện chỉ được khai báo; không được dùng để quyết định từ chối. CI đặt `--min-unanswerable-accuracy=0.0`.

Citation precision/recall trong offline evaluation được tính từ `citation_samples`/reference answers, còn faithfulness là lexical overlap. Tài liệu evaluation đã giải thích điều này tương đối trung thực — nên giữ cách giải thích đó ở mọi chỗ giới thiệu kết quả.

**Ảnh hưởng:** benchmark chưa chứng minh answer thật có citation đúng hoặc có thể nói “không đủ dữ kiện”. 0% abstention của retriever cũng không có nghĩa là đã đo thấy 100% answer thật hallucinate.

**Sửa:** tách development/calibration và held-out test; đo answerability, citation correctness và evidence support trên generated answers. Thêm câu hỏi ngoài phạm vi và câu hỏi tiếng Việt phù hợp người dùng mục tiêu. Điều chỉnh prompt đang yêu cầu dùng context kể cả chỉ liên quan một phần.

## Tính chuyên nghiệp của cách giới thiệu và trải nghiệm

### A6 — Vừa: deployment thực tế và mô tả kiến trúc dễ tạo kỳ vọng khác nhau

Trong lần truy cập audit, [readiness live](https://novaaiagent-4.onrender.com/health/ready) trả:

```json
{
  "ready": true,
  "infrastructure": {
    "database": "local-json",
    "redis": "local-memory",
    "index_workers": "local-thread-pool",
    "object_storage": "optional-local-mode",
    "malware_scanner": "optional"
  }
}
```

README phần Deployment nói PostgreSQL đang persist state và Redis/RQ đang điều phối indexing. Code có hỗ trợ các adapter đó, và runbook có ghi cần provision thêm, nhưng bản hosted quan sát được đang dùng local fallback. `optional-local-mode` không chứng minh B2 không cấu hình; endpoint không probe B2 bắt buộc trong chế độ này. Không suy luận dữ liệu đã mất từ tín hiệu này.

**Sửa:** mô tả riêng “live demo configuration” và “supported production configuration”; hoặc triển khai và kiểm chứng cấu hình production đúng như mô tả. Không cần mua thêm hạ tầng chỉ để làm portfolio nếu chưa cần.

### A7 — Vừa: giao diện đầu tiên nhấn mạnh không khí công nghệ hơn bằng chứng sản phẩm

Đã xem màn hình login live và screenshot desktop được commit. Giao diện có bố cục, hierarchy và branding, nhưng dùng nhiều glow tím/cyan, gradient, grid, monospace label rất nhỏ, animation sơ đồ và các nhãn `SYSTEM ONLINE`, `ENCRYPTED`, `Nova protocol 2.1`. Chúng tạo cảm giác concept AI/SaaS; chưa cho người xem hiểu ngay tài liệu nào được hỏi và bằng chứng nào hỗ trợ câu trả lời.

Một số chi tiết làm giảm độ tin cậy:

- `LoginScreen.tsx:125,284` vẫn ghi `Hybrid evidence` và `BM25 + Vector` dù BM25 là default.
- `SYSTEM ONLINE` tại dòng 88 là text cố định, không phải trạng thái health đo được.
- `ENCRYPTED` không nói rõ phạm vi; nhãn hiện tại không chứng minh mã hóa đầu cuối.
- Các `<label>` tại dòng 167 chưa liên kết `htmlFor`/`id` với input.
- README dòng 18 gọi screenshot login là “authenticated document workspace”.
- `WelcomeScreen.tsx:28` đề xuất “Generate code”, ít gắn với nhiệm vụ đọc và kiểm tra tài liệu.

**Sửa:** giảm trang trí, tăng độ đọc được; đưa answer/evidence thành trọng tâm. Dùng một ví dụ có tài liệu thật, câu hỏi cụ thể và đoạn trích có thể mở. Bỏ nhãn kỹ thuật không tạo thêm thông tin; lấy retrieval mode từ cấu hình thực khi cần hiển thị. Hoàn thiện label semantics và kiểm tra keyboard sau đăng nhập.

Nhận xét trực quan trực tiếp trong audit giới hạn ở login; phần workspace được đọc code và kiểm tra bằng E2E mock, chưa walkthrough với tài khoản/provider thật.

### A8 — Vừa: người xem chưa có đường thử sản phẩm với ít công sức

Từ trang đầu, người xem phải đăng ký/đăng nhập, thêm tài liệu, chờ startup/indexing rồi mới thấy giá trị. Repo có demo recording config và kịch bản 60–90 giây, nhưng README chưa nhúng video workflow hoặc screenshot answer kèm evidence.

**Sửa:** cung cấp demo workspace chỉ đọc hoặc sandbox có corpus công khai sẵn; cho chọn 2–3 câu hỏi có nội dung cụ thể, gồm một câu ngoài phạm vi. Phân biệt rõ fixture demo và kết quả đo thật. Đặt video ngắn hoặc GIF workflow cạnh phần mở đầu README.

### A9 — Vừa: “private” cần được giải thích bằng đường đi dữ liệu

Auth và cách ly user là những phần có thật. Tuy nhiên, provider mặc định và demo là Groq; `backend/rag/llm_client.py` gửi prompt chứa context/history tới API Groq. “Private workspace” không tự đồng nghĩa tài liệu chỉ được xử lý trên thiết bị hoặc máy chủ riêng.

**Sửa:** nói rõ excerpt nào được gửi tới provider, có thể chọn Ollama như thế nào, ai sở hữu dữ liệu và cách xóa/export. Đây là nội dung giúp người dùng quyết định trước khi upload, không cần biến UI thành tài liệu triển khai.

## Những điểm đáng giữ

- Auth/session có rotating refresh cookie, access token trong memory và kiểm thử phục hồi session.
- Upload không chỉ kiểm tra extension; có quarantine, kiểm soát nội dung/parser và SSRF trong downloader.
- Có kiểm thử ownership, rate limit, persistence và luồng upload → index → SSE.
- Playwright có responsive/settings/reconnect/accessibility và visual regression.
- Benchmark có paper version, checksum, evidence span và khai báo hạn chế annotation. Việc so sánh BM25 với các phương pháp nặng hơn là chất liệu phỏng vấn tốt nếu scope đo khớp runtime.
- Có migration, runbook và health/readiness. Nên giảm lời khẳng định vượt phần đã vận hành, không bỏ toàn bộ những phần này.

## Thứ tự hoàn thiện đề xuất

| Ưu tiên | Việc làm | Điều kiện hoàn tất có thể kiểm tra |
| --- | --- | --- |
| 1 | Sửa reconnect và retry/idempotency | Prefix thay đổi phải báo interrupted hoặc restart rõ ràng; retry không lặp user turn |
| 2 | Đồng nhất ingestion/retrieval/evaluation | Benchmark chạy qua production entry point; có corpus/config hash và kết quả mới |
| 3 | Citation có thể kiểm chứng | Bấm citation mở đúng file, trang và snippet; citation ID phải thuộc evidence backend cấp |
| 4 | Hiệu chỉnh abstention | Có held-out questions, công bố trade-off giữa answerable recall và false answers |
| 5 | Chốt phạm vi triển khai | Live demo/runbook/README khớp nhau; nếu dùng worker riêng, kiểm chứng revision/invalidation và durable writes |
| 6 | Làm đường thử và chỉnh cách trình bày | Người xem thử câu hỏi trên tài liệu công khai mà không phải chuẩn bị tài liệu; README có workflow thật |

Không ưu tiên thêm agent, model, dashboard hay một lượt animation mới trước các việc trên. Một sản phẩm hẹp, có nguồn kiểm chứng được và mô tả đúng giới hạn sẽ tạo ấn tượng tốt hơn một danh sách công nghệ dài.

## Cách đưa vào portfolio

Giới thiệu là **“Ứng dụng hỏi đáp tài liệu cá nhân với streaming, user isolation và evaluation cho quyết định retrieval”**. Case study nên có: bài toán cụ thể, workflow thật, một quyết định kỹ thuật được đo đúng, failure case và cách xử lý, giới hạn còn lại.

BM25 có thể là một lựa chọn kỹ thuật hợp lý. Chất lượng portfolio nằm ở khả năng chứng minh lựa chọn đó bằng pipeline sản phẩm, không nằm ở số framework/model được liệt kê.
