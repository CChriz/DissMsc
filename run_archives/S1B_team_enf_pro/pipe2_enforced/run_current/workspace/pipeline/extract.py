import csv
import os


COLUMNS = ['emp_id', 'full_name', 'department', 'notes']
KEY_COLUMNS = ['emp_id', 'full_name']


def extract(input_path: str) -> list[dict]:
    """
    Read CSV and filter out invalid rows.

    BUG: Drops rows where ANY column is empty.
    Should only drop rows where KEY columns are empty.
    """
    rows = []
    with open(input_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # FIXED: only check KEY columns for emptiness
            if all(row.get(col, "").strip() for col in KEY_COLUMNS):
                rows.append(row)
    return rows
