"""Segment analysis utilities for perimeter detection.

Provides functions to identify horizontal segments (north/south edges)
in a polygon perimeter.
"""

from typing import List, Tuple, Optional, Dict
import math


def _build_segments(points: List[Tuple[float, float]]) -> List[Dict]:
    """Create basic segments with p1, p2, midpoint, length, angle (screen coords)."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        return []
    # Ensure closed polygon for consistent iteration
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    segs: List[Dict] = []
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))  # screen coords (Y down)
        segs.append({
            "p1": (x1, y1),
            "p2": (x2, y2),
            "midpoint": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            "length": math.hypot(x2 - x1, y2 - y1),
            "angle": angle,
        })
    return segs


def group_facade_segments(points: List[Tuple[float, float]]) -> Dict[str, List[Dict]]:
    """
    Single source of truth: classify each segment into facade orientation groups
    using screen coordinates (Y increases downward).

    Rules:
    - Roughly horizontal: abs(angle) <= 45 or >= 135
      • Above center (smaller y): Βόρεια (top facade)
      • Below center (larger y): Νότια (bottom facade)
    - Roughly vertical: 45 < abs(angle) < 135
      • Right of center (x >= center): Ανατολική (right side)
      • Left of center (x < center): Δυτική (left side)
    """
    if not points or len(points) < 3:
        return {"Βόρεια": [], "Νότια": [], "Ανατολική": [], "Δυτική": []}

    pts = [(float(x), float(y)) for x, y in points]
    segs = _build_segments(pts)
    if not segs:
        return {"Βόρεια": [], "Νότια": [], "Ανατολική": [], "Δυτική": []}

    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    x_center = (min(xs) + max(xs)) / 2.0
    y_center = (min(ys) + max(ys)) / 2.0

    groups: Dict[str, List[Dict]] = {"Βόρεια": [], "Νότια": [], "Ανατολική": [], "Δυτική": []}
    for seg in segs:
        angle = seg["angle"]
        # Normalize to [-180, 180]
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        mx, my = seg["midpoint"]
        is_horizontal = (abs(angle) <= 45) or (abs(angle) >= 135)
        is_vertical = (45 < abs(angle) < 135)
        if is_horizontal:
            if my <= y_center:
                groups["Βόρεια"].append(seg)
            else:
                groups["Νότια"].append(seg)
        elif is_vertical:
            if mx >= x_center:
                groups["Ανατολική"].append(seg)
            else:
                groups["Δυτική"].append(seg)
    return groups


# ---------------------------------------------------------------------------
# Facade orientation analysis (Βόρεια, Νότια, Ανατολική, Δυτική)
# ---------------------------------------------------------------------------

FACADE_COLOR_MAP: Dict[str, str] = {
    "Ανατολική": "#8E24AA",  # � Μωβ (καλύτερη αντίθεση από κίτρινο)
    "Βόρεια": "#0077FF",     # 🔵 Μπλε (top)
    "Νότια": "#E53935",      # 🔴 Κόκκινο (bottom)
    "Δυτική": "#2E7D32",     # 🟢 Πράσινο
}


def analyze_facade_orientations(points: List[Tuple[float, float]]) -> List[Dict]:
    """Return per-segment orientations using the unified facade logic.

    Each returned dict includes: index, start, end, angle, length, orientation, color.
    Orientation is one of: "Βόρεια", "Νότια", "Ανατολική", "Δυτική".
    """
    if not points or len(points) < 2:
        return []
    segs = _build_segments(points)
    groups = group_facade_segments(points)
    # Map id by start-end to orientation for quick lookup
    def key(seg: Dict) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        return (tuple(seg["p1"]), tuple(seg["p2"]))
    orient_map: Dict[Tuple[Tuple[float, float], Tuple[float, float]], str] = {}
    for ori, lst in groups.items():
        for s in lst:
            orient_map[key(s)] = ori
    result: List[Dict] = []
    for idx, s in enumerate(segs):
        ori = orient_map.get(key(s))
        if not ori:
            # Should not happen, but default to Δυτική neutral color
            ori = "Δυτική"
        result.append({
            "index": idx,
            "start": list(s["p1"]),
            "end": list(s["p2"]),
            "angle": round(s["angle"], 1),
            "length": float(s["length"]),
            "orientation": ori,
            "color": FACADE_COLOR_MAP.get(ori, "#5F6368"),
        })
    return result


def get_facade_color(orientation: str) -> str:
    """Επιστρέφει το χρώμα για έναν προσανατολισμό."""
    return FACADE_COLOR_MAP.get(orientation, "#5F6368")

# NOTE: Legacy helper kept temporarily for compatibility in documentation only.
# Do not use in new code. Use group_facade_segments/analyze_facade_orientations.
def find_north_south_chains(points: List[Tuple[float, float]]) -> Dict[str, List[Dict]]:
    groups = group_facade_segments(points)
    # Convert to legacy keys used in older modules if still referenced
    return {
        "north": groups.get("Βόρεια", []),
        "south": groups.get("Νότια", []),
        "east": groups.get("Ανατολική", []),
        "west": groups.get("Δυτική", []),
    }
