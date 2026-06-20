# Tài liệu các tính năng tuỳ chỉnh (nhánh landc_trading_view)

Tài liệu này tổng hợp các tính năng và thay đổi cốt lõi đã được bạn phát triển riêng trên nhánh `landc_trading_view` so với phiên bản gốc (upstream).

## 1. Chức năng Giao dịch Phái sinh (Futures Mode)
- **Tính năng chính:** Bổ sung chế độ đánh Futures bên cạnh giao dịch Spot (cơ sở) truyền thống.
- **Chi tiết kỹ thuật:**
  - Bổ sung cấu trúc dữ liệu (`schemas.py`) và logic giao dịch (`trader.py`) chuyên biệt cho thị trường Futures.
  - Hỗ trợ các khái niệm đặc thù của giao dịch phái sinh như: Lệnh Short (Bán khống), Đòn bẩy (Leverage), Take Profit (Chốt lời), Stop Loss (Cắt lỗ), và các mức DCA.
  - Tích hợp lựa chọn và tối ưu hóa **khung thời gian (Timeframe)** dành riêng cho Futures, nổi bật là bản cập nhật nâng cấp cho đánh ngắn hạn `"Short-term (1-2 Weeks)"`.
  - Nâng cấp logic của các Agent như Portfolio Manager và đội Risk Management để tranh luận và đưa ra chiến lược phù hợp với độ rủi ro cao của Futures.

## 2. Giao diện Web (Web Layout UI)
- **Tính năng chính:** Xây dựng một giao diện trực quan trên nền tảng Web thay cho giao diện dòng lệnh (CLI) mặc định.
- **Chi tiết kỹ thuật:**
  - Toàn bộ source code giao diện nằm trong thư mục `web/` (gồm backend `app.py` và frontend `index.html`, `script.js`, `styles.css`).
  - Giao diện giúp người dùng thao tác mượt mà, dễ dàng nhập liệu mã cổ phiếu/crypto và theo dõi luồng suy nghĩ của các AI Agents.
  - Bổ sung entry point `run_web.py` để khởi động nhanh server web và `requirements-web.txt` chứa thư viện cần thiết.

## 3. Hệ thống Báo cáo Tự động (Hermes Auto Report)
- **Tính năng chính:** Tự động hóa quá trình chạy AI phân tích và xuất báo cáo.
- **Chi tiết kỹ thuật:**
  - Bổ sung script `run_my_analysis.py` phục vụ việc tự động kích hoạt luồng phân tích. Tính năng này đóng vai trò như một "trợ lý" tự động cập nhật tình hình thị trường mà không cần người dùng thao tác tay liên tục.

## 4. Tài liệu & Ghi chú Chiến lược Cá nhân
- **Tính năng chính:** Lưu trữ các bí quyết và "điểm vàng" thời gian để chạy bot hiệu quả.
- **Chi tiết kỹ thuật:**
  - Cấu trúc lại và lưu trữ các ghi chú qua các file text như `thoigianxemtintuc.txt` và `phuhopkhunggio.txt`.
  - Chứa đựng các công thức quý giá về thời điểm cho AI quét dữ liệu (Ví dụ: 7-8h sáng thứ Hai để bắt nến Tuần, hay sáng hôm sau các ngày ra tin vĩ mô lớn như Non-farm, CPI, FOMC).
