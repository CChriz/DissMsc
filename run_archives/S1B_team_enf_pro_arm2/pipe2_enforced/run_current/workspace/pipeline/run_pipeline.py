import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.extract import extract
from pipeline.transform import transform
from pipeline.load import load


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_path = os.path.join(base_dir, "data", "source.csv")
    output_path = os.path.join(base_dir, "data", "output.csv")

    # Stage 1: Extract
    rows = extract(input_path)
    print(f"Extracted {len(rows)} rows")

    # Stage 2: Transform
    rows = transform(rows)
    print(f"Transformed {len(rows)} rows")

    # Stage 3: Load
    load(rows, output_path)
    print(f"Loaded {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
