# Define Estimator and MaterialItem here

class Estimator:
    def __init__(self, materials, scale_factor):
        self.materials = materials
        self.scale_factor = scale_factor

    def compute_bill(self, xy, full=None, partial=None):
        """
        Compute a demonstration bill of materials based on grid box counts.
        Uses default mapping for demonstration: 
        - Full box: 4 columns, 2 beams
        - Partial box: 2 columns, 1 beam
        """
        # For demonstration, use dummy values if not provided
        if full is None:
            full = 10
        if partial is None:
            partial = 5

        # Demo material mapping
        material_map = {
            "column": {"full": 4, "partial": 2, "unit_price": 50},
            "beam":   {"full": 2, "partial": 1, "unit_price": 30},
        }
        bill = {}
        subtotal = 0
        for mat, vals in material_map.items():
            qty = vals["full"] * full + vals["partial"] * partial
            price = qty * vals["unit_price"]
            bill[mat] = {"quantity": qty, "unit_price": vals["unit_price"], "total": price}
            subtotal += price

        return {
            "materials": bill,
            "grid_cells": {"full": full, "partial": partial},
            "subtotal": subtotal,
            "currency": "EUR",
        }


class MaterialItem:
    def __init__(self, name, price):
        self.name = name
        self.price = price
