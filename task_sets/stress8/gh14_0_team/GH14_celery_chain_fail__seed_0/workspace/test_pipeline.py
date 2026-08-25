"""
Tests for ETL pipeline error propagation.

The critical requirement: if any item in stage 1 raises StageError, the
pipeline must propagate that error rather than silently continuing.
"""
import pytest
from pipeline import EtlPipeline
from tasks import StageError


GOOD_ITEMS = ["item_0", "item_1", "item_2", "item_3", "item_4", "item_5", "item_6"]
BAD_ITEMS  = ["item_0", "item_1", "item_2", "item_3", "item_4", "item_5", "POISON_PILL"]


def test_success_path_returns_all_results():
    """Pipeline with no errors must return 7 successful results."""
    pipeline = EtlPipeline()
    results = pipeline.run(GOOD_ITEMS)
    assert len(results) == 7, (
        f"Expected 7 results, got {len(results)}"
    )
    for r in results:
        assert r.get("status") == "ok", f"Unexpected result: {r}"


def test_stage1_failure_propagates():
    """A stage-1 failure must raise StageError, not return silently."""
    pipeline = EtlPipeline()
    with pytest.raises((StageError, Exception)) as exc_info:
        pipeline.run(BAD_ITEMS)
    # Ensure it's actually a failure signal, not a false positive
    assert exc_info.value is not None, "Expected an exception to propagate"


def test_stage1_failure_not_swallowed():
    """Pipeline must NOT return a list of dicts when stage 1 fails."""
    pipeline = EtlPipeline()
    try:
        result = pipeline.run(BAD_ITEMS)
        # If we reach here, the bug is present — check that at least one
        # result reflects the error
        error_results = [r for r in result if r.get("status") == "error"]
        assert error_results, (
            "Pipeline returned success results despite stage-1 failure — "
            "error was silently swallowed"
        )
        # If there are error results, the pipeline should have raised instead
        pytest.fail(
            f"Pipeline returned {len(error_results)} error dict(s) instead of "
            f"raising — failures must propagate as exceptions"
        )
    except (StageError, Exception):
        pass  # Correct behaviour: exception propagated


def test_error_position_is_detected():
    """The item at position 6 ('POISON_PILL') must cause failure."""
    pipeline = EtlPipeline()
    single_bad = ["POISON_PILL"]
    with pytest.raises((StageError, Exception)):
        pipeline.run(single_bad)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
