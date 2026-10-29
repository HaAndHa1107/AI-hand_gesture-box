"""Chromium 上一頁：🤘（食指與小指伸直，其餘手指收起）保持一段時間。"""
import pyautogui


class BrowserBackGesture:
    """只管理返回手勢的計時、單次觸發與鍵盤快捷鍵。"""

    def __init__(self, hold_duration=0.8, cooldown=1.2):
        self.hold_duration = hold_duration
        self.cooldown = cooldown
        self.hold_start = None
        self.last_trigger = float('-inf')
        self.armed = True
        # 保留舊版 main.py 使用的屬性名稱，以避免介面不相容。
        self.block_palm_hold = False

    def reset(self):
        self.hold_start = None
        self.armed = True
        self.block_palm_hold = False

    def update(self, gestures, landmarks, frame_width, now):
        """每影格呼叫；成功送出上一頁快捷鍵時回傳 True。

        landmarks/frame_width 保留作為與舊版呼叫介面相容的參數。
        """
        rock = bool(gestures.get('rock_sign', False))
        if not rock:
            self.hold_start = None
            self.armed = True
            self.block_palm_hold = False
            return False

        # 偵測到搖滾手勢期間，禁止與手掌長按計時互相干擾。
        self.block_palm_hold = True
        if not self.armed:
            return False
        if self.hold_start is None:
            self.hold_start = now
            return False
        if now - self.hold_start < self.hold_duration:
            return False
        if now - self.last_trigger < self.cooldown:
            return False

        try:
            pyautogui.hotkey('alt', 'left', interval=0.08)
        except Exception as exc:
            print(f'>>> [返回手勢] Alt+Left 發送失敗：{exc}', flush=True)
            self.hold_start = now  # 失敗後重新計時，避免每幀重試
            return False

        self.last_trigger = now
        self.armed = False  # 必須放開搖滾手勢，才能再次返回
        print('>>> [返回手勢] 🤘 維持 0.8 秒，已送出 Alt+Left', flush=True)
        return True
