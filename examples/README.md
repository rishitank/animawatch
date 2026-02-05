# AnimaWatch Examples

Example scripts demonstrating how to use AnimaWatch programmatically.

## Prerequisites

1. Install AnimaWatch and its dependencies:

   ```bash
   cd /path/to/animawatch
   uv sync
   uv run playwright install chromium
   ```

2. Set up your Gemini API key (free):

   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

   Get a free key at [Google AI Studio](https://aistudio.google.com/).

## Examples

### 1. Basic Animation Check

Records a webpage and analyzes it for animation issues.

```bash
uv run python examples/basic_animation_check.py
```

**What it does:**
- Opens a browser and navigates to a URL
- Records for 3 seconds to capture animations
- Sends the video to Gemini for analysis
- Reports any jank, stuttering, or timing issues

### 2. Screenshot Analysis

Takes a screenshot and analyzes it for visual/design issues.

```bash
uv run python examples/screenshot_analysis.py
```

**What it does:**
- Captures a full-page screenshot
- Analyzes layout, colors, and typography
- Reports issues with recommendations

### 3. Accessibility Check

Checks a webpage for visual accessibility issues.

```bash
uv run python examples/accessibility_check.py
```

**What it does:**
- Captures a full-page screenshot
- Analyzes for WCAG accessibility issues
- Reports contrast, readability, and touch target problems
- Provides an overall accessibility rating

### 4. Visual Comparison / Regression Testing

Compares two pages to detect visual differences.

```bash
uv run python examples/visual_comparison.py
```

**What it does:**
- Captures screenshots of two URLs (baseline vs comparison)
- Uses multi-image analysis to detect differences
- Reports layout, style, and content changes
- Categorizes differences by severity

**Use cases:**
- Compare staging vs production
- Before/after deployment checks
- A/B test visual validation

### 5. Multi-Page Workflow Testing

Tests user journeys across multiple pages with animations.

```bash
uv run python examples/multipage_workflow.py
```

**What it does:**
- Executes a series of workflow steps
- Records and analyzes each step
- Checks page transitions and loading animations
- Validates interactive element feedback

**Use cases:**
- E-commerce checkout flows
- User onboarding sequences
- Multi-step form wizards

### 6. Form Interaction Testing

Tests form interactions and input animations.

```bash
uv run python examples/form_interaction.py
```

**What it does:**
- Records form field interactions (focus, type, blur)
- Analyzes input focus states and transitions
- Checks validation feedback animations
- Validates button state changes

**Use cases:**
- Login/signup form testing
- Contact form validation
- Search input behavior

### 7. CI/CD Integration

Run AnimaWatch in automated pipelines with structured output.

```bash
# Basic usage
uv run python examples/ci_integration.py --url https://your-site.com

# With output file and custom threshold
uv run python examples/ci_integration.py \
  --url https://your-site.com \
  --threshold 0.9 \
  --output results.json
```

**What it does:**
- Analyzes a page and returns a quality score (0.0-1.0)
- Outputs structured JSON for CI systems
- Returns exit code 0 (pass) or 1 (fail)
- Counts issues by severity

**GitHub Actions Example:**
```yaml
- name: Visual QA Check
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
  run: |
    uv run python examples/ci_integration.py \
      --url https://your-site.com \
      --threshold 0.8 \
      --output visual-qa-results.json

- name: Upload Results
  uses: actions/upload-artifact@v4
  with:
    name: visual-qa-results
    path: visual-qa-results.json
```

## Customizing Examples

Edit the URL in any example's `main()` function:

```python
async def main() -> None:
    url = "https://your-website.com"  # Change this
    # ...
```

## Using with Ollama (100% Local)

To run without any API calls:

```bash
# Install and start Ollama
brew install ollama
ollama serve

# Pull a vision model
ollama pull qwen2.5-vl:7b

# Configure environment
export VISION_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5-vl:7b

# Run example
uv run python examples/screenshot_analysis.py
```

**Note**: Ollama doesn't support direct video analysis, so `basic_animation_check.py` 
will not work with Ollama. Use screenshot-based examples instead.

## Writing Your Own Scripts

```python
import asyncio
from animawatch.browser import BrowserRecorder
from animawatch.vision import get_vision_provider

async def my_analysis():
    browser = BrowserRecorder()
    vision = get_vision_provider()
    
    try:
        await browser.start()
        
        # Record with actions
        video_path = await browser.record_interaction(
            url="https://example.com",
            actions=[
                {"type": "click", "selector": ".menu-button"},
                {"type": "wait", "duration": 1.0},
            ],
            wait_time=2.0,
        )
        
        # Analyze
        result = await vision.analyze_video(video_path, "Check for animation issues")
        print(result)
        
    finally:
        await browser.stop()

asyncio.run(my_analysis())
```

## Available Actions for Recording

| Action | Parameters | Description |
|--------|------------|-------------|
| `click` | `selector` | Click an element |
| `type` | `selector`, `text` | Type text into input |
| `scroll` | `x`, `y` | Scroll by pixels |
| `hover` | `selector` | Hover over element |
| `wait` | `duration` | Wait for seconds |

