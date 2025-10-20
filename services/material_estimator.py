"""Material quantity estimation rules.

This module translates geometric estimation outputs into per-material
quantities, keeping the rule set explicit and testable.

Inputs are dictionaries returned by services/geometry_utils functions.
Outputs are dicts mapping material code -> quantity (float).

High-level contract
- Inputs:
  - posts_est: dict | None with keys like 'total_tall_posts', 'total_low_posts'
  - gutters_est: dict | None with keys like 'total_pieces'
  - grid_h_m: float (meters), used to choose gutter piece code (3m/4m/other)
- Output:
  - Dict[str, float] where keys are material codes and values are non-negative quantities.

Rules (current):
- Posts:
  - 'post_tall'  <- posts_est['total_tall_posts']
  - 'post_low'   <- posts_est['total_low_posts']
- Gutters:
  - If grid_h_m == 3.0 → 'gutter_3m'
  - If grid_h_m == 4.0 → 'gutter_4m'
  - Else → 'gutter_piece' (generic)
  - Quantity <- gutters_est['total_pieces']

All missing values default to 0. Invalid/missing inputs are tolerated.
"""

from __future__ import annotations

from typing import Dict, Optional


EPS = 1e-6


def _safe_float(d: dict | None, key: str) -> float:
    try:
        if not d:
            return 0.0
        v = d.get(key, 0) or 0
        return float(v)
    except Exception:
        return 0.0


def choose_gutter_code(grid_h_m: float) -> str:
    if abs(grid_h_m - 3.0) < EPS:
        return "gutter_3m"
    if abs(grid_h_m - 4.0) < EPS:
        return "gutter_4m"
    return "gutter_piece"


def estimate_material_quantities(
    posts_est: Optional[dict],
    gutters_est: Optional[dict],
    koutelou_est: Optional[dict],
    plevra_est: Optional[dict],
    grid_h_m: float
) -> Dict[str, float]:
    """Return {material_code: quantity} based on geometric estimates.

    This function encodes the mapping rules in a single place.
    
    Args:
        posts_est: Post estimation results
        gutters_est: Gutter estimation results
        koutelou_est: Koutelou pair estimation results
        plevra_est: Plevra (side support) estimation results
        grid_h_m: Grid height in meters
    """
    quantities: Dict[str, float] = {}

    # Posts
    tall_qty = _safe_float(posts_est, "total_tall_posts")
    low_qty = _safe_float(posts_est, "total_low_posts")
    if tall_qty > 0:
        quantities["post_tall"] = tall_qty
    if low_qty > 0:
        quantities["post_low"] = low_qty

    # Ridge caps (κορφιάτες)
    # Νέος κανόνας: μπαίνουν στις κορυφές των τριγώνων κατά μήκος (apex per row)
    # και μετρώνται κάθετα όπως οι υδρορροές ⇒ apex_per_row × (depth_m / grid_h_m).
    apex_per_row = 0.0
    try:
        if posts_est:
            # Προτίμηση: απευθείας τιμή αν παρέχεται
            if "tall_posts_per_row" in posts_est:
                apex_per_row = float(posts_est.get("tall_posts_per_row") or 0)
            elif "full_triangles_per_row" in posts_est:
                full = float(posts_est.get("full_triangles_per_row") or 0)
                has_half = 1.0 if posts_est.get("has_half_triangle_per_row") else 0.0
                apex_per_row = full + has_half
            elif (posts_est.get("rows") or 0) > 0:
                rows = float(posts_est.get("rows") or 0)
                if rows > 0:
                    apex_per_row = tall_qty / rows
    except Exception:
        apex_per_row = 0.0

    depth_m = 0.0
    try:
        if posts_est and (posts_est.get("depth_m") is not None):
            depth_m = float(posts_est.get("depth_m") or 0.0)
        elif gutters_est and (gutters_est.get("depth_m") is not None):
            depth_m = float(gutters_est.get("depth_m") or 0.0)
    except Exception:
        depth_m = 0.0

    rows_y = 0
    try:
        if grid_h_m > 0:
            # Στρογγυλοποίηση στις κοντινότερες "σειρές" κουτιών
            rows_y = int(round(depth_m / grid_h_m))
    except Exception:
        rows_y = 0

    ridge_qty = apex_per_row * rows_y
    if ridge_qty > 0:
        quantities["ridge_cap"] = ridge_qty

    # Gutters - διαχωρισμός σε πλευρικές και εσωτερικές
    if gutters_est:
        side_pieces = _safe_float(gutters_est, "side_pieces")  # Πλευρικές (αριστερά/δεξιά)
        internal_pieces = _safe_float(gutters_est, "internal_pieces")  # Εσωτερικές/εμπρός-πίσω
        side_type = gutters_est.get("side_gutter_type", "full")  # "full" ή "half"
        
        # Επιλογή κωδικού βάσει grid_h_m
        if abs(grid_h_m - 3.0) < EPS:
            full_code = "gutter_3m"
            half_code = "gutter_3m_half"
        elif abs(grid_h_m - 4.0) < EPS:
            full_code = "gutter_4m"
            half_code = "gutter_4m_half"
        else:
            full_code = "gutter_piece"
            half_code = "gutter_piece"  # Fallback: δεν υπάρχει μισή
        
        # Πλευρικές υδρορροές
        if side_pieces > 0:
            if side_type == "half":
                quantities[half_code] = side_pieces
            else:
                quantities[full_code] = quantities.get(full_code, 0.0) + side_pieces
        
        # Εσωτερικές υδρορροές (πάντα full)
        if internal_pieces > 0:
            quantities[full_code] = quantities.get(full_code, 0.0) + internal_pieces

    # Koutelou pairs (ζεύγη κουτελού)
    # Μπαίνουν μόνο στις προσόψεις (βορράς και νότος) αν είναι κανονικές
    # Κάθε πυραμίδα χρειάζεται 2 ζεύγη: (χαμηλός→ψηλός στύλος) + (κορφιάτης→υδρορροή)
    koutelou_pairs = _safe_float(koutelou_est, "total_pairs")
    if koutelou_pairs > 0:
        quantities["koutelou_pair"] = koutelou_pairs

    # Plevra (πλευρά - κανονικά πλευρά)
    # Τοποθετούνται κατά μήκος του άξονα Υ (βάθος)
    # Πρώτο: 0.5m από προσόψη, μετά ανά 1m
    plevra_count = _safe_float(plevra_est, "total_plevra")
    if plevra_count > 0:
        quantities["plevra"] = plevra_count

    return quantities
