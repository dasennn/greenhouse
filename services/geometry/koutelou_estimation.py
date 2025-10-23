"""Koutelou pair estimation utilities for greenhouse facades.

Provides functions to estimate the length of "koutelou pairs" (ζεύγη κουτελού)
needed for north and south facades of greenhouse structures.
"""

from typing import List, Tuple, Optional, Dict
import math

from .segment_analysis import group_facade_segments


def estimate_koutelou_pairs(
    points: List[Tuple[float, float]],
    grid_w_m: float = 5.0,
    grid_h_m: float = 3.0,
    scale_factor: float = 5.0,
    pipe_length_m: float = 2.54,
) -> Optional[Dict[str, float]]:
    """Estimate total number of koutelou pairs for north and south facades.

    Koutelou pairs are placed only on north and south facades (προσόψεις).
    For regular (non-diagonal) facades, each pyramid (triangle) requires 2 pairs:
    - 1 pair from low post to tall post (apex)
    - 1 pair from ridge cap to gutter
    
    The pipe_length_m is the length of the pipe (adjustable by user) but does NOT
    affect the quantity calculation. Quantity = number_of_pyramids × 2 pairs.

    Logic:
    - Identify north and south horizontal segments
    - Check if segments are regular (horizontal, not diagonal)
    - For each regular segment, calculate number of pyramids (triangles)
    - Total pairs = number_of_pyramids × 2

    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters (default 5.0)
        grid_h_m: Grid cell height in meters (default 3.0)
        scale_factor: Pixels per meter conversion factor
        pipe_length_m: Length of pipe from gutter to ridge (adjustable, default 2.54m)

    Returns:
        Dict with:
        - total_pairs: Total number of koutelou pairs (integer)
        - north_pyramids: Number of pyramids on north facade
        - south_pyramids: Number of pyramids on south facade
        - is_regular: Whether facades are regular (not diagonal)
        - pipe_length_m: The pipe length setting (for reference)
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

    grid_w_px = grid_w_m * scale_factor
    if grid_w_px <= 0:
        return None

    def is_segment_regular(segment: Dict, angle_tolerance: float = 10.0) -> bool:
        """Check if a segment is regular (approximately horizontal).
        
        A segment is considered regular if its angle is within tolerance
        of horizontal (0° or 180°).
        """
        angle = segment["angle"]
        # Normalize angle to [-180, 180]
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        
        # Check if close to horizontal (0° or ±180°)
        return abs(angle) <= angle_tolerance or abs(abs(angle) - 180) <= angle_tolerance

    def count_pyramids_in_segments(segments: List[Dict]) -> Tuple[int, bool]:
        """Count total pyramids (triangles) across all segments and check if regular.
        
        Each pyramid = one triangle = one grid box width (5m).
        Number of pyramids = number of grid boxes along the width.
        """
        if not segments:
            return 0, False
        
        # Check if all segments are regular
        all_regular = all(is_segment_regular(seg) for seg in segments)
        
        if not all_regular:
            return 0, False
        
        # Calculate total width from all segments
        total_width_px = sum(seg["length"] for seg in segments)
        
        # Calculate number of pyramids = number of grid boxes (5m each)
        num_pyramids = int(round(total_width_px / grid_w_px))
        
        return num_pyramids, True

    # Count pyramids for north and south
    north_pyramids, north_regular = count_pyramids_in_segments(north)
    south_pyramids, south_regular = count_pyramids_in_segments(south)

    # Both facades must be regular for koutelou pairs
    is_regular = north_regular and south_regular

    if not is_regular:
        return {
            "total_pairs": 0,
            "north_pyramids": 0,
            "south_pyramids": 0,
            "is_regular": False,
            "pipe_length_m": pipe_length_m,
            "notes": "Facades are not regular (diagonal); koutelou pairs not applicable.",
        }

    # Calculate total pairs: 2 pairs per pyramid
    total_pyramids = north_pyramids + south_pyramids
    total_pairs = total_pyramids * 2

    return {
        "total_pairs": total_pairs,
        "north_pyramids": north_pyramids,
        "south_pyramids": south_pyramids,
        "total_pyramids": total_pyramids,
        "is_regular": is_regular,
        "pipe_length_m": pipe_length_m,
        "grid_w_m": grid_w_m,
        "scale_factor": scale_factor,
        "notes": "Each pyramid requires 2 pairs: (low→tall post) + (ridge→gutter).",
    }
