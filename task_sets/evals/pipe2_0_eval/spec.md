# PIPE2: Data Pipeline Fix

## Goal

An ETL (Extract-Transform-Load) data pipeline has 3 bugs that compound across stages.
Each stage feeds into the next, so fixing one bug changes the input to the next stage.
All 3 bugs must be fixed for the pipeline to produce correct output.

## Architecture

- **Extractor** (`pipeline/extract.py`): Reads CSV source data and filters out invalid rows
- **Transformer** (`pipeline/transform.py`): Normalizes string fields and applies truncation
- **Loader** (`pipeline/load.py`): Maps transformed columns to the output schema and writes results
- **Pipeline Runner** (`pipeline/run_pipeline.py`): Orchestrates all 3 stages
- **Source Data** (`data/source.csv`): Input CSV file
- **Expected Output** (`data/expected_output.csv`): What the pipeline should produce

## Requirements

### Bug 1: Extractor drops too many rows

The extractor drops rows where ANY column is null. The spec says it should only drop rows
where KEY columns (the first 2 columns in the schema) are null. Rows with null values in
non-key columns should be kept with the null preserved.

Fix `extract.py` to only drop rows where key columns are null.

### Bug 2: Transformer truncates strings too aggressively

The transformer truncates all string fields to 50 characters. The spec in `PIPELINE_SPEC.md`
says the truncation limit is 255 characters. This causes data loss on long description fields.

Fix `transform.py` to use the correct truncation limit from the spec.

### Bug 3: Loader maps columns in wrong order

The loader swaps the second and third output columns when mapping from the transformer's
output to the final schema. This means column B data appears in column C's position and
vice versa.

Fix `load.py` to map columns in the correct order matching `PIPELINE_SPEC.md`.

## Supporting Documents

- `PIPELINE_SPEC.md` — Pipeline specification with column schemas, truncation limits, null handling rules
- `data/source.csv` — Input data
- `data/expected_output.csv` — Expected correct output
- `tests/test_pipeline.py` — End-to-end and per-stage tests

## Cascading Nature

These bugs compound: fixing the extractor changes which rows reach the transformer.
Fixing the transformer changes string lengths reaching the loader. Test the full
pipeline end-to-end after all fixes.

## Verification

Run: `python pipeline/run_pipeline.py && python -m pytest tests/test_pipeline.py`
