# HCMC AI Challenge 2026 - Video Retrieval System

Hệ thống Tìm kiếm Video tương tác (Interactive Video Retrieval) dành cho cuộc thi HCMC AI Challenge 2026.

## Cấu trúc thư mục (Monorepo)

- `docs/`: Tài liệu, đặc tả hệ thống, báo cáo. Đọc file `Dac_Ta_AIC_2026.docx` hoặc các file .md để nắm yêu cầu hệ thống.
- `frontend/`: Source code của Web UI (React/Vue). Nơi team Frontend làm việc chính.
- `backend/`: Source code của Server AI, API, Vector DB (FastAPI/Python). Nơi team Backend làm việc.
- `scripts/`: Các đoạn script tự động hóa (VD: gen docs, clone data).
- `research/`: Thư mục thử nghiệm mô hình, prompt, Jupyter Notebook của AI team.
- `tests/`: Chứa các script test hệ thống (sẽ viết sau).

## Hướng dẫn cài đặt cơ bản

### Dành cho Frontend
1. Cài đặt [Node.js](https://nodejs.org/).
2. Trỏ vào thư mục `frontend/`.
3. (Chờ team tạo base project Vite, sau đó chạy `npm install` và `npm run dev`).

### Dành cho Backend
1. Cài đặt Python 3.10+ (khuyến nghị dùng Conda/Miniconda).
2. Trỏ vào thư mục `backend/`.
3. (Chờ team setup requirements.txt, sau đó chạy `pip install -r requirements.txt`).

## Quy trình làm việc (Git)

Đọc file [CONTRIBUTING.md](CONTRIBUTING.md) để biết chi tiết nhiệm vụ và cách dùng Git phối hợp trong team.