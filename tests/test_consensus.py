"""Tests for multi-model consensus in animawatch.consensus."""

from animawatch.consensus import (
    ConsensusResult,
    _findings_similar,
    _max_severity,
)
from animawatch.models import Finding, IssueCategory, Severity


class TestConsensusResult:
    """Tests for ConsensusResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a consensus result."""
        finding1 = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Test",
            suggestion="Fix",
        )
        result = ConsensusResult(
            merged_findings=[finding1],
            gemini_only=[],
            ollama_only=[],
            agreed_findings=[finding1],
            gemini_result=None,
            ollama_result=None,
            consensus_score=100.0,
        )
        assert len(result.merged_findings) == 1
        assert result.consensus_score == 100.0

    def test_empty_result(self) -> None:
        """Test empty consensus result."""
        result = ConsensusResult(
            merged_findings=[],
            gemini_only=[],
            ollama_only=[],
            agreed_findings=[],
            gemini_result=None,
            ollama_result=None,
            consensus_score=100.0,
        )
        assert len(result.merged_findings) == 0


class TestFindingsSimilar:
    """Tests for _findings_similar helper function."""

    def test_same_category_similar_description(self) -> None:
        """Test that similar findings are detected."""
        f1 = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Animation has frame drops at button hover",
            suggestion="Fix",
        )
        f2 = Finding(
            id="2",
            category=IssueCategory.ANIMATION,
            severity=Severity.MINOR,
            confidence=70,
            element="btn",
            description="Frame drops detected at button hover animation",
            suggestion="Fix",
        )
        assert _findings_similar(f1, f2, 0.5) is True

    def test_different_category(self) -> None:
        """Test that different categories are not similar."""
        f1 = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Animation stutters",
            suggestion="Fix",
        )
        f2 = Finding(
            id="2",
            category=IssueCategory.TIMING,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Animation stutters",
            suggestion="Fix",
        )
        assert _findings_similar(f1, f2, 0.5) is False

    def test_different_description(self) -> None:
        """Test that very different descriptions are not similar."""
        f1 = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Button animation drops frames",
            suggestion="Fix",
        )
        f2 = Finding(
            id="2",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="menu",
            description="Menu fade in is broken",
            suggestion="Fix",
        )
        assert _findings_similar(f1, f2, 0.7) is False

    def test_empty_description(self) -> None:
        """Test handling of empty descriptions."""
        f1 = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="",
            suggestion="Fix",
        )
        f2 = Finding(
            id="2",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Test",
            suggestion="Fix",
        )
        assert _findings_similar(f1, f2, 0.5) is False

    def test_high_threshold(self) -> None:
        """Test with high similarity threshold."""
        f1 = Finding(
            id="1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Frame drops detected",
            suggestion="Fix",
        )
        f2 = Finding(
            id="2",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=80,
            element="btn",
            description="Frame drops found",
            suggestion="Fix",
        )
        result = _findings_similar(f1, f2, 0.9)
        assert result is False


class TestMaxSeverity:
    """Tests for _max_severity helper function."""

    def test_critical_vs_major(self) -> None:
        """Test that CRITICAL beats MAJOR."""
        assert _max_severity(Severity.CRITICAL, Severity.MAJOR) == Severity.CRITICAL
        assert _max_severity(Severity.MAJOR, Severity.CRITICAL) == Severity.CRITICAL

    def test_major_vs_minor(self) -> None:
        """Test that MAJOR beats MINOR."""
        assert _max_severity(Severity.MAJOR, Severity.MINOR) == Severity.MAJOR
        assert _max_severity(Severity.MINOR, Severity.MAJOR) == Severity.MAJOR

    def test_minor_vs_info(self) -> None:
        """Test that MINOR beats INFO."""
        assert _max_severity(Severity.MINOR, Severity.INFO) == Severity.MINOR
        assert _max_severity(Severity.INFO, Severity.MINOR) == Severity.MINOR

    def test_same_severity(self) -> None:
        """Test same severity returns first."""
        assert _max_severity(Severity.MAJOR, Severity.MAJOR) == Severity.MAJOR

    def test_critical_vs_info(self) -> None:
        """Test extremes."""
        assert _max_severity(Severity.CRITICAL, Severity.INFO) == Severity.CRITICAL
