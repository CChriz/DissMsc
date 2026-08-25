# Employees Data Pipeline Specification

## Schema

Columns: `emp_id`, `full_name`, `department`, `notes`

Key columns: `emp_id`, `full_name`

## Stage 1: Extract

- Read `data/source.csv`
- Drop rows where ANY **key column** (`emp_id`, `full_name`) is empty or null
- Preserve rows where non-key columns are empty (keep the empty value)

## Stage 2: Transform

- Normalize all string fields (strip leading/trailing whitespace)
- Truncate string fields longer than **255** characters

## Stage 3: Load

- Map columns to output schema in order: `emp_id`, `full_name`, `department`, `notes`
- Write to `data/output.csv`

## Output

The pipeline writes `data/output.csv` with the same column headers.
Expected output row count (excluding header): rows with non-null key columns.
