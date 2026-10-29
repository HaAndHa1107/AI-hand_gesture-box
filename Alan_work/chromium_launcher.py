"""Chromium kiosk 啟動。"""
import os
import shutil
import subprocess

CHROMIUM_CMD = "chromium-browser" if shutil.which("chromium-browser") else "chromium"

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


