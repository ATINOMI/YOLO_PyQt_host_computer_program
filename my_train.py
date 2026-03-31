from linecache import cache

from ultralytics import YOLO
if __name__ == '__main__':
    model=YOLO(r"yolo11n.pt")
    model.train(
        data=r"E:\deeplearning\qt - 副本\hands&fists\hands&fists\hd.yaml",
        epochs=100,
        imgsz=640,
        batch=-1,
        cache="ram",
        workers=1,
    )

