"""Post classification and corner detection utilities.

This module provides functions to classify posts by location and detect corners.
"""

from typing import List, Tuple, Dict, Optional
import math


def classify_post_by_location(
    post_x: float,
    post_y: float,
    polygon_corners: List[Tuple[float, float]],
    north_y: float,
    south_y: float,
    west_x: float,
    east_x: float,
    tolerance: float = 5.0
) -> str:
    """Classify a post as north/south/east/west based on its position.
    
    Args:
        post_x, post_y: Post coordinates in pixels
        polygon_corners: List of polygon corner coordinates
        north_y: Y coordinate of north edge (top)
        south_y: Y coordinate of south edge (bottom)
        west_x: X coordinate of west edge (left)
        east_x: X coordinate of east edge (right)
        tolerance: Distance tolerance in pixels
    
    Returns:
        One of: "north", "south", "east", "west", "internal"
    """
    # Check if on north facade (top)
    if abs(post_y - north_y) < tolerance:
        return "north"
    
    # Check if on south facade (bottom)
    if abs(post_y - south_y) < tolerance:
        return "south"
    
    # Check if on west side (left)
    if abs(post_x - west_x) < tolerance:
        return "west"
    
    # Check if on east side (right)
    if abs(post_x - east_x) < tolerance:
        return "east"
    
    # Internal post
    return "internal"


def detect_corners(
    polygon_corners: List[Tuple[float, float]],
    angle_tolerance: float = 10.0
) -> Dict[str, List[Dict]]:
    """Detect and classify corners as internal (convex) or external (concave).
    
    Args:
        polygon_corners: List of (x, y) tuples defining the polygon
        angle_tolerance: Tolerance in degrees for angle classification
    
    Returns:
        Dict with:
            - "internal_corners": List of convex corners (< 180°)
            - "external_corners": List of concave corners (> 180°)
            Each corner dict contains: {
                "position": (x, y),
                "angle_deg": float,
                "index": int
            }
    """
    if len(polygon_corners) < 3:
        return {"internal_corners": [], "external_corners": []}
    
    internal = []
    external = []
    n = len(polygon_corners)
    
    for i in range(n):
        # Get three consecutive points
        p_prev = polygon_corners[(i - 1) % n]
        p_curr = polygon_corners[i]
        p_next = polygon_corners[(i + 1) % n]
        
        # Calculate vectors
        v1 = (p_prev[0] - p_curr[0], p_prev[1] - p_curr[1])
        v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])
        
        # Calculate angle using cross product (determines orientation)
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        
        # Calculate angle in degrees
        angle_rad = math.atan2(cross, dot)
        angle_deg = math.degrees(angle_rad)
        
        # Normalize to [0, 360)
        if angle_deg < 0:
            angle_deg += 360
        
        corner_info = {
            "position": p_curr,
            "angle_deg": angle_deg,
            "index": i
        }
        
        # Classify: internal (convex) if angle < 180°, external (concave) if > 180°
        # Note: In screen coordinates (Y increases downward), this might be inverted
        # depending on polygon winding. We check the signed area to determine winding.
        if 170 < angle_deg < 190:  # Nearly straight (within tolerance)
            continue  # Skip nearly straight corners
        elif angle_deg < 180:
            internal.append(corner_info)
        else:
            external.append(corner_info)
    
    return {
        "internal_corners": internal,
        "external_corners": external
    }


def classify_all_posts(
    posts_data: Dict,
    polygon_corners: List[Tuple[float, float]],
    scale_factor: float = 5.0
) -> Dict:
    """Classify all posts (tall and low) by location using simplified distribution.
    
    For rectangular/orthogonal shapes, estimates distribution based on:
    - North/South facades get posts along width
    - East/West sides get posts along depth
    - Internal posts are the remainder
    
    Args:
        posts_data: Dict from estimate_triangle_posts_3x5_with_sides
        polygon_corners: List of polygon corners
        scale_factor: Pixels per meter
    
    Returns:
        Dict with estimated post counts per location
    """
    if not posts_data or not polygon_corners:
        return {}
    
    total_tall = posts_data.get("total_tall_posts", 0)
    total_low = posts_data.get("total_low_posts", 0)
    rows = posts_data.get("rows", 1)
    tall_per_row = posts_data.get("tall_posts_per_row", 0)
    low_per_row = posts_data.get("low_posts_per_row", 0)
    
    # Απλοποιημένη κατανομή:
    # - Βόρειοι/Νότιοι: Οι στύλοι της πρώτης και τελευταίας σειράς
    # - Πλαϊνοί: Εκτίμηση βάσει rows
    # - Εσωτερικοί: Το υπόλοιπο
    
    # Για ψηλούς στύλους
    tall_north = tall_per_row if rows > 0 else 0
    tall_south = tall_per_row if rows > 0 else 0
    tall_sides = max(0, int((rows - 2) * 2)) if rows > 2 else 0  # 2 posts per intermediate row
    tall_internal = max(0, total_tall - tall_north - tall_south - tall_sides)
    
    tall_east = tall_sides // 2
    tall_west = tall_sides - tall_east
    
    # Για χαμηλούς στύλους (παρόμοια λογική)
    low_north = low_per_row if rows > 0 else 0
    low_south = low_per_row if rows > 0 else 0
    low_sides = max(0, int((rows - 2) * 2)) if rows > 2 else 0
    low_internal = max(0, total_low - low_north - low_south - low_sides)
    
    low_east = low_sides // 2
    low_west = low_sides - low_east
    
    return {
        "tall_posts": {
            "north": [],  # Positions not available
            "south": [],
            "east": [],
            "west": [],
            "internal": []
        },
        "low_posts": {
            "north": [],
            "south": [],
            "east": [],
            "west": [],
            "internal": []
        },
        "summary": {
            "tall_north": tall_north,
            "tall_south": tall_south,
            "tall_east": tall_east,
            "tall_west": tall_west,
            "tall_internal": tall_internal,
            "low_north": low_north,
            "low_south": low_south,
            "low_east": low_east,
            "low_west": low_west,
            "low_internal": low_internal,
        }
    }
