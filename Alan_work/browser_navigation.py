"""網頁上一頁：張開手掌向左揮。僅由 main 的網頁模式呼叫。"""
from collections import deque
import pyautogui


class BrowserBackGesture:
    def __init__(self, min_distance=0.12, max_duration=1.0, cooldown=1.2):
        self.min_distance = min_distance
        self.max_duration = max_duration
        self.cooldown = cooldown
        self.points = deque()
        self.last_trigger = float('-inf')
        self.block_palm_hold = False
        self.last_palm_seen = float('-inf')
        self.last_debug = float('-inf')

    def reset(self):
        self.points.clear()
        self.block_palm_hold = False
        self.last_palm_seen = float('-inf')

    def update(self, gestures, landmarks, frame_width, now):
        """成功送出 Alt+Left 回傳 True；左移方向依已水平翻轉的影像。"""
        palm = bool(gestures.get('palm'))
        wrist = landmarks.get(0)
        if frame_width <= 0 or wrist is None:
            self.reset()
            return False

        if not palm:
            # 揮動時短暫丟失手掌分類，不立刻清空軌跡。
            if now - self.last_palm_seen > 0.25:
                self.points.clear()
                self.block_palm_hold = False
            return False

        self.last_palm_seen = now
        if self.block_palm_hold:
            return False

        x = wrist[0] / frame_width
        self.points.append((now, x))
        while self.points and now - self.points[0][0] > self.max_duration:
            self.points.popleft()

        if now - self.last_trigger < self.cooldown or len(self.points) < 2:
            return False

        # 起點必須是當前點之前的紀錄，避免單幀抖動造成誤判。
        start_x = max(p[1] for p in list(self.points)[:-1])
        distance = start_x - x
        if now - self.last_debug > 0.7 and distance > 0.04:
            print(f'>>> [返回手勢] 偵測左移 {distance:.1%}（門檻 {self.min_distance:.0%}）', flush=True)
            self.last_debug = now
        if distance < self.min_distance:
            return False

        print('>>> [返回手勢] 已觸發 Alt+Left', flush=True)
        pyautogui.hotkey('alt', 'left', interval=0.08)
        self.last_trigger = now
        self.block_palm_hold = True
        self.points.clear()
        return True
