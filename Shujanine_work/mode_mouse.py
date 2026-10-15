import cv2
import numpy as np
import pyautogui
from config import *


class MouseController:
    def __init__(self, base_w=1920):
        self.smooth_x = 0
        self.smooth_y = 0
        self.is_left_clicking = False
        self.is_right_clicking = False
        self.screen_w, self.screen_h = pyautogui.size()

        self.scale_ratio = base_w / self.screen_w
        self.dynamic_alpha = MOUSE_SMOOTH_ALPHA * self.scale_ratio
        self.dynamic_alpha = max(0.05, min(self.dynamic_alpha, 1.0))

        print(f">>> [MouseMode] 螢幕解析度: {self.screen_w}x{self.screen_h}, 動態平滑 Alpha: {self.dynamic_alpha:.3f}")

    def process(self, gestures, lm, w, h, frame):
        """處理所有滑鼠移動與點擊邏輯"""
        if not gestures.get("index_up", False):
            self.is_left_clicking = False
            self.is_right_clicking = False
            return

        tx = np.interp(lm[8][0], (w * 0.1, w * 0.9), (0, self.screen_w))
        ty = np.interp(lm[8][1], (h * 0.1, h * 0.9), (0, self.screen_h))

        self.smooth_x = int(self.smooth_x * (1 - self.dynamic_alpha) + tx * self.dynamic_alpha)
        self.smooth_y = int(self.smooth_y * (1 - self.dynamic_alpha) + ty * self.dynamic_alpha)

        # 🔥 核心修復：確保只要食指舉起，游標隨時跟隨，不被其他子條件卡住
        pyautogui.moveTo(self.smooth_x, self.smooth_y)

        if gestures.get("middle_up", False):
            self.is_right_clicking = False
            if gestures.get("together", False):
                cv2.circle(frame, lm[8], 15, COLOR_RED, cv2.FILLED)
                if not self.is_left_clicking:
                    pyautogui.click()
                    self.is_left_clicking = True
            else:
                cv2.circle(frame, lm[8], 10, COLOR_BLUE, cv2.FILLED)
                self.is_left_clicking = False
        else:
            self.is_left_clicking = False
            cv2.circle(frame, lm[8], 15, COLOR_YELLOW, cv2.FILLED)
            if not self.is_right_clicking:
                pyautogui.rightClick()
                self.is_right_clicking = True
