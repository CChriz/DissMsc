import csv
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.extract import extract
from pipeline.transform import transform
from pipeline.load import load


@pytest.fixture
def base_dir():
    return os.path.join(os.path.dirname(__file__), "..")


def test_extract_keeps_rows_with_nonkey_nulls(base_dir):
    """Rows with empty non-key columns should be kept."""
    rows = extract(os.path.join(base_dir, "data", "source.csv"))
    # Should keep 6 rows (drop only key-column-null rows)
    assert len(rows) == 6, \
        f"Expected 6 rows after extract, got {len(rows)}"


def test_extract_drops_key_null_rows(base_dir):
    """Rows with empty key columns should be dropped."""
    rows = extract(os.path.join(base_dir, "data", "source.csv"))
    for row in rows:
        for key_col in ['emp_id', 'full_name']:
            assert row.get(key_col, "").strip(), \
                f"Row with empty key column {{key_col}} should have been dropped"


def test_transform_truncation_limit(base_dir):
    """Strings should be truncated at 255 chars, not 50."""
    rows = extract(os.path.join(base_dir, "data", "source.csv"))
    transformed = transform(rows)
    for row in transformed:
        for col in ['emp_id', 'full_name', 'department', 'notes']:
            val = row.get(col, "")
            assert len(val) <= 255, \
                f"Column {col} value exceeds 255 chars: {len(val)}"


def test_transform_preserves_short_strings(base_dir):
    """Strings shorter than limit should not be modified (except stripping)."""
    rows = extract(os.path.join(base_dir, "data", "source.csv"))
    transformed = transform(rows)
    # At least some rows should have non-empty values preserved
    assert any(row.get("full_name", "").strip() for row in transformed)


def test_load_column_order(base_dir, tmp_path):
    """Output columns must be in correct order."""
    rows = extract(os.path.join(base_dir, "data", "source.csv"))
    transformed = transform(rows)
    output_path = str(tmp_path / "test_output.csv")
    load(transformed, output_path)
    with open(output_path) as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == ['emp_id', 'full_name', 'department', 'notes'], \
        f"Column order mismatch: {header} != ['emp_id', 'full_name', 'department', 'notes']"


def test_full_pipeline_matches_expected(base_dir):
    """Full pipeline output must match expected_output.csv."""
    import subprocess
    subprocess.run(
        [sys.executable, "pipeline/run_pipeline.py"],
        cwd=base_dir, check=True, capture_output=True
    )
    with open(os.path.join(base_dir, "data", "output.csv")) as f:
        actual = f.read().strip()
    with open(os.path.join(base_dir, "data", "expected_output.csv")) as f:
        expected = f.read().strip()
    assert actual == expected, "Pipeline output does not match expected"
