"""Gutter estimation utilities for greenhouse drainage systems.

Provides functions to estimate the number of gutter pieces needed
based on greenhouse dimensions and grid layout.
"""

from typing import List, Tuple, Optional, Dict
import math

from .segment_analysis import find_north_south_segments


def estimate_gutters_length(
    points: List[Tuple[float, float]],
    grid_w_m: float = 5.0,
    grid_h_m: float = 3.0,
    scale_factor: float = 5.0,
    tolerance_px: float = 0.75,
) -> Optional[Dict[str, float]]:
    """Estimate total number of gutter pieces needed.

    Logic (as specified):
    - Along the north base, consider module width = 2 * grid_w_m. Let n_full = floor(width / (2*grid_w)).
    - Create vertical gutter lines along Y at each module boundary plus the two outer edges.
      That yields lines_x = max(2, n_full + 1).
    - Each vertical line is covered by pieces of length equal to grid_h_m (3m for 5x3, 4m for 5x4).
      pieces_per_line = ceil(depth / grid_h_m).
    - Total pieces = lines_x * pieces_per_line.

    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters
        grid_h_m: Grid cell height in meters (also gutter piece length)
        scale_factor: Pixels per meter conversion factor
        tolerance_px: Tolerance for horizontal segment detection
    
    Returns:
        Dict with a breakdown of gutter calculation or None if invalid input
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    ns = find_north_south_segments(pts, tolerance_px=tolerance_px)
    north = ns.get("north") if ns else None
    south = ns.get("south") if ns else None
    if not north or not south:
        return None

    (nx1, ny1) = north["p1"]
    (nx2, ny2) = north["p2"]
    if nx2 < nx1:
        nx1, nx2 = nx2, nx1
        ny1, ny2 = ny2, ny1
    north_y = 0.5 * (ny1 + ny2)
    width_px = max(0.0, nx2 - nx1)

    (sx1, sy1) = south["p1"]
    (sx2, sy2) = south["p2"]
    south_y = 0.5 * (sy1 + sy2)
    depth_px = max(0.0, south_y - north_y)

    if scale_factor <= 0:
        return None
    width_m = width_px / scale_factor
    depth_m = depth_px / scale_factor

    # Align gutter vertical lines with triangle modules (now 5 m)
    module_w_m = 1.0 * grid_w_m
    if module_w_m <= 0 or grid_h_m <= 0:
        return None
    n_full = int(width_m // module_w_m)
    lines_x = max(2, n_full + 1)

    piece_len_m = grid_h_m
    pieces_per_line = int(math.ceil(depth_m / piece_len_m)) if piece_len_m > 0 else 0
    total_pieces = lines_x * pieces_per_line

    return {
        "grid_w_m": grid_w_m,
        "grid_h_m": grid_h_m,
        "scale_factor": scale_factor,
        "north_width_m": width_m,
        "depth_m": depth_m,
        "module_w_m": module_w_m,
        "n_full_modules": n_full,
        "lines_x": lines_x,
        "piece_len_m": piece_len_m,
        "pieces_per_line": pieces_per_line,
        "total_pieces": total_pieces,
        "notes": "lines_x = max(2, floor(width/(grid_w))+1); pieces_per_line = ceil(depth/grid_h).",
    }
