"""Tests for performance metrics in animawatch.metrics."""

from animawatch.metrics import (
    CoreWebVitals,
    MetricsThresholds,
    PerformanceMetrics,
    generate_metrics_report,
    rate_metric,
    rate_web_vitals,
)


class TestCoreWebVitals:
    """Tests for CoreWebVitals dataclass."""

    def test_vitals_creation(self) -> None:
        """Test creating core web vitals."""
        vitals = CoreWebVitals(
            lcp_ms=2000.0,
            fid_ms=50.0,
            cls_score=0.05,
            fcp_ms=1500.0,
            ttfb_ms=200.0,
            inp_ms=100.0,
        )
        assert vitals.lcp_ms == 2000.0
        assert vitals.cls_score == 0.05

    def test_vitals_defaults(self) -> None:
        """Test vitals with defaults (None)."""
        vitals = CoreWebVitals()
        assert vitals.lcp_ms is None
        assert vitals.fid_ms is None


class TestMetricsThresholds:
    """Tests for MetricsThresholds dataclass."""

    def test_default_thresholds(self) -> None:
        """Test default Google-recommended thresholds."""
        t = MetricsThresholds()
        assert t.lcp_good_ms == 2500.0
        assert t.lcp_poor_ms == 4000.0
        assert t.cls_good == 0.1
        assert t.cls_poor == 0.25


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics dataclass."""

    def test_metrics_creation(self) -> None:
        """Test creating performance metrics."""
        vitals = CoreWebVitals(lcp_ms=2000.0)
        metrics = PerformanceMetrics(
            url="https://example.com",
            core_web_vitals=vitals,
            load_time_ms=3000.0,
            dom_content_loaded_ms=2000.0,
            resource_count=50,
            total_transfer_size_kb=500.0,
            js_heap_size_mb=25.0,
            dom_node_count=1000,
        )
        assert metrics.url == "https://example.com"
        assert metrics.resource_count == 50


class TestRateMetric:
    """Tests for rate_metric function."""

    def test_good_rating(self) -> None:
        """Test rating within good threshold."""
        assert rate_metric(2000.0, 2500.0, 4000.0) == "good"

    def test_needs_improvement_rating(self) -> None:
        """Test rating between good and poor."""
        assert rate_metric(3000.0, 2500.0, 4000.0) == "needs-improvement"

    def test_poor_rating(self) -> None:
        """Test rating above poor threshold."""
        assert rate_metric(5000.0, 2500.0, 4000.0) == "poor"

    def test_none_value(self) -> None:
        """Test rating with None value."""
        assert rate_metric(None, 2500.0, 4000.0) == "unknown"

    def test_boundary_good(self) -> None:
        """Test exactly at good threshold."""
        assert rate_metric(2500.0, 2500.0, 4000.0) == "good"

    def test_boundary_poor(self) -> None:
        """Test exactly at poor threshold."""
        assert rate_metric(4000.0, 2500.0, 4000.0) == "needs-improvement"


class TestRateWebVitals:
    """Tests for rate_web_vitals function."""

    def test_all_good(self) -> None:
        """Test rating all good vitals."""
        vitals = CoreWebVitals(lcp_ms=2000.0, fid_ms=50.0, cls_score=0.05, fcp_ms=1500.0)
        ratings = rate_web_vitals(vitals)
        assert ratings["lcp"] == "good"
        assert ratings["fid"] == "good"
        assert ratings["cls"] == "good"
        assert ratings["fcp"] == "good"

    def test_all_poor(self) -> None:
        """Test rating all poor vitals."""
        vitals = CoreWebVitals(lcp_ms=5000.0, fid_ms=500.0, cls_score=0.5, fcp_ms=4000.0)
        ratings = rate_web_vitals(vitals)
        assert ratings["lcp"] == "poor"
        assert ratings["fid"] == "poor"
        assert ratings["cls"] == "poor"
        assert ratings["fcp"] == "poor"

    def test_mixed_ratings(self) -> None:
        """Test mixed vitals ratings."""
        vitals = CoreWebVitals(lcp_ms=2000.0, fid_ms=200.0, cls_score=0.3)
        ratings = rate_web_vitals(vitals)
        assert ratings["lcp"] == "good"
        assert ratings["fid"] == "needs-improvement"
        assert ratings["cls"] == "poor"

    def test_custom_thresholds(self) -> None:
        """Test with custom thresholds."""
        vitals = CoreWebVitals(lcp_ms=3000.0)
        custom = MetricsThresholds(lcp_good_ms=3500.0, lcp_poor_ms=5000.0)
        ratings = rate_web_vitals(vitals, custom)
        assert ratings["lcp"] == "good"


class TestGenerateMetricsReport:
    """Tests for generate_metrics_report function."""

    def test_report_generation(self) -> None:
        """Test basic report generation."""
        vitals = CoreWebVitals(lcp_ms=2000.0, fcp_ms=1500.0, cls_score=0.05)
        metrics = PerformanceMetrics(
            url="https://test.com",
            core_web_vitals=vitals,
            load_time_ms=3000.0,
            dom_content_loaded_ms=2000.0,
            resource_count=25,
            total_transfer_size_kb=250.0,
        )
        report = generate_metrics_report(metrics)
        assert "Performance Metrics Report" in report
        assert "https://test.com" in report
        assert "LCP" in report
        assert "good" in report

    def test_report_with_all_vitals(self) -> None:
        """Test report with all vitals present."""
        vitals = CoreWebVitals(
            lcp_ms=2000.0, fcp_ms=1500.0, cls_score=0.05, fid_ms=50.0, ttfb_ms=200.0
        )
        metrics = PerformanceMetrics(
            url="https://test.com",
            core_web_vitals=vitals,
            load_time_ms=3000.0,
            dom_content_loaded_ms=2000.0,
            resource_count=25,
            total_transfer_size_kb=250.0,
            dom_node_count=500,
            js_heap_size_mb=10.0,
        )
        report = generate_metrics_report(metrics)
        assert "FID" in report
        assert "TTFB" in report
        assert "DOM Nodes" in report
        assert "JS Heap" in report
