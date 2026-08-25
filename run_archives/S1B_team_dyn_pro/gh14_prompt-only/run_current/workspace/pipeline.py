"""
ETL pipeline — chained group executor.

Simulates Celery's chain-of-groups pattern WITHOUT requiring a running broker.
Each "group" is a list of tasks applied to each item; the groups are chained
so the output of stage N becomes the input to stage N+1.

BUG: When a stage-1 task raises an exception, the executor catches it and
stores a sentinel error dict, but the continuation loop does NOT check for
error dicts before passing results to the next stage.  Stage-2 and stage-3
then happily process the error sentinel, and the final result appears
successful even though stage-1 failed.

This mirrors Celery's behaviour where intermediate chord failures are not
propagated to the final chord callback.
"""
from tasks import extract_item, transform_item, load_item, StageError


def _run_group(fn, items):
    """Apply fn to each item in the group, catching exceptions.

    BUG: exceptions are swallowed into an error dict instead of being
    propagated.  The caller does not inspect these error dicts.
    """
    results = []
    for item in items:
        try:
            results.append(fn(item))
        except Exception as exc:
            # BUG: silently convert exception to an error dict and continue
            results.append({"status": "error", "reason": str(exc), "item": item})
    return results


def _check_results(results, stage_name):
    """检查结果列表中是否包含错误字典，有则抛出 StageError。"""
    errors = [r for r in results if r.get("status") == "error"]
    if errors:
        reasons = "; ".join(r.get("reason", "unknown") for r in errors)
        raise StageError(
            f"Stage '{stage_name}' had {len(errors)} failure(s): {reasons}"
        )


def _chain_groups(items):
    """Execute the three-stage chain.

    BUG: each _run_group call passes results unconditionally to the next
    stage.  Error dicts from stage 1 flow into stage 2 and stage 3 without
    raising, so the overall result looks like success.
    """
    stage1_results = _run_group(extract_item, items)
    _check_results(stage1_results, "extract")

    stage2_results = _run_group(transform_item, stage1_results)
    _check_results(stage2_results, "transform")

    stage3_results = _run_group(load_item, stage2_results)
    _check_results(stage3_results, "load")

    return stage3_results


class EtlPipeline:
    """Run the ETL pipeline chain for a list of records."""

    def run(self, items: list[str]) -> list[dict]:
        """Execute the pipeline and return final results.

        Should raise StageError if any item fails in any stage.
        Currently swallows failures silently (the bug).
        """
        return _chain_groups(items)
