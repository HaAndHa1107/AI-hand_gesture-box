import cv2
import numpy as np

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

    def open_preview(self, screen_w, screen_h):
        """
        每次進入手寫模式都能開啟預覽
        """

        if self.preview_open:
            return

        cv2.namedWindow(
            self.preview_name,
            cv2.WINDOW_NORMAL
        )

        cv2.resizeWindow(
            self.preview_name,
            self.preview_w,
            self.preview_h
        )

        self.preview_open = True

        self._position_preview(
            screen_w,
            screen_h
        )

    def _position_preview(self, screen_w, screen_h):
        margin = 25

        x = max(
            0,
            screen_w - self.preview_w - margin
        )

        y = max(
            0,
            screen_h - self.preview_h - margin - 40
        )

        cv2.moveWindow(
            self.preview_name,
            x,
            y
        )

        try:
            cv2.setWindowProperty(
                self.preview_name,
                cv2.WND_PROP_TOPMOST,
                1
            )
        except cv2.error:
            pass

    def show_preview(
        self,
        screen_w,
        screen_h,
        recognizing=False
    ):
        """
        每一幀更新右下角筆跡
        """

        if not self.preview_open:
            self.open_preview(
                screen_w,
                screen_h
            )

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

    def close_preview(self):
        """
        每次離開手寫模式就關閉
        下次進入可以重新建立
        """

        if self.preview_open:
            try:
                cv2.destroyWindow(
                    self.preview_name
                )
            except cv2.error:
                pass

        self.preview_open = False

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