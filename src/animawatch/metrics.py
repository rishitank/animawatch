"""Performance metrics extraction for Core Web Vitals.

This module provides utilities to extract and analyze performance
metrics like LCP, FID, CLS, and other Core Web Vitals from browser sessions.
"""

from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page


@dataclass
class CoreWebVitals:
    """Core Web Vitals metrics."""

    lcp_ms: float | None = None  # Largest Contentful Paint
    fid_ms: float | None = None  # First Input Delay
    cls_score: float | None = None  # Cumulative Layout Shift
    fcp_ms: float | None = None  # First Contentful Paint
    ttfb_ms: float | None = None  # Time to First Byte
    inp_ms: float | None = None  # Interaction to Next Paint


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a page."""

    url: str
    core_web_vitals: CoreWebVitals
    load_time_ms: float
    dom_content_loaded_ms: float
    resource_count: int
    total_transfer_size_kb: float
    js_heap_size_mb: float | None = None
    dom_node_count: int | None = None
    raw_entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MetricsThresholds:
    """Thresholds for good/needs-improvement/poor ratings."""

    lcp_good_ms: float = 2500.0
    lcp_poor_ms: float = 4000.0
    fid_good_ms: float = 100.0
    fid_poor_ms: float = 300.0
    cls_good: float = 0.1
    cls_poor: float = 0.25
    fcp_good_ms: float = 1800.0
    fcp_poor_ms: float = 3000.0


def rate_metric(value: float | None, good: float, poor: float) -> str:
    """Rate a metric as good, needs-improvement, or poor."""
    if value is None:
        return "unknown"
    if value <= good:
        return "good"
    if value <= poor:
        return "needs-improvement"
    return "poor"


def rate_web_vitals(
    vitals: CoreWebVitals,
    thresholds: MetricsThresholds | None = None,
) -> dict[str, str]:
    """Rate all Core Web Vitals against thresholds.

    Args:
        vitals: Core Web Vitals to rate
        thresholds: Thresholds to use (defaults to Google's recommendations)

    Returns:
        Dict mapping metric names to ratings
    """
    t = thresholds or MetricsThresholds()

    return {
        "lcp": rate_metric(vitals.lcp_ms, t.lcp_good_ms, t.lcp_poor_ms),
        "fid": rate_metric(vitals.fid_ms, t.fid_good_ms, t.fid_poor_ms),
        "cls": rate_metric(vitals.cls_score, t.cls_good, t.cls_poor),
        "fcp": rate_metric(vitals.fcp_ms, t.fcp_good_ms, t.fcp_poor_ms),
    }


async def extract_performance_metrics(page: Page, url: str) -> PerformanceMetrics:
    """Extract performance metrics from a Playwright page.

    Args:
        page: Playwright page that has loaded the URL
        url: URL that was loaded

    Returns:
        Performance metrics for the page
    """
    # Get navigation timing
    timing = await page.evaluate("""() => {
        const perf = performance.getEntriesByType('navigation')[0];
        return perf ? {
            loadTime: perf.loadEventEnd - perf.startTime,
            domContentLoaded: perf.domContentLoadedEventEnd - perf.startTime,
            ttfb: perf.responseStart - perf.requestStart,
        } : null;
    }""")

    # Get resource metrics
    resources = await page.evaluate("""() => {
        const entries = performance.getEntriesByType('resource');
        return {
            count: entries.length,
            totalSize: entries.reduce((sum, e) => sum + (e.transferSize || 0), 0),
        };
    }""")

    # Get Core Web Vitals using web-vitals library pattern
    vitals = await page.evaluate("""() => {
        const result = {};

        // LCP from largest-contentful-paint entries
        const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
        if (lcpEntries.length > 0) {
            result.lcp = lcpEntries[lcpEntries.length - 1].startTime;
        }

        // FCP from paint entries
        const paintEntries = performance.getEntriesByType('paint');
        for (const entry of paintEntries) {
            if (entry.name === 'first-contentful-paint') {
                result.fcp = entry.startTime;
            }
        }

        // CLS from layout-shift entries
        const clsEntries = performance.getEntriesByType('layout-shift');
        result.cls = clsEntries
            .filter(e => !e.hadRecentInput)
            .reduce((sum, e) => sum + e.value, 0);

        return result;
    }""")

    # Get memory info if available
    memory = await page.evaluate("""() => {
        if (performance.memory) {
            return performance.memory.usedJSHeapSize / (1024 * 1024);
        }
        return null;
    }""")

    # Get DOM node count
    dom_count = await page.evaluate("() => document.getElementsByTagName('*').length")

    core_vitals = CoreWebVitals(
        lcp_ms=vitals.get("lcp") if vitals else None,
        fcp_ms=vitals.get("fcp") if vitals else None,
        cls_score=vitals.get("cls") if vitals else None,
        ttfb_ms=timing.get("ttfb") if timing else None,
    )

    return PerformanceMetrics(
        url=url,
        core_web_vitals=core_vitals,
        load_time_ms=timing.get("loadTime", 0) if timing else 0,
        dom_content_loaded_ms=timing.get("domContentLoaded", 0) if timing else 0,
        resource_count=resources.get("count", 0) if resources else 0,
        total_transfer_size_kb=(resources.get("totalSize", 0) / 1024) if resources else 0,
        js_heap_size_mb=memory,
        dom_node_count=dom_count,
    )


async def collect_metrics_during_interaction(
    page: Page,
    interaction_fn: Any,
) -> CoreWebVitals:
    """Collect metrics while user interaction is happening.

    Args:
        page: Playwright page
        interaction_fn: Async function that performs user interactions

    Returns:
        Core Web Vitals collected during interaction
    """
    # Start observing
    await page.evaluate("""() => {
        window.__fidObserver = null;
        window.__fidValue = null;

        const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (entry.entryType === 'first-input') {
                    window.__fidValue = entry.processingStart - entry.startTime;
                }
            }
        });

        try {
            observer.observe({ type: 'first-input', buffered: true });
            window.__fidObserver = observer;
        } catch (e) {}
    }""")

    # Perform user interactions
    await interaction_fn()

    # Collect FID if captured
    fid = await page.evaluate("() => window.__fidValue")

    return CoreWebVitals(fid_ms=fid)


def generate_metrics_report(metrics: PerformanceMetrics) -> str:
    """Generate a human-readable performance report.

    Args:
        metrics: Performance metrics to report

    Returns:
        Formatted report string
    """
    vitals = metrics.core_web_vitals
    ratings = rate_web_vitals(vitals)

    lines = [
        "📊 Performance Metrics Report",
        "=" * 40,
        f"URL: {metrics.url}",
        "",
        "Core Web Vitals:",
    ]

    if vitals.lcp_ms is not None:
        rating = _rating_emoji(ratings["lcp"])
        lines.append(f"  {rating} LCP: {vitals.lcp_ms:.0f}ms ({ratings['lcp']})")

    if vitals.fcp_ms is not None:
        rating = _rating_emoji(ratings["fcp"])
        lines.append(f"  {rating} FCP: {vitals.fcp_ms:.0f}ms ({ratings['fcp']})")

    if vitals.cls_score is not None:
        rating = _rating_emoji(ratings["cls"])
        lines.append(f"  {rating} CLS: {vitals.cls_score:.3f} ({ratings['cls']})")

    if vitals.fid_ms is not None:
        rating = _rating_emoji(ratings["fid"])
        lines.append(f"  {rating} FID: {vitals.fid_ms:.0f}ms ({ratings['fid']})")

    if vitals.ttfb_ms is not None:
        lines.append(f"  ⏱️  TTFB: {vitals.ttfb_ms:.0f}ms")

    lines.extend(
        [
            "",
            "Page Metrics:",
            f"  📦 Load Time: {metrics.load_time_ms:.0f}ms",
            f"  📄 DOM Content Loaded: {metrics.dom_content_loaded_ms:.0f}ms",
            f"  🔗 Resources: {metrics.resource_count}",
            f"  📡 Transfer Size: {metrics.total_transfer_size_kb:.1f}KB",
        ]
    )

    if metrics.dom_node_count:
        lines.append(f"  🌳 DOM Nodes: {metrics.dom_node_count}")

    if metrics.js_heap_size_mb:
        lines.append(f"  💾 JS Heap: {metrics.js_heap_size_mb:.1f}MB")

    return "\n".join(lines)


def _rating_emoji(rating: str) -> str:
    """Get emoji for rating."""
    return {"good": "✅", "needs-improvement": "🟡", "poor": "🔴"}.get(rating, "❓")
