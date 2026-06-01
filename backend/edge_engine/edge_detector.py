"""
Edge detection pipeline using multi-spectral contrast enhancement,
K-means clustering, and active contour models.
"""

import numpy as np
from skimage import exposure, filters, morphology, measure, segmentation, color
from sklearn.cluster import KMeans
from shapely.geometry import shape, Polygon, LineString
from shapely import affinity


def enhance_contrast(pixel_matrix: np.ndarray) -> np.ndarray:
    """Apply contrast stretching to enhance edge visibility."""
    p2, p98 = np.percentile(pixel_matrix, (2, 98))
    return exposure.rescale_intensity(pixel_matrix, in_range=(p2, p98))


def cluster_pixels(buffer_pixels: np.ndarray, n_clusters: int = 3) -> np.ndarray:
    """
    Quantize pixels into discrete classes (e.g. road vs mud vs vegetation).
    Returns a 2D label array.
    """
    h, w = buffer_pixels.shape[:2]
    pixels_flat = buffer_pixels.reshape(-1, buffer_pixels.shape[-1])
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(pixels_flat)
    
    return labels.reshape(h, w)


def compute_edge_gradient(clustered: np.ndarray) -> np.ndarray:
    """Compute gradient magnitude from clustered pixel labels."""
    from skimage import filters as sk_filters
    gradient = sk_filters.sobel(clustered.astype(float))
    return gradient


def active_contour_snake(
    image: np.ndarray,
    initial_contour: np.ndarray,
    alpha: float = 0.01,
    beta: float = 0.1,
    max_iterations: int = 100,
) -> np.ndarray:
    """
    Fit an active contour (snake) to the strongest edges in the image.
    The initial contour seeds from the ML-predicted boundary.
    """
    from skimage.segmentation import active_contour
    
    snake = active_contour(
        image if image.ndim == 2 else color.rgb2gray(image),
        initial_contour,
        alpha=alpha,
        beta=beta,
        max_iterations=max_iterations,
    )
    return snake


def measure_deviation(
    predicted_vertices: np.ndarray,
    snake_vertices: np.ndarray,
) -> tuple[float, np.ndarray]:
    """
    Measure per-vertex Euclidean distance between ML-predicted boundary
    and snake-fitted boundary. Returns mean deviation and array of distances.
    """
    from scipy.spatial import cKDTree
    
    tree = cKDTree(snake_vertices)
    distances, _ = tree.query(predicted_vertices)
    return float(np.mean(distances)), distances


def compute_spectral_contrast(
    buffer_pixels: np.ndarray,
    labels: np.ndarray,
) -> float:
    """
    Compute inter-cluster distance as a measure of spectral contrast.
    Higher values = clearer edge distinction.
    """
    h, w = buffer_pixels.shape[:2]
    pixels_flat = buffer_pixels.reshape(-1, buffer_pixels.shape[-1]).astype(float)
    labels_flat = labels.flatten()
    
    unique_labels = np.unique(labels_flat)
    if len(unique_labels) < 2:
        return 0.0
    
    means = []
    for label in unique_labels:
        mask = labels_flat == label
        means.append(np.mean(pixels_flat[mask], axis=0))
    
    if len(means) < 2:
        return 0.0
    
    max_dist = 0.0
    for i in range(len(means)):
        for j in range(i + 1, len(means)):
            dist = np.linalg.norm(means[i] - means[j])
            max_dist = max(max_dist, dist)
    
    max_possible = np.linalg.norm(np.full(buffer_pixels.shape[-1], 255))
    return float(min(max_dist / max_possible, 1.0))
