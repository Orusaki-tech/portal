"""
Compute a composite confidence score (0.0–1.0) indicating how certain
the automated system is about the boundary alignment.

Score components:
  - spectral_contrast (w1): how distinct the pixel classes are
  - snake_strain (w2): how much the active contour had to stretch (inverted)
  - normalized_deviation (w3): deviation relative to buffer width (inverted)
"""

from dataclasses import dataclass


@dataclass
class ConfidenceWeights:
    spectral: float = 0.4
    strain: float = 0.3
    deviation: float = 0.3


def compute_confidence(
    spectral_contrast: float,
    total_vertex_movement: float,
    polygon_perimeter: float,
    mean_deviation: float,
    buffer_width_meters: float = 2.0,
    weights: ConfidenceWeights | None = None,
) -> float:
    if weights is None:
        weights = ConfidenceWeights()
    
    snake_strain = min(total_vertex_movement / max(polygon_perimeter, 1e-6), 1.0)
    normalized_deviation = min(mean_deviation / max(buffer_width_meters, 1e-6), 1.0)
    
    score = (
        weights.spectral * spectral_contrast
        + weights.strain * (1.0 - snake_strain)
        + weights.deviation * (1.0 - normalized_deviation)
    )
    
    return round(min(max(score, 0.0), 1.0), 4)


def is_ambiguous(confidence: float, threshold: float = 0.7) -> bool:
    """Return True if confidence falls below the threshold."""
    return confidence < threshold
