# count_grid_boxes(xy, scale_factor, grid_w_m, grid_h_m) is called by UI/main_window.py
# It receives the perimeter as a list of (x, y) floats and returns (full, partial) grid box counts.

full = partial = None
        # Try both package names so either layout works: backend/geometry.py or services/geometry.py
        _count_boxes = None
        try:
            from backend.geometry import count_grid_boxes as _count_boxes
        except Exception:
            try:
                from services.geometry import count_grid_boxes as _count_boxes
            except Exception:
                _count_boxes = None

        if _count_boxes is not None:
            try:
                full, partial = _count_boxes(
                    xy,
                    scale_factor=self.view.scale_factor,
                    grid_w_m=5.0,
                    grid_h_m=3.0,
                )
            except Exception:
                full = partial = None

        if full is None:
            try:
                # Fallback to view's local approximation
                full, partial = self.view.compute_grid_box_counts(points=xy, grid_w_m=5.0, grid_h_m=3.0, scale_factor=self.view.scale_factor)
            except Exception:
                full = partial = None