import cv2
import numpy as np
import pyautogui
from config import *
from utils import get_dist


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

        # 食指指尖(8)與掌根(0)的相對距離；放開門檻較大，避免抖動重複點擊
        self.left_click_down_ratio = 1.35
        self.left_click_up_ratio = 1.65

        print(f">>> [MouseMode] 螢幕解析度: {self.screen_w}x{self.screen_h}, 動態平滑 Alpha: {self.dynamic_alpha:.3f}")

    def process(self, gestures, lm, w, h, frame):
        """食指指尖靠近掌根點左鍵，原本游標平滑與右鍵操作保留。"""
        if not lm or not all(k in lm for k in (0, 5, 8, 9, 17)):
            self.is_left_clicking = False
            self.is_right_clicking = False
            return

        # 游標移動仍使用食指指尖；食指彎曲時游標停在原處以便點擊
        if gestures.get("index_up", False):
            tx = np.interp(lm[8][0], (w * 0.1, w * 0.9), (0, self.screen_w))
            ty = np.interp(lm[8][1], (h * 0.1, h * 0.9), (0, self.screen_h))
            self.smooth_x = int(self.smooth_x * (1 - self.dynamic_alpha) + tx * self.dynamic_alpha)
            self.smooth_y = int(self.smooth_y * (1 - self.dynamic_alpha) + ty * self.dynamic_alpha)
            pyautogui.moveTo(self.smooth_x, self.smooth_y)

        palm_size = max(get_dist(lm[5], lm[17]), get_dist(lm[0], lm[9]), 1.0)
        ratio = get_dist(lm[8], lm[0]) / palm_size

        # 排除其他模式控制手勢；不要求 index_up，因為彎曲食指時它可能是 False
        special = any(gestures.get(name, False) for name in
                      ("mode_switch", "ok", "lock_sign", "palm", "eraser", "three_up"))

        if self.is_left_clicking:
            if ratio >= self.left_click_up_ratio:
                self.is_left_clicking = False
        elif not special and ratio <= self.left_click_down_ratio:
            pyautogui.click(button="left")
            self.is_left_clicking = True
            self.is_right_clicking = False

        if self.is_left_clicking:
            cv2.circle(frame, lm[8], 15, COLOR_RED, cv2.FILLED)
            return

        # 保留原本右鍵：食指伸直、中指收起；一次伸手只點一次
        if gestures.get("index_up", False) and not special:
            if gestures.get("middle_up", False):
                self.is_right_clicking = False
                cv2.circle(frame, lm[8], 10, COLOR_BLUE, cv2.FILLED)
            else:
                cv2.circle(frame, lm[8], 15, COLOR_YELLOW, cv2.FILLED)
                if not self.is_right_clicking:
                    pyautogui.rightClick()
                    self.is_right_clicking = True
        else:
            self.is_right_clicking = False
