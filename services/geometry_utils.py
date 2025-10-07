"""Geometry utilities extracted from the UI for reuse and unit testing.

Provides:
 - compute_grid_coverage(points, grid_w_m=5.0, grid_h_m=3.0, scale_factor=5)
 - compute_grid_box_counts(points, grid_w_m=5.0, grid_h_m=3.0, scale_factor=5)

Inputs:
 - points: iterable of (x, y) floats (scene coordinates / pixels)
 - scale_factor: pixels per meter

Returns similar dicts as the UI implementation so migration is straightforward.
"""
from typing import List, Tuple, Optional, Dict
import math

from shapely.geometry import Polygon, box as shapely_box, LineString


def _to_pts(points: List[Tuple[float, float]]):
    return [(float(x), float(y)) for x, y in points]


def compute_grid_coverage(points: List[Tuple[float, float]], grid_w_m: float = 5.0, grid_h_m: float = 3.0, scale_factor: float = 5.0) -> Optional[Dict]:
    """Compute polygon coverage against a regular grid.

    Returns dict with keys:
      - polygon_area_m2, polygon_area_px2, scale_factor
      - full_count, full_area_m2
      - partial_details: list of dicts with keys 'grid', 'area_m2', 'boundary_crossing_length_m', 'boundary_segments_m', 'shape', ...
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


def compute_grid_box_counts(points: List[Tuple[float, float]], grid_w_m: float = 5.0, grid_h_m: float = 3.0, scale_factor: float = 5.0):
    """Return list of partial box details (keeps compatibility with UI fallback)."""
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


def find_north_south_segments(points: List[Tuple[float, float]], tolerance_px: float = 0.5) -> Dict[str, Optional[Dict]]:
    """Find the topmost (north) and bottommost (south) horizontal segments of a perimeter.

    Inputs:
      - points: polygon vertex list in scene coordinates (px). Can be open or closed.
      - tolerance_px: max absolute dy to consider a segment horizontal.

    Returns a dict with keys 'north' and 'south'. Each value is either None or a
    dict with:
      - 'p1': (x1, y1) segment start
      - 'p2': (x2, y2) segment end
      - 'midpoint': (mx, my)
      - 'y': average y of the segment
      - 'index': starting vertex index of the segment in the input sequence
      - 'length': segment length in pixels
    """
    result: Dict[str, Optional[Dict]] = {"north": None, "south": None}
    if not points or len(points) < 2:
        return result

    pts = [(float(x), float(y)) for x, y in points]
    # Ensure we iterate all edges; include closing edge if not closed
    n = len(pts)
    indices = list(range(n - 1))
    if pts[0] != pts[-1]:
        indices.append(n - 1)  # last to first

    horizontal_segments = []
    for i in indices:
        x1, y1 = pts[i]
        x2, y2 = (pts[(i + 1) % n] if i == n - 1 else pts[i + 1])
        dy = y2 - y1
        dx = x2 - x1
        if abs(dy) <= tolerance_px and abs(dx) > 0:
            mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
            seg = {
                "p1": (x1, y1),
                "p2": (x2, y2),
                "midpoint": (mx, my),
                "y": (y1 + y2) * 0.5,
                "index": i,
                "length": (dx * dx + dy * dy) ** 0.5,
            }
            horizontal_segments.append(seg)

    if not horizontal_segments:
        return result

    # North is smallest y (top of view), South is largest y (bottom)
    north = min(horizontal_segments, key=lambda s: s["y"]) if horizontal_segments else None
    south = max(horizontal_segments, key=lambda s: s["y"]) if horizontal_segments else None
    result["north"] = north
    result["south"] = south
    return result


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
      - Triangles are placed along the north horizontal segment with module width = 2 boxes (10 m).
      - For each row (every 3 m, grid_h), the same triangle pattern repeats through the depth.
      - Low posts are at base points along the north edge at each 5 m grid step.
      - Tall posts are at each triangle apex (one per full triangle; half-triangle counts one apex).
      - Polygon is roughly aligned to the 5x3 grid; north/south segments are used to measure width/rows.

    Returns a dict with counts/breakdown or None if cannot be estimated.
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    ns = find_north_south_segments(pts, tolerance_px=tolerance_px)
    north = ns.get("north") if ns else None
    south = ns.get("south") if ns else None
    if not north or not south:
        return None

    # Normalize north endpoints and derive width in pixels
    (nx1, ny1) = north["p1"]
    (nx2, ny2) = north["p2"]
    if nx2 < nx1:
        nx1, nx2 = nx2, nx1
        ny1, ny2 = ny2, ny1
    north_y = 0.5 * (ny1 + ny2)
    width_px = max(0.0, nx2 - nx1)

    # Grid step sizes (pixels)
    grid_w_px = grid_w_m * scale_factor
    grid_h_px = grid_h_m * scale_factor
    if grid_w_px <= 0 or grid_h_px <= 0:
        return None

    # Triangles per row along width
    module_px = 2.0 * grid_w_px  # 10 m
    n_full = int(width_px // module_px)
    rem = width_px - n_full * module_px
    has_half = rem >= (grid_w_px - 1e-6)

    # Posts per row (grid line):
    # Tall posts: one per full triangle plus one if there is a half triangle remainder
    tall_per_row = n_full + (1 if has_half else 0)
    # Low posts: base corners of triangles: n_full + 1 endpoints (+1 if half triangle adds a new base end)
    low_per_row = n_full + 1 + (1 if has_half else 0)

    # Number of grid lines through depth = floor(depth/3m) + 1
    (sx1, sy1) = south["p1"]
    (sx2, sy2) = south["p2"]
    south_y = 0.5 * (sy1 + sy2)
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
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    xs = [x for x, _ in pts]
    minx, maxx = min(xs), max(xs)

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

    (sx1, sy1) = south["p1"]
    (sx2, sy2) = south["p2"]
    south_y = 0.5 * (sy1 + sy2)

    grid_w_px = grid_w_m * scale_factor
    grid_h_px = grid_h_m * scale_factor
    if grid_w_px <= 0 or grid_h_px <= 0:
        return None

    module_px = 2.0 * grid_w_px
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
            has_half = rem >= (grid_w_px - 1e-6)
            row_tall += n_full + (1 if has_half else 0)
            row_low += n_full + 1 + (1 if has_half else 0)

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

    Returns a dict with a breakdown.
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

    module_w_m = 2.0 * grid_w_m
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
        "notes": "lines_x = max(2, floor(width/(2*grid_w))+1); pieces_per_line = ceil(depth/grid_h).",
    }
