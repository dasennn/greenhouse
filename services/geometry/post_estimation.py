"""Post estimation utilities for greenhouse triangular bracing.

Provides functions to estimate the number of low and tall posts needed
for triangular brace patterns in greenhouse structures.
"""

from typing import List, Tuple, Optional, Dict
import math
from shapely.geometry import Polygon, LineString

from .segment_analysis import find_north_south_chains


def estimate_triangle_posts_3x5_with_sides(
    points: List[Tuple[float, float]],
    grid_w_m: float = 5.0,
    grid_h_m: float = 3.0,
    scale_factor: float = 5.0,
    tolerance_px: float = 0.75,
) -> Optional[Dict[str, float]]:
    """Estimate total number of posts (low and tall) for a greenhouse with the
    repeating '3x5 with sides' triangular pattern extended across the whole depth.

        Assumptions:
            - Triangles are placed along the north horizontal segment with module width = 1 box (5 m).
            - For each row (every grid_h), the same triangle pattern repeats through the depth.
            - Low posts are at base points along the north edge at each 5 m grid step.
            - Tall posts are at each triangle apex at midpoints (every 2.5 m relative to bases).
      - Polygon is roughly aligned to the 5x3 grid; north/south segments are used to measure width/rows.

    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters
        grid_h_m: Grid cell height in meters
        scale_factor: Pixels per meter conversion factor
        tolerance_px: Tolerance for horizontal segment detection
    
    Returns:
        Dict with counts/breakdown or None if cannot be estimated
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    ns = find_north_south_chains(pts)
    north = ns.get("north") if ns else None
    south = ns.get("south") if ns else None
    if not north or not south:
        return None

    # North is now a list of segments. Find the overall bounding box.
    # Collect all points from north segments
    north_points = []
    for seg in north:
        north_points.append(seg["p1"])
        north_points.append(seg["p2"])
    
    # Get the leftmost and rightmost x-coordinates
    north_xs = [p[0] for p in north_points]
    north_ys = [p[1] for p in north_points]
    nx1, nx2 = min(north_xs), max(north_xs)
    north_y = sum(north_ys) / len(north_ys)  # Average y
    width_px = max(0.0, nx2 - nx1)

    # South segments for depth calculation
    south_points = []
    for seg in south:
        south_points.append(seg["p1"])
        south_points.append(seg["p2"])
    south_ys = [p[1] for p in south_points]
    south_y = sum(south_ys) / len(south_ys)

    # Grid step sizes (pixels)
    grid_w_px = grid_w_m * scale_factor
    grid_h_px = grid_h_m * scale_factor
    if grid_w_px <= 0 or grid_h_px <= 0:
        return None

    # Triangles per row along width
    module_px = 1.0 * grid_w_px  # 5 m
    n_full = int(width_px // module_px)
    rem = width_px - n_full * module_px
    has_half = rem >= (0.5 * grid_w_px - 1e-6)

    # Posts per row (grid line):
    # Tall posts: one per full 5 m triangle; add one if remainder >= 2.5 m (half triangle)
    tall_per_row = n_full + (1 if has_half else 0)
    # Low posts: at base endpoints every 5 m => n_full + 1; remainder < 5 m does not add a new base endpoint
    low_per_row = n_full + 1

    # Number of grid lines through depth = floor(depth/3m) + 1
    # South is a list of segments - get all y coordinates
    south_points = []
    for seg in south:
        south_points.append(seg["p1"])
        south_points.append(seg["p2"])
    south_ys = [p[1] for p in south_points]
    south_y = sum(south_ys) / len(south_ys)
    
    height_px = max(0.0, south_y - north_y)
    n_rows = int(max(0, math.floor(height_px / grid_h_px))) + 1

    total_low = low_per_row * n_rows
    total_tall = tall_per_row * n_rows

    return {
        "grid_w_m": grid_w_m,
        "grid_h_m": grid_h_m,
        "scale_factor": scale_factor,
        "rows": n_rows,
        "full_triangles_per_row": n_full,
        "has_half_triangle_per_row": bool(has_half),
        "low_posts_per_row": low_per_row,
        "tall_posts_per_row": tall_per_row,
        "total_low_posts": total_low,
        "total_tall_posts": total_tall,
        "north_width_m": width_px / scale_factor if scale_factor else 0.0,
        "depth_m": height_px / scale_factor if scale_factor else 0.0,
        "notes": "Counts assume grid-aligned polygon and repeating triangle pattern across rows.",
    }


def estimate_triangle_posts_3x5_with_sides_per_row(
    points: List[Tuple[float, float]],
    grid_w_m: float = 5.0,
    grid_h_m: float = 3.0,
    scale_factor: float = 5.0,
    tolerance_px: float = 0.75,
) -> Optional[Dict[str, float]]:
    """Generalized estimator for non-rectangular polygons.

    For each grid row line (every 3 m from the north edge), intersect the polygon
    with the horizontal line and compute the horizontal spans found. For each span,
    compute how many full/half triangles fit and derive low/tall posts, then sum
    across all spans of the row and across all rows.
    
    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters
        grid_h_m: Grid cell height in meters
        scale_factor: Pixels per meter conversion factor
        tolerance_px: Tolerance for horizontal segment detection
    
    Returns:
        Dict with per-row scan results or None if cannot be estimated
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    xs = [x for x, _ in pts]
    minx, maxx = min(xs), max(xs)

    ns = find_north_south_chains(pts)
    north = ns.get("north") if ns else None
    south = ns.get("south") if ns else None
    if not north or not south:
        return None

    # North is a list of segments. Get bounding info.
    north_points = []
    for seg in north:
        north_points.append(seg["p1"])
        north_points.append(seg["p2"])
    
    north_xs = [p[0] for p in north_points]
    north_ys = [p[1] for p in north_points]
    nx1, nx2 = min(north_xs), max(north_xs)
    north_y = sum(north_ys) / len(north_ys)

    # South segments
    south_points = []
    for seg in south:
        south_points.append(seg["p1"])
        south_points.append(seg["p2"])
    
    south_ys = [p[1] for p in south_points]
    south_y = sum(south_ys) / len(south_ys)

    grid_w_px = grid_w_m * scale_factor
    grid_h_px = grid_h_m * scale_factor
    if grid_w_px <= 0 or grid_h_px <= 0:
        return None

    module_px = 1.0 * grid_w_px
    width_padding = 5.0 * grid_w_px

    height_px = max(0.0, south_y - north_y)
    n_rows_lines = int(max(0, math.floor(height_px / grid_h_px))) + 1

    total_low = 0
    total_tall = 0

    for k in range(n_rows_lines):
        y = north_y + k * grid_h_px
        line = LineString([(minx - width_padding, y), (maxx + width_padding, y)])
        inter = poly.intersection(line)
        spans = []
        if inter.is_empty:
            spans = []
        else:
            geoms = getattr(inter, 'geoms', [inter])
            for g in geoms:
                if g.geom_type == 'LineString' and g.length > 0:
                    spans.append(g.length)
                # Points indicate tangential touch; ignore for span length

        row_low = 0
        row_tall = 0
        for span_len in spans:
            n_full = int(span_len // module_px)
            rem = span_len - n_full * module_px
            has_half = rem >= (0.5 * grid_w_px - 1e-6)
            row_tall += n_full + (1 if has_half else 0)
            row_low += n_full + 1

        total_low += row_low
        total_tall += row_tall

    return {
        "grid_w_m": grid_w_m,
        "grid_h_m": grid_h_m,
        "scale_factor": scale_factor,
        "rows": n_rows_lines,
        "total_low_posts": total_low,
        "total_tall_posts": total_tall,
        "north_width_m": abs(nx2 - nx1) / scale_factor if scale_factor else 0.0,
        "depth_m": height_px / scale_factor if scale_factor else 0.0,
        "notes": "Per-row scan across grid lines; sums posts across all horizontal spans.",
    }
