import json
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