# Hướng Dẫn Cài Đặt AIC 2026 Toàn Tập (Từ A-Z)

Tài liệu này dành cho người **chưa cài đặt bất kỳ phần mềm nào** trên máy (máy tính trắng). Hệ thống AIC 2026 bao gồm 2 phần chính:
- **Backend (Python)**: Xử lý logic AI, thị giác máy tính, truy vấn Faiss Vector.
- **Frontend (Node.js/React)**: Giao diện tìm kiếm người dùng cuối.

---

## Phần 1: Cài Đặt Môi Trường Nền Tảng

Để chạy được dự án, bạn cần cài đặt 3 công cụ bắt buộc: **Git**, **Python**, và **Node.js**.

### 1.1. Cài Đặt Git (Dùng để tải code)
1. Truy cập [git-scm.com/download/win](https://git-scm.com/download/win).
2. Tải bản **64-bit Git for Windows Setup**.
3. Chạy file cài đặt, bấm **Next** liên tục cho đến khi hoàn tất (giữ nguyên mọi tuỳ chọn mặc định).

### 1.2. Cài Đặt Python (Dành cho Backend)
1. Truy cập [python.org/downloads](https://www.python.org/downloads/).
2. Tải bản Python mới nhất (Khuyến nghị **Python 3.10** hoặc **3.11**).
3. **⚠️ QUAN TRỌNG:** Khi mở file cài đặt, hãy tích vào ô **"Add Python to PATH"** (ở góc dưới cùng màn hình) trước khi bấm "Install Now".

### 1.3. Cài Đặt Node.js (Dành cho Frontend)
1. Truy cập [nodejs.org](https://nodejs.org/).
2. Tải bản **LTS (Long Term Support)** (ví dụ: v20.x).
3. Chạy file cài đặt và bấm **Next** liên tục cho đến khi hoàn tất.

*💡 Kiểm tra cài đặt thành công: Mở **PowerShell** và gõ:*
```powershell
git --version
python --version
node --version
npm --version
```
*(Nếu tất cả đều hiện ra phiên bản, chúc mừng bạn đã cài đặt nền tảng thành công!)*

---

## Phần 2: Tải Mã Nguồn & Cấu Hình Dữ Liệu

### 2.1. Clone Code Từ GitHub
Mở **PowerShell** tại thư mục bạn muốn lưu dự án (ví dụ `Desktop`) và chạy:
```powershell
git clone https://github.com/OreoAndJuliet/aic26-search.git
cd aic26-search
```

### 2.2. Chuẩn Bị Dữ Liệu (Quan Trọng)
Dự án cần có dữ liệu video, keyframes và đặc trưng vector (.npy) để có thể tìm kiếm.
1. Tại thư mục `aic26-search/backend`, bạn hãy tạo một thư mục tên là `data`.
2. Đưa toàn bộ các thư mục dữ liệu vào trong `data` theo cấu trúc sau:
```
backend/
└── data/
    ├── features/         # (Chứa các file .npy, ví dụ: L21_V001.npy)
    ├── keyframes/        # (Chứa thư mục ảnh, ví dụ: L21_V001/0.jpg)
    ├── map-keyframes/    # (Chứa các file CSV)
    ├── metadata/         # (Chứa file metadata json)
    └── videos/           # (Tùy chọn: Chứa video gốc)
```
3. Copy file `backend/.env.example` thành `backend/.env` (Nều cài tự động ở phần 3, hệ thống sẽ tự làm giúp bạn). Điền API Key Gemini vào file `.env` nếu bạn muốn dùng VQA.

---

## Phần 3: Cài Đặt Tự Động (One-Click Install)

Chúng tôi đã viết sẵn một script cài đặt toàn bộ mọi thứ chỉ bằng 1 cú click chuột.

1. Vào thư mục gốc `aic26-search`.
2. Nhấn **chuột phải** vào file `install_all.ps1`.
3. Chọn **"Run with PowerShell"**.

Script sẽ tự động:
- Cài đặt Virtual Environment (.venv) cho Python.
- Tải toàn bộ thư viện Backend (`pip install`).
- Cài đặt thư viện Frontend (`npm install`).

*Lưu ý: Nếu PowerShell báo lỗi màu đỏ cấm chạy script, hãy mở PowerShell quyền Admin và gõ lệnh: `Set-ExecutionPolicy RemoteSigned -Force` rồi thử lại.*

---

## Phần 4: Khởi Động Hệ Thống

Sau khi cài đặt xong, mỗi lần muốn sử dụng, bạn chỉ cần bật 2 cửa sổ PowerShell:

### Bước 4.1: Bật Backend Server
Mở PowerShell, trỏ vào thư mục `backend` và chạy file `start.bat`:
```powershell
cd backend
.\start.bat
```
*Đợi khoảng 30s cho hệ thống nạp Vector và Mô hình AI vào RAM. Khi thấy dòng `Uvicorn running on http://0.0.0.0:8000`, backend đã sẵn sàng.*

### Bước 4.2: Bật Frontend UI
Mở một cửa sổ PowerShell **mới**, trỏ vào thư mục `frontend` và chạy:
```powershell
cd frontend
npm run dev
```
*Giao diện người dùng sẽ hiện ra ở địa chỉ: http://localhost:5173*

---

## Phần 5: Tính Năng & Lưu Ý Khi Tìm Kiếm

1. **Truy Vấn Văn Bản (Text Search)**: Gõ mô tả cảnh vật, sự kiện.
2. **Truy Vấn Câu Hỏi VQA**: Nhấn chọn thẻ "VISUAL QA" trên giao diện. Gõ tên video (VD: `L22 Building`) vào ô bên trái, và câu hỏi (VD: `how many cars`) vào ô bên phải.
3. **Cập Nhật Dữ Liệu Nóng (Redo Vector)**: Nếu bạn mới copy thêm file `.npy` hoặc `keyframes` mới vào thư mục `data`, bạn không cần tắt server. Chỉ cần nhấn nút **"Redo Vector"** màu cam trên giao diện Web. Server sẽ nạp file mới vào bộ nhớ trong tích tắc!
4. **Tối Ưu Phần Cứng**:
   - Mặc định hệ thống tự phát hiện bạn có Card Đồ Hoạ (GPU) hay CPU để nạp model (Nếu có NVIDIA GPU, hãy cài thêm CUDA để tìm kiếm siêu tốc).
   - Backend được thiết kế bảo vệ chống Spam API (Circuit Breaker), nếu bạn đếm đối tượng, mô hình cục bộ Faster R-CNN sẽ được ưu tiên để vượt mọi giới hạn miễn phí!
