# Define Estimator and MaterialItem here

class Estimator:
    def __init__(self, materials, scale_factor):
        self.materials = materials
        self.scale_factor = scale_factor

    def compute_bill(self, xy):
        # Placeholder implementation
        return {
            "geometry": {"area_m2": 100.0, "perimeter_m": 40.0},
            "grid_cells": {"full": 10, "partial": 5},
            "subtotal": 500.0,
            "currency": "EUR",
        }


class MaterialItem:
    def __init__(self, name, price):
        self.name = name
        self.price = price
