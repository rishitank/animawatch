"""Shared fixtures: test pages served over HTTP, and a real Chromium recorder."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from animawatch.browser import BrowserRecorder

#: A linear CSS transform animation: runs on the compositor, nothing on the
#: main thread. Should measure as smooth.
SMOOTH_CSS = """<!doctype html>
<html><head><title>smooth</title><style>
  #box { width: 80px; height: 80px; background: #c00;
         animation: slide 1s linear infinite alternate; }
  @keyframes slide { from { transform: translateX(0) } to { transform: translateX(600px) } }
</style></head><body><div id="box"></div></body></html>
"""

#: The main thread is blocked for 100 ms every 150 ms by a timer, while a
#: requestAnimationFrame loop moves a box (a main-thread animation).
BLOCKED_MAIN_THREAD = """<!doctype html>
<html><head><title>blocked</title><style>
  #box { position: absolute; top: 0; width: 80px; height: 80px; background: #00c; }
</style></head><body><div id="box"></div>
<script src="/blocker.js"></script>
<script>
  const box = document.getElementById('box');
  function step(t) { box.style.left = (t / 5 % 600) + 'px'; requestAnimationFrame(step); }
  requestAnimationFrame(step);
</script></body></html>
"""

#: The same 100 ms blocks, but the animation is a CSS transform, which the
#: compositor keeps running while the main thread is busy.
BLOCKED_WITH_CSS_ANIMATION = SMOOTH_CSS.replace(
    "</body>", '<script src="/blocker.js"></script></body>'
)

BLOCKER_JS = """
function blockMainThread() {
  const start = performance.now();
  while (performance.now() - start < 100) { /* busy */ }
}
setInterval(blockMainThread, 150);
"""

#: A page whose link navigates to the smooth page.
NAVIGATES = """<!doctype html>
<html><head><title>navigates</title></head>
<body><a id="go" href="/smooth.html">next</a></body></html>
"""


#: Large text (an LCP candidate), then a block inserted after 1 s that pushes
#: the paragraph down: a layout shift outside the 500 ms recent-input window.
LAYOUT_SHIFT = """<!doctype html>
<html><head><title>shift</title></head><body>
<h1 style="font-size: 80px">Largest paint</h1><div id="gap"></div>
<p style="font-size: 40px">This paragraph moves.</p>
<script>setTimeout(() => { document.getElementById('gap').style.height = '300px'; }, 1000);</script>
</body></html>
"""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@pytest.fixture(scope="session")
def page_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Serve the test pages on 127.0.0.1; yields the base URL."""
    root: Path = tmp_path_factory.mktemp("pages")
    (root / "smooth.html").write_text(SMOOTH_CSS)
    (root / "blocked.html").write_text(BLOCKED_MAIN_THREAD)
    (root / "blocked-css.html").write_text(BLOCKED_WITH_CSS_ANIMATION)
    (root / "blocker.js").write_text(BLOCKER_JS)
    (root / "navigates.html").write_text(NAVIGATES)
    (root / "shift.html").write_text(LAYOUT_SHIFT)

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
async def chromium() -> AsyncIterator[BrowserRecorder]:
    """A BrowserRecorder driving a real headless Chromium."""
    recorder = BrowserRecorder()
    await recorder.start()
    try:
        yield recorder
    finally:
        await recorder.stop()
