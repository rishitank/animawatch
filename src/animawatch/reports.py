"""Report generation for analysis results.

This module provides utilities to generate PDF and HTML reports
from AnimaWatch analysis results, including screenshots and findings.
"""

import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import AnalysisResult, Severity


@dataclass
class ReportConfig:
    """Configuration for report generation."""

    title: str = "AnimaWatch Analysis Report"
    include_screenshots: bool = True
    include_metadata: bool = True
    max_findings: int = 50  # Maximum findings to include
    output_format: str = "html"  # "html" or "pdf"


def generate_html_report(
    result: AnalysisResult,
    screenshots: list[Path] | None = None,
    config: ReportConfig | None = None,
) -> str:
    """Generate an HTML report from analysis result.

    Args:
        result: Analysis result to report
        screenshots: Optional list of screenshot paths to include
        config: Report configuration

    Returns:
        HTML string of the report
    """
    cfg = config or ReportConfig()
    timestamp = datetime.now().isoformat()

    # Start HTML document
    html = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"    <title>{cfg.title}</title>",
        "    <style>",
        _get_report_styles(),
        "    </style>",
        "</head>",
        "<body>",
        f"    <h1>{cfg.title}</h1>",
        f"    <p class='timestamp'>Generated: {timestamp}</p>",
    ]

    # Summary section
    html.extend(_generate_summary_section(result))

    # Screenshots section
    if cfg.include_screenshots and screenshots:
        html.extend(_generate_screenshots_section(screenshots))

    # Findings section
    html.extend(_generate_findings_section(result, cfg.max_findings))

    # Metadata section
    if cfg.include_metadata:
        html.extend(_generate_metadata_section(result))

    html.extend(["</body>", "</html>"])

    return "\n".join(html)


def _get_report_styles() -> str:
    """Return CSS styles for the report."""
    return """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        h1 { color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }
        h2 { color: #16213e; margin-top: 30px; }
        .timestamp { color: #666; font-size: 0.9em; }
        .summary { background: white; padding: 20px; border-radius: 8px; margin: 20px 0;
                   box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .score { font-size: 2em; font-weight: bold; }
        .score.good { color: #2ecc71; }
        .score.warning { color: #f39c12; }
        .score.bad { color: #e74c3c; }
        .finding { background: white; padding: 15px; margin: 10px 0; border-radius: 8px;
                   border-left: 4px solid #ddd; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .finding.critical { border-left-color: #e74c3c; }
        .finding.major { border-left-color: #f39c12; }
        .finding.minor { border-left-color: #3498db; }
        .finding.info { border-left-color: #95a5a6; }
        .finding-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .severity { padding: 2px 8px; border-radius: 4px; font-size: 0.8em; color: white; }
        .severity.critical { background: #e74c3c; }
        .severity.major { background: #f39c12; }
        .severity.minor { background: #3498db; }
        .severity.info { background: #95a5a6; }
        .confidence { color: #666; font-size: 0.9em; }
        .screenshot { max-width: 100%; border-radius: 8px; margin: 10px 0;
                      box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .screenshot-grid { display: grid; gap: 20px; margin: 20px 0;
                           grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
        .metadata { background: #1a1a2e; color: white; padding: 15px; border-radius: 8px;
                    margin-top: 30px; font-family: monospace; }
        .metadata dt { color: #e94560; }
        .metadata dd { margin-left: 20px; margin-bottom: 10px; }
    """


def _generate_summary_section(result: AnalysisResult) -> list[str]:
    """Generate summary section HTML."""
    if result.overall_score >= 80:
        score_class = "good"
    elif result.overall_score >= 50:
        score_class = "warning"
    else:
        score_class = "bad"

    return [
        "    <div class='summary'>",
        "        <h2>Summary</h2>",
        f"        <p class='score {score_class}'>{result.overall_score}/100</p>",
        f"        <p>{result.summary}</p>",
        f"        <p>Total Findings: {len(result.findings)} "
        f"({result.critical_count} critical, {result.major_count} major, "
        f"{result.minor_count} minor)</p>",
        "    </div>",
    ]


def _generate_screenshots_section(screenshots: list[Path]) -> list[str]:
    """Generate screenshots section HTML."""
    html = [
        "    <h2>Screenshots</h2>",
        "    <div class='screenshot-grid'>",
    ]

    for i, path in enumerate(screenshots[:10]):  # Limit to 10 screenshots
        if path.exists():
            # Embed image as base64
            with open(path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()
            suffix = path.suffix.lower()
            mime_type = "image/png" if suffix == ".png" else "image/jpeg"
            html.append(
                f"        <img class='screenshot' src='data:{mime_type};base64,{img_data}' "
                f"alt='Screenshot {i + 1}' />"
            )

    html.append("    </div>")
    return html


def _generate_findings_section(result: AnalysisResult, max_findings: int) -> list[str]:
    """Generate findings section HTML."""
    html = ["    <h2>Findings</h2>"]

    # Sort by severity (critical first)
    severity_order = {Severity.CRITICAL: 0, Severity.MAJOR: 1, Severity.MINOR: 2, Severity.INFO: 3}
    sorted_findings = sorted(result.findings, key=lambda f: severity_order.get(f.severity, 4))

    for finding in sorted_findings[:max_findings]:
        severity_val = finding.severity.value
        html.extend(
            [
                f"    <div class='finding {severity_val}'>",
                "        <div class='finding-header'>",
                f"            <strong>{finding.element}</strong>",
                f"            <span class='severity {severity_val}'>{severity_val.upper()}</span>",
                "        </div>",
                f"        <p>{finding.description}</p>",
                f"        <p><strong>Suggestion:</strong> {finding.suggestion}</p>",
                f"        <p class='confidence'>Confidence: {finding.confidence}%</p>",
                "    </div>",
            ]
        )

    if len(result.findings) > max_findings:
        html.append(f"    <p>... and {len(result.findings) - max_findings} more findings</p>")

    return html


def _generate_metadata_section(result: AnalysisResult) -> list[str]:
    """Generate metadata section HTML."""
    meta = result.metadata
    return [
        "    <div class='metadata'>",
        "        <h2>Analysis Metadata</h2>",
        "        <dl>",
        f"            <dt>Provider</dt><dd>{meta.provider}</dd>",
        f"            <dt>Model</dt><dd>{meta.model}</dd>",
        f"            <dt>Duration</dt><dd>{meta.analysis_duration_ms}ms</dd>",
        f"            <dt>Average Confidence</dt><dd>{result.average_confidence:.1f}%</dd>",
        "        </dl>",
        "    </div>",
    ]


def save_html_report(
    result: AnalysisResult,
    output_path: Path,
    screenshots: list[Path] | None = None,
    config: ReportConfig | None = None,
) -> Path:
    """Generate and save an HTML report.

    Args:
        result: Analysis result to report
        output_path: Path to save the HTML file
        screenshots: Optional screenshots to include
        config: Report configuration

    Returns:
        Path to the saved report
    """
    html = generate_html_report(result, screenshots, config)
    output_path.write_text(html, encoding="utf-8")
    return output_path


async def generate_pdf_report(
    result: AnalysisResult,
    output_path: Path,
    screenshots: list[Path] | None = None,
    config: ReportConfig | None = None,
) -> Path:
    """Generate a PDF report using Playwright.

    Args:
        result: Analysis result to report
        output_path: Path to save the PDF file
        screenshots: Optional screenshots to include
        config: Report configuration

    Returns:
        Path to the saved PDF report
    """
    from playwright.async_api import async_playwright

    # First generate HTML
    cfg = config or ReportConfig()
    cfg.output_format = "pdf"
    html = generate_html_report(result, screenshots, cfg)

    # Use Playwright to render HTML to PDF
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(path=str(output_path), format="A4", print_background=True)
        await browser.close()

    return output_path
