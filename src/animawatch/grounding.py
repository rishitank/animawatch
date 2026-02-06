"""Hallucination prevention through grounding and verification.

This module provides utilities to reduce vision AI hallucinations by:
1. Grounding claims with visual evidence (screenshots)
2. Self-verification prompts
3. Bounding box annotations for precise issue location
4. Multi-pass analysis for verification
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from .models import BoundingBox, Finding, IssueCategory, Severity

if TYPE_CHECKING:
    from .vision import VisionProvider


class GroundedFinding(Finding):
    """A finding with visual evidence for grounding."""

    screenshot_path: Path | None = Field(default=None, description="Path to screenshot evidence")
    grounding_box: BoundingBox | None = Field(default=None, description="Bounding box for issue")
    verification_status: str = Field(
        default="unverified", description="Verification status: verified, rejected, uncertain"
    )
    verification_reason: str = Field(default="", description="Reason for verification status")


@dataclass
class VerificationResult:
    """Result of verifying a finding."""

    original_finding: Finding
    is_verified: bool
    confidence_adjustment: float  # Positive = more confident, negative = less
    reason: str
    evidence_path: Path | None = None


# Grounding prompts that force the model to provide evidence
GROUNDING_PROMPT = """
When reporting issues, you MUST:
1. Describe exactly WHERE on the screen the issue appears (top/bottom/left/right/center)
2. Specify the ELEMENT involved (button, text, image, etc.)
3. Provide COORDINATES if possible (approximate x,y or bounding box)
4. Explain HOW you identified this issue visually

Format each finding as:
- Location: [exact screen position]
- Element: [specific element description]
- Coordinates: [x, y, width, height] or "unknown"
- Visual Evidence: [what you see that indicates this issue]
- Issue: [description of the problem]
"""

VERIFICATION_PROMPT = """
Review the following findings and verify each one:

{findings}

For EACH finding, answer:
1. Is this issue clearly visible in the image? (yes/no/uncertain)
2. Is the location description accurate? (yes/no)
3. Could this be a false positive? (yes/no)
4. Confidence level after review (0-100)

Be skeptical. Reject findings that:
- Reference elements not visible in the image
- Have vague or incorrect location descriptions
- Could be misinterpretations of normal UI elements
"""

BOUNDING_BOX_PROMPT = """
For each issue you identify, provide precise bounding box coordinates:

Format: [x, y, width, height] in pixels where:
- x: distance from left edge
- y: distance from top edge
- width: horizontal extent of the issue area
- height: vertical extent of the issue area

Image dimensions: {width}x{height} pixels

Only report issues where you can specify at least approximate coordinates.
If you cannot determine coordinates, mark as "location_uncertain": true.
"""


def create_grounded_prompt(base_prompt: str, image_width: int, image_height: int) -> str:
    """Create a prompt that enforces grounding and bounding box annotation."""
    return f"""{base_prompt}

{GROUNDING_PROMPT}

{BOUNDING_BOX_PROMPT.format(width=image_width, height=image_height)}
"""


def create_verification_prompt(findings: list[Finding]) -> str:
    """Create a prompt to verify existing findings."""
    findings_text = "\n".join(
        f"{i + 1}. [{f.severity}] {f.description} at {f.element or 'unknown location'}"
        for i, f in enumerate(findings)
    )
    return VERIFICATION_PROMPT.format(findings=findings_text)


def parse_bounding_box(text: str) -> BoundingBox | None:
    """Parse bounding box coordinates from model output."""
    import re

    # Look for patterns like [100, 200, 50, 30] or (100, 200, 50, 30)
    pattern = r"[\[\(]\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*[\]\)]"
    match = re.search(pattern, text)
    if match:
        x, y, width, height = map(int, match.groups())
        return BoundingBox(x=x, y=y, width=width, height=height)
    return None


def apply_verification_result(
    finding: Finding, verification: VerificationResult
) -> GroundedFinding:
    """Apply verification result to upgrade finding to grounded finding."""
    conf_adj = finding.confidence + verification.confidence_adjustment
    adjusted_confidence = int(min(100, max(0, conf_adj)))

    return GroundedFinding(
        id=finding.id,
        category=finding.category,
        severity=finding.severity if verification.is_verified else Severity.INFO,
        confidence=adjusted_confidence,
        timestamp=finding.timestamp,
        element=finding.element,
        description=finding.description,
        suggestion=finding.suggestion,
        evidence=finding.evidence,
        grounding_box=finding.bounding_box,
        screenshot_path=verification.evidence_path,
        verification_status="verified" if verification.is_verified else "rejected",
        verification_reason=verification.reason,
    )


async def multi_pass_analysis(
    image_path: Path,
    vision_provider: "VisionProvider",
    base_prompt: str,
    passes: int = 2,
) -> list[GroundedFinding]:
    """Perform multi-pass analysis for verification.

    Pass 1: Initial analysis to find issues
    Pass 2+: Verification passes to confirm findings

    Args:
        image_path: Path to image to analyze
        vision_provider: Vision AI provider to use
        base_prompt: Base analysis prompt
        passes: Number of analysis passes (default 2)

    Returns:
        List of verified grounded findings
    """
    from PIL import Image

    # Get image dimensions for bounding box prompts
    with Image.open(image_path) as img:
        width, height = img.size

    # Pass 1: Initial grounded analysis
    grounded_prompt = create_grounded_prompt(base_prompt, width, height)
    initial_result = await vision_provider.analyze_image(image_path, grounded_prompt)

    # Parse initial findings
    initial_findings = _parse_findings_from_result(initial_result)

    if not initial_findings or passes < 2:
        return [_finding_to_grounded(f, image_path) for f in initial_findings]

    # Pass 2+: Verification passes
    verified_findings: list[GroundedFinding] = []

    for finding in initial_findings:
        verification_prompt = create_verification_prompt([finding])
        verification_result = await vision_provider.analyze_image(image_path, verification_prompt)

        # Convert result to string for parsing
        result_str = _result_to_str(verification_result)

        # Parse verification result
        is_verified = _parse_verification(result_str)
        confidence_adj = 10.0 if is_verified else -30.0

        verification = VerificationResult(
            original_finding=finding,
            is_verified=is_verified,
            confidence_adjustment=confidence_adj,
            reason=result_str[:200] if result_str else "",
            evidence_path=image_path,
        )

        grounded = apply_verification_result(finding, verification)
        if grounded.verification_status == "verified":
            verified_findings.append(grounded)

    return verified_findings


def _result_to_str(result: str | object) -> str:
    """Convert vision provider result to string."""
    from .models import AnalysisResult

    if isinstance(result, AnalysisResult):
        return result.summary
    return str(result) if result else ""


def _finding_to_grounded(finding: Finding, image_path: Path) -> GroundedFinding:
    """Convert a regular finding to a grounded finding."""
    return GroundedFinding(
        id=finding.id,
        category=finding.category,
        severity=finding.severity,
        confidence=finding.confidence,
        timestamp=finding.timestamp,
        element=finding.element,
        description=finding.description,
        suggestion=finding.suggestion,
        evidence=finding.evidence,
        grounding_box=finding.bounding_box,
        screenshot_path=image_path,
        verification_status="unverified",
        verification_reason="",
    )


def _parse_findings_from_result(result: str | object) -> list[Finding]:
    """Parse findings from vision AI result text."""
    from .models import AnalysisResult

    # If result is already an AnalysisResult, extract findings
    if isinstance(result, AnalysisResult):
        return result.findings

    # Convert to string if needed
    result_str = str(result) if result else ""

    # This is a simplified parser - real implementation would use
    # structured output mode or more sophisticated parsing
    findings: list[Finding] = []
    import uuid

    # Look for issue patterns in the result
    lines = result_str.split("\n")
    current_issue = ""

    for line in lines:
        line = line.strip()
        if line.startswith("-") or line.startswith("*") or line.startswith("•"):
            if current_issue:
                findings.append(
                    Finding(
                        id=str(uuid.uuid4())[:8],
                        category=IssueCategory.VISUAL_ARTIFACT,
                        severity=Severity.MINOR,
                        confidence=70,
                        element="Unknown element",
                        description=current_issue,
                        suggestion="Review and verify this issue manually",
                    )
                )
            current_issue = line.lstrip("-*• ").strip()
        elif current_issue and line:
            current_issue += " " + line

    # Don't forget the last issue
    if current_issue:
        findings.append(
            Finding(
                id=str(uuid.uuid4())[:8],
                category=IssueCategory.VISUAL_ARTIFACT,
                severity=Severity.MINOR,
                confidence=70,
                element="Unknown element",
                description=current_issue,
                suggestion="Review and verify this issue manually",
            )
        )

    return findings


def _parse_verification(result: str) -> bool:
    """Parse verification result to determine if finding is verified."""
    result_lower = result.lower()

    # Count positive vs negative indicators
    positive = sum(
        1
        for word in ["yes", "verified", "confirmed", "visible", "accurate"]
        if word in result_lower
    )
    negative = sum(
        1
        for word in ["no", "rejected", "not visible", "false positive", "uncertain"]
        if word in result_lower
    )

    return positive > negative
