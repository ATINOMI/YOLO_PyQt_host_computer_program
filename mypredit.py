from ultralytics import YOLO
model = YOLO(r"E:\deeplearning\qt - 副本\runs\detect\train\weights\best.pt")
model.predict(
    source=0,
    save=False,
    show=True,
)