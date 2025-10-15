"""Segment analysis utilities for perimeter detection.

Provides functions to identify horizontal segments (north/south edges)
in a polygon perimeter.
"""

from typing import List, Tuple, Optional, Dict


def find_north_south_segments(
    points: List[Tuple[float, float]], 
    tolerance_px: float = 0.5
) -> Dict[str, Optional[Dict]]:
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
    
    Args:
        points: List of (x, y) tuples representing polygon vertices
        tolerance_px: Maximum vertical deviation to consider segment horizontal
    
    Returns:
        Dict with 'north' and 'south' keys containing segment info or None
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
