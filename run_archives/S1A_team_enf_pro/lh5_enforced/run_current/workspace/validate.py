"""
Validation helpers for the data migration.
Run after migration to verify correctness.
"""
import csv
import hashlib
import json
import os
import sys


SOURCE_DIR = "data/old_format"
TRANSFORM_DIR = "data/transformed"
DEST_DIR = "data/new_format"
BACKUP_DIR = "data/backup"
CHECKSUM_FILE = "checksums.json"
VERIFICATION_REPORT = "verification_report.json"
MIGRATION_LOG = "migration_log.jsonl"
MIGRATION_REPORT = "migration_report.json"

PRIMARY_TABLE = "sensor_readings"
REF_TABLE = "devices"
REF_KEY = "device_id"
SOURCE_EXT = "csv"
EXPECTED_PRIMARY_ROWS = 60


def count_records(filepath):
    """Count data rows (excluding header) in a CSV/TSV/JSONL file."""
    if filepath.endswith(".jsonl"):
        count = 0
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    else:
        with open(filepath) as f:
            lines = [l for l in f if l.strip()]
        return max(0, len(lines) - 1)


def check_migration_report():
    """Check migration_report.json exists and status == success."""
    if not os.path.exists(MIGRATION_REPORT):
        print("FAIL: migration_report.json missing")
        return False
    with open(MIGRATION_REPORT) as f:
        report = json.load(f)
    if report.get("status") != "success":
        print(f"FAIL: migration status={report.get('status')}")
        return False
    print("PASS: migration_report.json status=success")
    return True


def check_all_steps_completed():
    """Verify all expected steps appear as completed in the log."""
    if not os.path.exists(MIGRATION_LOG):
        print("FAIL: migration_log.jsonl missing")
        return False
    completed = set()
    with open(MIGRATION_LOG) as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("status") == "completed":
                completed.add(entry.get("step"))
    if not os.path.exists(MIGRATION_REPORT):
        print("FAIL: migration_report.json missing")
        return False
    with open(MIGRATION_REPORT) as f:
        report = json.load(f)
    expected_steps = set(report.get("steps_completed", []))
    if not expected_steps:
        print("FAIL: no steps_completed in migration_report")
        return False
    missing = expected_steps - completed
    if missing:
        print(f"FAIL: steps not logged as completed: {missing}")
        return False
    print(f"PASS: all {len(expected_steps)} steps logged as completed")
    return True


def check_row_counts():
    """Verify row counts match between source and destination."""
    src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
    if not os.path.exists(src_path):
        print(f"FAIL: source file missing: {src_path}")
        return False

    src_count = count_records(src_path)
    if src_count != EXPECTED_PRIMARY_ROWS:
        print(f"FAIL: source row count={src_count}, expected={EXPECTED_PRIMARY_ROWS}")
        return False

    # Check destination
    dest_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.jsonl")
    if not os.path.exists(dest_path):
        print(f"FAIL: destination file missing: {dest_path}")
        return False

    dest_count = count_records(dest_path)
    if dest_count != src_count:
        print(f"FAIL: row count mismatch src={src_count} dest={dest_count}")
        return False

    print(f"PASS: row counts match ({src_count} records)")
    return True


def check_checksums():
    """Verify checksums.json exists and has entries for both source and transformed."""
    if not os.path.exists(CHECKSUM_FILE):
        print("FAIL: checksums.json missing")
        return False
    with open(CHECKSUM_FILE) as f:
        checksums = json.load(f)
    if "source" not in checksums or "transformed" not in checksums:
        print("FAIL: checksums.json missing 'source' or 'transformed' keys")
        return False
    if not checksums["source"] or not checksums["transformed"]:
        print("FAIL: checksums.json has empty checksum sections")
        return False
    for section, entries in checksums.items():
        for fname, chk in entries.items():
            if not isinstance(chk, str) or len(chk) != 64:
                print(f"FAIL: invalid checksum for {section}/{fname}: {chk!r}")
                return False
    print(f"PASS: checksums.json valid ({len(checksums['source'])} source, "
          f"{len(checksums['transformed'])} transformed entries)")
    return True


def check_no_orphaned_references():
    """Verify no orphaned foreign keys in destination primary table."""
    ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.jsonl")
    primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.jsonl")

    if not os.path.exists(ref_path):
        print(f"FAIL: ref table missing in dest: {ref_path}")
        return False
    if not os.path.exists(primary_path):
        print(f"FAIL: primary table missing in dest: {primary_path}")
        return False

    valid_ids = set()
    with open(ref_path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if REF_KEY in rec:
                valid_ids.add(str(rec[REF_KEY]))

    orphans = []
    with open(primary_path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            val = str(rec.get(REF_KEY, ""))
            if val and val not in valid_ids:
                orphans.append(val)

    if orphans:
        print(f"FAIL: {len(orphans)} orphaned {REF_KEY} values found: {orphans[:5]}")
        return False

    print(f"PASS: no orphaned {REF_KEY} references ({len(valid_ids)} valid ids)")
    return True


def check_verification_report():
    """Verify verification_report.json confirms counts match."""
    if not os.path.exists(VERIFICATION_REPORT):
        print("FAIL: verification_report.json missing")
        return False
    with open(VERIFICATION_REPORT) as f:
        report = json.load(f)
    if not report.get("counts_match", False):
        print(f"FAIL: counts_match=False in verification_report: {report}")
        return False
    src_c = report.get("source_count", -1)
    dst_c = report.get("dest_count", -1)
    if src_c != dst_c:
        print(f"FAIL: source_count={src_c} != dest_count={dst_c}")
        return False
    print(f"PASS: verification_report counts_match=True ({src_c} records)")
    return True


def check_backup_exists():
    """Verify backup directory was created."""
    if not os.path.isdir(BACKUP_DIR):
        print(f"FAIL: backup directory missing: {BACKUP_DIR}")
        return False
    files = [f for f in os.listdir(BACKUP_DIR) if not f.startswith(".")]
    if not files:
        print("FAIL: backup directory is empty")
        return False
    print(f"PASS: backup directory exists with {len(files)} file(s)")
    return True


def check_steps_in_order():
    """Verify migration log shows steps executed in correct order."""
    if not os.path.exists(MIGRATION_LOG):
        print("FAIL: migration_log.jsonl missing")
        return False
    step_order = []
    seen = set()
    with open(MIGRATION_LOG) as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("status") == "start" and entry.get("step") not in ("migration",):
                s = entry["step"]
                if s not in seen:
                    step_order.append(s)
                    seen.add(s)

    if not os.path.exists(MIGRATION_REPORT):
        print("FAIL: migration_report.json missing")
        return False
    with open(MIGRATION_REPORT) as f:
        report = json.load(f)
    expected_order = report.get("steps_completed", [])
    if step_order != expected_order:
        print(f"FAIL: steps executed out of order. Got {step_order}, expected {expected_order}")
        return False
    print(f"PASS: steps executed in correct order: {step_order}")
    return True


CHECKS = [
    ("migration_report_exists", check_migration_report),
    ("all_steps_completed", check_all_steps_completed),
    ("steps_in_order", check_steps_in_order),
    ("backup_exists", check_backup_exists),
    ("row_counts_match", check_row_counts),
    ("checksums_valid", check_checksums),
    ("verification_report_valid", check_verification_report),
    ("no_orphaned_references", check_no_orphaned_references),
]


def main():
    passed = 0
    failed = 0
    for name, fn in CHECKS:
        try:
            ok = fn()
        except Exception as exc:
            print(f"FAIL: {name} raised exception: {exc}")
            ok = False
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{passed}/{passed + failed} checks passed")
    if failed == 0:
        print("ALL VALIDATION CHECKS PASSED")
        sys.exit(0)
    else:
        print("VALIDATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
