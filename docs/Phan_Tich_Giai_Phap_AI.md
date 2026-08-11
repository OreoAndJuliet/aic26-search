# Phân tích Giải pháp AI - HCMC AI Challenge 2026

Để giải quyết bài toán của cuộc thi (đạt R-Score cao nhất trong thời gian giới hạn 3 tiếng), bạn cần xây dựng một **Hệ thống Truy xuất Video (Video Retrieval System)**. Dưới đây là phân tích chi tiết về cách thiết kế AI dựa trên dữ liệu BTC cung cấp.

## 1. Khai thác tài nguyên dữ liệu của BTC

BTC đã "làm giúp" phần nặng nhất là trích xuất đặc trưng. Cách chúng ta dùng AI sẽ xoay quanh việc tận dụng các file này:

- **CLIP Features (`.npy`):** Đây là "xương sống". Mô hình `clip-ViT-B-32` của OpenAI có khả năng đưa cả Văn bản (Text) và Hình ảnh (Image) vào cùng một không gian vector toán học. Khung hình nào có nội dung giống với đoạn văn bản thì khoảng cách giữa 2 vector của chúng sẽ rất gần nhau.
- **Objects JSON (Faster R-CNN):** Rất giá trị cho các câu hỏi chi tiết. Ví dụ, nếu truy vấn là "tìm cảnh có 3 chiếc xe hơi", thay vì phụ thuộc hoàn toàn vào CLIP (CLIP đếm số lượng rất kém), bạn có thể filter/đếm số lượng bounding box `car` trong file JSON.
- **Metadata:** Dùng để tìm kiếm bằng từ khoá truyền thống (keyword-based search). Thường các video trên YouTube sẽ có tiêu đề và mô tả chứa bối cảnh lớn.

---

## 2. Chiến lược xử lý từng dạng truy vấn

### 2.1. Textual KIS (Tìm video & frame qua văn bản)
**Mục tiêu:** Nhập mô tả $\rightarrow$ Trả ra `video_id` và `frame_id`.

* **Giải pháp Cốt lõi (Zero-shot Retrieval):**
  1. Xây dựng một Vector Database (như **FAISS**, **Milvus** hoặc **Qdrant**) và nạp toàn bộ CLIP features `.npy` của BTC vào.
  2. Khi có câu truy vấn (query), đưa câu đó qua mô hình text encoder của CLIP (`clip-ViT-B-32`) để lấy vector văn bản. Dịch tiếng Việt sang tiếng Anh trước khi đưa vào (vì CLIP bản gốc train chủ yếu bằng tiếng Anh).
  3. Tính **Cosine Similarity** giữa vector văn bản và kho vector hình ảnh.
  4. Trả về Top $K$ kết quả có điểm similarity cao nhất.
* **Tối ưu (Reranking):** Lọc lại kết quả bằng cách kiểm tra file `Objects JSON` xem khung hình đó có chứa vật thể được nhắc đến trong câu truy vấn hay không để tăng độ chính xác.

### 2.2. VQA (Hỏi - Đáp trên Video)
**Mục tiêu:** Nhập câu hỏi $\rightarrow$ Tìm frame $\rightarrow$ Suy luận ra Câu Trả Lời.

Dạng này yêu cầu sự kết hợp giữa hệ thống Retrieval (truy xuất) và VLM (Vision-Language Model).
* **Bước 1 (Retrieval):** Chuyển bối cảnh câu hỏi thành câu trần thuật, dùng phương pháp của Textual KIS để tìm ra đoạn video/frame chứa sự kiện đó.
* **Bước 2 (Answering):** 
  - Đưa frame (hoặc một vài frame lân cận) vừa tìm được cùng với câu hỏi ban đầu vào một mô hình VLM.
  - Các VLM mạnh hiện nay (mở/API) có thể kể đến: **Qwen-VL, LLaVA, Gemini 1.5 Flash/Pro, GPT-4o**.
  - Yêu cầu VLM sinh ra câu trả lời thật ngắn gọn (dưới 100 ký tự).
  - *Mẹo đếm số lượng:* Nếu câu hỏi là "Có bao nhiêu X?", hãy dùng script Python đọc file `Objects JSON` của frame đó, đếm số nhãn X để trả lời thay vì hỏi VLM (vì VLM có thể đếm sai (hallucinate)).

### 2.3. TRAKE (Truy xuất và căn chỉnh chuỗi sự kiện)
**Mục tiêu:** Tìm 1 video và chỉ định chính xác một chuỗi frame theo đúng thứ tự thời gian ($T_1 < T_2 < ... < T_n$).

Đây là dạng câu hỏi khó nhất (Temporal Action Localization).
* **Bước 1 (Tìm Video):** Dùng từ khoá tổng quan của toàn bộ sự kiện để tìm ra video_id đúng. (VD: "Cảnh nhảy sào").
* **Bước 2 (Temporal Alignment):** 
  - Tách sự kiện thành $N$ truy vấn nhỏ ($E_1, E_2, ..., E_N$). Mã hoá $N$ truy vấn này thành $N$ vector CLIP text.
  - Lấy toàn bộ CLIP image features của video tìm được ở Bước 1 (theo đúng trình tự thời gian).
  - Sử dụng thuật toán **Dynamic Time Warping (DTW)** hoặc **Hidden Markov Model (HMM)** để tìm ra một chuỗi $N$ frame khớp nhất với $N$ text vector, với điều kiện thời gian tịnh tiến ($t_1 < t_2 < ... < t_n$).

---

## 3. Kiến trúc Hệ thống đề xuất cho Cuộc thi

Để thi tốt trong 3 tiếng, đội của bạn không nên chỉ code script chạy Terminal, mà cần một **giao diện web (UI)**. Giao diện này sẽ là nơi con người và AI cùng làm việc (Human-in-the-loop).

1. **Giao diện (Frontend - React/Vue):**
   - Ô nhập câu truy vấn.
   - Trình duyệt ảnh (hiển thị Grid các frame tìm được).
   - Module xem video xung quanh frame đó (rất quan trọng để check xem frame đó có thực sự nằm trong một diễn biến đúng như mô tả không).
   - Nút "Thêm vào danh sách Submit".
2. **Backend (Python - FastAPI):**
   - Xử lý các request dịch ngôn ngữ (Google Translate API) $\rightarrow$ CLIP Embedding.
   - Giao tiếp với **FAISS / Milvus** để query kết quả thần tốc ($< 1$ giây).
   - Gọi API (Gemini/OpenAI) để sinh câu trả lời cho phần VQA.
3. **Module Xuất File:** Khi hết thời gian, có nút bấm tự động xuất định dạng `.csv` không header và nén `.zip` đúng chuẩn Codabench để nộp.

> [!TIP]
> **Điểm mấu chốt:** BTC cung cấp mô hình Faster R-CNN và CLIP. Tuy nhiên, nếu hạ tầng (GPU) đội bạn cho phép, bạn có thể chạy song song một bộ trích xuất đặc trưng mới bằng các mô hình hiện đại hơn (như **BLIP-2** hoặc **SigLIP**) lên toàn bộ thư mục Keyframes. Sử dụng Multi-model ensemble (kết hợp điểm số từ CLIP và SigLIP) sẽ đẩy R-Score lên cực kỳ cao.
