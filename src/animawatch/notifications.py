"""Notification services for AlertWatch analysis results.

This module provides utilities to send notifications via
Slack, Discord, and other webhook-based services.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from .models import AnalysisResult, Severity


@dataclass
class NotificationConfig:
    """Configuration for notifications."""

    webhook_url: str
    service: str = "slack"  # "slack", "discord", "generic"
    mention_on_critical: bool = True
    mention_users: list[str] | None = None  # User IDs to mention
    include_findings: bool = True
    max_findings: int = 5


async def send_notification(
    result: AnalysisResult,
    config: NotificationConfig,
) -> bool:
    """Send a notification about analysis results.

    Args:
        result: Analysis result to notify about
        config: Notification configuration

    Returns:
        True if notification was sent successfully
    """
    if config.service == "slack":
        payload = _build_slack_payload(result, config)
    elif config.service == "discord":
        payload = _build_discord_payload(result, config)
    else:
        payload = _build_generic_payload(result, config)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            config.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        return response.status_code in (200, 204)


def _build_slack_payload(result: AnalysisResult, config: NotificationConfig) -> dict[str, Any]:
    """Build Slack webhook payload."""
    # Determine color based on score
    if result.overall_score >= 80:
        color = "#2ecc71"  # Green
    elif result.overall_score >= 50:
        color = "#f39c12"  # Orange
    else:
        color = "#e74c3c"  # Red

    # Build message blocks
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔍 AnimaWatch Analysis Report"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Score:* {result.overall_score}/100"},
                {"type": "mrkdwn", "text": f"*Findings:* {len(result.findings)}"},
                {"type": "mrkdwn", "text": f"*Critical:* {result.critical_count}"},
                {"type": "mrkdwn", "text": f"*Major:* {result.major_count}"},
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Summary:* {result.summary}"}},
    ]

    # Add findings if configured
    if config.include_findings and result.findings:
        findings_text = _format_findings_for_slack(result, config.max_findings)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": findings_text}})

    # Add mentions if critical issues
    text = ""
    if config.mention_on_critical and result.critical_count > 0 and config.mention_users:
        mentions = " ".join(f"<@{uid}>" for uid in config.mention_users)
        text = f"⚠️ {mentions} - Critical issues detected!"

    return {"text": text, "attachments": [{"color": color, "blocks": blocks}]}


def _format_findings_for_slack(result: AnalysisResult, max_findings: int) -> str:
    """Format findings for Slack message."""
    lines = ["*Top Findings:*"]

    severity_icons = {
        Severity.CRITICAL: "🔴",
        Severity.MAJOR: "🟠",
        Severity.MINOR: "🟡",
        Severity.INFO: "🔵",
    }

    for finding in result.findings[:max_findings]:
        icon = severity_icons.get(finding.severity, "⚪")
        lines.append(f"{icon} {finding.element}: {finding.description[:80]}...")

    if len(result.findings) > max_findings:
        lines.append(f"_...and {len(result.findings) - max_findings} more_")

    return "\n".join(lines)


def _build_discord_payload(result: AnalysisResult, config: NotificationConfig) -> dict[str, Any]:
    """Build Discord webhook payload."""
    if result.overall_score >= 80:
        color = 0x2ECC71
    elif result.overall_score >= 50:
        color = 0xF39C12
    else:
        color = 0xE74C3C

    fields = [
        {"name": "Score", "value": f"{result.overall_score}/100", "inline": True},
        {"name": "Findings", "value": str(len(result.findings)), "inline": True},
        {"name": "Critical", "value": str(result.critical_count), "inline": True},
    ]

    if config.include_findings and result.findings:
        findings_text = _format_findings_for_discord(result, config.max_findings)
        fields.append({"name": "Top Issues", "value": findings_text, "inline": False})

    content = ""
    if config.mention_on_critical and result.critical_count > 0 and config.mention_users:
        content = " ".join(f"<@{uid}>" for uid in config.mention_users)

    return {
        "content": content,
        "embeds": [
            {
                "title": "🔍 AnimaWatch Analysis Report",
                "description": result.summary,
                "color": color,
                "fields": fields,
            }
        ],
    }


def _format_findings_for_discord(result: AnalysisResult, max_findings: int) -> str:
    """Format findings for Discord embed."""
    lines = []

    severity_icons = {
        Severity.CRITICAL: "🔴",
        Severity.MAJOR: "🟠",
        Severity.MINOR: "🟡",
        Severity.INFO: "🔵",
    }

    for finding in result.findings[:max_findings]:
        icon = severity_icons.get(finding.severity, "⚪")
        desc = finding.description[:60]
        if len(finding.description) > 60:
            desc += "..."
        lines.append(f"{icon} **{finding.element}**: {desc}")

    if len(result.findings) > max_findings:
        lines.append(f"*...and {len(result.findings) - max_findings} more*")

    return "\n".join(lines)


def _build_generic_payload(result: AnalysisResult, config: NotificationConfig) -> dict[str, Any]:
    """Build a generic JSON webhook payload."""
    return {
        "title": "AnimaWatch Analysis Report",
        "score": result.overall_score,
        "summary": result.summary,
        "findings_count": len(result.findings),
        "critical_count": result.critical_count,
        "major_count": result.major_count,
        "minor_count": result.minor_count,
        "findings": [
            {
                "element": f.element,
                "severity": f.severity.value,
                "description": f.description,
                "confidence": f.confidence,
            }
            for f in result.findings[: config.max_findings]
        ],
    }


async def notify_on_threshold(
    result: AnalysisResult,
    config: NotificationConfig,
    score_threshold: int = 70,
    critical_threshold: int = 1,
) -> bool:
    """Send notification only if thresholds are exceeded.

    Args:
        result: Analysis result
        config: Notification configuration
        score_threshold: Send if score is below this value
        critical_threshold: Send if critical count exceeds this value

    Returns:
        True if notification was sent (or not needed)
    """
    should_notify = (
        result.overall_score < score_threshold or result.critical_count >= critical_threshold
    )

    if should_notify:
        return await send_notification(result, config)

    return True  # No notification needed, but not an error
