# Đèn ngủ cảm biến chuyển động: kịch bản và tự đánh giá

Dựng: `python3 make_video.py scripts/den-ngu-cam-bien.json`
Ra 3 bản (chỉ khác 3 giây đầu) để A/B test:
- `output/den-ngu-cam-bien.mp4`: hook A (bản chính)
- `output/den-ngu-cam-bien-hookB.mp4`
- `output/den-ngu-cam-bien-hookC.mp4`

> Giá ~40K và các tính năng (sạc USB, ánh vàng, dán được) là mô tả chung của dòng
> sản phẩm này. **Phải đối chiếu với đúng mẫu đang gắn link** rồi sửa lời thoại nếu khác.

## 1. Ba hook (3 giây đầu)

Chấm 1–5 theo 5 tiêu chí: dừng lướt / tò mò / đồng cảm / đúng tệp người mua / vừa 3 giây.

| Hook | Lời đọc | Công thức | Điểm | Nhận xét |
|---|---|---|---|---|
| **A** | "Đừng bật đèn phòng lúc hai giờ sáng nữa!" | Mệnh lệnh phủ định + thời điểm cụ thể | 5/5/4/3/5 = **22** | Câu cấm gây phản xạ "tại sao?". "2 giờ sáng" ai cũng từng trải qua. Hình ảnh bóng đèn bật sáng đúng lúc đọc "đừng bật đèn" tạo đối lập, giữ mắt. |
| B | "Bốn mươi nghìn thôi, mà cả nhà tôi đêm nào cũng dùng." | Sốc giá + bằng chứng dùng thật | 4/3/3/3/4 = 17 | Nói giá ngay nên nghe giống quảng cáo, người xem dễ lướt. Hợp hơn khi trang đã có follower tin tưởng. |
| C | "Nhà có ông bà hay con nhỏ thì phải xem cái này." | Gọi đúng tệp khách | 3/3/4/5/4 = 19 | Lọc đúng người mua (mua tặng bố mẹ) nhưng "phải xem cái này" là câu mồi quen, độ tò mò thấp. |

**Chọn A làm bản chính.** Nên đăng cả 3 bản cách nhau vài ngày, so sánh tỉ lệ xem qua 3 giây.
Bản thắng là công thức hook cho các video sau.

## 2. Cấu trúc: AIDA kết hợp PAS

| Giây | Khối | Mục đích | Nội dung |
|---|---|---|---|
| 0–3 | Hook | Dừng lướt | Hook A |
| 3–6 | A: Problem (PAS) | Người xem thấy mình trong đó | Nửa đêm mò công tắc, vấp chân |
| 6–9 | A: Agitate (PAS) | Khoét sâu nỗi đau | Bật đèn to thì chói mắt, cả nhà tỉnh giấc |
| 9–15 | I: Solution | Giới thiệu sản phẩm + giá | Đèn cảm biến ~40K, dán được nhiều chỗ |
| 15–20 | D: Lợi ích | Lợi ích, không chỉ tính năng | Tự sáng/tắt, ánh vàng không chói |
| 20–24 | D: Ai cần | Mở rộng lý do mua (mua tặng) | Ông bà đỡ lo té ngã, sạc USB |
| 24–29 | D: Nhược điểm thật | Tạo niềm tin | Chỉ đủ soi đường, không đọc sách được |
| 29–33 | A: Action | Chốt + khẩn cấp | Link bình luận ghim, đang giảm giá, lưu lại |

## 3. Kỹ thuật giữ chân người xem đã áp dụng

- Đổi cảnh nền mỗi 1,5–2,5 giây (17 clip Pixabay chọn tay theo ID, không để máy chọn ngẫu nhiên).
- Phụ đề karaoke: từ đang đọc tô vàng, ngắt dòng theo dấu câu.
- Thanh tiến trình vàng ở đáy, người xem thấy video ngắn nên xem tiếp.
- Hook có zoom nhẹ và cảnh đèn bừng sáng ở giây thứ 1.
- Cắt khoảng lặng cuối mỗi câu của giọng đọc, tổng 33 giây (Reels nên dưới 35 giây).
- Kết bằng câu "lưu lại": lượt lưu là tín hiệu mạnh với thuật toán.

## 4. Tự đánh giá kịch bản

| Tiêu chí | Điểm /10 | Ghi chú |
|---|---|---|
| Hook | 8 | Mạnh về câu chữ. Sẽ đạt 10 nếu cảnh đầu là chính chiếc đèn bật sáng dưới gầm giường. |
| Nỗi đau rõ ràng | 9 | Cụ thể, ai cũng gặp. |
| Lợi ích thay vì tính năng | 8 | Có "không đánh thức ai", "đỡ lo té ngã". |
| Độ tin cậy | 7 | Có nhược điểm thật. Thiếu cảnh quay sản phẩm thật nên vẫn giống video stock. |
| Lời kêu gọi hành động | 8 | Rõ ràng, có lý do mua ngay. Nên thêm giá thật khi đã kiểm tra. |
| Khớp hình với lời | 6 | Pixabay **không có** cảnh đèn cảm biến thật. Cảnh "40K" đang dùng bóng đèn treo minh họa. |
| **Tổng** | **46/60** | |

**Điểm yếu lớn nhất: không có cảnh quay sản phẩm thật.** Người xem Reels mua hàng khi thấy
chính món đồ hoạt động. Cách nâng cấp nhanh nhất:
1. Quay bằng điện thoại 3 cảnh, mỗi cảnh 3–5 giây (quay dọc, phòng tối):
   tay đưa qua và đèn bật, đèn dưới gầm giường lúc chân bước xuống, đèn trên cầu thang.
2. Lưu vào `assets/clips/` rồi thay vào JSON, ví dụ `{"file": "assets/clips/den-bat.mp4"}`
   (đặt ở hook A và cảnh "Đèn cảm biến chuyển động").
3. Dựng lại bằng lệnh ở đầu file.

Nhạc nền: để trống, nên chọn nhạc thịnh hành ngay trong Facebook lúc đăng
(nhạc có bản quyền trong app, giúp tăng tiếp cận). Có thể thêm `"bgm": "đường/dẫn.mp3"` vào JSON nếu muốn.
