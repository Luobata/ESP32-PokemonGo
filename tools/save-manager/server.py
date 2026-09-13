#!/usr/bin/env python3
"""Static-only developer UI: serial and files stay in the user's browser."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}
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
