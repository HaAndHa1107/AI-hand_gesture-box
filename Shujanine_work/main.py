import os
import sys
import time
import shutil
import platform
import tempfile
import subprocess
import multiprocessing as mp_process
from queue import Empty

# 僅在 Linux 環境設定 X 視窗相關環境變數
if platform.system() != "Windows":
    os.environ["DISPLAY"] = ":0.0"
    os.environ["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
    os.environ["FLAGS_selected_gpus"] = "0"

if sys.version_info < (3, 9):
    try:
        import backports.zoneinfo
        sys.modules["zoneinfo"] = backports.zoneinfo
    except ImportError:
        pass

import cv2
import numpy as np
import mediapipe as mp
import pyautogui

from config import *
from utils import get_dist
from gesture_engine import analyze_hand_gestures
from mode_mouse import MouseController
from mode_write import WriteController
from tv_manager import TVManager
from ocr_process import ocr_worker
from browser_input import BrowserInput

SCREEN_W = 2560
SCREEN_H = 1440

STATE_MENU = 0
STATE_STREAMING = 3
STATE_WRITING = 4

OK_COOLDOWN = 0.8
PALM_REQUIRED_DURATION = 1.2
OCR_TIMEOUT = 8.0


def get_browser_command():
    if platform.system() == "Windows":
        win_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        ]
        for path in win_candidates:
            if os.path.exists(path):
                return path
        return "chrome"
    else:
        return "chromium-browser" if shutil.which("chromium-browser") else "chromium"


# 取得目前系統可用的瀏覽器指令（只保留這一個，刪除原本舊的 CHROMIUM_CMD）
CHROMIUM_CMD = get_browser_command()


def kill_kiosk_browser():
    """跨平台關閉瀏覽器行程"""
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/IM", "msedge.exe", "/T"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["pkill", "-f", "smart-tv-chromium"], check=False)


def launch_kiosk(url):
    env = os.environ.copy()
    if platform.system() != "Windows":
        env["DISPLAY"] = ":0.0"

    user_data_dir = os.path.join(tempfile.gettempdir(), "smart-tv-chromium")

    subprocess.Popen([
        CHROMIUM_CMD,
        f"--user-data-dir={user_data_dir}",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-first-run",
        "--disable-features=TranslateUI",
        url
    ], env=env)
def launch_kiosk(url):
    env = os.environ.copy()
    env["DISPLAY"] = ":0.0"

    # 使用獨立的 Chromium 使用者資料夾，
    # 確保遠端除錯埠能正常啟動
    subprocess.Popen([
        CHROMIUM_CMD,
        "--user-data-dir=/tmp/smart-tv-chromium",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-first-run",
        "--disable-features=TranslateUI",
        url
    ], env=env)


class InteractiveTile:
    def __init__(
        self, title, x1, y1, x2, y2,
        color, hover_color, url
    ):
        self.title = title
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self.hover_color = hover_color
        self.url = url

        self.is_hovered = False
        self.is_clicked = False
        self.hover_start_time = None

    def update_state(self, cx, cy, now):
        inside = (
            cx is not None
            and cy is not None
            and self.x1 <= cx <= self.x2
            and self.y1 <= cy <= self.y2
        )

        if inside:
            if not self.is_hovered:
                self.hover_start_time = now
            self.is_hovered = True
        else:
            self.is_hovered = False
            self.is_clicked = False
            self.hover_start_time = None

    def draw(self, img, now):
        if self.is_clicked:
            color = (0, 200, 0)
        elif self.is_hovered:
            color = self.hover_color
        else:
            color = self.color

        cv2.rectangle(
            img,
            (self.x1, self.y1),
            (self.x2, self.y2),
            color,
            -1
        )

        if self.is_hovered:
            cv2.rectangle(
                img,
                (self.x1 - 4, self.y1 - 4),
                (self.x2 + 4, self.y2 + 4),
                (255, 255, 255),
                4
            )

            if self.hover_start_time is not None:
                progress = min(
                    1.0,
                    (now - self.hover_start_time) / 1.0
                )
                bar_w = int((self.x2 - self.x1) * progress)

                cv2.rectangle(
                    img,
                    (self.x1, self.y2 - 6),
                    (self.x1 + bar_w, self.y2),
                    COLOR_GREEN,
                    -1
                )

        text = "LOADING..." if self.is_clicked else self.title

        cv2.putText(
            img,
            text,
            (self.x1 + 18, (self.y1 + self.y2) // 2 + 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2
        )


def encode_ocr_image(image):
    if image is None:
        return None

    success, encoded = cv2.imencode(".png", image)

    if not success:
        return None

    return encoded.tobytes()


def show_status(frame, text, color=COLOR_YELLOW):
    cv2.rectangle(
        frame,
        (0, 0),
        (frame.shape[1], 65),
        (25, 25, 25),
        -1
    )

    cv2.putText(
        frame,
        text,
        (25, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        color,
        2
    )


def main():
    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = False

    mp_hands = mp.solutions.hands

    hands = mp_hands.Hands(
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=1
    )

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

    if not cap.isOpened():
        print("ERROR: Camera unavailable")
        return

    mouse_mode = MouseController()
    write_mode = WriteController()
    tv_ctrl = TVManager()
    browser = BrowserInput()

    input_queue = mp_process.Queue()
    output_queue = mp_process.Queue()

    ocr_process = mp_process.Process(
        target=ocr_worker,
        args=(input_queue, output_queue),
        daemon=True
    )
    ocr_process.start()

    tiles = [
        InteractiveTile(
            "NETFLIX", 50, 120, 220, 260,
            (200, 20, 20), (255, 60, 60),
            "https://www.netflix.com"
        ),
        InteractiveTile(
            "YouTube", 240, 120, 410, 260,
            (180, 0, 0), (230, 40, 40),
            "https://www.youtube.com"
        ),
        InteractiveTile(
            "Browser", 430, 120, 600, 260,
            (30, 100, 220), (60, 150, 255),
            "https://www.google.com"
        )
    ]

    current_state = STATE_MENU

    is_locked = True
    last_cmd_time = 0

    prev_ok = False
    prev_click_state = False
    last_ok_time = 0

    palm_hold_start_time = None

    ocr_pending = False
    ocr_start_time = 0
    ocr_status = ""
    ocr_status_until = 0

    window_name = "Smart TV Launcher"

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(
        window_name,
        cv2.WND_PROP_FULLSCREEN,
        cv2.WINDOW_FULLSCREEN
    )
    cv2.setWindowProperty(
        window_name,
        cv2.WND_PROP_TOPMOST,
        1
    )

    try:
        while cap.isOpened():
            success, frame = cap.read()

            if not success:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            now = time.monotonic()

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            gestures = {}
            lm = {}

            has_hand = bool(results.multi_hand_landmarks)

            if has_hand:
                hand = results.multi_hand_landmarks[0]

                lm = {
                    i: (
                        int(point.x * w),
                        int(point.y * h)
                    )
                    for i, point in enumerate(hand.landmark)
                }

                base = get_dist(lm[0], lm[9])
                gestures = analyze_hand_gestures(lm, base)

            ok_now = bool(gestures.get("ok", False))
            ok_pressed = ok_now and not prev_ok
            prev_ok = ok_now

            display_frame, tv_state_changed = tv_ctrl.process(
                gestures, frame, w, h
            )

            if tv_state_changed:
                is_locked = not tv_ctrl.is_tv_on

                if not tv_ctrl.is_tv_on:
                    current_state = STATE_MENU
                    browser.disconnect()
                    write_mode.reset()
                    ocr_pending = False

                    subprocess.run(
                        ["pkill", "-f", "smart-tv-chromium"],
                        check=False
                    )

            if tv_ctrl.is_tv_on:
                cursor_x = lm[8][0] if has_hand else None
                cursor_y = lm[8][1] if has_hand else None

                # -----------------------------
                # 主選單
                # -----------------------------
                if current_state == STATE_MENU:
                    cv2.rectangle(
                        display_frame,
                        (0, 0),
                        (w, h),
                        (30, 30, 30),
                        -1
                    )

                    cv2.putText(
                        display_frame,
                        "TV LAUNCHER",
                        (40, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (200, 200, 200),
                        2
                    )

                    for tile in tiles:
                        tile.update_state(cursor_x, cursor_y, now)
                        tile.draw(display_frame, now)

                    show_status(
                        display_frame,
                        "HOVER 1s OR PINCH TO SELECT"
                    )

                if has_hand and cursor_x is not None:
                    cv2.circle(
                        display_frame,
                        (cursor_x, cursor_y),
                        8,
                        COLOR_RED,
                        -1
                    )

                # -----------------------------
                # 鎖定手勢
                # -----------------------------
                if has_hand and gestures.get("lock_sign"):
                    if now - last_cmd_time > 2.0:
                        is_locked = not is_locked
                        last_cmd_time = now

                if is_locked:
                    show_status(
                        display_frame,
                        "SYSTEM LOCKED",
                        COLOR_RED
                    )

                else:
                    # -----------------------------
                    # 主選單選取
                    # -----------------------------
                    if current_state == STATE_MENU:
                        palm_hold_start_time = None

                        if has_hand:
                            dist_pinch = get_dist(lm[4], lm[8])
                            dist_im = get_dist(lm[8], lm[12])

                            gesture_click = (
                                dist_pinch < 65
                                or dist_im < 60
                            )

                            for tile in tiles:
                                if not tile.is_hovered:
                                    continue

                                dwell = (
                                    tile.hover_start_time is not None
                                    and now - tile.hover_start_time > 1.0
                                )

                                click = (
                                    gesture_click
                                    and now - last_cmd_time > 0.5
                                )

                                if (dwell or click) and (
                                    now - last_cmd_time > 1.0
                                ):
                                    tile.is_clicked = True

                                    cv2.setWindowProperty(
                                        window_name,
                                        cv2.WND_PROP_TOPMOST,
                                        0
                                    )

                                    launch_kiosk(tile.url)

                                    current_state = STATE_STREAMING
                                    last_cmd_time = now
                                    prev_click_state = False
                                    break

                    # -----------------------------
                    # 網頁滑鼠模式
                    # -----------------------------
                    elif current_state == STATE_STREAMING:
                        for tile in tiles:
                            tile.is_clicked = False

                        # OK 只能在可輸入欄位中開啟手寫
                        if ok_pressed and now - last_ok_time > OK_COOLDOWN:
                            last_ok_time = now
                            if browser.is_text_input_focused():
                                current_state = STATE_WRITING
                                write_mode.reset(w, h)
                                ocr_status = ""
                                ocr_pending = False
                                print(">>> Enter handwriting mode")
                            else:
                                ocr_status = "SELECT A TEXT FIELD FIRST"
                                ocr_status_until = now + 2.0

                        if current_state == STATE_STREAMING:
                            if has_hand:
                                # 只要不是在比 OK，才允許滑鼠游標與點擊
                                if not ok_now:
                                    mouse_mode.process(
                                        gestures,
                                        lm, w, h,
                                        display_frame
                                    )

                                    # 🌟 使用仿實體滑鼠的「食指下壓」動作
                                    is_clicking = gestures.get("mouse_click", False)

                                    # 單次點擊判定 (Edge-trigger)
                                    if is_clicking and not prev_click_state:
                                        pyautogui.click()

                                    prev_click_state = is_clicking
                                else:
                                    prev_click_state = False

                                # 張開手掌返回主選單
                                if gestures.get("palm"):
                                    if palm_hold_start_time is None:
                                        palm_hold_start_time = now

                                    elapsed = now - palm_hold_start_time

                                    if (
                                        elapsed >= PALM_REQUIRED_DURATION
                                        and now - last_cmd_time > 1.0
                                    ):
                                        subprocess.run(
                                            [
                                                "pkill", "-f",
                                                "smart-tv-chromium"
                                            ],
                                            check=False
                                        )

                                        browser.disconnect()

                                        cv2.setWindowProperty(
                                            window_name,
                                            cv2.WND_PROP_TOPMOST,
                                            1
                                        )

                                        current_state = STATE_MENU
                                        last_cmd_time = now
                                        palm_hold_start_time = None
                                else:
                                    palm_hold_start_time = None
                            else:
                                prev_click_state = False
                                palm_hold_start_time = None

                            if now < ocr_status_until:
                                show_status(
                                    display_frame,
                                    ocr_status
                                )
                            else:
                                show_status(
                                    display_frame,
                                    "MOUSE MODE | OK: HANDWRITING"
                                )

                    # -----------------------------
                    # 手寫模式
                    # -----------------------------
                    elif current_state == STATE_WRITING:
                        # 不讓攝影機畫面覆蓋整個畫布
                        display_frame[:] = (35, 35, 35)

                        if not ocr_pending:
                            if has_hand and not ok_now:
                                action = write_mode.process(
                                    gestures,
                                    lm, w, h,
                                    display_frame
                                )

                                if action == "BACKSPACE":
                                    browser.evaluate(
                                        """
                                        (() => {
                                            const el = document.activeElement;
                                            if (!el) return false;
                                            if (el.isContentEditable) return false;
                                            if (!("value" in el)) return false;
                                            const s = el.selectionStart;
                                            const e = el.selectionEnd;
                                            if (s === null || e === null) return false;
                                            const start = s === e ? Math.max(0,s-1) : s;
                                            el.setRangeText("",start,e,"end");
                                            el.dispatchEvent(new Event("input",{bubbles:true}));
                                            return true;
                                        })()
                                        """
                                    )

                                elif action == "ENTER":
                                    # 方案 A 不自動搜尋，Enter 手勢暫不執行
                                    pass

                            if (
                                ok_pressed
                                and now - last_ok_time > OK_COOLDOWN
                            ):
                                last_ok_time = now

                                image = write_mode.get_ocr_image()

                                if image is None:
                                    # 沒有筆跡時直接返回
                                    current_state = STATE_STREAMING
                                    write_mode.reset()
                                else:
                                    data = encode_ocr_image(image)

                                    if data:
                                        try:
                                            while True:
                                                output_queue.get_nowait()
                                        except Empty:
                                            pass

                                        input_queue.put(data)
                                        ocr_pending = True
                                        ocr_start_time = now
                                        ocr_status = "RECOGNIZING..."

                        else:
                            # 非阻塞讀取 OCR 結果
                            try:
                                detected_text = output_queue.get_nowait()
                            except Empty:
                                detected_text = None

                            if detected_text is not None:
                                ocr_pending = False

                                if (
                                    detected_text
                                    and detected_text != "ERROR"
                                ):
                                    if browser.insert_text(detected_text):
                                        ocr_status = "TEXT INSERTED"
                                    else:
                                        ocr_status = "INPUT FIELD LOST"
                                else:
                                    ocr_status = "OCR FAILED"

                                ocr_status_until = now + 2.0
                                write_mode.reset()
                                current_state = STATE_STREAMING

                            elif now - ocr_start_time > OCR_TIMEOUT:
                                ocr_pending = False
                                ocr_status = "OCR TIMEOUT"
                                ocr_status_until = now + 2.0
                                write_mode.reset()
                                current_state = STATE_STREAMING

                        if current_state == STATE_WRITING:
                            write_mode.draw_canvas(display_frame)

                            show_status(
                                display_frame,
                                "HANDWRITING | OK: RECOGNIZE",
                                COLOR_GREEN
                            )

                            if ocr_pending:
                                show_status(
                                    display_frame,
                                    "RECOGNIZING...",
                                    COLOR_YELLOW
                                )

            fullscreen_display = cv2.resize(
                display_frame,
                (SCREEN_W, SCREEN_H)
            )

            cv2.imshow(window_name, fullscreen_display)

            if cv2.waitKey(1) & 0xFF == 27:
                break

    finally:
        try:
            input_queue.put("EXIT")
        except Exception:
            pass

        browser.disconnect()
        cap.release()
        hands.close()
        cv2.destroyAllWindows()

        if ocr_process.is_alive():
            ocr_process.join(timeout=1.0)

        if ocr_process.is_alive():
            ocr_process.terminate()

        print(">>> System closed safely")


if __name__ == "__main__":
    mp_process.set_start_method("spawn", force=True)
    mp_process.set_executable(sys.executable)
    main()
