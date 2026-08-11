# TÀI LIỆU ĐẶC TẢ HỆ THỐNG VÀ GIAO ƯỚC KỸ THUẬT (PRD & TECH SPEC)
**Dự án:** HCMC AI Challenge 2025 - Phân hệ Tìm kiếm Video (Interactive Video Retrieval)
**Vai trò:** Nhóm Frontend & Nhóm Backend/AI

> [!NOTE]
> Tài liệu này được soạn thảo dưới góc nhìn của một Technical Leader & Business Analyst. Mục đích là tạo ra ranh giới công việc rõ ràng, thiết lập các "Giao ước bắt buộc" (Contracts) giữa Frontend và Backend, đồng thời trao quyền tự chủ tối đa về mặt công nghệ cho từng team.

---

## 1. MỤC TIÊU CỐT LÕI (CORE OBJECTIVES)

Hệ thống phải giúp con người giải quyết 3 dạng truy vấn (Textual-KIS, VQA, TRAKE) nhanh nhất có thể trong thời gian 3 tiếng.
- **Tốc độ:** Truy vấn từ Backend trả về Frontend phải dưới **1 giây**.
- **Tính chính xác:** Hiển thị đúng frame ảnh, đúng timeline để người dùng xác nhận.
- **Tính tự động ở khâu nộp bài:** Bấm 1 nút, hệ thống tự động sinh ra file `[Tên Truy Vấn].csv` và gói vào `submission.zip` chuẩn Codabench không cần sửa tay.

---

## 2. PHÂN QUYỀN VÀ TỰ DO CÔNG NGHỆ (TEAM BOUNDARIES & FREEDOM)

### 2.1. Nhóm Frontend (Tồn tại chủ yếu ở Giai đoạn 1 & 2)
**Mục tiêu:** Xây dựng một giao diện thân thiện, không giật lag khi render hàng trăm hình ảnh cùng lúc.
- **Tự do công nghệ:** Các bạn được toàn quyền chọn React, Vue, Svelte, Angular, hoặc thậm chí Vanilla JS tuỳ thích. Chọn UI Framework nào cũng được (Tailwind, Material, AntD,...).
- **Yêu cầu bắt buộc:**
  - Phải có cơ chế lazy-load hình ảnh (không tải toàn bộ ảnh cùng lúc để tránh sập trình duyệt).
  - Phải có tính năng "Preview Video" (xem đoạn video ngắn xung quanh frame ảnh vừa tìm được).
  - Phải có một "Giỏ hàng" (Cart) để lưu tạm các đáp án được chọn trước khi xuất file CSV.

### 2.2. Nhóm Backend / AI (Xuyên suốt dự án)
**Mục tiêu:** Xử lý hàng chục GB dữ liệu đặc trưng (CLIP, Faster R-CNN), lưu trữ và truy vấn thần tốc.
- **Tự do công nghệ:** Các bạn tự do chọn ngôn ngữ (Python, Go, Node.js...) và Vector Database (FAISS, Milvus, Qdrant...). Tự do sử dụng các mô hình AI từ CLIP, Qwen-VL, Gemini,...
- **Yêu cầu bắt buộc:** 
  - Đảm bảo API luôn sẵn sàng (High Availability) trong lúc thi.
  - Xử lý mượt các request đa luồng.
  - Trả về đúng format JSON như đã giao ước (bên dưới) để Frontend không bị lỗi.

---

## 3. LỘ TRÌNH THỰC HIỆN (PHASES)

### Giai đoạn 1: Base Retrieval & UI Foundation (Tuần 1-2)
- **Frontend:** Dựng Layout giao diện gồm: Ô search, Grid hiển thị ảnh kết quả, Sidebar chứa danh sách "Đáp án đã chọn". Gọi thử API Mockup.
- **Frontend:** Bổ sung ô nhập "Câu hỏi" cho dạng VQA. Xây dựng UI cho dạng TRAKE (kéo thả hoặc chọn chuỗi sự kiện theo thứ tự). Hoàn thiện nút "Export to Codabench ZIP".
- **Backend:** Setup Vector DB, nạp dữ liệu CLIP `.npy` vào. Xây dựng API `/search` cơ bản (Textual-KIS). Trả về mock data cho Frontend test.

### Giai đoạn 2: VLM Integration & Advanced Features (Tuần 3-4)

- **Backend:** Tích hợp mô hình VLM (để trả lời câu hỏi VQA). Viết thuật toán DTW/HMM để căn chỉnh thời gian cho dạng TRAKE.
- **Chuyển giao:** Nhóm Frontend (sau khi chốt xong UI) sẽ hòa nhập cùng Backend để phụ giúp viết scripts tiền xử lý dữ liệu, tối ưu mô hình AI, và làm testing.

### Giai đoạn 3: Thực chiến (Mock Test)
- Đưa hệ thống vào chạy thử nghiệm với 50% dữ liệu thực. Đo lường tốc độ, fix bugs khẩn cấp.

---

## 4. GIAO ƯỚC BẮT BUỘC (API & DATA CONTRACTS)

> [!IMPORTANT]
> Đây là phần **KHÔNG ĐƯỢC PHÉP THAY ĐỔI** trừ khi cả 2 team cùng họp và thống nhất. Backend phải tuân thủ chuẩn đầu ra, Frontend phải tuân thủ chuẩn đầu vào.

### 4.1. Quy ước Phục vụ File Tĩnh (Static Files)
Backend cần mở một server tĩnh (Static File Server - ví dụ qua Nginx hoặc thư mục `static` của FastAPI) để host toàn bộ ảnh Keyframes và Video proxy (video dung lượng thấp).
- **URL Ảnh:** `http://<backend_ip>/keyframes/<video_name>/<frame_id>.jpg`
- **URL Video:** `http://<backend_ip>/videos/<video_name>.mp4`

### 4.2. API 1: Tìm kiếm Textual-KIS & VQA
**Endpoint:** `POST /api/search`

**Request Body (Frontend gửi):**
```json
{
  "query_type": "KIS", // Có thể là "KIS" hoặc "VQA"
  "text": "Một người đàn ông đang đạp xe",
  "question": "", // Dành cho VQA (vd: Quần áo màu gì?)
  "top_k": 100
}
```

**Response Body (Backend trả về):**
```json
{
  "status": "success",
  "data": [
    {
      "video_name": "L01_V001",
      "frame_index": 1500,
      "score": 0.95,
      "answer": "", // Nếu là VQA, trả về đáp án text ở đây (vd: "Màu đỏ")
      "thumbnail_url": "http://<ip>/keyframes/L01_V001/1500.jpg"
    }
    // ... 99 items khác
  ]
}
```

### 4.3. API 2: Tìm kiếm TRAKE (Chuỗi sự kiện)
**Endpoint:** `POST /api/search_trake`

**Request Body:**
```json
{
  "events": [
    "Vận động viên bắt đầu chạy",
    "Vận động viên nhảy lên sào",
    "Vận động viên rơi xuống đệm"
  ],
  "top_k": 10
}
```

**Response Body:**
```json
{
  "status": "success",
  "data": [
    {
      "video_name": "L05_V120",
      "score": 0.88,
      "frame_sequence": [
         {"frame_index": 500, "thumbnail_url": ".../500.jpg"},
         {"frame_index": 650, "thumbnail_url": ".../650.jpg"},
         {"frame_index": 800, "thumbnail_url": ".../800.jpg"}
      ]
    }
  ]
}
```

### 4.4. Cấu trúc Output Cuối Cùng (Bắt buộc)
Frontend có trách nhiệm thiết kế logic để khi người dùng ấn **Export**, hệ thống tự động sinh ra một file `.zip` chứa các file `.csv` không có dòng Header, đúng chuẩn:
- **KIS:** `L01_V001, 1500`
- **VQA:** `L01_V001, 1500, "Màu đỏ"` (Luôn bọc answer trong ngoặc kép).
- **TRAKE:** `L05_V120, 500, 650, 800`

---
*Văn bản này đóng vai trò là "hiến pháp" cho dự án. Chúc hai nhóm phối hợp nhịp nhàng và bùng nổ tại HCMC AI Challenge 2025!*
