"""Geometry utilities package.

This package provides geometry analysis utilities for greenhouse design:
- Polygon coverage analysis (grid intersection)
- Segment analysis (north/south edge detection)
- Post estimation (triangular brace patterns)
- Gutter estimation (drainage system)

All functions from the original geometry_utils.py are re-exported here
for backward compatibility.
"""

# Re-export all public functions for backward compatibility
from .polygon_coverage import (
    compute_grid_coverage,
    compute_grid_box_counts,
)
from .segment_analysis import (
    find_north_south_chains,
)
from .post_estimation import (
    estimate_triangle_posts_3x5_with_sides,
    estimate_triangle_posts_3x5_with_sides_per_row,
)
from .gutter_estimation import (
    estimate_gutters_length,
)
from .koutelou_estimation import (
    estimate_koutelou_pairs,
)
from .plevra_estimation import (
    estimate_plevra,
)

__all__ = [
    # Polygon coverage
    'compute_grid_coverage',
    'compute_grid_box_counts',
    # Segment analysis
    'find_north_south_chains',
    # Post estimation
    'estimate_triangle_posts_3x5_with_sides',
    'estimate_triangle_posts_3x5_with_sides_per_row',
    # Gutter estimation
    'estimate_gutters_length',
    # Koutelou estimation
    'estimate_koutelou_pairs',
    # Plevra estimation
    'estimate_plevra',
]
