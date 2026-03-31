import cv2
import os

video_path = r"C:/Users\ATINOMI\Desktop\WIN_20260312_10_54_21_Pro.mp4"
output_dir = r"E:/2222"

os.makedirs(output_dir, exist_ok=True)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError("视频无法打开")

frame_interval = 5   # ⭐ 控制频率：每 10 帧一张

frame_id = 0
saved_count = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    if frame_id % frame_interval == 0:
        output_path = os.path.join(
            output_dir, f"frame_{frame_id:06d}.jpg"
        )
        if cv2.imwrite(output_path, frame):
            saved_count += 1

    frame_id += 1

cap.release()
print(f"完成：共保存 {saved_count} 张图片")