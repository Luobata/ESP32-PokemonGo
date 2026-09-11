#!/usr/bin/env python3
"""Exercise the real HTTP input boundary and compare every frame with native C."""
import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
import server
from native import Renderer, build


def main():
    class QuietHandler(server.Handler):
        def log_message(self, *args): pass

    httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    executable, version = build()
    reference = Renderer(executable)
    url = f'http://127.0.0.1:{httpd.server_port}/api/firmware'
    session = None
    frames = 0

    def post(data):
        data = dict(data, session=session)
        with urlopen(Request(url, data=json.dumps(data).encode(),
                             headers={'Content-Type': 'application/json'})) as response:
            return response.headers, response.read()

    def compare(data, command):
        nonlocal session, frames
        headers, pixels = post(data)
        session = headers['X-Preview-Session']
        expected = reference.command(command)
        assert pixels == expected['pixels'], command
        assert headers['X-Preview-Page'] == expected['page'], command
        assert headers['X-Preview-Version'] == version
        frames += 1
        return int(expected['page'][1:])

    def gesture(key, events):
        page = None
        for event in events:
            page = compare({'action': 'key', 'key': key, 'event': event}, f'key {key} {event}')
        return page

    try:
        compare({'action': 'reset', 'page': 1, 'team': 1}, 'boot 1 25 12 74 3 1 0 0 1')
        assert gesture(1, (0, 4, 1, 5)) == 1
        assert gesture(2, (0, 4, 1, 5)) == 11
        assert gesture(1, (0, 3, 4, 5)) == 1
        gesture(0, (0, 4, 0, 4, 2, 5))
        for event in (-1, 6, True):
            try:
                post({'action': 'key', 'key': 0, 'event': event})
            except HTTPError as error:
                assert error.code == 400
            else:
                raise AssertionError(f'invalid event accepted: {event!r}')
        compare({'action': 'check'}, 'check')
        result = {'build': version, 'frames': frames, 'passed': True,
                  'events': list(range(6)), 'invalid_rejected': [-1, 6, True],
                  'scope': 'actual HTTP handler + native production C frame comparison'}
        out = ROOT / 'reports/evidence/controls-growth-2026-09-10/http-input.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        reference.close()
        httpd.shutdown()
        thread.join()
        httpd.server_close()
        server.close_all()


if __name__ == '__main__':
    main()
