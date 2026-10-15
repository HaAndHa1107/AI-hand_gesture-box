import cv2
import numpy as np
import shutil
import subprocess
import time

from config import COLOR_GREEN


class WriteController:

    def __init__(self):
        self.canvas = None
        self.last_point = None
        self.has_strokes = False

        self.preview_name = "Handwriting Preview"
        self.preview_w = 520
        self.preview_h = 300
        self.preview_open = False
        self.preview_visible = False
        self._last_raise = 0.0

    def reset(self, w, h):
        self.canvas = np.zeros(
            (h, w, 3),
            dtype=np.uint8
        )
        self.last_point = None
        self.has_strokes = False

    def clear_canvas(self):
        if self.canvas is not None:
            self.canvas.fill(0)

        self.last_point = None
        self.has_strokes = False

    def process(self, gestures, lm, w, h, frame):
        if (
            self.canvas is None
            or self.canvas.shape[:2] != (h, w)
        ):
            self.reset(w, h)

        if not lm:
            self.last_point = None
            return

        # 以下手勢都不能產生筆跡
        special = (
            "mode_switch",
            "ok",
            "backspace",
            "three_up"
        )

        if any(gestures.get(g, False) for g in special):
            self.last_point = None
            return

        if gestures.get("eraser", False):
            self.clear_canvas()
            return

        # 食指書寫
        if (
            gestures.get("index_up", False)
            and not gestures.get("middle_up", False)
            and 8 in lm
        ):
            point = lm[8]

            if self.last_point is not None:
                cv2.line(
                    self.canvas,
                    self.last_point,
                    point,
                    (255, 255, 255),
                    14,
                    cv2.LINE_AA
                )
                self.has_strokes = True

            self.last_point = point

            cv2.circle(
                frame,
                point,
                10,
                COLOR_GREEN,
                -1
            )
        else:
            self.last_point = None

    def overlay(self, frame):
        if self.canvas is None:
            return frame

        base = (
            frame * 0.20
        ).astype(np.uint8)

        return cv2.add(base, self.canvas)

    def _raise_preview(self):
        """Try to bring the preview above Chromium without taking keyboard focus."""
        try:
            cv2.setWindowProperty(self.preview_name, cv2.WND_PROP_TOPMOST, 1)
        except cv2.error:
            pass

        # Optional X11 fallback; runs automatically when xdotool is available.
        if shutil.which("xdotool"):
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--name", "^Handwriting Preview$"],
                    capture_output=True, text=True, timeout=0.4,
                )
                ids = result.stdout.split()
                if ids:
                    subprocess.run(
                        ["xdotool", "windowmap", ids[-1]],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=0.4,
                    )
                    subprocess.run(
                        ["xdotool", "windowraise", ids[-1]],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=0.4,
                    )
            except (OSError, subprocess.SubprocessError):
                pass

    def open_preview(self, screen_w, screen_h):
        """Create once, and bring back the same window on every entry."""
        if not self.preview_open:
            cv2.namedWindow(self.preview_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.preview_name, self.preview_w, self.preview_h)
            self.preview_open = True

        self.preview_visible = True
        self._position_preview(screen_w, screen_h)
        self._raise_preview()
        self._last_raise = time.monotonic()

    def _position_preview(self, screen_w, screen_h):
        margin = 25
        x = max(0, screen_w - self.preview_w - margin)
        y = max(0, screen_h - self.preview_h - margin - 40)
        cv2.moveWindow(self.preview_name, x, y)

    def show_preview(
        self,
        screen_w,
        screen_h,
        recognizing=False
    ):
        """
        每一幀更新右下角筆跡
        """

        if not self.preview_visible:
            self.open_preview(screen_w, screen_h)

        preview = np.full(
            (self.preview_h, self.preview_w, 3),
            (25, 18, 12),
            dtype=np.uint8
        )

        cv2.rectangle(
            preview,
            (0, 0),
            (self.preview_w, 42),
            (48, 37, 28),
            -1
        )

        cv2.putText(
            preview,
            "HANDWRITING PREVIEW",
            (15, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        area_x = 12
        area_y = 52
        area_w = self.preview_w - 24
        area_h = self.preview_h - 98

        cv2.rectangle(
            preview,
            (area_x, area_y),
            (
                area_x + area_w,
                area_y + area_h
            ),
            (10, 10, 10),
            -1
        )

        if self.canvas is not None:
            resized = cv2.resize(
                self.canvas,
                (area_w, area_h),
                interpolation=cv2.INTER_AREA
            )

            preview[
                area_y:area_y + area_h,
                area_x:area_x + area_w
            ] = resized

        if recognizing:
            status = "RECOGNIZING..."
            color = (0, 220, 255)

        elif self.has_strokes:
            status = "OK: OCR | PINKY: DEL | 3 FINGERS: ENTER"
            color = (100, 230, 100)

        else:
            status = "INDEX: WRITE | THUMB UP: EXIT"
            color = (190, 190, 190)

        cv2.putText(
            preview,
            status,
            (15, self.preview_h - 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            color,
            1,
            cv2.LINE_AA
        )

        cv2.imshow(
            self.preview_name,
            preview
        )

        # Reassert stacking periodically in case Chromium raises itself.
        if time.monotonic() - self._last_raise > 2.0:
            self._raise_preview()
            self._last_raise = time.monotonic()

    def close_preview(self):
        """Hide without destroying the native window (safe to re-enter)."""
        if not self.preview_open:
            return
        self.preview_visible = False
        try:
            cv2.setWindowProperty(self.preview_name, cv2.WND_PROP_TOPMOST, 0)
        except cv2.error:
            pass
        try:
            cv2.moveWindow(self.preview_name, -2000, -2000)
        except cv2.error:
            pass

    def encoded_canvas(self):
        if (
            not self.has_strokes
            or self.canvas is None
        ):
            return None

        gray = cv2.cvtColor(
            self.canvas,
            cv2.COLOR_BGR2GRAY
        )

        points = cv2.findNonZero(gray)

        if points is None:
            return None

        x, y, w, h = cv2.boundingRect(points)

        pad = 24

        y0 = max(0, y - pad)
        y1 = min(
            gray.shape[0],
            y + h + pad
        )

        x0 = max(0, x - pad)
        x1 = min(
            gray.shape[1],
            x + w + pad
        )

        crop = 255 - gray[
            y0:y1,
            x0:x1
        ]

        success, data = cv2.imencode(
            ".png",
            crop
        )

        if success:
            return data.tobytes()

        return None