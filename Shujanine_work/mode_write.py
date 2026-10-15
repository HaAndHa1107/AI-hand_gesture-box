import cv2
import numpy as np
import time

from config import *


class WriteController:
    def __init__(self):
        self.xp = 0
        self.yp = 0
        self.canvas = None
        self.history_x = []
        self.last_backspace_time = 0
        self.last_enter_time = 0

    def reset(self, w=None, h=None):
        self.xp = 0
        self.yp = 0
        self.history_x = []

        if w is not None and h is not None:
            self.canvas = np.zeros((h, w, 3), np.uint8)
        elif self.canvas is not None:
            self.canvas.fill(0)

    def clear_canvas(self):
        if self.canvas is not None:
            self.canvas.fill(0)
        self.xp = 0
        self.yp = 0
        self.history_x = []

    def process(self, gestures, lm, w, h, frame):
        if self.canvas is None or self.canvas.shape[:2] != (h, w):
            self.reset(w, h)

        if not lm:
            self.xp = 0
            self.yp = 0
            return

        # OK 手勢由主程式負責，不在此處處理
        if gestures.get("ok", False):
            self.xp = 0
            self.yp = 0
            return

        # 小拇指：刪除最後一個輸入字元
        if gestures.get("backspace", False):
            self.xp = 0
            self.yp = 0

            cv2.circle(frame, lm[20], 15, COLOR_RED, cv2.FILLED)

            if time.time() - self.last_backspace_time > 0.5:
                self.last_backspace_time = time.time()
                return "BACKSPACE"

            return

        # 三指向上：Enter
        if gestures.get("three_up", False):
            self.xp = 0
            self.yp = 0

            if time.time() - self.last_enter_time > 0.7:
                self.last_enter_time = time.time()
                return "ENTER"

            return

        # 四指展開並左右揮動：清除畫布
        if gestures.get("eraser", False):
            self.xp = 0
            self.yp = 0

            cv2.circle(frame, lm[9], 40, COLOR_BLUE, 3)

            self.history_x.append(lm[9][0])

            if len(self.history_x) > 15:
                self.history_x.pop(0)

            if len(self.history_x) == 15:
                if max(self.history_x) - min(self.history_x) > w * 0.1:
                    self.clear_canvas()

            return

        # 食指書寫
        if gestures.get("index_up", False):
            self.history_x = []

            # 食指、中指靠近：提筆
            if gestures.get("middle_up", False) and gestures.get("together", False):
                self.xp = 0
                self.yp = 0
                cv2.circle(frame, lm[8], 10, COLOR_BLUE, cv2.FILLED)
                return

            # 只有食指舉起：書寫
            if not gestures.get("middle_up", False):
                x, y = lm[8]

                if self.xp == 0 and self.yp == 0:
                    self.xp, self.yp = x, y

                cv2.line(
                    self.canvas,
                    (self.xp, self.yp),
                    (x, y),
                    COLOR_GREEN,
                    12,
                    cv2.LINE_AA
                )

                cv2.circle(
                    frame, (x, y), 12,
                    COLOR_GREEN, cv2.FILLED
                )

                self.xp, self.yp = x, y
                return

        self.xp = 0
        self.yp = 0

    def has_writing(self):
        return (
            self.canvas is not None
            and np.any(self.canvas > 0)
        )

    def get_ocr_image(self):
        if not self.has_writing():
            return None

        gray = cv2.cvtColor(self.canvas, cv2.COLOR_BGR2GRAY)
        points = cv2.findNonZero(gray)

        if points is None:
            return None

        x, y, w, h = cv2.boundingRect(points)

        padding = 20

        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(self.canvas.shape[1], x + w + padding)
        y2 = min(self.canvas.shape[0], y + h + padding)

        cropped = self.canvas[y1:y2, x1:x2]

        # OCR 使用白底黑字
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY)

        result = 255 - binary
        return cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

    def draw_canvas(self, frame):
        if self.canvas is None:
            return frame

        mask = cv2.cvtColor(self.canvas, cv2.COLOR_BGR2GRAY) > 0
        frame[mask] = self.canvas[mask]

        return frame
