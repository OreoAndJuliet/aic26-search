# Hướng dẫn Phối hợp & Kế hoạch làm việc (CONTRIBUTING)

Chào mừng các thành viên của đội tham gia dự án HCMC AI Challenge 2026. File này hướng dẫn luồng làm việc chung và nhiệm vụ cụ thể cho từng nhóm.

---

## 1. Quy trình làm việc với Git

Chúng ta sẽ sử dụng Git theo mô hình **Feature Branch**.
1. **Lấy code mới nhất:**
   ```bash
   git checkout main
   git pull origin main
   ```
2. **Tạo nhánh mới để làm việc:**
   ```bash
   # Tên nhánh: [fe/be]/[tên-tính-năng]
   # Ví dụ: fe/search-ui hoặc be/setup-faiss
   git checkout -b fe/search-ui
   ```
3. **Lưu và đẩy code lên (Commit & Push):**
   ```bash
   git add .
   git commit -m "feat: design search bar UI"
   git push origin fe/search-ui
   ```
4. **Cập nhật nhánh hiện tại với main (tránh conflict):**
   ```bash
   git checkout fe/search-ui
   git merge main
   ```
5. **Gộp code:** Mở Pull Request / Merge Request trên nền tảng (GitHub/GitLab) để Leader duyệt.

---

## 2. Kế hoạch cụ thể cho Nhóm FRONTEND

Nhóm Frontend đóng vai trò sống còn trong 2 tuần đầu tiên để tạo ra giao diện "Human-in-the-loop".

### Giai đoạn 1 (Ngay lập tức)
**Mục tiêu:** Xây dựng xong bộ khung giao diện để Backend có chỗ cắm API vào.
- **Bước 1:** Khởi tạo project React bằng Vite trong thư mục `frontend/`.
  ```bash
  cd frontend
  npm create vite@latest . -- --template react-ts
  npm install
  ```
- **Bước 2:** Dựng **Màn hình Tìm kiếm (Search View)**. Cần 1 ô input to, 1 nút search, 1 dropdown chọn loại truy vấn (KIS, VQA, TRAKE).
- **Bước 3:** Dựng **Lưới Hình Ảnh (Grid View)**. Tự code cứng (Mock data) khoảng 20 bức ảnh vào mảng JSON để hiển thị ra màn hình dạng lưới (Pinterest layout). Yêu cầu ảnh không vỡ, cuộn mượt.
- **Bước 4:** Dựng **Modal Video Player**. Bấm vào ảnh nào thì hiện cái popup phát 1 video mẫu cục bộ (`<video>` tag của HTML5).

### Giai đoạn 2 (Tuần 3)
- Gắn API thực tế gọi tới Backend (Dùng Axios hoặc Fetch).
- Dựng UI "Giỏ hàng" (Sidebar lưu các kết quả đúng).
- Viết logic tạo file ZIP & CSV khi bấm nút "Export Codabench". (Sử dụng thư viện `jszip`).
- Bàn giao UI, chuyển sang phụ team AI test dữ liệu.

---

## 3. Kế hoạch cụ thể cho Nhóm BACKEND
- **Giai đoạn 1:** Khởi tạo FastAPI trong `backend/`. Thiết lập FAISS. Public API `/api/v1/search` trả về JSON giả cho FE làm việc. Viết script nạp file `.npy` vào RAM.
- **Giai đoạn 2:** Gọi thực tế mô hình CLIP (hoặc gửi request tới server AI nội bộ). Host folder `static/` chứa hàng triệu ảnh keyframes ra port 8000.
- **Giai đoạn 3:** Tích hợp VLM để giải bài VQA. Xử lý thuật toán căn thời gian (TRAKE).

Chúc cả team phối hợp tốt và đạt giải cao! 🏆
