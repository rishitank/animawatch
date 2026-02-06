"""Tests for Pydantic models in animawatch.models."""

from animawatch.models import (
    AnalysisMetadata,
    AnalysisResult,
    BoundingBox,
    Finding,
    IssueCategory,
    Severity,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self) -> None:
        """Test that all severity levels exist."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.MAJOR.value == "major"
        assert Severity.MINOR.value == "minor"
        assert Severity.INFO.value == "info"


class TestIssueCategory:
    """Tests for IssueCategory enum."""

    def test_issue_categories(self) -> None:
        """Test that all issue categories exist."""
        categories = [
            IssueCategory.ANIMATION,
            IssueCategory.VISUAL_ARTIFACT,
            IssueCategory.LAYOUT,
            IssueCategory.TIMING,
            IssueCategory.ACCESSIBILITY,
            IssueCategory.PERFORMANCE,
        ]
        assert len(categories) == 6


class TestBoundingBox:
    """Tests for BoundingBox model."""

    def test_bounding_box_creation(self) -> None:
        """Test creating a bounding box."""
        box = BoundingBox(x=10, y=20, width=100, height=50)
        assert box.x == 10
        assert box.y == 20
        assert box.width == 100
        assert box.height == 50


class TestFinding:
    """Tests for Finding model."""

    def test_finding_with_required_fields(self) -> None:
        """Test creating a finding with all required fields."""
        finding = Finding(
            id="test-1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=85,
            element=".button",
            description="Test description",
            suggestion="Fix this",
        )
        assert finding.id == "test-1"
        assert finding.category == IssueCategory.ANIMATION
        assert finding.severity == Severity.MAJOR
        assert finding.confidence == 85
        assert finding.description == "Test description"

    def test_finding_with_all_fields(self) -> None:
        """Test creating a finding with all fields."""
        box = BoundingBox(x=0, y=0, width=100, height=100)
        finding = Finding(
            id="test-2",
            category=IssueCategory.ANIMATION,
            severity=Severity.CRITICAL,
            confidence=95,
            timestamp=1.5,
            element=".button",
            description="Animation stutters",
            suggestion="Use transform instead",
            evidence="Visible jank at 1.5s",
            bounding_box=box,
        )
        assert finding.timestamp == 1.5
        assert finding.element == ".button"
        assert finding.bounding_box == box


class TestAnalysisMetadata:
    """Tests for AnalysisMetadata model."""

    def test_metadata_creation(self) -> None:
        """Test metadata creation with required fields."""
        meta = AnalysisMetadata(
            provider="gemini",
            model="gemini-2.0-flash",
            analysis_duration_ms=1500,
        )
        assert meta.provider == "gemini"
        assert meta.frame_count is None


class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    def test_empty_result(self) -> None:
        """Test result with no findings."""
        meta = AnalysisMetadata(
            provider="gemini", model="gemini-2.0-flash", analysis_duration_ms=100
        )
        result = AnalysisResult(
            id="test-1",
            success=True,
            summary="No issues found",
            findings=[],
            overall_score=100,
            metadata=meta,
        )
        assert result.critical_count == 0
        assert result.major_count == 0
        assert result.minor_count == 0
        assert result.average_confidence == 100.0  # No findings = 100%

    def test_result_with_findings(self) -> None:
        """Test result with multiple findings."""
        meta = AnalysisMetadata(
            provider="gemini", model="gemini-2.0-flash", analysis_duration_ms=100
        )
        findings = [
            Finding(
                id="1",
                category=IssueCategory.ANIMATION,
                severity=Severity.CRITICAL,
                confidence=90,
                element="btn",
                description="Critical",
                suggestion="Fix",
            ),
            Finding(
                id="2",
                category=IssueCategory.TIMING,
                severity=Severity.MAJOR,
                confidence=80,
                element="el",
                description="Major",
                suggestion="Fix",
            ),
            Finding(
                id="3",
                category=IssueCategory.VISUAL_ARTIFACT,
                severity=Severity.MINOR,
                confidence=70,
                element="img",
                description="Minor",
                suggestion="Fix",
            ),
        ]
        result = AnalysisResult(
            id="test-2",
            success=True,
            summary="Issues found",
            findings=findings,
            overall_score=60,
            metadata=meta,
        )
        assert result.critical_count == 1
        assert result.major_count == 1
        assert result.minor_count == 1
        assert result.average_confidence == 80.0

    def test_to_markdown(self) -> None:
        """Test markdown output generation."""
        meta = AnalysisMetadata(
            provider="gemini", model="gemini-2.0-flash", analysis_duration_ms=100
        )
        finding = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=85,
            element=".button",
            description="Frame drops detected",
            suggestion="Optimize animation",
        )
        result = AnalysisResult(
            id="test-3",
            success=True,
            summary="Animation issues",
            findings=[finding],
            overall_score=75,
            metadata=meta,
        )
        md = result.to_markdown()
        assert "Animation issues" in md
        assert "75/100" in md
        assert "animation" in md
        assert "major" in md
