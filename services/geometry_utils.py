"""Geometry utilities - DEPRECATED, use services.geometry package instead.

This module is kept for backward compatibility only. All functions have been
moved to the services.geometry package with better organization:
- services.geometry.polygon_coverage: compute_grid_coverage, compute_grid_box_counts
- services.geometry.segment_analysis: find_north_south_chains
- services.geometry.post_estimation: estimate_triangle_posts_3x5_with_sides, etc.
- services.geometry.gutter_estimation: estimate_gutters_length

Please import from services.geometry or services.geometry.* instead.
"""

# Re-export all functions from the new package for backward compatibility
from services.geometry import (
    compute_grid_coverage,
    compute_grid_box_counts,
    find_north_south_chains,
    estimate_triangle_posts_3x5_with_sides,
    estimate_triangle_posts_3x5_with_sides_per_row,
    estimate_gutters_length,
    estimate_koutelou_pairs,
    estimate_plevra,
    estimate_cultivation_pipes,
)

__all__ = [
    'compute_grid_coverage',
    'compute_grid_box_counts',
    'find_north_south_chains',
    'estimate_triangle_posts_3x5_with_sides',
    'estimate_triangle_posts_3x5_with_sides_per_row',
    'estimate_gutters_length',
    'estimate_koutelou_pairs',
    'estimate_plevra',
    'estimate_cultivation_pipes',
]
