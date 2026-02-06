# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1](https://github.com/rishitank/animawatch/compare/v0.3.0...v0.3.1) (2026-02-06)


### 🚀 Features

* add comprehensive feature upgrades ([#8](https://github.com/rishitank/animawatch/issues/8)) ([e12ce55](https://github.com/rishitank/animawatch/commit/e12ce55b87fa115c0fb733216f4ebe4bb601f10e))
* integrate new modules as MCP tools ([#12](https://github.com/rishitank/animawatch/issues/12)) ([5ae50b2](https://github.com/rishitank/animawatch/commit/5ae50b2e6936ed9352fe1d72fb3e6b88265a97f2))


### ♻️ Refactoring

* remove modules that don't fit core debugging use case ([#10](https://github.com/rishitank/animawatch/issues/10)) ([6a828bc](https://github.com/rishitank/animawatch/commit/6a828bc57b3ecdfc3d8f1835cef3aaee30ed6631))


### 🧪 Tests

* add comprehensive tests for new modules ([#11](https://github.com/rishitank/animawatch/issues/11)) ([0367c7d](https://github.com/rishitank/animawatch/commit/0367c7df06d9d5de3fe542362c8be051d2512182))

## [0.3.0](https://github.com/rishitank/animawatch/compare/v0.2.0...v0.3.0) (2026-02-06)


### ⚠ BREAKING CHANGES

* Renamed package from visual-diagnosis-mcp to animawatch

### 🚀 Features

* Add production-ready improvements, new examples, and fix Release Please ([#5](https://github.com/rishitank/animawatch/issues/5)) ([cdfda30](https://github.com/rishitank/animawatch/commit/cdfda30c7084a2f267ff08275fddb5e17af2cf4f))
* initial implementation of visual diagnosis MCP server ([857759c](https://github.com/rishitank/animawatch/commit/857759cfbcb39d799248ad65acd1aea66834b1d2))
* Migrate to google-genai SDK, fix vulnerability, and add examples ([#4](https://github.com/rishitank/animawatch/issues/4)) ([7aeeb8b](https://github.com/rishitank/animawatch/commit/7aeeb8b1dc250c2185d6f67a3ed17c17b183903e))
* rename to AnimaWatch and upgrade to FastMCP with latest MCP spec ([ec94aa6](https://github.com/rishitank/animawatch/commit/ec94aa6aac7840e9ab67a2d23ff5f9587a57ccaf))


### 🐛 Bug Fixes

* resolve lint and type errors ([#2](https://github.com/rishitank/animawatch/issues/2)) ([7c0fc19](https://github.com/rishitank/animawatch/commit/7c0fc19d2fc8bf938147c93dd6bdcbd7acbef9d6))
* Use PAT for Release Please to allow PR creation ([#6](https://github.com/rishitank/animawatch/issues/6)) ([5ba64a0](https://github.com/rishitank/animawatch/commit/5ba64a0bf837f89d492f6d3a5313ebcc09514e9b))


### 📚 Documentation

* update BRANCH_PROTECTION.md to reflect ruleset configuration ([93442fa](https://github.com/rishitank/animawatch/commit/93442fa7da6d9b7ccc4cdc9c3942e0712df0f171))


### 🧪 Tests

* add comprehensive tests for browser, vision, and server modules ([#3](https://github.com/rishitank/animawatch/issues/3)) ([f4ccff9](https://github.com/rishitank/animawatch/commit/f4ccff994939572082f16b1f0b1f127c98c73b71))


### 🔧 CI/CD

* add GitHub workflows, CodeRabbit, dependabot, and release-please configuration ([a34a05c](https://github.com/rishitank/animawatch/commit/a34a05c1240d3a92e966883d85e568dbabfe78cc))
* **deps:** bump astral-sh/setup-uv from 5 to 7 ([#1](https://github.com/rishitank/animawatch/issues/1)) ([e6291b8](https://github.com/rishitank/animawatch/commit/e6291b87f794a3b4020df7bd8a7359677c409af8))

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
