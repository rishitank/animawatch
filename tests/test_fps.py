"""Tests for FPS analysis in animawatch.fps."""

from animawatch.fps import (
    FPSAnalysisResult,
    FrameTimingInfo,
    JankEvent,
    generate_fps_report,
)


class TestFrameTimingInfo:
    """Tests for FrameTimingInfo dataclass."""

    def test_frame_timing_creation(self) -> None:
        """Test creating frame timing info."""
        timing = FrameTimingInfo(frame_number=5, timestamp_ms=166.67, delta_ms=16.67)
        assert timing.frame_number == 5
        assert timing.timestamp_ms == 166.67
        assert timing.delta_ms == 16.67


class TestJankEvent:
    """Tests for JankEvent dataclass."""

    def test_jank_event_creation(self) -> None:
        """Test creating a jank event."""
        event = JankEvent(
            frame_number=10,
            timestamp_ms=500.0,
            expected_delta_ms=16.67,
            actual_delta_ms=50.0,
            severity="major",
            dropped_frames=2,
        )
        assert event.frame_number == 10
        assert event.severity == "major"
        assert event.dropped_frames == 2


class TestFPSAnalysisResult:
    """Tests for FPSAnalysisResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating an FPS analysis result."""
        result = FPSAnalysisResult(
            average_fps=58.5,
            target_fps=60.0,
            min_fps=45.0,
            max_fps=62.0,
            total_frames=120,
            jank_events=[],
            jank_percentage=0.0,
            frame_time_consistency=95.0,
            duration_ms=2000.0,
        )
        assert result.average_fps == 58.5
        assert result.target_fps == 60.0
        assert result.total_frames == 120

    def test_result_with_jank(self) -> None:
        """Test result with jank events."""
        events = [
            JankEvent(1, 100.0, 16.67, 50.0, "major", 2),
            JankEvent(5, 300.0, 16.67, 33.0, "minor", 1),
        ]
        result = FPSAnalysisResult(
            average_fps=55.0,
            target_fps=60.0,
            min_fps=30.0,
            max_fps=60.0,
            total_frames=100,
            jank_events=events,
            jank_percentage=2.0,
            frame_time_consistency=85.0,
            duration_ms=1800.0,
        )
        assert len(result.jank_events) == 2
        assert result.jank_percentage == 2.0


class TestGenerateFPSReport:
    """Tests for generate_fps_report function."""

    def test_report_no_jank(self) -> None:
        """Test report generation with no jank."""
        result = FPSAnalysisResult(
            average_fps=60.0,
            target_fps=60.0,
            min_fps=59.0,
            max_fps=61.0,
            total_frames=120,
            jank_events=[],
            jank_percentage=0.0,
            frame_time_consistency=98.0,
            duration_ms=2000.0,
        )
        report = generate_fps_report(result)
        assert "FPS Analysis Report" in report
        assert "Average FPS" in report
        assert "60.0" in report
        assert "Jank Events" in report
        assert "0" in report

    def test_report_with_jank(self) -> None:
        """Test report generation with jank events."""
        events = [
            JankEvent(10, 500.0, 16.67, 50.0, "major", 2),
        ]
        result = FPSAnalysisResult(
            average_fps=55.0,
            target_fps=60.0,
            min_fps=30.0,
            max_fps=60.0,
            total_frames=100,
            jank_events=events,
            jank_percentage=1.0,
            frame_time_consistency=85.0,
            duration_ms=1800.0,
        )
        report = generate_fps_report(result)
        assert "Jank Events" in report
        assert "major" in report
        assert "Frame 10" in report

    def test_report_many_jank_events(self) -> None:
        """Test that report limits displayed jank events."""
        events = [JankEvent(i, i * 100.0, 16.67, 33.0, "minor", 1) for i in range(15)]
        result = FPSAnalysisResult(
            average_fps=50.0,
            target_fps=60.0,
            min_fps=25.0,
            max_fps=60.0,
            total_frames=200,
            jank_events=events,
            jank_percentage=7.5,
            frame_time_consistency=70.0,
            duration_ms=3500.0,
        )
        report = generate_fps_report(result)
        assert "... and 5 more events" in report
