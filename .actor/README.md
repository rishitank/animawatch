# AnimaWatch MCP server

AnimaWatch is a Model Context Protocol (MCP) server that checks how web pages animate. It opens a page in headless Chromium and measures dropped frames inside the page. It can also record the page and have Gemini review the recording for visual problems.

## What it measures

- **Dropped frames.** It records `requestAnimationFrame` timestamps in the page and compares them with the display's refresh interval, which it measures in the same browser. It reports the share of refreshes that got no new frame, and frame-time percentiles.
- **Long animation frames.** It lists frames over 50 ms from Chromium's Long Animation Frames API, with the script and function that held each one up.
- **Compositor frames** (optional, `trace_compositor: true`). It reads Chromium's own per-frame verdicts from a trace. They show whether a CSS animation stayed smooth while the main thread was busy.
- **Core Web Vitals** (LCP, FCP, CLS, TTFB), screenshots, visual diffs between two pages, and device emulation.
- **AI vision** (optional). Gemini reviews a recording or screenshot for visual glitches, layout shifts and accessibility problems. It uses **your own Gemini API key**. Without a key, vision is off and everything else still works.

The video recording runs at about 25 fps. It is used only for the vision review, never for frame timing.

## Connect

This Actor runs in Standby mode. Point your MCP client at:

```
https://<username>--animawatch.apify.actor/mcp
Authorization: Bearer <your Apify API token>
```

## Settings (Actor input)

| Field | What it does |
|---|---|
| `geminiApiKey` | Your own Gemini API key, stored encrypted. Leave it empty to turn vision off. If you or your users are in the UK, the EEA or Switzerland, Google's Gemini API terms require a paid (billing-enabled) key. |
| `visionEnabled` | Turns vision on or off. |
| `visionModel` | The Gemini model to use. The default is `gemini-3.8-flash`, and the model must accept video. |
| `maxWaitSeconds` | The longest one call waits or measures after a page loads (1 to 120 seconds). |

## Tools

- `analyze_fps`: dropped frames and long animation frames for a URL, after optional actions.
- `watch` and `watch_with_device`: frame timing plus a vision review of the recording.
- `screenshot`, `check_accessibility`, `compare_screenshots`, `get_performance_metrics`, `analyze_with_consensus_tool` and `list_devices`.

Only `http` and `https` URLs are opened.

## What you pay

Your server runs in your own Apify account (single-tenant). You pay:

- the Apify platform usage of your run;
- a fee for each page a tool loads and analyses. Comparing two pages counts as two.

If you use your own Gemini key, Google bills you for it separately. Pages that fail to load are not charged. When your run's spending limit is reached, tools refuse new pages instead of working unpaid.
