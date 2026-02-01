# Visual Diagnosis MCP Server

An MCP (Model Context Protocol) server that enables AI assistants to diagnose web animations and UI issues by **watching** them like a human tester would.

## 🎯 What It Does

```
YOU: "Diagnose the animation on this modal"
     ↓
MCP SERVER:
  1. Records the browser interaction as video (Playwright)
  2. Sends video to Vision AI (Gemini FREE or Ollama local)
  3. AI watches the recording and identifies issues
     ↓
RESULT: "Jank detected at 1.2s - fade-in stutters for 180ms"
```

## ✨ Features

- **🎥 Video Recording**: Records browser interactions using Playwright
- **👁️ AI Vision Analysis**: Uses Gemini 2.0 Flash (FREE) or Ollama (local) to analyze recordings
- **🔍 Animation Diagnosis**: Detects jank, stuttering, timing issues, visual artifacts
- **📸 Screenshot Analysis**: Fast static analysis for non-animated issues
- **🆓 100% FREE**: Uses Gemini's free tier or runs entirely locally with Ollama

## 🛠️ MCP Tools

| Tool | Description |
|------|-------------|
| `diagnose_animation` | Record and analyze a page for animation issues |
| `diagnose_page` | Screenshot-based analysis (faster, no video) |
| `analyze_video` | Analyze an existing video file |
| `record_interaction` | Just record without analysis |

## 🚀 Quick Start

### 1. Install

```bash
cd ~/github/visual-diagnosis-mcp-server
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
    "visual-diagnosis": {
      "command": "uv",
      "args": ["--directory", "/Users/YOUR_USER/github/visual-diagnosis-mcp-server", "run", "visual-diagnosis-mcp"],
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
    "visual-diagnosis": {
      "command": "uv",
      "args": ["--directory", "/Users/YOUR_USER/github/visual-diagnosis-mcp-server", "run", "visual-diagnosis-mcp"],
      "env": {
        "GEMINI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## 📖 Usage Examples

### Diagnose Animation Issues
```
"Use visual-diagnosis to check the modal animation on https://example.com"
```

The tool will:
1. Navigate to the URL
2. Record the page for 3 seconds
3. Upload video to Gemini
4. Return detailed analysis with timestamps

### Perform Actions Then Analyze
```
"Record clicking the hamburger menu on https://example.com and diagnose the animation"
```

### Custom Analysis Prompt
```
"Analyze https://example.com for any loading spinner issues"
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

## 📄 License

MIT

