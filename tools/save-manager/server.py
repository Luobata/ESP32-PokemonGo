#!/usr/bin/env python3
"""Static-only developer UI: serial and files stay in the user's browser."""
import argparse
import io
import zipfile
from urllib.parse import urlsplit
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUNDLE_FILES = ('server.py', 'web/index.html', 'web/style.css', 'web/backup.mjs', 'web/app.mjs')

def local_bundle():
    """Only public application files; never include saves or the working directory."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        files = {name: (ROOT/name).read_bytes() for name in BUNDLE_FILES}
        files['START-HERE.txt'] = ("PokeWalk local save manager\n\n"
            "Requires Python 3.8+ and desktop Chrome / Edge. No pip packages needed.\n"
            "1. Extract the ZIP, then open a terminal in this folder.\n"
            "2. macOS/Linux: python3 server.py\n"
            "   Windows: py -3 server.py\n"
            "3. Open http://localhost:8767 in Chrome / Edge.\n"
            "4. Choose a private backup folder and connect USB.\n"
            "5. Use Options > Save Backup / Import Save on the device.\n"
            "Keep the terminal open. Ctrl+C stops the local server.\n"
            "If port 8767 is occupied, use --port 8768 and open localhost:8768.\n"
            "Saves stay on your computer. Same device and exact PokeWalk build only.\n").encode()
        for name, data in files.items():
            info = zipfile.ZipInfo('PokeWalkSaveManager/'+name, (2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}
    def bundle_response(self, body):
        data = local_bundle()
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', 'attachment; filename="PokeWalkSaveManager.zip"')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if body:
            self.wfile.write(data)

    def do_GET(self):
        if urlsplit(self.path).path == '/download/PokeWalkSaveManager.zip':
            self.bundle_response(True)
        else:
            super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path == '/download/PokeWalkSaveManager.zip':
            self.bundle_response(False)
        else:
            super().do_HEAD()

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        super().end_headers()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8767);a=p.parse_args()
    handler=partial(Handler,directory=str(Path(__file__).resolve().parent/'web'))
    print(f'PokeWalk save manager: http://{a.host}:{a.port}',flush=True)
    ThreadingHTTPServer((a.host,a.port),handler).serve_forever()
