"""Pydantic models for structured JSON output with confidence scoring.

Provides type-safe, validated response models for vision AI analysis results.
All findings include confidence scores (0-100) for hallucination prevention.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class IssueCategory(str, Enum):
    """Categories of visual issues."""

    ANIMATION = "animation"
    VISUAL_ARTIFACT = "visual_artifact"
    LAYOUT = "layout"
    TIMING = "timing"
    ACCESSIBILITY = "accessibility"
    PERFORMANCE = "performance"


class BoundingBox(BaseModel):
    """Bounding box coordinates for issue location."""

    x: int = Field(ge=0, description="X coordinate (pixels from left)")
    y: int = Field(ge=0, description="Y coordinate (pixels from top)")
    width: int = Field(gt=0, description="Width in pixels")
    height: int = Field(gt=0, description="Height in pixels")


class Finding(BaseModel):
    """A single finding from visual analysis with confidence scoring."""

    id: str = Field(description="Unique identifier for this finding")
    category: IssueCategory = Field(description="Category of the issue")
    severity: Severity = Field(description="Issue severity level")
    confidence: int = Field(ge=0, le=100, description="Confidence score (0-100) for this finding")
    timestamp: float | None = Field(
        default=None, description="Timestamp in seconds (for video analysis)"
    )
    element: str = Field(description="Description of the affected UI element")
    description: str = Field(description="Detailed description of the issue")
    suggestion: str = Field(description="Recommended fix for the issue")
    bounding_box: BoundingBox | None = Field(
        default=None, description="Location of the issue (if determinable)"
    )
    evidence: str | None = Field(
        default=None, description="Visual evidence supporting this finding"
    )


class AnalysisMetadata(BaseModel):
    """Metadata about the analysis process."""

    provider: str = Field(description="Vision provider used (gemini/ollama)")
    model: str = Field(description="Model name used for analysis")
    analysis_duration_ms: int = Field(description="Time taken for analysis in milliseconds")
    frame_count: int | None = Field(default=None, description="Number of frames analyzed (video)")
    image_dimensions: tuple[int, int] | None = Field(
        default=None, description="Image dimensions (width, height)"
    )


class AnalysisResult(BaseModel):
    """Complete structured analysis result with all findings."""

    id: str = Field(description="Unique analysis ID")
    url: str | None = Field(default=None, description="URL that was analyzed")
    success: bool = Field(description="Whether analysis completed successfully")
    findings: list[Finding] = Field(default_factory=list, description="List of all findings")
    summary: str = Field(description="Human-readable summary of the analysis")
    overall_score: int = Field(ge=0, le=100, description="Overall quality score (100 = no issues)")
    metadata: AnalysisMetadata = Field(description="Analysis metadata")

    @property
    def critical_count(self) -> int:
        """Count of critical severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def major_count(self) -> int:
        """Count of major severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.MAJOR)

    @property
    def minor_count(self) -> int:
        """Count of minor severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.MINOR)

    @property
    def average_confidence(self) -> float:
        """Average confidence score across all findings."""
        if not self.findings:
            return 100.0
        return sum(f.confidence for f in self.findings) / len(self.findings)

    def to_markdown(self) -> str:
        """Convert analysis result to formatted markdown."""
        lines = [
            "## Analysis Result",
            "",
            f"**Score**: {self.overall_score}/100",
            f"**Findings**: {len(self.findings)} ({self.critical_count} critical, "
            f"{self.major_count} major, {self.minor_count} minor)",
            f"**Avg Confidence**: {self.average_confidence:.1f}%",
            "",
            "### Summary",
            f"{self.summary}",
            "",
        ]

        if self.findings:
            lines.append("### Findings")
            lines.append("")
            for i, finding in enumerate(self.findings, 1):
                severity_icon = {"critical": "🔴", "major": "🟠", "minor": "🟡", "info": "🔵"}
                icon = severity_icon.get(finding.severity.value, "⚪")
                lines.append(f"#### {i}. {icon} {finding.element}")
                lines.append(f"- **Category**: {finding.category.value}")
                lines.append(f"- **Severity**: {finding.severity.value}")
                lines.append(f"- **Confidence**: {finding.confidence}%")
                if finding.timestamp is not None:
                    lines.append(f"- **Timestamp**: {finding.timestamp:.1f}s")
                lines.append(f"- **Issue**: {finding.description}")
                lines.append(f"- **Fix**: {finding.suggestion}")
                lines.append("")

        return "\n".join(lines)


# JSON schema for prompting vision models to return structured output
STRUCTURED_OUTPUT_SCHEMA: dict[str, Any] = AnalysisResult.model_json_schema()
