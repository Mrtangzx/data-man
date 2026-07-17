from __future__ import annotations

import json
import time
import urllib.request

from websockets.sync.client import connect


def open_tab() -> dict:
    request = urllib.request.Request("http://127.0.0.1:9223/json/new?http://127.0.0.1:8787", method="PUT")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


tab = open_tab()
sequence = 0
exceptions: list[str] = []

with connect(tab["webSocketDebuggerUrl"], open_timeout=5) as socket:
    def command(method: str, params: dict | None = None):
        global sequence
        sequence += 1
        current = sequence
        socket.send(json.dumps({"id": current, "method": method, "params": params or {}}))
        while True:
            message = json.loads(socket.recv(timeout=10))
            if message.get("method") == "Runtime.exceptionThrown":
                exceptions.append(message["params"]["exceptionDetails"].get("text", "JavaScript exception"))
            if message.get("id") == current:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def evaluate(expression: str):
        result = command("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        return result.get("result", {}).get("value")

    def wait_until(expression: str, label: str, seconds: float = 15):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if evaluate(expression):
                return
            time.sleep(0.15)
        raise TimeoutError(f"Timed out waiting for {label}")

    command("Runtime.enable")
    command("Page.enable")
    wait_until("document.readyState === 'complete' && document.body.innerText.includes('开始会话')", "workspace load")
    wait_until(
        "document.querySelector('.portrait-frame.photo img')?.complete && document.querySelector('.portrait-frame.photo img')?.naturalWidth > 0",
        "uploaded avatar preview",
    )
    avatar_source = evaluate("document.querySelector('.portrait-frame.photo img').getAttribute('src')")

    evaluate("[...document.querySelectorAll('button')].find(x => x.innerText.includes('开始会话')).click()")
    wait_until("document.body.innerText.includes('会话已连接')", "realtime connect")
    evaluate("""
      (() => {
        const el = document.querySelector('#realtime-message');
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, '浏览器端到端验收');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
      })()
    """)
    evaluate("document.querySelector('.composer button[type=submit]').click()")
    wait_until("document.body.innerText.includes('我收到了：浏览器端到端验收')", "realtime turn")
    evaluate("[...document.querySelectorAll('button')].find(x => x.innerText.includes('打断')).click()")
    wait_until("document.body.innerText.includes('已确认打断')", "interrupt ACK")

    evaluate("[...document.querySelectorAll('.nav-button')].find(x => x.innerText.includes('视频创作')).click()")
    wait_until("document.body.innerText.includes('从文案生成成片')", "video workspace")
    motion_options = evaluate("[...document.querySelectorAll('#motion-select option')].map(x => x.value)")
    if motion_options != ["steady", "natural", "expressive"]:
        raise RuntimeError(f"Unexpected motion profiles: {motion_options}")
    evaluate("[...document.querySelectorAll('button')].find(x => x.innerText.includes('生成示例视频')).click()")
    wait_until("document.body.innerText.includes('100%') && document.querySelector('video') !== null", "video artifact", 20)

    video = evaluate("document.querySelector('video').getAttribute('src')")
    nav_labels = evaluate("[...document.querySelectorAll('.nav-button')].map(x => x.innerText.trim())")
    evaluate("[...document.querySelectorAll('.nav-button')].find(x => x.innerText.includes('形象与声音')).click()")
    wait_until("document.body.innerText.includes('添加人物或声音素材')", "assets workspace")
    evaluate("[...document.querySelectorAll('.nav-button')].find(x => x.innerText.includes('系统与算力')).click()")
    wait_until("document.body.innerText.includes('控制平面状态')", "settings workspace")
    command("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
    time.sleep(0.25)
    mobile_layout = evaluate("({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, navBottom: Math.round(document.querySelector('.nav-rail').getBoundingClientRect().bottom), height: innerHeight })")
    print(json.dumps({
        "page_title": evaluate("document.title"),
        "uploaded_avatar_preview": True,
        "avatar_source": avatar_source,
        "realtime_turn": True,
        "interrupt_ack": True,
        "video_ready": True,
        "motion_profiles": motion_options,
        "video_src": video,
        "nav_workspaces": nav_labels,
        "assets_workspace": True,
        "settings_workspace": True,
        "mobile_layout": mobile_layout,
        "javascript_exceptions": exceptions,
    }, ensure_ascii=False, indent=2))
