import os

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2


IP = "10.224.131.2"
USER = "admin"
PASSWORD = "admin1"
CHANNEL = 2        # 1-based NVR channel: 1 = Test Cell 4, 2 = Test Cell 5 - B Cam, ...
PROFILE = "sub"    # "sub" (640x360 @ 10fps) or "main" (4K @ 25fps)


def stream():
    url = f"rtsp://{USER}:{PASSWORD}@{IP}:554//h264Preview_{CHANNEL:02d}_{PROFILE}"
    print(f"opening {url}")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("failed to open stream")
        return

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            cv2.imshow("name", maintain_aspect_ratio_resize(frame, width=600))
            if cv2.waitKey(1) == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def maintain_aspect_ratio_resize(image, width=None, height=None, inter=cv2.INTER_AREA):
    (h, w) = image.shape[:2]

    if width is None and height is None:
        return image

    if width is None:
        r = height / float(h)
        dim = (int(w * r), height)
    else:
        r = width / float(w)
        dim = (width, int(h * r))

    return cv2.resize(image, dim, interpolation=inter)


stream()