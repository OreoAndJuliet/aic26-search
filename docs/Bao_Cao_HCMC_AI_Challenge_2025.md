# Báo cáo Tổng quan HCMC AI Challenge 2025 (Bảng A)

> [!NOTE]
> Báo cáo này tổng hợp đầy đủ các thông tin quan trọng nhất từ tài liệu đề thi và nền tảng đánh giá Codabench, bao gồm các mốc thời gian, định dạng nộp bài, phương pháp đánh giá và các nguồn tài nguyên tham khảo.

## 1. Giới thiệu chung
- **Tên cuộc thi:** Hội thi Thử thách Trí tuệ Nhân tạo (AI Challenge) Thành phố Hồ Chí Minh năm 2025.
- **Đối tượng (Bảng A):** Dành cho Học sinh Trung học phổ thông (THPT) hoặc tương đương.
- **Mục tiêu:** Thúc đẩy phong trào học tập, ứng dụng AI, đặc biệt hướng tới mục tiêu xây dựng đô thị thông minh tại TP.HCM.
- **Tổ chức bởi:** Sở Khoa học và Công nghệ (Sở KHCN) TP.HCM phối hợp cùng ĐHQG-HCM, Sở GD&ĐT, Thành Đoàn và Hội Tin học TP (HCA).

## 2. Các mốc thời gian (Timeline)

Quá trình thi vòng sơ tuyển được chia làm 4 giai đoạn chính trên Codabench:

| Giai đoạn | Thời gian bắt đầu (GMT+7) | Thời gian kết thúc (GMT+7) | Mô tả |
| :--- | :--- | :--- | :--- |
| **Lượt nộp thử nghiệm** | 09:00, 24/08/2025 | 23:59, 30/08/2025 | Dùng để test định dạng nộp bài, kiểm tra lỗi hệ thống Codabench. |
| **Lượt 1 (Round 1)** | 09:00, 31/08/2025 | 11:59, 31/08/2025 | Đề: `AIC25-Pack1-GroupA`. Public leaderboard chỉ tính điểm trên 50% test data. |
| **Lượt 2 (Round 2)** | 09:00, 07/09/2025 | 11:59, 07/09/2025 | Đề: `AIC25-Pack2-GroupA`. Public leaderboard chỉ tính điểm trên 50% test data. |
| **Lượt 3 (Round 3)** | 09:00, 14/09/2025 | 11:59, 14/09/2025 | Đề: `AIC25-Pack3-GroupA`. Public leaderboard chỉ tính điểm trên 50% test data. |

> [!IMPORTANT]
> Chỉ có **3 tiếng** làm bài trong mỗi Lượt chính thức (từ 09:00 sáng đến 11:59 trưa các ngày Chủ Nhật). Leaderboard công khai chỉ là điểm tạm thời (hiển thị 50%).

## 3. Quy cách làm bài và Nộp bài (Submission)

Cuộc thi yêu cầu đội thi giải quyết 3 dạng truy vấn. Kết quả của mỗi truy vấn phải được lưu dưới dạng **CSV**.

### 3.1. Các dạng truy vấn
1. **Textual Known Item Search (Textual-KIS):** Tìm đoạn video và frame tương ứng với văn bản.
   - **Định dạng CSV:** `<Video Filename>, <Frame Index>`
2. **Visual Question Answering (VQA):** Trả lời câu hỏi dựa trên nội dung video.
   - **Định dạng CSV:** `<Video Filename>, <Frame Index>, <Answer>`
   - **Quy tắc Answer:** Tối đa 100 ký tự (chấp nhận Tiếng Anh/Việt). 
   - *Lưu ý chuỗi:* Nếu đáp án có dấu phẩy `,`, ngoặc kép `"` hoặc xuống dòng, bắt buộc phải bao quanh bằng dấu ngoặc kép `"..."`. (Ví dụ: `"Con mèo, con chó"`). Dấu ngoặc kép bên trong thì phải escape bằng 2 dấu `""`. Tốt nhất là luôn bọc toàn bộ đáp án vào trong ngoặc kép cho an toàn.
3. **Temporal Retrieval and Alignment of Key Events (TRAKE):** Truy xuất chuỗi sự kiện theo thời gian.
   - **Định dạng CSV:** `<Video Filename>, <Frame ID_1>, <Frame ID_2>, ..., <Frame ID_N>`.
   - *Lưu ý:* Các Frame ID phải xếp theo trình tự thời gian xảy ra sự kiện và số lượng phải khớp với số lượng sự kiện truy vấn yêu cầu.

### 3.2. Quy định Format File
- **Đuôi file:** Bắt buộc là `.csv`. KHÔNG nộp `.xlsx`.
- **Giới hạn:** Tối đa 100 dòng (top 100 kết quả) cho mỗi truy vấn.
- **Tiêu đề (Header):** KHÔNG chứa dòng tiêu đề (dữ liệu nằm ngay dòng 1).
- **Encoding & Delimiter:** UTF-8, dấu phẩy `,`.

### 3.3. Cấu trúc đóng gói bài nộp
1. Tạo một thư mục có tên chính xác là `submission/`.
2. Bỏ tất cả các file CSV của các truy vấn vào thư mục này (VD: `query-1-kis.csv`, `query-2-qa.csv`...).
3. Nén thư mục `submission/` lại thành một file `.zip` (VD: `team_KHTN_round1.zip`).
4. Upload file `.zip` lên Codabench.

## 4. Cơ chế chấm điểm (Evaluation Metrics)

Điểm số cho mỗi bài nộp được tính bằng công thức **Mean of Top-k R-Scores**:

$$ Final Score = \frac{1}{5} \sum_{k \in \{1, 5, 20, 50, 100\}} \left(\max_{1 \le i \le k} \{R\text{-}Score(r_i)\}\right) $$

**Chi tiết tính R-Score:**
- **Textual-KIS:** Đúng cả tên video và frame index nằm trong vùng Ground Truth $[s, e] \rightarrow$ 1 điểm. Sai $\rightarrow$ 0 điểm.
- **VQA:** Phải đúng tên video, đúng frame index (nằm trong $[s, e]$) VÀ đúng câu trả lời (so sánh chính xác ngữ nghĩa) $\rightarrow$ 1 điểm. Sai $\rightarrow$ 0 điểm.
- **TRAKE:** Nếu đúng tên video, điểm tính theo tỉ lệ số Frame ID khớp với Ground Truth. Sai tên video $\rightarrow$ 0 điểm.

**Xếp hạng:** Tổng điểm 3 Lượt (Pack 1, 2, 3) cộng lại. Nếu bằng điểm, các đội sẽ được đồng hạng.

## 5. Luật lệ cuộc thi (Terms & Conditions)

> [!WARNING]
> Bất kỳ vi phạm nào cũng có thể dẫn đến việc huỷ bỏ kết quả.

- **Đội thi:** Tối đa 5 thành viên, phải đăng ký trước qua form BTC.
- **Tài khoản Codabench:** MỖI ĐỘI CHỈ DÙNG 1 TÀI KHOẢN DUY NHẤT. Tạo nhiều tài khoản ảo để gian lận hay submit nhiều lần sẽ bị loại. Tài khoản cần được BTC duyệt thông qua link form đăng ký.
- **Tính độc lập:** Các đội phải làm việc độc lập. Hành vi trao đổi, chép bài hay hợp tác giữa các đội bị nghiêm cấm.
- **Hạ tầng:** Tự lo phần cứng, phần mềm.
- **An toàn hệ thống:** Cấm mọi hình thức hack/DDoS hệ thống Codabench hay mạo danh đội khác.

## 6. Nguồn tài liệu tham khảo (Hệ thống & Tools)

Trong file Excel, BTC có đính kèm các nguồn tài nguyên nhằm giúp các đội xây dựng ứng dụng / hệ thống tìm kiếm:

- **Hệ thống đánh giá DRES (Distributed Retrieval Evaluation Server):** 
  - Đây là core backend server được dùng để chạy và đánh giá.
  - Github DRES: [dres-dev/DRES](https://github.com/dres-dev/DRES)
  - Ví dụ Client giao tiếp với DRES: [dres-dev/Client-Examples](https://github.com/dres-dev/Client-Examples)
- **Hệ thống truy xuất tham khảo (Reference Systems):**
  - Giới thiệu các hệ thống từ VBS 2025: [Video Browser Showdown 2025 Systems (Youtube)](https://www.youtube.com/watch?v=9GCXqSd7SGU)
  - Demo hệ thống truy xuất video Visione: [visione.isti.cnr.it](https://visione.isti.cnr.it/)
- **Kinh nghiệm các năm trước:** 
  - Vòng Chung kết 2025 (Clip giới thiệu/luật thi): [Vòng chung kết 2025](https://www.youtube.com/watch?v=UWgQFhm_MCA)
  - Tài liệu HCMAI 2024: [Link Drive HCMAI 2024](https://drive.google.com/file/d/1D_tXHNltV8RSeu_031jAYPmilPSd6-uP/view?usp=sharing)
