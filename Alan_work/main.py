import os
import sys
import shutil
import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import time
import subprocess
import multiprocessing as mp_process

from config import *
from utils import get_dist, draw_chinese_text
from gesture_engine import analyze_hand_gestures
from mode_mouse import MouseController
from tv_manager import TVManager
from mode_write import WriteController
from ocr_process import ocr_worker
from browser_input import BrowserInput

# Raspberry Pi 5 圖形介面
os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")

if sys.version_info < (3, 9):
    try:
        import backports.zoneinfo
        sys.modules["zoneinfo"] = backports.zoneinfo
    except ImportError:
        pass

os.environ["FLAGS_selected_gpus"] = "0"

# 自動使用目前桌面的輸出解析度（需先讓電視與桌面正確設定解析度）
# 若無法取得桌面大小，回退至原本的 2560x1440 設定。
try:
    SCREEN_W, SCREEN_H = map(int, pyautogui.size())
    if SCREEN_W <= 0 or SCREEN_H <= 0:
        raise ValueError("無效的桌面解析度")
except Exception as exc:
    print(f">>> [Display] 無法自動偵測解析度：{exc}，使用 2560x1440")
    SCREEN_W, SCREEN_H = 2560, 1440

print(f">>> [Display] 桌面解析度：{SCREEN_W}x{SCREEN_H}")

CHROMIUM_CMD = (
    "chromium-browser"
    if shutil.which("chromium-browser")
    else "chromium"
)

STATE_MENU = 0
STATE_MOUSE = 1
STATE_STREAMING = 3
STATE_WRITE = 4


def launch_kiosk(url):
    """啟動 Chromium Kiosk"""
    env = os.environ.copy()
    env["DISPLAY"] = ":0.0"

    subprocess.Popen([
        CHROMIUM_CMD,
        "--kiosk",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--user-data-dir=/tmp/smart-tv-chromium",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-first-run",
        "--fast",
        "--fast-start",
        "--disable-features=TranslateUI",
        url
    ], env=env)


class InteractiveTile:
    """主選單按鈕"""

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
                self.is_hovered = True
                self.hover_start_time = now
        else:
            self.is_hovered = False
            self.hover_start_time = None
            self.is_clicked = False

        return self.is_hovered

    def draw(self, img, now):
        if self.is_clicked:
            cur_color = (0, 200, 0)
        elif self.is_hovered:
            cur_color = self.hover_color
        else:
            cur_color = self.color

        cv2.rectangle(
            img,
            (self.x1, self.y1),
            (self.x2, self.y2),
            cur_color,
            -1
        )

        if self.is_hovered or self.is_clicked:
            cv2.rectangle(
                img,
                (self.x1 - 4, self.y1 - 4),
                (self.x2 + 4, self.y2 + 4),
                (255, 255, 255),
                5
            )

            if self.hover_start_time:
                progress = min(
                    1.0,
                    (now - self.hover_start_time) / 1.0
                )
                bar_w = int(
                    (self.x2 - self.x1) * progress
                )

                cv2.rectangle(
                    img,
                    (self.x1, self.y2 - 6),
                    (self.x1 + bar_w, self.y2),
                    (0, 255, 0),
                    -1
                )

        # 按鈕文字延後到螢幕原生解析度繪製，避免放大模糊。


def draw_menu_text_hd(image, tiles, source_w, source_h):
    """主選單文字在目前桌面輸出解析度上重新繪製。"""
    sx = image.shape[1] / source_w
    sy = image.shape[0] / source_h
    scale = min(sx, sy)
    thickness = max(2, round(2 * scale))

    cv2.putText(image, "TV LAUNCHER",
                (round(40 * sx), round(50 * sy)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8 * scale,
                (200, 200, 200), thickness, cv2.LINE_AA)

    for tile in tiles:
        label = "LOADING..." if tile.is_clicked else tile.title
        cv2.putText(image, label,
                    (round((tile.x1 + 18) * sx),
                     round((tile.y1 + (tile.y2 - tile.y1) / 2 + 10) * sy)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75 * scale,
                    (255, 255, 255), thickness, cv2.LINE_AA)

    cv2.putText(image, "Hover or Pinch to Select",
                (round(40 * sx), round(320 * sy)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6 * scale,
                COLOR_YELLOW, thickness, cv2.LINE_AA)



if __name__ == "__main__":

    mp_process.set_start_method(
        "spawn",
        force=True
    )
    mp_process.set_executable(sys.executable)

    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = False

    # =====================================
    # MediaPipe 手部辨識
    # =====================================
    mp_hands = mp.solutions.hands

    hands = mp_hands.Hands(
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=1
    )

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

    # =====================================
    # 控制器
    # =====================================
    mouse_mode = MouseController()
    tv_ctrl = TVManager()
    writer = WriteController()
    browser = BrowserInput()

    # =====================================
    # OCR 背景程序
    # =====================================
    ocr_in = mp_process.Queue(maxsize=2)
    ocr_out = mp_process.Queue(maxsize=2)

    ocr_proc = mp_process.Process(
        target=ocr_worker,
        args=(ocr_in, ocr_out),
        daemon=True
    )
    ocr_proc.start()

    ocr_pending = False
    ocr_started = 0

    # =====================================
    # 👍 比讚：只切換模式
    # =====================================
    switch_prev = False
    switch_armed = True

    # =====================================
    # 👌 OK：只執行 OCR
    # =====================================
    ok_prev = False
    ok_armed = True

    write_ready_at = 0

    # 手寫模式按鍵冷卻（由 CDP 發送，不依賴 OpenCV 視窗焦點）
    last_backspace_time = 0.0
    last_enter_time = 0.0
    BACKSPACE_COOLDOWN = 0.3
    ENTER_COOLDOWN = 0.5

    # =====================================
    # 主選單
    # =====================================
    tiles = [
        InteractiveTile(
            "NETFLIX",
            50, 120, 220, 260,
            (200, 20, 20),
            (255, 60, 60),
            "https://www.netflix.com"
        ),
        InteractiveTile(
            "YouTube",
            240, 120, 410, 260,
            (180, 0, 0),
            (230, 40, 40),
            "https://www.youtube.com"
        ),
        InteractiveTile(
            "Browser",
            430, 120, 600, 260,
            (30, 100, 220),
            (60, 150, 255),
            "https://www.google.com"
        )
    ]

    current_state = STATE_MENU
    last_cmd_time = 0
    is_locked = True
    menu_click_held = False

    palm_hold_start_time = None
    PALM_REQUIRED_DURATION = 1.2

    # =====================================
    # OpenCV 顯示視窗
    # =====================================
    window_name = "Smart TV Launcher"

    cv2.namedWindow(
        window_name,
        cv2.WINDOW_NORMAL
    )

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

    fps_time = time.time()
    fps_counter = 0
    current_fps = 0

    last_overlay_update = 0.0

    try:
        while cap.isOpened():

            success, frame = cap.read()

            if not success:
                continue

            frame = cv2.flip(frame, 1)

            h, w, _ = frame.shape
            now = time.time()

            # =====================================
            # FPS
            # =====================================
            fps_counter += 1

            if now - fps_time >= 1.0:
                current_fps = fps_counter
                fps_counter = 0
                fps_time = now

            # =====================================
            # 手勢辨識
            # =====================================
            results = hands.process(
                cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2RGB
                )
            )

            gestures = {}
            lm = {}

            has_hand = bool(
                results
                and results.multi_hand_landmarks
            )

            if has_hand:
                lm_list = (
                    results.multi_hand_landmarks[0]
                )

                lm = {
                    i: (
                        int(l.x * w),
                        int(l.y * h)
                    )
                    for i, l in enumerate(
                        lm_list.landmark
                    )
                }

                gestures = analyze_hand_gestures(
                    lm,
                    get_dist(lm[0], lm[9])
                )

            # =====================================
            # 👍 比讚防止重複觸發
            # =====================================
            switch_now = bool(
                gestures.get("mode_switch")
            )

            switch_pressed = (
                switch_now
                and not switch_prev
                and switch_armed
            )

            if not switch_now:
                switch_armed = True

            switch_prev = switch_now

            # =====================================
            # 👌 OK 防止重複觸發
            # =====================================
            ok_now = bool(
                gestures.get("ok")
            )

            ok_pressed = (
                ok_now
                and not ok_prev
                and ok_armed
            )

            if not ok_now:
                ok_armed = True

            ok_prev = ok_now

            # =====================================
            # 電視開關控制
            # =====================================
            display_frame, tv_state_changed = (
                tv_ctrl.process(
                    gestures,
                    frame,
                    w,
                    h
                )
            )

            if tv_state_changed:
                is_locked = not tv_ctrl.is_tv_on

                if not tv_ctrl.is_tv_on:
                    current_state = STATE_MENU
                    ocr_pending = False
                    browser.hide_handwriting_overlay()
                    writer.close_preview()
                    browser.close()

            if tv_ctrl.is_tv_on:

                cursor_x = None
                cursor_y = None

                if has_hand and 8 in lm:
                    cursor_x, cursor_y = lm[8]

                # =====================================
                # 主選單畫面
                # =====================================
                if current_state == STATE_MENU:

                    cv2.rectangle(
                        display_frame,
                        (0, 0),
                        (w, h),
                        (30, 30, 30),
                        -1
                    )

                    for tile in tiles:
                        tile.update_state(
                            cursor_x,
                            cursor_y,
                            now
                        )
                        tile.draw(
                            display_frame,
                            now
                        )


                if has_hand:

                    if (
                        cursor_x is not None
                        and current_state != STATE_WRITE
                    ):
                        cv2.circle(
                            display_frame,
                            (cursor_x, cursor_y),
                            8,
                            (0, 0, 255),
                            -1
                        )

                        cv2.circle(
                            display_frame,
                            (cursor_x, cursor_y),
                            10,
                            (255, 255, 255),
                            2
                        )

                    # =====================================
                    # 鎖定功能
                    # =====================================
                    if (
                        current_state != STATE_WRITE
                        and gestures.get("lock_sign")
                        and now - last_cmd_time > 2.0
                    ):
                        is_locked = not is_locked
                        last_cmd_time = now

                    if is_locked:

                        cv2.putText(
                            display_frame,
                            "SYSTEM LOCKED (Show PALM)",
                            (30, 45),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            COLOR_RED,
                            2
                        )

                    else:

                        # =====================================
                        # 主選單操作
                        # =====================================
                        if current_state == STATE_MENU:

                            palm_hold_start_time = None

                            # 主選單點擊：食指指尖(8)靠近掌根(0)
                            # 與 mode_mouse.py 使用相同的比例及遲滯門檻
                            palm_size = max(
                                get_dist(lm[5], lm[17]),
                                get_dist(lm[0], lm[9]),
                                1.0
                            )
                            index_wrist_ratio = (
                                get_dist(lm[8], lm[0]) / palm_size
                            )
                            click_blocked = any(
                                gestures.get(name, False)
                                for name in (
                                    "mode_switch", "ok", "lock_sign",
                                    "palm", "eraser", "three_up"
                                )
                            )
                            if menu_click_held:
                                is_gesture_click = False
                                if index_wrist_ratio >= 1.65:
                                    menu_click_held = False
                            else:
                                is_gesture_click = (
                                    not click_blocked
                                    and index_wrist_ratio <= 1.35
                                )
                                if is_gesture_click:
                                    menu_click_held = True

                            trigger_tile = None

                            for tile in tiles:

                                if tile.is_hovered:

                                    dwell_triggered = (
                                        tile.hover_start_time
                                        is not None
                                        and now - tile.hover_start_time > 1.0
                                    )

                                    gesture_triggered = (
                                        is_gesture_click
                                        and now - last_cmd_time > 0.5
                                    )

                                    if (
                                        dwell_triggered
                                        or gesture_triggered
                                    ):
                                        trigger_tile = tile
                                        break

                            if (
                                trigger_tile
                                and now - last_cmd_time > 1.0
                            ):

                                trigger_tile.is_clicked = True

                                temp_display = cv2.resize(
                                    display_frame,
                                    (SCREEN_W, SCREEN_H)
                                )

                                draw_menu_text_hd(temp_display, tiles, w, h)

                                cv2.imshow(
                                    window_name,
                                    temp_display
                                )
                                cv2.waitKey(1)

                                cv2.setWindowProperty(
                                    window_name,
                                    cv2.WND_PROP_TOPMOST,
                                    0
                                )

                                launch_kiosk(
                                    trigger_tile.url
                                )

                                current_state = STATE_STREAMING
                                last_cmd_time = now

                        # =====================================
                        # 手寫模式
                        # =====================================
                        elif current_state == STATE_WRITE:

                            writer.process(
                                gestures,
                                lm,
                                w,
                                h,
                                display_frame
                            )

                            cv2.putText(
                                display_frame,
                                "THUMB UP: Mouse | OK: OCR | Four fingers: Clear",
                                (25, 45),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                COLOR_YELLOW,
                                2
                            )

                            # =====================================
                            # 👍 比讚：只返回滑鼠模式
                            # =====================================
                            if (
                                switch_pressed
                                and now >= write_ready_at
                                and not ocr_pending
                            ):

                                current_state = STATE_STREAMING

                                writer.reset(w, h)

                                cv2.setWindowProperty(
                                    window_name,
                                    cv2.WND_PROP_TOPMOST,
                                    0
                                )

                                switch_armed = False
                                last_cmd_time = now
                                browser.hide_handwriting_overlay()
                                print(
                                    ">>> [模式] 返回滑鼠模式"
                                )

                            # =====================================
                            # 👌 OK：只執行 OCR
                            # =====================================
                            elif (
                                ok_pressed
                                and now >= write_ready_at
                                and not ocr_pending
                            ):

                                ok_armed = False

                                data = writer.encoded_canvas()

                                if data:

                                    try:
                                        ocr_in.put_nowait(data)

                                        ocr_pending = True
                                        ocr_started = now

                                        print(
                                            ">>> [OCR] 開始辨識"
                                        )

                                    except Exception as e:
                                        print(
                                            ">>> [OCR] 佇列錯誤:",
                                            e
                                        )

                                else:
                                    print(
                                        ">>> [OCR] 畫布沒有筆跡"
                                    )

                            # 小拇指：直接對 Chromium 發送 Backspace
                            # 避免預覽視窗搶走鍵盤焦點
                            if (
                                current_state == STATE_WRITE
                                and not ocr_pending
                                and gestures.get("backspace")
                                and now - last_backspace_time >= BACKSPACE_COOLDOWN
                            ):
                                if browser.press_backspace():
                                    print(">>> [手勢] Backspace")
                                else:
                                    print(">>> [手勢] Backspace 失敗：網頁輸入欄未聚焦")
                                last_backspace_time = now

                            # 三指：直接對 Chromium 發送 Enter
                            if (
                                current_state == STATE_WRITE
                                and not ocr_pending
                                and gestures.get("three_up")
                                and now - last_enter_time >= ENTER_COOLDOWN
                            ):
                                if browser.press_enter():
                                    print(">>> [手勢] Enter")
                                else:
                                    print(">>> [手勢] Enter 失敗：網頁輸入欄未聚焦")
                                last_enter_time = now

                            if ocr_pending:

                                cv2.putText(
                                    display_frame,
                                    "RECOGNIZING...",
                                    (25, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8,
                                    COLOR_YELLOW,
                                    2
                                )

                        # =====================================
                        # 滑鼠／瀏覽器模式
                        # =====================================
                        elif current_state == STATE_STREAMING:

                            for tile in tiles:
                                tile.is_clicked = False

                            # 👍 比讚：進入手寫模式
                            # 必須先選取可輸入文字的欄位
                            if (
                                switch_pressed
                                and now - last_cmd_time > 0.6
                                and browser.editable_focused()
                            ):

                                current_state = STATE_WRITE

                                writer.reset(w, h)

                                write_ready_at = now + 0.45
                                switch_armed = False

                                # 只讓手寫預覽置頂，不讓整個主視窗蓋住瀏覽器
                                cv2.setWindowProperty(
                                    window_name,
                                    cv2.WND_PROP_TOPMOST,
                                    0
                                )

                                # 每次進入手寫模式都重新開啟預覽
                                browser.show_handwriting_overlay(writer.canvas)

                                last_cmd_time = now

                                print(
                                    ">>> [模式] 進入手寫模式"
                                )

                                # 不使用 continue，讓本幀照常更新 OpenCV 視窗

                            # =====================================
                            # 一般滑鼠操作
                            # =====================================
                            if (
                                current_state == STATE_STREAMING
                                and lm
                                and not gestures.get(
                                    "mode_switch"
                                )
                            ):

                                mouse_mode.process(
                                    gestures,
                                    lm,
                                    w,
                                    h,
                                    display_frame
                                )

                            # =====================================
                            # 張開手掌返回主選單
                            # =====================================
                            if gestures.get("palm"):

                                if palm_hold_start_time is None:
                                    palm_hold_start_time = now

                                elapsed_palm = (
                                    now - palm_hold_start_time
                                )

                                percent = min(
                                    1.0,
                                    elapsed_palm
                                    / PALM_REQUIRED_DURATION
                                )

                                cv2.putText(
                                    display_frame,
                                    "HOLD PALM TO RETURN: "
                                    + f"{int(percent * 100)}%",
                                    (30, 45),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8,
                                    COLOR_YELLOW,
                                    2
                                )

                                if (
                                    elapsed_palm
                                    >= PALM_REQUIRED_DURATION
                                    and now - last_cmd_time > 1.0
                                ):

                                    subprocess.run(
                                        [
                                            "pkill",
                                            "-f",
                                            "chromium"
                                        ],
                                        check=False
                                    )

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

                                cv2.putText(
                                    display_frame,
                                    "STREAMING (Hold PALM 1.2s to Return)",
                                    (30, 45),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8,
                                    COLOR_GREEN,
                                    2
                                )

                else:
                    # 沒有偵測到手
                    palm_hold_start_time = None
                    menu_click_held = False

                    if current_state == STATE_WRITE:
                        writer.last_point = None

                # =====================================
                # OCR 結果處理
                # 不論有沒有偵測到手都會執行
                # =====================================
                if (
                    current_state == STATE_WRITE
                    and ocr_pending
                ):

                    try:
                        result_text = (
                            ocr_out.get_nowait()
                        )
                    except Exception:
                        result_text = None

                    timed_out = (
                        now - ocr_started > 12
                    )

                    if (
                        result_text is not None
                        or timed_out
                    ):

                        ocr_pending = False

                        if (
                            result_text
                            and result_text != "ERROR"
                        ):

                            success = browser.insert_text(
                                result_text
                            )

                            if success:

                                print(
                                    ">>> [OCR] 已輸入:",
                                    result_text
                                )

                                # 成功後清空畫布
                                writer.reset(w, h)

                            else:
                                print(
                                    ">>> [OCR] 無法輸入，"
                                    "保留畫布以便重試"
                                )

                        else:
                            print(
                                ">>> [OCR] 辨識失敗或逾時，"
                                "保留畫布"
                            )

                        # OK 辨識後不切換模式
                        current_state = STATE_WRITE

            # 即使沒有偵測到手，也持續更新右下角手寫預覽
            if tv_ctrl.is_tv_on and current_state == STATE_WRITE:
                # 直接更新 Chromium 頁面內的預覽，不使用 OpenCV 子視窗
                if now - last_overlay_update >= 0.15:
                    # 食指第 8 點的位置；停筆時仍顯示游標，但不新增筆跡。
                    cursor = None
                    if has_hand and 8 in lm:
                        cursor = (
                            max(0.0, min(1.0, lm[8][0] / max(w, 1))),
                            max(0.0, min(1.0, lm[8][1] / max(h, 1)))
                        )
                    pen_down = bool(
                        cursor is not None
                        and gestures.get("index_up", False)
                        and not gestures.get("middle_up", False)
                        and not any(gestures.get(g, False) for g in
                                    ("mode_switch", "ok", "backspace", "three_up", "eraser"))
                        and not ocr_pending
                    )
                    browser.show_handwriting_overlay(
                        writer.canvas,
                        recognizing=ocr_pending,
                        cursor=cursor,
                        pen_down=pen_down
                    )
                    last_overlay_update = now

            # =====================================
            # 畫面輸出
            # =====================================
            fullscreen_display = cv2.resize(
                display_frame,
                (SCREEN_W, SCREEN_H)
            )

            if tv_ctrl.is_tv_on and current_state == STATE_MENU:
                draw_menu_text_hd(fullscreen_display, tiles, w, h)

            cv2.imshow(
                window_name,
                fullscreen_display
            )

            if cv2.waitKey(1) & 0xFF == 27:
                break

    finally:

        browser.hide_handwriting_overlay()
        browser.close()

        try:
            ocr_in.put_nowait("EXIT")
        except Exception:
            pass

        if ocr_proc.is_alive():
            ocr_proc.terminate()
            ocr_proc.join(timeout=2)

        hands.close()
        writer.close_preview()
        cap.release()
        cv2.destroyAllWindows()

        print(
            ">>> [系統] 系統已安全關閉。"
        )