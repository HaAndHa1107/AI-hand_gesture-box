import cv2
import time
import numpy as np

class TVManager:
    def __init__(self):
        self.is_tv_on = False
        self.action_timer = 0

    def simulate_tv_signal(self, action):
        print(f">>> [硬體模擬] 📡 已發送紅外線電視 【{action}】 訊號！")

    def process(self, gestures, frame, w, h):
        now = time.time()
        display_frame = frame if self.is_tv_on else np.zeros((h, w, 3), dtype=np.uint8)
        state_changed = False

        if not self.is_tv_on:
            if gestures.get("palm"):
                if self.action_timer == 0: self.action_timer = now
                elapsed = now - self.action_timer
                progress = int(min(elapsed / 1.5, 1.0) * 100)
                
                cv2.putText(display_frame, f"POWERING ON... {progress}%", (w//2-200, h//2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
                
                if elapsed > 1.5:
                    self.simulate_tv_signal("ON")
                    self.is_tv_on = True
                    self.action_timer = 0
                    state_changed = True
            else:
                self.action_timer = 0
                cv2.putText(display_frame, "TV POWER OFF", (w//2-150, h//2-50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                cv2.putText(display_frame, "Show PALM to Power On", (w//2-230, h//2+50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        else:
            if gestures.get("fist"):
                if self.action_timer == 0: self.action_timer = now
                elapsed = now - self.action_timer
                progress = int(min(elapsed / 1.5, 1.0) * 100)
                
                cv2.putText(display_frame, f"SHUTTING DOWN... {progress}%", (w//2-250, h//2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                
                if elapsed > 1.5:
                    self.simulate_tv_signal("OFF")
                    self.is_tv_on = False
                    self.action_timer = 0
                    state_changed = True
                    display_frame = np.zeros((h, w, 3), dtype=np.uint8)
            else:
                self.action_timer = 0

        return display_frame, state_changed