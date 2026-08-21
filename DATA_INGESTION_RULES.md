# BỘ NGUYÊN TẮC CÀI ĐẶT & KIỂM TRA DỮ LIỆU (DATA INGESTION RULES)

Để hệ thống AIC 2026 Search hoạt động chính xác và không bao giờ gặp tình trạng "có kết quả nhưng không có ảnh", bạn cần tuân thủ nghiêm ngặt quy trình **4 bước đồng bộ** sau đây mỗi khi nạp dữ liệu (Batch mới, L22, L23...).

---

## QUY TẮC SỐ 1: NGUYÊN LÝ "HAI NỬA ĐỒNG BỘ"
Dữ liệu của hệ thống luôn bao gồm **2 nửa không thể tách rời**:
1. **Nửa Trí Tuệ (Features/Metadata)**: File `.npy` (CLIP/Faiss), `metadata.json`, `ocr.json`, v.v... Quyết định **việc tìm kiếm có ra kết quả hay không**.
2. **Nửa Hiển Thị (Keyframes Images)**: Các file `.jpg` nằm trong `Keyframes_L*.zip`. Quyết định **việc ảnh có hiển thị lên giao diện hay không**.

> [!WARNING]
> Nếu bạn chỉ cài "Nửa Trí Tuệ" (như bộ `clip-features...zip`), hệ thống sẽ **vẫn tìm ra** các Frame ID của L22, nhưng Frontend sẽ hiển thị **màn hình đen** vì thiếu "Nửa Hiển Thị" (`Keyframes_L22.zip`).

---

## QUY TẮC SỐ 2: QUY TRÌNH NẠP DỮ LIỆU (3 BƯỚC)

Mỗi lần nhận một lô dữ liệu (VD: L22), bạn phải:

### Bước 1: Ném TẤT CẢ các file zip vào `data/inbox`
Bạn không cần tự giải nén. Bạn **phải** đảm bảo trong thư mục `backend/data/inbox/` có đủ bộ:
- `Keyframes_L22.zip` (Ảnh hiển thị - RẤT QUAN TRỌNG)
- `clip-features-...zip` (Vector)
- `metadata-...zip` (Thông tin)
- `objects-...zip` / `ocr-...zip` (Nếu có)

### Bước 2: Chạy Script Giải Nén Thông Minh
Mở terminal tại thư mục `backend/` và chạy:
```bash
.\.venv\Scripts\python.exe scripts\ingest_zips.py
# HOẶC
.\.venv\Scripts\python.exe scripts\extract_zips.py
```
Hệ thống sẽ tự động phân loại: `.npy` vào `features/`, `.jpg` vào `static/keyframes/`, `.json` vào đúng chỗ.

### Bước 3: Đồng Bộ Vector (FAISS / Milvus)
Sau khi nén xong, bắt buộc chạy lại lệnh Build Index để nhận diện dữ liệu mới:
```bash
.\.venv\Scripts\python.exe scripts\sync_milvus_simple.py
# HOẶC
.\.venv\Scripts\python.exe -m app.services.kis_engine
```

---

## QUY TẮC SỐ 3: TỰ KIỂM TRA (SELF-CHECK) TRƯỚC KHI CHẠY WEB

Đừng bật Web vội! Hãy dùng lệnh sau để kiểm tra xem "Hai nửa" đã khớp nhau chưa:

**Kiểm tra số lượng ảnh:**
Đảm bảo thư mục `backend/static/keyframes/L22_*` ĐÃ XUẤT HIỆN và có chứa file `.jpg`.
Nếu không thấy thư mục này, nghĩa là bạn đã QUÊN bỏ file `Keyframes_L22.zip` vào inbox.

**Lệnh chẩn đoán nhanh:**
```bash
.\.venv\Scripts\python.exe scripts\audit_codebase.py
# HOẶC kiểm tra dữ liệu
.\.venv\Scripts\python.exe scripts\run_direct_search.py --mode KIS --query "L22" --top-k 1
```

---

## TỔNG KẾT LỖI HIỆN TẠI CỦA BẠN (TRƯỜNG HỢP L22)
1. Trong `inbox/` của bạn hiện tại **chỉ có `Keyframes_L21.zip`**.
2. Bộ `clip-features-32-aic25-b1.zip` (chứa Nửa Trí Tuệ của cả L21, L22, L23...) đã được giải nén.
3. Vì vậy, AI tìm thấy kết quả L22 rất tốt, nhưng Frontend không thể tải ảnh tĩnh từ thư mục `static/keyframes/L22_V001/` vì thư mục đó **chưa hề tồn tại**.

**Cách khắc phục NGAY BÂY GIỜ:**
Vui lòng tải file `Keyframes_L22.zip` (hoặc các file ảnh keyframe tương tự), copy nó vào `backend/data/inbox/`, sau đó chạy:
`.\.venv\Scripts\python.exe scripts\extract_zips.py`
Refresh lại Frontend, toàn bộ ảnh L22 sẽ hiển thị ngay lập tức!
