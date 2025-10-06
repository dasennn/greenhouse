# Greenhouse

A small PySide6 app for drawing and analyzing greenhouse grid coverage.

## Requirements

- Python 3.10+
- PySide6>=6.5.0
- shapely>=2.0

Install deps:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

## Notes

- Grid is 5m x 3m. Use the toolbar to toggle modes and close the perimeter.
- Coverage computations use Shapely.
