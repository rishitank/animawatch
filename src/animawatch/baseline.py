"""Baseline comparison for regression detection.

This module provides utilities to compare current analysis results
against stored baselines to detect visual regressions.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Finding, Severity


@dataclass
class Baseline:
    """Stored baseline for comparison."""

    id: str
    name: str
    url: str
    created_at: str
    analysis_result: AnalysisResult
    screenshot_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BaselineComparison:
    """Result of comparing current state against baseline."""

    baseline_id: str
    baseline_name: str
    is_regression: bool
    score_delta: int  # Positive = improvement, negative = regression
    new_findings: list[Finding]
    resolved_findings: list[Finding]
    unchanged_findings: list[Finding]
    summary: str


class BaselineStore:
    """Store and manage baselines for comparison."""

    def __init__(self, storage_path: Path) -> None:
        """Initialize baseline store.

        Args:
            storage_path: Directory to store baseline files
        """
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save_baseline(
        self,
        name: str,
        url: str,
        result: AnalysisResult,
        screenshot_path: Path | None = None,
    ) -> Baseline:
        """Save a new baseline.

        Args:
            name: Human-readable name for the baseline
            url: URL that was analyzed
            result: Analysis result to use as baseline
            screenshot_path: Optional screenshot to hash

        Returns:
            Created baseline object
        """
        baseline_id = self._generate_id(name, url)
        screenshot_hash = None

        if screenshot_path and screenshot_path.exists():
            screenshot_hash = self._hash_file(screenshot_path)

        baseline = Baseline(
            id=baseline_id,
            name=name,
            url=url,
            created_at=datetime.now().isoformat(),
            analysis_result=result,
            screenshot_hash=screenshot_hash,
        )

        self._save_to_disk(baseline)
        return baseline

    def load_baseline(self, baseline_id: str) -> Baseline | None:
        """Load a baseline by ID.

        Args:
            baseline_id: ID of baseline to load

        Returns:
            Baseline if found, None otherwise
        """
        file_path = self.storage_path / f"{baseline_id}.json"
        if not file_path.exists():
            return None

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        return self._deserialize_baseline(data)

    def list_baselines(self) -> list[Baseline]:
        """List all stored baselines."""
        baselines = []
        for file_path in self.storage_path.glob("*.json"):
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            baselines.append(self._deserialize_baseline(data))
        return baselines

    def delete_baseline(self, baseline_id: str) -> bool:
        """Delete a baseline by ID."""
        file_path = self.storage_path / f"{baseline_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def _generate_id(self, name: str, url: str) -> str:
        """Generate a unique baseline ID."""
        content = f"{name}:{url}:{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _hash_file(self, path: Path) -> str:
        """Generate hash of file contents."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _save_to_disk(self, baseline: Baseline) -> None:
        """Serialize and save baseline to disk."""
        file_path = self.storage_path / f"{baseline.id}.json"
        data = self._serialize_baseline(baseline)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _serialize_baseline(self, baseline: Baseline) -> dict[str, Any]:
        """Convert baseline to JSON-serializable dict."""
        return {
            "id": baseline.id,
            "name": baseline.name,
            "url": baseline.url,
            "created_at": baseline.created_at,
            "screenshot_hash": baseline.screenshot_hash,
            "metadata": baseline.metadata,
            "analysis_result": {
                "id": baseline.analysis_result.id,
                "success": baseline.analysis_result.success,
                "summary": baseline.analysis_result.summary,
                "overall_score": baseline.analysis_result.overall_score,
                "findings": [
                    {
                        "id": f.id,
                        "category": f.category.value,
                        "severity": f.severity.value,
                        "confidence": f.confidence,
                        "timestamp": f.timestamp,
                        "element": f.element,
                        "description": f.description,
                        "suggestion": f.suggestion,
                        "evidence": f.evidence,
                    }
                    for f in baseline.analysis_result.findings
                ],
                "metadata": {
                    "provider": baseline.analysis_result.metadata.provider,
                    "model": baseline.analysis_result.metadata.model,
                    "analysis_duration_ms": baseline.analysis_result.metadata.analysis_duration_ms,
                },
            },
        }

    def _deserialize_baseline(self, data: dict[str, Any]) -> Baseline:
        """Convert dict back to Baseline object."""
        from .models import AnalysisMetadata, IssueCategory

        result_data = data["analysis_result"]
        findings = [
            Finding(
                id=f["id"],
                category=IssueCategory(f["category"]),
                severity=Severity(f["severity"]),
                confidence=f["confidence"],
                timestamp=f["timestamp"],
                element=f["element"],
                description=f["description"],
                suggestion=f["suggestion"],
                evidence=f.get("evidence"),
            )
            for f in result_data["findings"]
        ]

        metadata = AnalysisMetadata(
            provider=result_data["metadata"]["provider"],
            model=result_data["metadata"]["model"],
            analysis_duration_ms=result_data["metadata"]["analysis_duration_ms"],
        )

        result = AnalysisResult(
            id=result_data.get("id", data["id"]),
            success=True,
            summary=result_data["summary"],
            overall_score=result_data["overall_score"],
            findings=findings,
            metadata=metadata,
        )

        return Baseline(
            id=data["id"],
            name=data["name"],
            url=data["url"],
            created_at=data["created_at"],
            analysis_result=result,
            screenshot_hash=data.get("screenshot_hash"),
            metadata=data.get("metadata", {}),
        )


def compare_against_baseline(
    current: AnalysisResult,
    baseline: Baseline,
    score_threshold: int = 5,
) -> BaselineComparison:
    """Compare current analysis against a stored baseline.

    Args:
        current: Current analysis result
        baseline: Baseline to compare against
        score_threshold: Score difference considered significant

    Returns:
        Comparison result with regression status and details
    """
    baseline_result = baseline.analysis_result
    score_delta = current.overall_score - baseline_result.overall_score

    # Find new, resolved, and unchanged findings
    current_ids = {f.id for f in current.findings}
    baseline_ids = {f.id for f in baseline_result.findings}

    new_findings = [f for f in current.findings if f.id not in baseline_ids]
    resolved_findings = [f for f in baseline_result.findings if f.id not in current_ids]
    unchanged_findings = [f for f in current.findings if f.id in baseline_ids]

    # Determine if this is a regression
    is_regression = score_delta < -score_threshold or any(
        f.severity in (Severity.CRITICAL, Severity.MAJOR) for f in new_findings
    )

    # Generate summary
    if is_regression:
        summary = f"⚠️ REGRESSION: Score dropped by {abs(score_delta)} points. "
        summary += f"{len(new_findings)} new issues found."
    elif score_delta > score_threshold:
        summary = f"✅ IMPROVEMENT: Score improved by {score_delta} points. "
        summary += f"{len(resolved_findings)} issues resolved."
    else:
        summary = f"➡️ STABLE: Score unchanged ({current.overall_score}/100)."

    return BaselineComparison(
        baseline_id=baseline.id,
        baseline_name=baseline.name,
        is_regression=is_regression,
        score_delta=score_delta,
        new_findings=new_findings,
        resolved_findings=resolved_findings,
        unchanged_findings=unchanged_findings,
        summary=summary,
    )
