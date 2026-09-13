#!/usr/bin/env python3
"""Verify the HTTP download contains only public files and runs locally."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
from functools import partial
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

with tempfile.TemporaryDirectory() as tmp:
    temp=Path(tmp);source=ROOT/'tools/save-manager'
    for name in ('server.py','web/index.html','web/style.css','web/backup.mjs','web/app.mjs'):
        dst=temp/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dst)
    (temp/'private.pksave').write_text('PRIVATE_SAVE_SENTINEL')
    (temp/'web'/'unlisted.txt').write_text('PRIVATE_SAVE_SENTINEL')
    m=load(temp/'server.py','distribution_server');raw=m.local_bundle()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert set(z.namelist())=={'PokeWalkSaveManager/'+p for p in (*m.BUNDLE_FILES,'START-HERE.txt')}
        assert not any(b'PRIVATE_SAVE_SENTINEL' in z.read(n) for n in z.namelist())
        z.extractall(temp/'extracted')
    app=temp/'extracted/PokeWalkSaveManager';m=load(app/'server.py','extracted_server')
    class Quiet(m.Handler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(app/'web')))
    t=threading.Thread(target=server.serve_forever);t.start();base='http://127.0.0.1:'+str(server.server_port)
    try:
        with urllib.request.urlopen(base+'/') as r:assert '下载本地存档工具'.encode() in r.read()
        with urllib.request.urlopen(base+'/app.mjs') as r:assert r.headers.get_content_type()=='text/javascript'
        with urllib.request.urlopen(base+'/download/PokeWalkSaveManager.zip') as r:
            data=r.read();assert data==raw;assert r.headers.get_content_type()=='application/zip'
        with urllib.request.urlopen(urllib.request.Request(base+'/download/PokeWalkSaveManager.zip',method='HEAD')) as r:
            assert int(r.headers['Content-Length'])==len(raw) and not r.read()
        for path,method,status in [('/private.pksave','GET',404),('/server.py','GET',404),('/','POST',501)]:
            try:urllib.request.urlopen(urllib.request.Request(base+path,method=method));raise AssertionError(path)
            except urllib.error.HTTPError as e:assert e.code==status
    finally:server.shutdown();t.join();server.server_close()
print(json.dumps({'passed':True,'scope':'public-file allowlist, extracted offline server, MIME, GET/HEAD, no save exposure or upload API'}))
