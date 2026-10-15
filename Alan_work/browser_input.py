import json
import base64
import cv2
import urllib.request

try:
    import websocket
except ImportError:
    websocket = None


class BrowserInput:

    def __init__(self, port=9222):
        self.port = port
        self.ws = None
        self.target_id = None
        self.seq = 0

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

        self.ws = None
        self.target_id = None

    def _connect(self):
        if websocket is None:
            return False

        if self.ws:
            return True

        try:
            url = (
                f"http://127.0.0.1:"
                f"{self.port}/json"
            )

            with urllib.request.urlopen(
                url,
                timeout=0.5
            ) as response:
                targets = json.load(response)

            pages = [
                p for p in targets
                if p.get("type") == "page"
                and p.get("webSocketDebuggerUrl")
            ]

            if not pages:
                return False

            page = pages[0]

            self.ws = websocket.create_connection(
                page["webSocketDebuggerUrl"],
                timeout=0.8,
                suppress_origin=True
            )

            self.target_id = page["id"]
            return True

        except Exception as e:
            print("[BrowserInput] 連線失敗:", e)
            self.close()
            return False

    def call(self, method, params=None):
        if not self._connect():
            return None

        try:
            self.seq += 1
            request_id = self.seq

            self.ws.send(json.dumps({
                "id": request_id,
                "method": method,
                "params": params or {}
            }))

            for _ in range(30):
                response = json.loads(
                    self.ws.recv()
                )

                if response.get("id") == request_id:
                    if "error" in response:
                        print(
                            "[BrowserInput] CDP 錯誤:",
                            response["error"]
                        )
                        return None

                    return response

        except Exception as e:
            print("[BrowserInput] 指令失敗:", e)
            self.close()

        return None

    def editable_focused(self):
        """
        檢查網頁內目前是否有可編輯欄位
        """

        js = r"""
        (() => {
            let el = document.activeElement;

            if (!el) return false;

            if (el.tagName === "IFRAME")
                return false;

            if (el.isContentEditable)
                return true;

            if (el.tagName === "TEXTAREA")
                return !el.disabled && !el.readOnly;

            if (el.tagName !== "INPUT")
                return false;

            const type = (
                el.type || "text"
            ).toLowerCase();

            const allowed = [
                "text",
                "search",
                "url",
                "email",
                "tel",
                "password",
                "number"
            ];

            return (
                !el.disabled &&
                !el.readOnly &&
                allowed.includes(type)
            );
        })()
        """

        response = self.call(
            "Runtime.evaluate",
            {
                "expression": js,
                "returnByValue": True
            }
        )

        if not response:
            return False

        result = response.get(
            "result", {}
        ).get("result", {})

        return result.get("value") is True

    def insert_text(self, text):
        """
        OCR 辨識完成後直接輸入文字
        """

        if not text:
            return False

        if not self.editable_focused():
            print(
                "[BrowserInput] 沒有可輸入的欄位"
            )
            return False

        response = self.call(
            "Input.insertText",
            {"text": str(text)}
        )

        return response is not None

    def _send_key(self, event_type, key,
                  code, windows_key_code,
                  text=None):
        """
        透過 CDP 發送鍵盤事件
        """

        params = {
            "type": event_type,
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": windows_key_code,
            "nativeVirtualKeyCode": windows_key_code
        }

        if text is not None:
            params["text"] = text
            params["unmodifiedText"] = text

        return self.call(
            "Input.dispatchKeyEvent",
            params
        ) is not None

    def press_backspace(self):
        """
        小拇指：刪除輸入欄最後一個字元
        """

        if not self.editable_focused():
            return False

        down = self._send_key(
            "rawKeyDown",
            "Backspace",
            "Backspace",
            8
        )

        up = self._send_key(
            "keyUp",
            "Backspace",
            "Backspace",
            8
        )

        return down and up

    def press_enter(self):
        """
        三指：送出 Enter
        """

        if not self.editable_focused():
            return False

        down = self._send_key(
            "rawKeyDown",
            "Enter",
            "Enter",
            13
        )

        char = self._send_key(
            "char",
            "Enter",
            "Enter",
            13,
            "\r"
        )

        up = self._send_key(
            "keyUp",
            "Enter",
            "Enter",
            13
        )

        return down and char and up
    def show_handwriting_overlay(self, canvas, recognizing=False, cursor=None, pen_down=False):
        """在 Chromium 頁面右下角顯示預覽，不建立 OpenCV 視窗。"""
        if canvas is None:
            return False
        image = cv2.resize(canvas, (472, 192), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return False
        data_uri = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
        status = "RECOGNIZING..." if recognizing else "INDEX: WRITE  |  TWO FINGERS: LIFT  |  OK: OCR"
        # 座標是相對於手寫畫布的 0~1 比例，避免因畫面縮放而偏移。
        cursor_data = None
        if cursor is not None:
            cursor_data = [float(cursor[0]), float(cursor[1])]
        js = """(() => {
          let panel = document.getElementById('__smart_tv_handwriting_preview__');
          if (!panel) {
            panel = document.createElement('div');
            panel.id = '__smart_tv_handwriting_preview__';
            panel.style.cssText = 'position:fixed!important;right:25px!important;bottom:65px!important;width:520px!important;height:300px!important;box-sizing:border-box!important;background:#19120c!important;color:white!important;border:2px solid #55c877!important;border-radius:12px!important;box-shadow:0 5px 28px #0009!important;z-index:2147483647!important;pointer-events:none!important;display:block!important;font:17px Arial,sans-serif!important;padding:12px!important;';
            const title = document.createElement('div');
            title.textContent = 'HANDWRITING PREVIEW';
            title.style.cssText = 'height:32px;font-weight:bold;';
            const drawing = document.createElement('div');
            drawing.style.cssText = 'position:relative;width:472px;height:192px;background:black;overflow:hidden;';
            const img = document.createElement('img');
            img.style.cssText = 'display:block;width:472px;height:192px;object-fit:fill;background:black;';
            const pointer = document.createElement('div');
            pointer.id = '__smart_tv_pen_cursor__';
            pointer.style.cssText = 'position:absolute;left:0;top:0;width:16px;height:16px;border-radius:50%;border:2px solid #38f2aa;background:#38f2aa33;box-shadow:0 0 7px #38f2aa;transform:translate(-50%,-50%);display:none;pointer-events:none;box-sizing:border-box;';
            drawing.append(img,pointer);
            const footer = document.createElement('div');
            footer.style.cssText = 'font:13px Arial,sans-serif;margin-top:14px;color:#aaf0aa;';
            panel.append(title,drawing,footer);
            (document.body || document.documentElement).appendChild(panel);
          }
          panel.style.setProperty('display','block','important');
          const drawing = panel.children[1];
          const img = drawing.querySelector('img');
          if (img) img.src = DATA_URI;
          let pointer = document.getElementById('__smart_tv_pen_cursor__');
          // 相容已存在的舊版預覽面板：重新補上游標。
          if (!pointer) {
            pointer = document.createElement('div');
            pointer.id = '__smart_tv_pen_cursor__';
            pointer.style.cssText = 'position:absolute;width:16px;height:16px;border-radius:50%;border:2px solid #38f2aa;transform:translate(-50%,-50%);pointer-events:none;box-sizing:border-box;';
            drawing.appendChild(pointer);
          }
          if (CURSOR && Array.isArray(CURSOR)) {
            pointer.style.display = 'block';
            pointer.style.left = (Math.max(0,Math.min(1,CURSOR[0]))*100)+'%';
            pointer.style.top = (Math.max(0,Math.min(1,CURSOR[1]))*100)+'%';
            pointer.style.borderColor = PEN_DOWN ? '#38f2aa' : '#60d9ff';
            pointer.style.background = PEN_DOWN ? '#38f2aa55' : '#60d9ff22';
            pointer.style.boxShadow = PEN_DOWN ? '0 0 8px #38f2aa' : '0 0 8px #60d9ff';
          } else {
            pointer.style.display = 'none';
          }
          panel.children[2].textContent = STATUS;
          return true;
        })()""".replace("DATA_URI", json.dumps(data_uri)).replace("STATUS", json.dumps(status)).replace("CURSOR", json.dumps(cursor_data)).replace("PEN_DOWN", "true" if pen_down else "false")
        result = self.call("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return bool(result and result.get("result", {}).get("result", {}).get("value") is True)

    def hide_handwriting_overlay(self):
        js = """(() => {const p=document.getElementById('__smart_tv_handwriting_preview__');if(p){p.remove();}return true;})()"""
        return self.call("Runtime.evaluate", {"expression": js, "returnByValue": True}) is not None
