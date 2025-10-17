"""Segment analysis utilities for perimeter detection.

Provides functions to identify horizontal segments (north/south edges)
in a polygon perimeter.
"""

from typing import List, Tuple, Optional, Dict
import math


def find_north_south_chains(points: List[Tuple[float, float]]) -> Dict[str, List[Dict]]:
    """
    Analyzes a polygon to find its "north", "south", "east", and "west" segments.

    This method identifies segments based on their orientation and position:
    - North: Roughly horizontal segments in the upper half of the shape
    - South: Roughly horizontal segments in the lower half of the shape
    - East: Roughly vertical segments in the right half of the shape
    - West: Roughly vertical segments in the left half of the shape

    Args:
        points: A list of (x, y) tuples defining the vertices of the polygon.

    Returns:
        A dictionary with four keys: "north", "south", "east", "west", each containing
        a list of segment dictionaries for that orientation.
    """
    if not points or len(points) < 3:
        return {"north": [], "south": [], "east": [], "west": []}

    pts = [(float(x), float(y)) for x, y in points]
    n = len(pts)

    # Helper to create a segment dictionary
    def create_segment(p1_idx, p2_idx):
        x1, y1 = pts[p1_idx]
        x2, y2 = pts[p2_idx]
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        return {
            "p1": (x1, y1),
            "p2": (x2, y2),
            "midpoint": ((x1 + x2) / 2, (y1 + y2) / 2),
            "length": math.sqrt((x2 - x1)**2 + (y2 - y1)**2),
            "angle": angle
        }

    # Create all segments
    all_segments = []
    for i in range(n):
        next_idx = (i + 1) % n
        # Skip if it's a duplicate closing edge
        if i == n - 1 and pts[0] == pts[-1]:
            continue
        all_segments.append(create_segment(i, next_idx))

    if not all_segments:
        return {"north": [], "south": [], "east": [], "west": []}

    # Find the center of the shape
    all_x_coords = [p[0] for p in pts]
    all_y_coords = [p[1] for p in pts]
    x_center = (min(all_x_coords) + max(all_x_coords)) / 2
    y_center = (min(all_y_coords) + max(all_y_coords)) / 2

    # Classify segments based on angle and position
    north_segments = []
    south_segments = []
    east_segments = []
    west_segments = []
    
    for seg in all_segments:
        angle = seg["angle"]
        midpoint_x = seg["midpoint"][0]
        midpoint_y = seg["midpoint"][1]
        
        # Normalize angle to [-180, 180]
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        
        # Classify based on angle:
        # Horizontal: -45° to 45° or 135° to 180° or -180° to -135°
        # Vertical: 45° to 135° or -135° to -45°
        
        is_horizontal = (abs(angle) <= 45) or (abs(angle) >= 135)
        is_vertical = (45 < abs(angle) < 135)
        
        if is_horizontal:
            if midpoint_y < y_center:
                # Upper half = North
                north_segments.append(seg)
            else:
                # Lower half = South
                south_segments.append(seg)
        elif is_vertical:
            if midpoint_x >= x_center:
                # Right half = East
                east_segments.append(seg)
            else:
                # Left half = West
                west_segments.append(seg)

    return {
        "north": north_segments,
        "south": south_segments,
        "east": east_segments,
        "west": west_segments
    }
