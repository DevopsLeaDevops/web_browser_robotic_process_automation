"""純色錄影測試網站：白色起始頁、藍色新分頁，點擊後變紅；不含業務資料。"""

import functools
import http.server
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:rgb(255,255,255);height:100vh">
<button id="go" style="position:fixed;left:16px;top:16px">變紅</button>
<script>
setTimeout(() => { const p = document.createElement('p'); p.id = 'ready';
  p.textContent = 'ready'; p.style.cssText = 'position:fixed;left:16px;top:48px;margin:0';
  document.body.appendChild(p); }, 1200);
document.getElementById('go').onclick = () => {
  document.body.style.background = 'rgb(255,0,0)';
  setTimeout(() => { const p = document.createElement('p'); p.id = 'done';
    p.textContent = 'done'; p.style.cssText = 'position:fixed;left:16px;top:80px;margin:0';
    document.body.appendChild(p); }, 1500);
};
</script></body></html>
"""

PAGES_SCENARIO = """schemaVersion: 1
id: video-pages
name: 分頁錄影合成測試
browser:
  baseUrl: http://localhost
  engine: chromium
  viewport: {width: 640, height: 360}
steps:
  - {id: open, action: goto, url: /main.html}
  - {id: ready, action: waitFor, target: {css: '#ready'}}
  - {id: popup, action: click, target: {css: '#popup'}, popup: child}
  - {id: child-ready, action: waitFor, page: child, target: {css: '#ready'}}
  - {id: child-red, action: click, page: child, target: {css: '#go'}}
  - {id: child-done, action: waitFor, page: child, target: {css: '#done'}}
  - {id: close, action: click, page: child, target: {css: '#close'}}
  - {id: main-red, action: click, target: {css: '#go'}}
  - {id: main-done, action: waitFor, target: {css: '#done'}}
"""


@contextmanager
def recording_site(folder: Path) -> Generator[str]:
    (folder / "page.html").write_text(PAGE, encoding="utf-8")
    (folder / "main.html").write_text(
        PAGE.replace("</body>", '<a id="popup" href="/child.html" target="_blank">open</a></body>'),
        encoding="utf-8",
    )
    (folder / "child.html").write_text(
        PAGE.replace("background:rgb(255,255,255)", "background:rgb(0,0,255)").replace(
            "</body>", '<button id="close" onclick="window.close()">close</button></body>'
        ),
        encoding="utf-8",
    )

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
