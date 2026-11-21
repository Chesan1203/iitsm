"""A very small helper that drives Microsoft Edge (headless) through the Chrome DevTools Protocol.

It is used only to make the report: rendering the Mermaid diagrams to PNG and taking screenshots of the
running application. It needs nothing beyond what the project already installs (the `websockets` package
comes with `uvicorn[standard]`) and the Edge browser that ships with Windows.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


class Edge:
    def __init__(self, port: int = 9333, width: int = 1400, height: int = 1000):
        self.profile = tempfile.mkdtemp(prefix="edge-profile-")
        self.proc = subprocess.Popen(
            [EDGE, "--headless=new", f"--remote-debugging-port={port}", "--remote-allow-origins=*",
             f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check",
             "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        target = None
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as response:
                    pages = [t for t in json.load(response) if t.get("type") == "page"]
                if pages:
                    target = pages[0]
                    break
            except OSError:
                pass
            time.sleep(0.2)
        if target is None:
            self.close()
            raise RuntimeError("Edge did not start")
        self.ws = connect(target["webSocketDebuggerUrl"], max_size=None)
        self._id = 0

    # -- protocol -----------------------------------------------------------------------------
    def call(self, method: str, **params):
        self._id += 1
        message_id = self._id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == message_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def evaluate(self, expression: str):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("text", "script error"))
        return result["result"].get("value")

    # -- helpers ------------------------------------------------------------------------------
    def viewport(self, width: int, height: int, scale: float = 1.0, mobile: bool = False):
        self.call("Emulation.setDeviceMetricsOverride", width=int(width), height=int(height),
                  deviceScaleFactor=scale, mobile=mobile)

    def goto(self, url: str, settle: float = 0.8, timeout: float = 30.0):
        self.call("Page.navigate", url=url)
        end = time.time() + timeout
        while time.time() < end:
            if self.evaluate("document.readyState") == "complete":
                break
            time.sleep(0.2)
        time.sleep(settle)

    def wait_for(self, expression: str, timeout: float = 30.0):
        end = time.time() + timeout
        while time.time() < end:
            value = self.evaluate(expression)
            if value:
                return value
            time.sleep(0.25)
        raise TimeoutError(expression)

    def set_cookie(self, name: str, value: str, url: str):
        self.call("Network.setCookie", name=name, value=value, url=url)

    def clear_cookies(self):
        self.call("Network.clearBrowserCookies")

    def screenshot(self, path: str, clip: dict | None = None, full_page: bool = False):
        params = {"format": "png", "captureBeyondViewport": True}
        if clip:
            params["clip"] = {**clip, "scale": 1}
        elif full_page:
            size = self.call("Page.getLayoutMetrics")["cssContentSize"]
            params["clip"] = {"x": 0, "y": 0, "width": size["width"], "height": size["height"], "scale": 1}
        data = self.call("Page.captureScreenshot", **params)["data"]
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(data))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
