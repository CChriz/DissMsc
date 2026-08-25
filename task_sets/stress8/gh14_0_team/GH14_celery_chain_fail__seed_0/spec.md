# GH14: Chain-of-Groups Failure Propagation — Full Specification (Planner Only)

## Overview

The workspace implements a ETL pipeline (`EtlPipeline`) that chains three
stages: `extract` → `transform` → `load`. There is **one bug** in `pipeline.py`
where failures in stage 1 are silently swallowed.

## Program Structure

- `pipeline.py` — chain executor with the bug (`_run_group`, `_chain_groups`)
- `tasks.py` — individual stage functions (correct, do not modify)
- `test_pipeline.py` — pytest tests that detect the bug

## The Bug

**Location:** `_run_group()` and `_chain_groups()` in `pipeline.py`.

**Root cause:** This mirrors Celery's chain-of-groups behaviour.  When Celery
converts a `group | chain` into chords internally, failures in an intermediate
chord's tasks do not automatically propagate to subsequent chords' callbacks.
The `on_error` / `link_error` mechanism must be wired explicitly.

In this standalone reproduction, `_run_group()` catches exceptions and stores
error sentinel dicts instead of re-raising.  `_chain_groups()` passes the
results unconditionally to the next stage — so a `'POISON_PILL'` item in
stage 1 produces an error dict that flows silently through stage 2 and 3.

**Buggy code:**
```python
def _chain_groups(items):
    stage1_results = _run_group(extract_item, items)
    # BUG: no check — error dicts pass to stage 2
    stage2_results = _run_group(transform_item, stage1_results)
    stage3_results = _run_group(load_item, stage2_results)
    return stage3_results
```

**Fix:** After each `_run_group` call, inspect results for error dicts and
raise if any are found:
```python
def _check_results(results, stage_name):
    errors = [r for r in results if r.get("status") == "error"]
    if errors:
        reasons = "; ".join(r.get("reason", "unknown") for r in errors)
        raise StageError(f"Stage '{stage_name}' had {len(errors)} failure(s): {reasons}")

def _chain_groups(items):
    stage1_results = _run_group(extract_item, items)
    _check_results(stage1_results, "extract")
    stage2_results = _run_group(transform_item, stage1_results)
    _check_results(stage2_results, "transform")
    stage3_results = _run_group(load_item, stage2_results)
    _check_results(stage3_results, "load")
    return stage3_results
```

## Acceptance Criteria

1. `pipeline.run(["POISON_PILL"])` raises `StageError` (or subclass)
2. `pipeline.run(["POISON_PILL", "item_1"])` raises `StageError`
3. `pipeline.run(["item_0", "item_1", ...])` (no error item) returns all-ok results
4. All tests pass: `pytest test_pipeline.py -v`

## Important Notes

- Fix is in `pipeline.py` only — `_run_group` and/or `_chain_groups`
- Do NOT modify `tasks.py` or `test_pipeline.py`
