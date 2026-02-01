# 🎬 AnimaWatch

> MCP server that **watches** web animations like a human tester — detects jank, stuttering, visual artifacts using AI vision.

Built with **FastMCP** leveraging the latest MCP spec (2025-11-25) features.

## ✨ What It Does

```
YOU: "Watch the modal animation on this page"
     ↓
ANIMAWATCH:
  1. Records browser interaction as video (Playwright)
  2. Sends video to Vision AI (Gemini FREE or Ollama local)
  3. AI watches the recording like a human would
     ↓
RESULT: "Jank detected at 1.2s - fade-in stutters for 180ms"
```

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **🎥 Video Recording** | Records browser interactions using Playwright |
| **👁️ AI Vision Analysis** | Uses Gemini 2.0 Flash (FREE) or Ollama (local) |
| **🔍 Animation Diagnosis** | Detects jank, stuttering, timing issues, visual artifacts |
| **📸 Screenshot Analysis** | Fast static analysis for non-animated issues |
| **♿ Accessibility Checks** | Visual accessibility analysis (contrast, readability) |
| **💾 Resources** | Access recordings and analyses via MCP resources |
| **📝 Prompts** | Pre-defined prompt templates for different analysis types |
| **🆓 100% FREE** | Uses Gemini's free tier or runs locally with Ollama |

## 🛠️ MCP Capabilities

### Tools

| Tool | Description |
|------|-------------|
| `watch` | 🎬 Record and analyze animations (main tool) |
| `screenshot` | 📸 Fast static page analysis with image return |
| `analyze_video` | 🎥 Analyze an existing video file |
| `record` | ⏺️ Just record without analysis |
| `check_accessibility` | ♿ Visual accessibility analysis |

### Resources

| URI | Description |
|-----|-------------|
| `animawatch://recordings/{id}` | Access stored video recordings |
| `animawatch://analyses/{id}` | Access stored analysis results |
| `animawatch://config` | Current server configuration |

### Prompts

| Prompt | Description |
|--------|-------------|
| `animation_diagnosis` | Comprehensive animation analysis template |
| `page_analysis` | Static page visual analysis template |
| `accessibility_check` | Accessibility-focused analysis template |

## 🚀 Quick Start

### 1. Install

```bash
cd ~/github/animawatch
uv sync
uv run playwright install chromium
```

### 2. Get FREE Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Click "Get API Key" → Create API key
3. Copy your key

### 3. Configure

```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 4. Add to Your MCP Client

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "animawatch": {
      "command": "uv",
      "args": ["--directory", "/Users/YOUR_USER/github/animawatch", "run", "animawatch"],
      "env": {
        "GEMINI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Augment Code** (settings):
```json
{
  "mcpServers": {
    "animawatch": {
      "command": "uv",
      "args": ["--directory", "/Users/YOUR_USER/github/animawatch", "run", "animawatch"],
      "env": {
        "GEMINI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## 📖 Usage Examples

### Watch Animation Issues
```
"Watch the modal animation on https://example.com for any jank"
```

### Perform Actions Then Watch
```
"Click the hamburger menu on https://example.com and watch the slide-in animation"
```

### Focus on Specific Area
```
"Watch https://example.com with focus on scroll behavior"
```

### Accessibility Check
```
"Check accessibility on https://example.com"
```

### Access Previous Results
```
"Show me the analysis from animawatch://analyses/abc123"
```

## 🔧 Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `GEMINI_API_KEY` | - | Google Gemini API key (FREE) |
| `VISION_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `VISION_MODEL` | `gemini-2.0-flash` | Vision model to use |
| `BROWSER_HEADLESS` | `true` | Run browser headless |
| `VIDEO_WIDTH` | `1280` | Recording width |
| `VIDEO_HEIGHT` | `720` | Recording height |
| `MAX_RECORDING_DURATION` | `30` | Max recording seconds |

## 🏠 100% Local with Ollama

To run entirely locally (no API calls):

```bash
# Install Ollama
brew install ollama
ollama serve

# Pull a vision model
ollama pull qwen2.5-vl:7b

# Configure
export VISION_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5-vl:7b
```

**Note**: Ollama doesn't support direct video analysis, so it will analyze screenshots/frames instead.

## 💰 Cost

| Provider | Cost |
|----------|------|
| Gemini (AI Studio) | **FREE** (15 req/min, 1M tokens/day) |
| Ollama | **FREE** (runs locally) |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       AnimaWatch                            │
│                    (FastMCP Server)                         │
├─────────────────────────────────────────────────────────────┤
│  Lifespan Context (AppContext)                              │
│  ├── BrowserRecorder (Playwright)                           │
│  ├── VisionProvider (Gemini/Ollama)                         │
│  ├── recordings: dict[id, Path]                             │
│  └── analyses: dict[id, str]                                │
├─────────────────────────────────────────────────────────────┤
│  Tools       │  Resources              │  Prompts           │
│  ─────────   │  ─────────────────────  │  ──────────────    │
│  watch       │  animawatch://recordings│  animation_diagnosis│
│  screenshot  │  animawatch://analyses  │  page_analysis     │
│  record      │  animawatch://config    │  accessibility_check│
│  analyze_video│                        │                    │
│  check_access│                         │                    │
└─────────────────────────────────────────────────────────────┘
```

## 📄 License

MIT

