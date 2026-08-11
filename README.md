# OreoAndJuliet - AIC 2026 Video Retrieval System

Chào mừng toàn đội đến với dự án **OreoAndJuliet** phục vụ cho cuộc thi HCMC AI Challenge 2026. Dưới đây là hướng dẫn từ A-Z để một thành viên mới có thể kéo code về máy, cài đặt môi trường và bắt đầu lập trình.

---

## 🛠 Yêu cầu phần mềm (Prerequisites)
Trước khi bắt đầu, hãy đảm bảo máy tính của bạn đã cài đặt các phần mềm sau:
1. **[Git](https://git-scm.com/downloads)** - Dành cho quản lý mã nguồn.
2. **[Node.js](https://nodejs.org/en/download/)** (Bản LTS) - Dành cho team Frontend (chạy React/Vite).
3. **[Python 3.10+](https://www.python.org/downloads/)** - Dành cho team Backend & AI. Khuyến nghị sử dụng Miniconda hoặc venv.

---

## 🚀 Hướng dẫn Cài đặt & Chạy dự án (Quick Start)

### Bước 1: Kéo mã nguồn về máy (Clone)
Mở Terminal (hoặc Git Bash / Command Prompt) và chạy lệnh:
```bash
git clone https://github.com/OreoAndJuliet/aic26-search.git
cd aic26-search
```

### Bước 2: Khởi động Frontend (React + Vite)
Team FE hoặc bất kỳ ai muốn xem giao diện thì làm theo bước này. Mở một Tab Terminal mới:
```bash
cd frontend
npm install       # Chỉ cần chạy lần đầu để tải các thư viện
npm run dev       # Khởi động server Frontend
```
👉 Sau đó, mở trình duyệt và truy cập: **http://localhost:5173**

### Bước 3: Khởi động Backend (FastAPI)
Mở một Tab Terminal khác (giữ Frontend vẫn chạy):
```bash
cd backend

# Khởi tạo môi trường ảo Python (Virtual Environment)
python -m venv .venv

# Kích hoạt môi trường ảo:
# - Trên Windows:
.venv\Scripts\activate
# - Trên Mac/Linux:
source .venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt

# Chạy server Backend
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
👉 API Server sẽ chạy tại: **http://127.0.0.1:8000**
👉 Xem tài liệu API (Swagger): **http://127.0.0.1:8000/docs**

---

## 🤝 Quy trình Cập nhật & Đẩy code (Git Workflow)

Để tránh xung đột code (conflict) ảnh hưởng đến người khác, mọi thành viên **BẮT BUỘC** làm theo quy trình sau mỗi khi muốn viết code mới:

### 1. Luôn cập nhật code mới nhất trước khi làm việc
```bash
git checkout main
git pull origin main
```

### 2. Không code trực tiếp trên nhánh `main`, hãy tạo nhánh riêng!
Ví dụ, bạn đang làm tính năng giỏ hàng cho frontend:
```bash
git checkout -b fe/cart-feature
```
*(Tên nhánh nên tuân theo cú pháp `nhóm/tên-chức-năng`, ví dụ: `be/setup-faiss`, `ai/train-clip`)*

### 3. Lưu lại code khi hoàn thành (Commit & Push)
Khi bạn đã test kỹ code trên máy mình và muốn đẩy lên mạng:
```bash
# Thêm toàn bộ các file đã thay đổi
git add .

# Tạo ghi chú cho thay đổi đó (ngắn gọn, rõ ý)
git commit -m "feat: thêm chức năng giỏ hàng bên sidebar"

# Đẩy nhánh của bạn lên GitHub
git push origin fe/cart-feature
```

### 4. Gộp code (Tạo Pull Request)
- Lên trang GitHub của dự án.
- Bạn sẽ thấy nút xanh **"Compare & pull request"**. Bấm vào đó.
- Nhờ Leader hoặc một bạn khác review code và bấm gộp (Merge) vào nhánh `main`.

---

## 📚 Tài liệu tham khảo thêm
- [CONTRIBUTING.md](./CONTRIBUTING.md): Phân chia nhiệm vụ cụ thể của Giai đoạn 1 và 2.
- [Dac_Ta_AIC_2026.docx](./Dac_Ta_AIC_2026.docx): Tài liệu đặc tả yêu cầu chi tiết từ BTC.
psh:

$payload = @{
    type     = "VQA"
    text     = "đoàn người đang di chuyển"
    question = "What logo is shown?"
    top_k    = 5
} | ConvertTo-Json -Compress

$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($payload)

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/search" `
                  -Method Post `
                  -ContentType "application/json; charset=utf-8" `
                  -Body $utf8Body | ConvertTo-Json -Depth 8
