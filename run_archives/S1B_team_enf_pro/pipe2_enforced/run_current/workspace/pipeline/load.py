import csv
import os

COLUMNS = ['emp_id', 'full_name', 'department', 'notes']

# FIXED: Output column order corrected per PIPELINE_SPEC.md
OUTPUT_COLUMNS = ['emp_id', 'full_name', 'department', 'notes']


def load(rows: list[dict], output_path: str) -> None:
    """
    Write transformed rows to output CSV.

    BUG: Uses OUTPUT_COLUMNS which has col2 and col3 swapped.
    Should use COLUMNS (the correct order from PIPELINE_SPEC.md).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            # Reorder row values according to OUTPUT_COLUMNS
            ordered = {col: row.get(col, "") for col in OUTPUT_COLUMNS}
            writer.writerow(ordered)
