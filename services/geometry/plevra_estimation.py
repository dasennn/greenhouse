"""Plevra (side support) estimation utilities for greenhouse.

Provides functions to estimate the number of regular "plevra" (πλευρά)
needed along the depth of greenhouse structures.
"""

from typing import List, Tuple, Optional, Dict
import math

from .segment_analysis import group_facade_segments


def estimate_plevra(
    points: List[Tuple[float, float]],
    grid_w_m: float = 5.0,
    grid_h_m: float = 3.0,
    scale_factor: float = 5.0,
    pipe_length_m: float = 2.54,
    first_offset_m: float = 0.5,
    spacing_m: float = 1.0,
) -> Optional[Dict[str, float]]:
    """Estimate total number of regular plevra for all pyramids.

    Plevra (πλευρά) are support bars placed in each pyramid along the Y-axis (depth):
    - Same philosophy as koutelou pairs but placed INSIDE each pyramid, not on facades
    - Each plevra has the SAME LENGTH as koutelou pairs (pipe_length_m, e.g., 2.54m)
    - In EACH pyramid: place plevra along the depth (Y-axis)
    - First plevra: 0.5m from koutelou pair position
    - Subsequent plevra: every 1.0m
    - NOT pairs - individual pieces
    
    Logic:
    - For each pyramid (5m width box), calculate plevra along depth
    - Start at first_offset_m (0.5m) from koutelou pair
    - Place plevra every spacing_m (1.0m) along the depth
    - Total plevra = number_of_pyramids × plevra_per_pyramid

    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters (default 5.0)
        grid_h_m: Grid cell height in meters (default 3.0)
        scale_factor: Pixels per meter conversion factor
        pipe_length_m: Length of each plevra piece (same as koutelou, default 2.54m)
        first_offset_m: Distance from koutelou pair to first plevra (default 0.5m)
        spacing_m: Distance between consecutive plevra (default 1.0m)

    Returns:
        Dict with:
        - total_plevra: Total number of plevra pieces across all pyramids (integer)
        - num_pyramids: Number of pyramids (same as koutelou calculation)
        - plevra_per_pyramid: Plevra per pyramid
        - pipe_length_m: Length of each plevra (same as koutelou)
        - width_m: Width of greenhouse (for reference)
        - depth_m: Depth of greenhouse
        - usable_depth_m: Depth available for plevra per pyramid (after offsets)
        - first_offset_m: Offset from koutelou pair
        - spacing_m: Spacing between plevra
        or None if cannot be estimated
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    groups = group_facade_segments(pts)
    
    if not groups:
        return None

    north = groups.get("Βόρεια", [])
    south = groups.get("Νότια", [])

    if not north or not south:
        return None

    scale_factor = float(scale_factor)
    if scale_factor <= 0:
        return None

    # Calculate width from north segments (to determine number of pyramids)
    north_points = []
    for seg in north:
        north_points.append(seg["p1"])
        north_points.append(seg["p2"])
    
    north_xs = [p[0] for p in north_points]
    north_ys = [p[1] for p in north_points]
    width_px = max(north_xs) - min(north_xs)
    north_y = sum(north_ys) / len(north_ys)
    
    # Calculate depth from south segments
    south_points = []
    for seg in south:
        south_points.append(seg["p1"])
        south_points.append(seg["p2"])
    
    south_ys = [p[1] for p in south_points]
    south_y = sum(south_ys) / len(south_ys)
    
    depth_px = abs(south_y - north_y)
    
    # Convert to meters
    width_m = width_px / scale_factor
    depth_m = depth_px / scale_factor
    
    # Calculate number of pyramids (same as koutelou calculation)
    # Each pyramid = one grid box width (5m)
    grid_w_px = grid_w_m * scale_factor
    if grid_w_px <= 0:
        return None
    
    num_pyramids = int(round(width_px / grid_w_px))
    
    if num_pyramids == 0:
        return {
            "total_plevra": 0,
            "num_pyramids": 0,
            "plevra_per_pyramid": 0,
            "pipe_length_m": pipe_length_m,
            "width_m": width_m,
            "depth_m": depth_m,
            "usable_depth_m": 0.0,
            "first_offset_m": first_offset_m,
            "spacing_m": spacing_m,
            "notes": "No pyramids found.",
        }
    
    # Calculate plevra per pyramid along the depth (Y-axis)
    # Usable depth: leave space at both ends (first_offset_m from koutelou pairs)
    usable_depth_m = depth_m - (2 * first_offset_m)
    
    if usable_depth_m <= 0:
        return {
            "total_plevra": 0,
            "num_pyramids": num_pyramids,
            "plevra_per_pyramid": 0,
            "pipe_length_m": pipe_length_m,
            "width_m": width_m,
            "depth_m": depth_m,
            "usable_depth_m": usable_depth_m,
            "first_offset_m": first_offset_m,
            "spacing_m": spacing_m,
            "notes": "Pyramid depth too short for plevra placement.",
        }
    
    # Calculate plevra per pyramid
    # First plevra at first_offset_m, then every spacing_m
    plevra_per_pyramid = int(math.floor(usable_depth_m / spacing_m)) + 1
    
    # Total plevra = pyramids × plevra_per_pyramid
    total_plevra = num_pyramids * plevra_per_pyramid
    
    return {
        "total_plevra": total_plevra,
        "num_pyramids": num_pyramids,
        "plevra_per_pyramid": plevra_per_pyramid,
        "pipe_length_m": pipe_length_m,
        "width_m": width_m,
        "depth_m": depth_m,
        "usable_depth_m": usable_depth_m,
        "first_offset_m": first_offset_m,
        "spacing_m": spacing_m,
        "notes": f"Total: {total_plevra} plevra = {num_pyramids} pyramids × {plevra_per_pyramid} plevra/pyramid. Each {pipe_length_m}m long.",
    }
