import json
import time
import urllib.request
from urllib.parse import quote

import websocket


class BrowserInput:
    def __init__(self, port=9222):
        self.port = port
        self.ws = None
        self.request_id = 0
        self.target_id = None

    def disconnect(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.target_id = None

    def connect(self):
        try:
            url = f"http://127.0.0.1:{self.port}/json"
            with urllib.request.urlopen(url, timeout=0.3) as response:
                targets = json.load(response)

            pages = [
                t for t in targets
                if t.get("type") == "page"
                and t.get("webSocketDebuggerUrl")
                and not t.get("url", "").startswith("devtools:")
            ]

            if not pages:
                self.disconnect()
                return False

            target = pages[0]
            target_id = target["id"]

            if self.ws and self.target_id == target_id:
                return True

            self.disconnect()

            self.ws = websocket.create_connection(
                target["webSocketDebuggerUrl"],
                timeout=0.5,
                suppress_origin=True
            )
            self.target_id = target_id
            return True

        except Exception:
            self.disconnect()
            return False

    def evaluate(self, expression):
        if not self.connect():
            return None

        try:
            self.request_id += 1
            request_id = self.request_id

            self.ws.send(json.dumps({
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": False
                }
            }))

            deadline = time.monotonic() + 0.6

            while time.monotonic() < deadline:
                response = json.loads(self.ws.recv())

                if response.get("id") != request_id:
                    continue

                if "exceptionDetails" in response.get("result", {}):
                    return None

                return (
                    response.get("result", {})
                    .get("result", {})
                    .get("value")
                )

        except Exception:
            self.disconnect()

        return None

    def is_text_input_focused(self):
        script = """
        (() => {
            function activeElement(doc) {
                let el = doc.activeElement;

                while (el && el.shadowRoot &&
                       el.shadowRoot.activeElement) {
                    el = el.shadowRoot.activeElement;
                }

                return el;
            }

            let el = activeElement(document);

            if (!el) return false;

            if (el.tagName === "IFRAME") {
                try {
                    el = activeElement(el.contentDocument);
                } catch (e) {
                    return false;
                }
            }

            if (!el) return false;

            if (el.disabled || el.readOnly) return false;

            if (el.isContentEditable) return true;

            if (el.tagName === "TEXTAREA") return true;

            if (el.tagName === "INPUT") {
                const types = [
                    "text", "search", "url", "email",
                    "tel", "number", "password"
                ];

                return types.includes(
                    (el.type || "text").toLowerCase()
                );
            }

            return false;
        })()
        """

        return self.evaluate(script) is True

    def insert_text(self, text):
        if not text:
            return False

        # 先確認目前仍有可輸入的欄位
        if not self.is_text_input_focused():
            return False

        # 透過瀏覽器輸入事件輸入文字，避免中文鍵盤配置問題
        # 這會保留大部分網站的正常 input 事件處理
        self.request_id += 1
        request_id = self.request_id

        try:
            self.ws.send(json.dumps({
                "id": request_id,
                "method": "Input.insertText",
                "params": {"text": text}
            }))

            deadline = time.monotonic() + 0.6

            while time.monotonic() < deadline:
                response = json.loads(self.ws.recv())

                if response.get("id") == request_id:
                    return "error" not in response

        except Exception:
            self.disconnect()

        return False
