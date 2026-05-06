import cv2
import threading
import time
from typing import Generator


class VideoService:
    def __init__(self, device_index: int = 0):
        self._device_index = device_index
        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._latest_frame: bytes | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        if self._running:
            return
        self._cap = cv2.VideoCapture(self._device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f'카메라 장치 {self._device_index}를 열 수 없습니다.')
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None

    def is_running(self) -> bool:
        return self._running

    def _capture_loop(self):
        while self._running:
            if not self._cap or not self._cap.isOpened():
                break
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            with self._lock:
                self._latest_frame = buf.tobytes()

    def get_latest_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_frame

    def mjpeg_stream(self) -> Generator[bytes, None, None]:
        """MJPEG 스트림 제너레이터 — 30 FPS 상한, 중복 프레임 스킵"""
        boundary = b'--frame'
        interval = 1.0 / 30
        last_sent: bytes | None = None
        while self._running:
            t0 = time.monotonic()
            frame = self.get_latest_frame()
            if frame is None or frame is last_sent:
                time.sleep(0.02)
                continue
            last_sent = frame
            yield (
                boundary + b'\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame + b'\r\n'
            )
            elapsed = time.monotonic() - t0
            wait = interval - elapsed
            if wait > 0:
                time.sleep(wait)


video_service = VideoService(device_index=0)
