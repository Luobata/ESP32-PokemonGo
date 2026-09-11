#!/usr/bin/env python3
"""Inspector static files plus a local production-firmware rendering service."""
from __future__ import annotations

import argparse
import atexit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
from urllib.parse import urlparse

from native import HERE, Renderer, build

sessions = {}
lock = threading.Lock()
PAGES = (*range(7), 9, 10, 11, 12, 13, 14, 15)


def close_all():
    for renderer, _ in sessions.values():
        renderer.close()
    sessions.clear()


atexit.register(close_all)


def integer(data, name, default, lo, hi):
    value = data.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValueError(f"{name} 必须在 {lo}..{hi}")
    return value


def page_value(data):
    value = integer(data, "page", 3, 0, 15)
    if value not in PAGES:
        raise ValueError("页面必须是 P0–P6 或 P9–P15")
    return value


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def json_response(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/firmware":
            self.json_response(200, {"renderer": "firmware-native", "pages": PAGES})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/api/firmware":
            return self.json_response(404, {"error": "未知接口"})
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host.split(":")[0] not in ("127.0.0.1", "localhost") or (origin and urlparse(origin).netloc != host):
            return self.json_response(403, {"error": "只接受本地预览页面请求"})
        session = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError("请求大小不合法")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("请求必须是 JSON 对象")
            action = data.get("action")
            session = data.get("session")
            if session is not None and not isinstance(session, str):
                raise ValueError("session 不合法")
            with lock:
                for stale, (renderer, _) in list(sessions.items()):
                    if time.monotonic() - renderer.updated > 1800:
                        renderer.close(); del sessions[stale]
                if action == "reset":
                    values = [page_value(data), integer(data, "pet", 25, 1, 151),
                              integer(data, "level", 12, 1, 100), integer(data, "wild", 74, 1, 151),
                              integer(data, "rarity", 3, 1, 5), integer(data, "seed", 1, 0, 2**32 - 1),
                              integer(data, "shiny", 0, 0, 1), integer(data, "names", 0, 0, 1),
                              integer(data, "team", 0, 0, 1)]
                    if session in sessions:
                        sessions.pop(session)[0].close()
                    if len(sessions) >= 8:
                        old = min(sessions, key=lambda k: sessions[k][0].updated)
                        sessions.pop(old)[0].close()
                    executable, version = build()
                    renderer = Renderer(executable)
                    session = secrets.token_hex(16)
                    sessions[session] = renderer, version
                    command = "boot " + " ".join(map(str, values))
                else:
                    if session not in sessions:
                        return self.json_response(409, {"error": "预览会话已结束，请重新载入"})
                    renderer, version = sessions[session]
                    if action == "audio":
                        samples = integer(data, 'samples', 3528, 1, 11025)
                        pcm = renderer.audio(samples)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Content-Length", str(len(pcm)))
                        self.send_header("X-Audio-Sample-Rate", "22050")
                        self.end_headers()
                        self.wfile.write(pcm)
                        return
                    if action == "key":
                        command = f"key {integer(data, 'key', 0, 0, 2)} {integer(data, 'event', 1, 0, 5)}"
                    elif action == "tick":
                        command = f"tick {integer(data, 'ms', 60, 0, 60000)}"
                    elif action == "page":
                        command = f"page {page_value(data)}"
                    elif action == "move_preview":
                        if renderer.inspect()["page"] != 3:
                            raise ValueError("招式验收请先载入 P3 对战页面")
                        supported = {m["id"] for m in json.loads((HERE / "move-catalog.json").read_text())}
                        if integer(data, "move", 1, 1, 250) not in supported:
                            raise ValueError("此招式尚未实现")
                        command = f"move_preview {integer(data, 'move', 1, 1, 250)} {integer(data, 'side', 0, 0, 1)} {integer(data, 'frame', 0, 0, 255)} {integer(data, 'mode', 0, 0, 3)}"
                    elif action == "check":
                        command = "check"
                    elif action == "names":
                        command = f"names {integer(data, 'style', 0, 0, 1)}"
                    else:
                        raise ValueError("未知操作")
                result = renderer.command(command)
                state = renderer.inspect()
                name_style = state["names"]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(result["pixels"])))
            for name, value in (("Session", session), ("Page", result["page"]),
                                ("Ms", result["ms"]), ("Mismatch", result["mismatch"]),
                                ("Version", version), ("Names", name_style),
                                ("Music", state.get("music", 0)),
                                ("Animation-Frames", state.get("move_animation_frames", 0)),
                                ("Screen-Off", int(state["display"]["off"]))):
                self.send_header("X-Preview-" + name, str(value))
            self.end_headers()
            self.wfile.write(result["pixels"])
        except (ValueError, TypeError) as error:
            self.json_response(400, {"error": str(error)})
        except (RuntimeError, OSError) as error:
            with lock:
                if session in sessions:
                    sessions.pop(session)[0].close()
            self.json_response(500, {"error": str(error)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    executable, version = build()
    print(f"固件同源预览 {version}: http://127.0.0.1:{args.port}/firmware.html", flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        close_all()
