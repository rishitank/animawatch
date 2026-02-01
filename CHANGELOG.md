# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-01

### 🚀 Features

- Renamed project from visual-diagnosis-mcp to AnimaWatch
- Upgraded from low-level MCP Server to FastMCP (latest Python SDK)
- Implemented MCP spec 2025-11-25 features:
  - Lifespan management with typed AppContext
  - Resources for recordings and analyses (URI templates)
  - Prompts for different analysis types
  - Image content type for screenshots
- New tools: watch, screenshot, record, analyze_video, check_accessibility
- Resources: `animawatch://recordings/{id}`, `animawatch://analyses/{id}`, `animawatch://config`
- Prompts: animation_diagnosis, page_analysis, accessibility_check
- Support both stdio and streamable-http transports

## [0.1.0] - 2026-02-01

### 🚀 Features

- Initial release
- Browser automation and video recording using Playwright
- AI vision analysis using Gemini 2.0 Flash (FREE) or Ollama (local)
- Animation diagnosis tools for detecting jank, stuttering, visual artifacts
- Screenshot analysis for non-animated issues
- Configurable via environment variables

