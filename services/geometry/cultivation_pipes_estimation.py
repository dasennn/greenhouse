"""Cultivation pipes estimation utilities for greenhouse horizontal support.

Provides functions to estimate the number and classification of cultivation pipes
(σωλήνες καλλιέργειας) needed for plant wire support systems.
"""

from typing import List, Tuple, Optional, Dict
import math


def estimate_cultivation_pipes(
    points: List[Tuple[float, float]],
    grid_w_m: float = 5.0,
    grid_h_m: float = 3.0,
    scale_factor: float = 5.0,
    pipe_length_m: float = 5.0,
) -> Optional[Dict[str, float]]:
    """Estimate cultivation pipes running perpendicular to horizontal axis.

    Cultivation pipes (σωλήνες καλλιέργειας) run parallel to the X-axis (width)
    to support wire for plants. They are spaced along the Y-axis (depth) according
    to grid_h_m spacing.

    Calculation logic:
    - Number of pipes = depth_m / grid_h_m (spacing based on grid height)
    - Total meters = number_of_pipes × width_m
    - Total pieces = total_meters / pipe_length_m
    - Classification:
      - Left side: "πάτημα-στένεμα" (pressed-narrow)
      - Middle: "στένεμα-ανοιχτό" (narrow-open)
      - Right side: "πάτημα-ανοιχτό" (pressed-open)
      - Distribution: left=N, middle=2N, right=N where N = total/4

    Example:
    - If depth=21m, grid_h=3m → 7 pipes
    - If width=20m → 7×20 = 140m total
    - If pipe_length=5m → 140/5 = 28 pieces
    - Classification: 7 left, 14 middle, 7 right

    Args:
        points: List of (x, y) tuples in scene coordinates (pixels)
        grid_w_m: Grid cell width in meters (default 5.0)
        grid_h_m: Grid cell height in meters (default 3.0)
        scale_factor: Pixels per meter conversion factor
        pipe_length_m: Length of individual pipe pieces (adjustable, default 5.0m)

    Returns:
        Dict with:
        - total_pipes: Total number of cultivation pipe pieces (integer)
        - total_meters: Total length in meters
        - num_lines: Number of parallel pipe lines
        - width_m: Width of greenhouse (meters)
        - depth_m: Depth of greenhouse (meters)
        - pipe_length_m: Individual pipe length setting
        - left_pieces: Pieces for left side (πάτημα-στένεμα)
        - middle_pieces: Pieces for middle (στένεμα-ανοιχτό)
        - right_pieces: Pieces for right side (πάτημα-ανοιχτό)
        or None if cannot be estimated
    """
    if not points or len(points) < 3:
        return None

    pts = [(float(x), float(y)) for x, y in points]
    
    # Close polygon if not already closed
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    
    # Calculate bounding box to get width and depth
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    width_px = max_x - min_x
    depth_px = max_y - min_y
    
    width_m = width_px / scale_factor
    depth_m = depth_px / scale_factor
    
    if width_m <= 0 or depth_m <= 0 or grid_h_m <= 0 or pipe_length_m <= 0:
        return None
    
    # Number of pipe lines = (depth / grid_height) + 1
    # Includes both edge lines (start and end) plus intermediate lines
    # Example: 21m / 3m = 7 intervals → 8 lines (including both edges)
    num_lines = int(depth_m / grid_h_m) + 1
    
    # Total meters = number of lines × width
    total_meters = num_lines * width_m
    
    # Total pieces = total meters / pipe length (rounded up)
    total_pieces = math.ceil(total_meters / pipe_length_m)
    
    # Classification into left/middle/right
    # Distribution: approximately 1:2:1 (left : middle : right)
    # For num_lines=7: left=7/4≈2, middle=7/2≈3-4, right=7/4≈2
    # But based on your example: 7, 14, 7 suggests equal distribution per line
    # So: pieces_per_line, then distribute
    
    # Alternative interpretation from your example:
    # If we have 7 lines and 28 total pieces (4 pieces per line on average)
    # Classification: 7 pieces left, 14 middle, 7 right
    # This suggests: left = total/4, middle = total/2, right = total/4
    
    left_pieces = int(round(total_pieces / 4))
    right_pieces = int(round(total_pieces / 4))
    middle_pieces = total_pieces - left_pieces - right_pieces  # Remainder goes to middle
    
    return {
        "total_pipes": total_pieces,
        "total_meters": round(total_meters, 2),
        "num_lines": round(num_lines, 2),
        "width_m": round(width_m, 2),
        "depth_m": round(depth_m, 2),
        "pipe_length_m": pipe_length_m,
        "left_pieces": left_pieces,      # πάτημα-στένεμα
        "middle_pieces": middle_pieces,  # στένεμα-ανοιχτό
        "right_pieces": right_pieces,    # πάτημα-ανοιχτό
        "grid_h_m": grid_h_m,
        "grid_w_m": grid_w_m,
        "scale_factor": scale_factor,
        "notes": "Pipes run parallel to X-axis (width), spaced by grid_h_m along Y-axis (depth).",
    }
