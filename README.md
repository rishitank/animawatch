# 🎬 AnimaWatch

> An MCP server that checks web animations the way a tester would. It **measures** dropped frames inside the page, and it can **look** at a recording with AI vision to find visual glitches.

AnimaWatch is built with FastMCP from the official MCP Python SDK.

## ✨ What It Does

```
YOU: "Check the menu animation on this page for jank"
     ↓
ANIMAWATCH:
  1. Opens the page in Chromium and measures every frame in the page
     (requestAnimationFrame + Long Animation Frames), against the
     display's real refresh rate
  2. Optionally records the interaction and asks a vision model
     (Gemini with your own key, or Ollama locally) what looks wrong
     ↓
RESULT: "18.4% of frames dropped. A 104 ms long animation frame at 1.3s
         came from blockMainThread (app.js). The menu text overlaps the logo
         while it slides in."
```

### How it measures jank

Frame timing comes from inside the page, not from the video:

- **`requestAnimationFrame` timestamps.** A gap of *n* refresh intervals between two frames means *n − 1* dropped frames. The jank percentage is the share of the display's refreshes that got no new frame.
- **The refresh interval is measured.** Before each page loads, AnimaWatch samples the blank tab in the same browser, so it judges a 120 Hz display at 120 Hz. You can also set the rate yourself.
- **Long Animation Frames API** (Chromium 123+). It lists frames over 50 ms and the script, and where possible the function, that held each one up.
- **Compositor frames** (optional, `trace_compositor`). Chromium's own per-frame verdicts come from a DevTools trace. A CSS `transform` or `opacity` animation runs on the compositor and can stay smooth while the main thread is blocked. The trace shows the difference.
- **Page load is not counted.** Measurement starts once the network is idle.

The video is used only for the vision pass. Playwright records it at a fixed 25 fps, so frame gaps in the video say nothing about the page's frame rate. Versions up to 0.3.1 measured jank from the video, and a perfectly smooth animation scored 98.8% jank there. That method has been removed.

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **🎯 Frame timing** | Dropped frames, frame-time percentiles and long animation frames, measured in the page. No AI or API key needed. |
| **👁️ AI vision** | Gemini (your own API key) or Ollama (local) reviews recordings and screenshots for visual problems |
| **📱 Device emulation** | iPhone, Pixel, iPad and desktop profiles |
| **📊 Core Web Vitals** | LCP, FCP, CLS (largest session window) and TTFB |
| **🔍 Visual diff** | Pixel comparison of two pages |
| **♿ Accessibility checks** | Visual accessibility review (contrast, readability); needs vision |
| **💾 Resources** | Recordings and analyses as MCP resources |
| **📝 Prompts** | Prompt templates for animation, page and accessibility reviews |

## 🛠️ MCP Capabilities

### Tools

| Tool | Description | Needs vision |
|------|-------------|:---:|
| `analyze_fps` | 🎯 Dropped frames and long animation frames for a URL, after optional actions | No |
| `watch` | 🎬 Frame timing, plus a vision review of the recording | Optional |
| `watch_with_device` | 📱 `watch` with device emulation | Optional |
| `screenshot` | 📸 Screenshot, with a vision review when vision is on | Optional |
| `get_performance_metrics` | 📊 Core Web Vitals and page-load numbers | No |
| `compare_screenshots` | 🔍 Pixel diff between two URLs | No |
| `list_devices` | 📱 Device profiles | No |
| `check_accessibility` | ♿ Visual accessibility review | Yes |
| `analyze_with_consensus_tool` | 🤝 Gemini and Ollama review the same screenshot, and the findings they agree on are reported (not offered when hosted) | Yes (both) |
| `analyze_video` | 🎥 Vision review of a local video file (not offered when hosted) | Yes |
| `record` | ⏺️ Record without analysis, saving to a local folder (not offered when hosted) | No |

Actions (`click`, `hover`, `type`, `scroll` and `wait`) are passed as a list, for example `[{"type": "click", "selector": "#menu"}]`. They are validated before any page opens: an unknown action or a missing selector is an error, not a skipped step. Only `http` and `https` URLs are opened, plus `file://` on a local install. Each wait is capped at `MAX_RECORDING_DURATION` seconds.

### Resources

| URI | Description |
|-----|-------------|
| `animawatch://recordings/{id}` | Stored video recordings |
| `animawatch://analyses/{id}` | Stored analysis results |
| `animawatch://config` | Current server configuration (never the API key) |

### Prompts

| Prompt | Description |
|--------|-------------|
| `animation_diagnosis` | Animation review template |
| `page_analysis` | Static page review template |
| `accessibility_check` | Accessibility review template |

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/rishitank/animawatch.git
cd animawatch
uv sync
uv run playwright install chromium
```

### 2. Choose a vision option (optional)

Frame timing, Core Web Vitals, screenshots and diffs work without any of these.

- **Gemini, with your own API key.** Create a key in [Google AI Studio](https://aistudio.google.com/) and set `GEMINI_API_KEY`. See [Cost](#-cost) before you rely on the free tier.
- **Ollama, on your own machine.** See [Local vision with Ollama](#-local-vision-with-ollama).
- **None.** Set `VISION_PROVIDER=none`. AnimaWatch also runs without vision when Gemini has no key.

### 3. Configure

```bash
cp .env.example .env
# Edit .env if you use Gemini or Ollama
```

### 4. Add to Your MCP Client

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "animawatch": {
      "command": "uv",
      "args": ["--directory", "/path/to/animawatch", "run", "animawatch"],
      "env": {
        "GEMINI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Other MCP clients take the same command and arguments. To serve over streamable HTTP instead of stdio, run `uv run animawatch --http`. It listens on `SERVER_HOST:SERVER_PORT` (default `127.0.0.1:8765`) at `/mcp`. It accepts only localhost, the bind address and the names in `ALLOWED_HOSTS` in Host and Origin headers, which protects it against DNS rebinding. The HTTP transport has no authentication, so do not expose it beyond your machine without a proxy that adds it.

## 📖 Usage Examples

```
"Measure the frame rate of https://example.com while the carousel runs"
"Click #hamburger on https://example.com and watch the slide-in animation"
"Watch https://example.com on an iPhone 15 Pro with focus on scroll behaviour"
"Check accessibility on https://example.com"
"Show me the analysis from animawatch://analyses/abc123"
```

## 🔧 Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `VISION_PROVIDER` | `gemini` | `gemini`, `ollama` or `none` |
| `GEMINI_API_KEY` | (none) | Your own Gemini API key. Without it, vision is off. |
| `VISION_MODEL` | `gemini-3.8-flash` | The Gemini model. It must accept video. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen2.5-vl:7b` | The Ollama vision model |
| `REFRESH_RATE_HZ` | measured | The refresh rate to judge frames against |
| `BROWSER_HEADLESS` | `true` | Run the browser headless |
| `BROWSER_EXECUTABLE_PATH` | (Playwright's) | Launch this Chromium instead of Playwright's bundled one |
| `ALLOW_FILE_URLS` | `true` | Allow `file://` URLs |
| `VIDEO_WIDTH` / `VIDEO_HEIGHT` | `1280` / `720` | Viewport and recording size |
| `MAX_RECORDING_DURATION` | `30` | Upper bound in seconds on every wait |
| `SERVER_HOST` / `SERVER_PORT` | `127.0.0.1` / `8765` | Bind address for `--http` |
| `ALLOWED_HOSTS` | (none) | Extra host names, comma-separated, that `--http` accepts in Host and Origin headers, for example a reverse proxy's domain |

The default model was checked on 13 Nov 2026. Google retired `gemini-2.0-flash`, the previous default, on 1 Jun 2026, and lists `gemini-3.8-flash` as stable with video input ([models](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [deprecations](https://ai.google.dev/gemini-api/docs/deprecations)).

## 💰 Cost

AnimaWatch is open source (MIT), and frame timing needs no paid service. The vision pass is the only part that can cost money:

| Option | What you pay |
|--------|--------------|
| No vision | Nothing beyond your own machine |
| Ollama | Nothing to a provider. It runs on your hardware, and a 7B vision model needs a capable machine. |
| Gemini | Google bills your key according to [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing). Video input uses far more tokens than a screenshot. |

**About Gemini's free tier.** Google offers free quota with rate limits. However, the [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) (last updated 28 April 2026) say: *"You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom."* So if you make an app built on AnimaWatch available to users in the UK, the EEA or Switzerland, use a paid (billing-enabled) Gemini key, or use Ollama or no vision. This is a summary, not legal advice.

## 🏠 Local vision with Ollama

```bash
# Install and start Ollama (https://ollama.com)
ollama serve
ollama pull qwen2.5-vl:7b

# AnimaWatch needs the ollama extra, and ffmpeg for video
uv sync --extra ollama
export VISION_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5-vl:7b
```

Ollama's vision models take images, not video. For `watch`, AnimaWatch therefore takes 8 frames spread across the whole recording (up to 60 s of it) and reviews each one. This needs `ffmpeg` on your `PATH`. The model sees still frames, not motion. Frame timing is measured in the page either way.

## ☁️ Apify Actor (single-tenant Standby)

The repository includes an Apify Actor definition. Nothing is published yet.

- `.actor/actor.json` turns on Standby mode, with the MCP server at `webServerMcpPath: /mcp`.
- The `Dockerfile` is based on `apify/actor-python-playwright` and keeps that image's Playwright version, so the bundled browsers match.
- `.actor/input_schema.json` holds the user's own Gemini key, as a secret field. Without a key, vision is off.
- `.actor/pay_per_event.json` defines one event, `page-analysed`, charged once for each page a tool loads and analyses. **$0.05 is a proposed price, not a final one.**
- It is designed to be single-tenant. Each user's server runs in that user's own Apify account, so the user pays the platform compute plus the events, and nothing is shared between users. Hosted, it refuses `file://` URLs, does not offer `analyze_video`, `record` or `analyze_with_consensus_tool` (there is no Ollama), and writes no diff images. With vision turned off, any key in the input is dropped.
- Known limitation: the hosted browser will open any `http(s)` address, including private or loopback ones. Single-tenancy limits that to the caller's own run. A multi-tenant mode would first need request interception that blocks private addresses on every request, redirects included.

Run it locally with `uv pip install 'apify>=4.0.0,<5'`, then `uv run animawatch-actor`. Set `ACTOR_TEST_PAY_PER_EVENT=true` to log charges to a local dataset.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         AnimaWatch                           │
│                      (FastMCP server)                        │
├──────────────────────────────────────────────────────────────┤
│  Lifespan context (one per server, shared by all sessions)   │
│  ├── BrowserRecorder (Playwright Chromium)                   │
│  │    ├── in-page frame collector (rAF + LoAF)               │
│  │    ├── optional CDP trace (compositor frames)             │
│  │    └── video recording (vision pass only)                 │
│  ├── VisionProvider: Gemini | Ollama | none                  │
│  └── recordings / analyses                                   │
├──────────────────────────────────────────────────────────────┤
│  Tools: analyze_fps, watch, watch_with_device, screenshot,   │
│         get_performance_metrics, compare_screenshots, ...    │
│  Resources: animawatch://recordings, analyses, config        │
│  Prompts: animation_diagnosis, page_analysis, accessibility  │
├──────────────────────────────────────────────────────────────┤
│  Transports: stdio | streamable HTTP (/mcp) | Apify Standby  │
└──────────────────────────────────────────────────────────────┘
```

## 🧪 Development

```bash
uv sync --all-extras
uv run playwright install chromium
uv run pytest            # includes tests that drive a real Chromium
uv run ruff check . && uv run mypy src/
```

The frame-timing regression tests open real pages in Chromium. A smooth CSS animation must score under 2% jank. A page that blocks its main thread for 100 ms every 150 ms must score over 30%. To use a Chromium installed elsewhere, set `BROWSER_EXECUTABLE_PATH`.

## 📄 License

MIT
