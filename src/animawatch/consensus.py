"""Multi-model consensus for improved analysis accuracy.

This module provides utilities to run analysis across multiple vision providers
(e.g., Gemini + Ollama) and merge results for higher confidence.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .logging import log_extra
from .models import AnalysisResult, Finding, Severity
from .vision import VisionProvider, get_vision_provider


@dataclass
class ConsensusResult:
    """Result of multi-model consensus analysis."""

    merged_findings: list[Finding]
    gemini_only: list[Finding]
    ollama_only: list[Finding]
    agreed_findings: list[Finding]
    gemini_result: AnalysisResult | None
    ollama_result: AnalysisResult | None
    consensus_score: float  # 0-100, higher = more agreement


async def analyze_with_consensus(
    image_path: Path,
    prompt: str,
    gemini_provider: VisionProvider | None = None,
    ollama_provider: VisionProvider | None = None,
    similarity_threshold: float = 0.7,
) -> ConsensusResult:
    """Analyze an image with multiple models and merge results.

    Args:
        image_path: Path to the image to analyze
        prompt: Analysis prompt
        gemini_provider: Optional Gemini provider (created if not provided)
        ollama_provider: Optional Ollama provider (created if not provided)
        similarity_threshold: Threshold for considering findings similar (0-1)

    Returns:
        ConsensusResult with merged findings and agreement metrics
    """
    # Create providers if not provided
    gemini_result: AnalysisResult | None = None
    ollama_result: AnalysisResult | None = None

    # Run both analyses concurrently
    async def run_gemini() -> AnalysisResult | None:
        try:
            provider = gemini_provider or get_vision_provider()
            result = await provider.analyze_image(image_path, prompt, structured=True)
            return result if isinstance(result, AnalysisResult) else None
        except Exception as e:
            log_extra("Gemini analysis failed", error=str(e))
            return None

    async def run_ollama() -> AnalysisResult | None:
        try:
            from .config import settings

            # Temporarily switch to Ollama
            original = settings.vision_provider
            settings.vision_provider = "ollama"
            try:
                provider = ollama_provider or get_vision_provider()
                result = await provider.analyze_image(image_path, prompt, structured=True)
                return result if isinstance(result, AnalysisResult) else None
            finally:
                settings.vision_provider = original
        except Exception as e:
            log_extra("Ollama analysis failed", error=str(e))
            return None

    gemini_result, ollama_result = await asyncio.gather(run_gemini(), run_ollama())

    # Merge findings
    gemini_findings = gemini_result.findings if gemini_result else []
    ollama_findings = ollama_result.findings if ollama_result else []

    # Find agreed findings (similar issues found by both)
    agreed: list[Finding] = []
    gemini_only: list[Finding] = []
    ollama_matched: set[int] = set()

    for gf in gemini_findings:
        matched = False
        for i, of in enumerate(ollama_findings):
            if i in ollama_matched:
                continue
            if _findings_similar(gf, of, similarity_threshold):
                # Merge findings - take higher confidence and combine details
                merged_finding = Finding(
                    id=gf.id,
                    category=gf.category,
                    severity=_max_severity(gf.severity, of.severity),
                    confidence=max(gf.confidence, of.confidence),
                    timestamp=gf.timestamp or of.timestamp,
                    element=gf.element,
                    description=f"{gf.description} (Gemini) / {of.description} (Ollama)",
                    suggestion=gf.suggestion or of.suggestion,
                    evidence=gf.evidence or of.evidence,
                )
                agreed.append(merged_finding)
                ollama_matched.add(i)
                matched = True
                break
        if not matched:
            gemini_only.append(gf)

    ollama_only = [of for i, of in enumerate(ollama_findings) if i not in ollama_matched]

    # Calculate consensus score
    total_findings = len(gemini_findings) + len(ollama_findings)
    if total_findings == 0:
        consensus_score = 100.0
    else:
        # Score based on agreement ratio
        agreed_count = len(agreed) * 2  # Each agreed finding counts for both
        consensus_score = (agreed_count / total_findings) * 100

    log_extra(
        "Consensus analysis complete",
        agreed=len(agreed),
        gemini_only=len(gemini_only),
        ollama_only=len(ollama_only),
        consensus_score=consensus_score,
    )

    # Merged findings: agreed first (highest confidence), then others
    merged = agreed + gemini_only + ollama_only

    return ConsensusResult(
        merged_findings=merged,
        gemini_only=gemini_only,
        ollama_only=ollama_only,
        agreed_findings=agreed,
        gemini_result=gemini_result,
        ollama_result=ollama_result,
        consensus_score=consensus_score,
    )


def _findings_similar(f1: Finding, f2: Finding, threshold: float) -> bool:
    """Check if two findings are similar enough to be considered the same issue."""
    # Same category is required
    if f1.category != f2.category:
        return False

    # Check description similarity using simple word overlap
    words1 = set(f1.description.lower().split())
    words2 = set(f2.description.lower().split())
    if not words1 or not words2:
        return False

    overlap = len(words1 & words2)
    total = len(words1 | words2)
    similarity = overlap / total if total > 0 else 0

    return similarity >= threshold


def _max_severity(s1: Severity, s2: Severity) -> Severity:
    """Return the more severe of two severities."""
    severity_order = {
        Severity.CRITICAL: 4,
        Severity.MAJOR: 3,
        Severity.MINOR: 2,
        Severity.INFO: 1,
    }
    return s1 if severity_order.get(s1, 0) >= severity_order.get(s2, 0) else s2
