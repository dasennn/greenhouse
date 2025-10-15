"""Polygon coverage analysis utilities.

Provides functions to compute how a polygon intersects with a regular grid,
including full and partial grid cell coverage.
"""

from typing import List, Tuple, Optional, Dict
from shapely.geometry import Polygon, box as shapely_box


def _to_pts(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Convert points to float tuples."""
    return [(float(x), float(y)) for x, y in points]


def compute_grid_coverage(
    points: List[Tuple[float, float]], 
    grid_w_m: float = 5.0, 
    grid_h_m: float = 3.0, 
    scale_factor: float = 5.0
) -> Optional[Dict]:
    """Compute polygon coverage against a regular grid.

    Returns dict with keys:
      - polygon_area_m2, polygon_area_px2, scale_factor
      - full_count, full_area_m2
      - partial_details: list of dicts with keys 'grid', 'area_m2', 
        'boundary_crossing_length_m', 'boundary_segments_m', 'shape', ...
    
    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters
        grid_h_m: Grid cell height in meters
        scale_factor: Pixels per meter conversion factor
    
    Returns:
        Dict with coverage details or None if invalid input
    """
    if points is None:
        return None
    pts = _to_pts(points)
    if len(pts) < 3:
        return None

    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    poly_area_px2 = poly.area
    poly_area_m2 = poly_area_px2 / (scale_factor * scale_factor) if scale_factor else 0.0

    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    grid_w = grid_w_m * scale_factor
    grid_h = grid_h_m * scale_factor

    gx0 = int((minx) // grid_w) - 1
    gy0 = int((miny) // grid_h) - 1
    gx1 = int((maxx) // grid_w) + 2
    gy1 = int((maxy) // grid_h) + 2

    full_count = 0
    full_area_px2 = 0.0
    partial_details = []

    for gy in range(gy0, gy1):
        y0 = gy * grid_h
        y1 = y0 + grid_h
        for gx in range(gx0, gx1):
            x0 = gx * grid_w
            x1 = x0 + grid_w
            cell = shapely_box(x0, y0, x1, y1)
            inter = poly.intersection(cell)
            if inter.is_empty:
                continue
            if inter.equals(cell):
                full_count += 1
                full_area_px2 += cell.area
            else:
                # filter negligible
                if inter.area <= max(1e-6, 1e-6 * cell.area):
                    continue
                area_m2 = inter.area / (scale_factor * scale_factor) if scale_factor else 0.0

                # boundary and crossing lengths
                try:
                    boundary_in_cell = poly.boundary.intersection(cell)
                    if boundary_in_cell.is_empty:
                        segment_lengths_m = []
                    else:
                        segment_lengths_m = []
                        geoms = getattr(boundary_in_cell, 'geoms', [boundary_in_cell])
                        for g in geoms:
                            if not (hasattr(g, 'length') and g.length):
                                continue
                            if g.geom_type not in ('LineString', 'LinearRing'):
                                continue
                            seg_len_m = g.length / scale_factor if scale_factor else 0.0
                            segment_lengths_m.append(seg_len_m)

                    inner_eps = max(1e-6, min(grid_w, grid_h) * 1e-6)
                    try:
                        inner_cell = shapely_box(x0 + inner_eps, y0 + inner_eps, x1 - inner_eps, y1 - inner_eps)
                        crossing = poly.boundary.intersection(inner_cell)
                        crossing_segments_m = []
                        if not crossing.is_empty:
                            cgeoms = getattr(crossing, 'geoms', [crossing])
                            for cg in cgeoms:
                                if hasattr(cg, 'length') and cg.length and cg.geom_type in ('LineString', 'LinearRing'):
                                    crossing_segments_m.append(cg.length / scale_factor if scale_factor else 0.0)
                    except Exception:
                        crossing_segments_m = []
                except Exception:
                    segment_lengths_m = []
                    crossing_segments_m = []

                boundary_len_m = sum(segment_lengths_m) if segment_lengths_m else 0.0
                crossing_len_m = sum(crossing_segments_m) if crossing_segments_m else 0.0

                partial_details.append({
                    'grid': (gx, gy),
                    'area_m2': area_m2,
                    'boundary_length_m': boundary_len_m,
                    'boundary_crossing_length_m': crossing_len_m,
                    'boundary_segments_m': segment_lengths_m,
                    'boundary_crossing_segments_m': crossing_segments_m,
                    'boundary_num_segments': len(segment_lengths_m),
                    'boundary_num_crossing_segments': len(crossing_segments_m),
                    'shape': inter,
                })

    full_area_m2 = full_area_px2 / (scale_factor * scale_factor) if scale_factor else 0.0
    return {
        'polygon_area_m2': poly_area_m2,
        'polygon_area_px2': poly_area_px2,
        'scale_factor': scale_factor,
        'full_count': full_count,
        'full_area_m2': full_area_m2,
        'partial_details': partial_details,
    }


def compute_grid_box_counts(
    points: List[Tuple[float, float]], 
    grid_w_m: float = 5.0, 
    grid_h_m: float = 3.0, 
    scale_factor: float = 5.0
) -> List[Dict]:
    """Return list of partial box details (keeps compatibility with UI fallback).
    
    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters
        grid_h_m: Grid cell height in meters
        scale_factor: Pixels per meter conversion factor
    
    Returns:
        List of dicts with partial grid cell information
    """
    if points is None:
        return []
    pts = _to_pts(points)
    if len(pts) < 3:
        return []

    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    grid_w = grid_w_m * scale_factor
    grid_h = grid_h_m * scale_factor
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    gx0 = int((minx) // grid_w) - 1
    gy0 = int((miny) // grid_h) - 1
    gx1 = int((maxx) // grid_w) + 2
    gy1 = int((maxy) // grid_h) + 2

    partial_details = []
    for gy in range(gy0, gy1):
        y0 = gy * grid_h
        y1 = y0 + grid_h
        for gx in range(gx0, gx1):
            x0 = gx * grid_w
            x1 = x0 + grid_w
            cell = shapely_box(x0, y0, x1, y1)
            inter = poly.intersection(cell)
            if inter.is_empty or inter.equals(cell):
                continue
            cell_area = cell.area
            if inter.area <= max(1e-6, 1e-6 * cell_area):
                continue
            partial_details.append({
                'grid': (gx, gy),
                'intersection_area': inter.area,
                'intersection_shape': inter,
            })
    return partial_details
