"""Tests for grounding and verification in animawatch.grounding."""

from pathlib import Path

from animawatch.grounding import (
    GroundedFinding,
    VerificationResult,
    _parse_verification,
    apply_verification_result,
    create_grounded_prompt,
    create_verification_prompt,
    parse_bounding_box,
)
from animawatch.models import BoundingBox, Finding, IssueCategory, Severity


class TestGroundedFinding:
    """Tests for GroundedFinding model."""

    def test_grounded_finding_creation(self) -> None:
        """Test creating a grounded finding."""
        finding = GroundedFinding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=85,
            element=".button",
            description="Frame drop at button",
            suggestion="Optimize",
            screenshot_path=Path("/tmp/evidence.png"),
            grounding_box=BoundingBox(x=10, y=20, width=100, height=50),
            verification_status="verified",
            verification_reason="Clearly visible in screenshot",
        )
        assert finding.verification_status == "verified"
        assert finding.screenshot_path == Path("/tmp/evidence.png")

    def test_grounded_finding_defaults(self) -> None:
        """Test grounded finding with defaults."""
        finding = GroundedFinding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MINOR,
            confidence=70,
            element="btn",
            description="Test",
            suggestion="Fix",
        )
        assert finding.verification_status == "unverified"
        assert finding.screenshot_path is None


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_verification_result_creation(self) -> None:
        """Test creating a verification result."""
        finding = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Test",
            suggestion="Fix",
        )
        result = VerificationResult(
            original_finding=finding,
            is_verified=True,
            confidence_adjustment=10.0,
            reason="Issue is clearly visible",
            evidence_path=Path("/tmp/evidence.png"),
        )
        assert result.is_verified is True
        assert result.confidence_adjustment == 10.0


class TestParseBoundingBox:
    """Tests for parse_bounding_box function."""

    def test_parse_square_brackets(self) -> None:
        """Test parsing [x, y, w, h] format."""
        text = "The issue is at [100, 200, 50, 30] coordinates"
        box = parse_bounding_box(text)
        assert box is not None
        assert box.x == 100
        assert box.y == 200
        assert box.width == 50
        assert box.height == 30

    def test_parse_parentheses(self) -> None:
        """Test parsing (x, y, w, h) format."""
        text = "Location: (150, 250, 80, 40)"
        box = parse_bounding_box(text)
        assert box is not None
        assert box.x == 150
        assert box.y == 250

    def test_parse_with_spaces(self) -> None:
        """Test parsing with extra spaces."""
        text = "Coordinates: [ 10 , 20 , 30 , 40 ]"
        box = parse_bounding_box(text)
        assert box is not None
        assert box.x == 10

    def test_parse_no_match(self) -> None:
        """Test returning None when no match."""
        text = "No coordinates here"
        box = parse_bounding_box(text)
        assert box is None


class TestParseVerification:
    """Tests for _parse_verification function."""

    def test_verified_positive(self) -> None:
        """Test detecting positive verification."""
        assert _parse_verification("yes, the issue is verified and visible") is True
        assert _parse_verification("confirmed, accurate location") is True

    def test_verified_negative(self) -> None:
        """Test detecting negative verification."""
        assert _parse_verification("no, this is a false positive") is False
        assert _parse_verification("rejected, not visible in image") is False

    def test_mixed_signals(self) -> None:
        """Test with mixed signals (more positive)."""
        text = "yes visible yes confirmed but uncertain about one aspect"
        assert _parse_verification(text) is True

    def test_empty_string(self) -> None:
        """Test with empty string."""
        assert _parse_verification("") is False


class TestCreateGroundedPrompt:
    """Tests for create_grounded_prompt function."""

    def test_prompt_contains_base(self) -> None:
        """Test that grounded prompt contains base prompt."""
        base = "Analyze this animation"
        result = create_grounded_prompt(base, 1920, 1080)
        assert base in result
        assert "1920" in result
        assert "1080" in result

    def test_prompt_contains_grounding_instructions(self) -> None:
        """Test that grounded prompt has grounding instructions."""
        result = create_grounded_prompt("Test", 100, 100)
        assert "WHERE" in result
        assert "ELEMENT" in result
        assert "COORDINATES" in result


class TestCreateVerificationPrompt:
    """Tests for create_verification_prompt function."""

    def test_verification_prompt(self) -> None:
        """Test verification prompt generation."""
        findings = [
            Finding(
                id="1",
                category=IssueCategory.ANIMATION,
                severity=Severity.MAJOR,
                confidence=80,
                element=".button",
                description="Frame drops",
                suggestion="Fix",
            ),
        ]
        result = create_verification_prompt(findings)
        assert "Frame drops" in result
        assert ".button" in result
        assert "MAJOR" in result


class TestApplyVerificationResult:
    """Tests for apply_verification_result function."""

    def test_apply_verified(self) -> None:
        """Test applying a verified result."""
        finding = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Test",
            suggestion="Fix",
        )
        verification = VerificationResult(finding, True, 10.0, "Confirmed", Path("/tmp/e.png"))
        grounded = apply_verification_result(finding, verification)
        assert grounded.verification_status == "verified"
        assert grounded.confidence == 90

    def test_apply_rejected(self) -> None:
        """Test applying a rejected result."""
        finding = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Test",
            suggestion="Fix",
        )
        verification = VerificationResult(finding, False, -30.0, "Not visible")
        grounded = apply_verification_result(finding, verification)
        assert grounded.verification_status == "rejected"
        assert grounded.severity == Severity.INFO
        assert grounded.confidence == 50
