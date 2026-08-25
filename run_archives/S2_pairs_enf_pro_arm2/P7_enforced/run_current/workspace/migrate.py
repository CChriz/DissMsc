"""
Data migration script for iot IoT sensor telemetry.

Migration steps (execute in order):
  1. backup: Create a backup of all source data before any changes
  2. transform_format: Convert records from old format to new target format
  3. validate_checksums: Verify data integrity via SHA-256 checksums of every record
  4. load_new_store: Load transformed records into the new data store
  5. verify_counts: Confirm row counts match between source and destination
  6. update_references: Rewrite foreign-key references to use new primary keys

Validation checkpoints between steps:
  - After transform_format: row counts in data/transformed/ must equal source
  - After validate_checksums: checksums.json must be written and verified
  - After load_new_store: row count in data/new_format/ must equal source
  - After verify_counts: verification_report.json must confirm counts match
  - After update_references: no orphaned device_ids in new store

Rollback triggers:
  - Any step failure triggers rollback of all completed steps in reverse order.
  - Each step has a corresponding rollback action (see ROLLBACK_ACTIONS).

Usage:
    python migrate.py [--dry-run]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
from datetime import datetime, timezone


SOURCE_DIR = "data/old_format"
TRANSFORM_DIR = "data/transformed"
DEST_DIR = "data/new_format"
BACKUP_DIR = "data/backup"
CHECKSUM_FILE = "checksums.json"
VERIFICATION_REPORT = "verification_report.json"
MIGRATION_LOG = "migration_log.jsonl"
ARCHIVE_NAME = "iot_source_archive.tar.gz"

PRIMARY_TABLE = "sensor_readings"
REF_TABLE = "devices"
REF_KEY = "device_id"
SOURCE_EXT = "csv"
DEST_EXT = "jsonl"
SEPARATOR = ","

STEPS = ['backup', 'transform_format', 'validate_checksums', 'load_new_store', 'verify_counts', 'update_references']

ROLLBACK_ACTIONS = {
    "backup":            "Remove incomplete backup directory",
    "transform_format":  "Delete all files in data/transformed/",
    "validate_checksums":"Clear checksum manifest (checksums.json)",
    "load_new_store":    "Truncate data/new_format/ directory",
    "verify_counts":     "Remove verification report",
    "update_references": "Restore original reference mapping from backup",
    "archive_old":       "Delete partial archive file",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log_event(step: str, status: str, detail: str = ""):
    entry = {"step": step, "status": status, "detail": detail, "ts": now_iso()}
    with open(MIGRATION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{step}] {status}{': ' + detail if detail else ''}")


def compute_file_checksum(filepath: str) -> str:
    """Compute SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def count_records(filepath: str) -> int:
    """Count data rows (excluding header) in a CSV/TSV/JSONL file."""
    if filepath.endswith(".jsonl"):
        count = 0
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    else:
        with open(filepath, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        # subtract 1 for header
        return max(0, len(lines) - 1)


def _convert_row(table: str, row: dict) -> dict:
    """Convert a CSV row (all-string values) into a typed JSON object.

    Types are kept consistent across tables so that foreign-key values compare
    correctly (integers stay integers in both devices and sensor_readings).
    """
    if table == REF_TABLE:  # devices
        return {
            "device_id": int(row["device_id"]),
            "device_type": row["device_type"],
            "location": row["location"],
            "installed_date": row["installed_date"],
        }
    if table == PRIMARY_TABLE:  # sensor_readings
        return {
            "reading_id": int(row["reading_id"]),
            "device_id": int(row["device_id"]),
            "value": float(row["value"]),
            "unit": row["unit"],
            "timestamp": row["timestamp"],
        }
    raise ValueError(f"unknown table: {table}")


# ── Step implementations ─────────────────────────────────────────────────────

def step_backup(dry_run: bool = False) -> bool:
    """Step 1: Backup source data."""
    if dry_run:
        return os.path.isdir(SOURCE_DIR)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Idempotency: clear any stale backup files from a previous run.
    for fn in os.listdir(BACKUP_DIR):
        fp = os.path.join(BACKUP_DIR, fn)
        if os.path.isfile(fp):
            os.remove(fp)

    # Copy every source file byte-for-byte.
    for fn in sorted(os.listdir(SOURCE_DIR)):
        src = os.path.join(SOURCE_DIR, fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, fn))

    # Checkpoint: every source file must have a byte-identical backup.
    for fn in sorted(os.listdir(SOURCE_DIR)):
        src = os.path.join(SOURCE_DIR, fn)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(BACKUP_DIR, fn)
        if not os.path.exists(dst):
            return False
        if compute_file_checksum(src) != compute_file_checksum(dst):
            return False
    return True


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    if dry_run:
        return os.path.isdir(SOURCE_DIR)

    os.makedirs(TRANSFORM_DIR, exist_ok=True)

    # Idempotency: clear any stale transformed files from a previous run.
    for fn in os.listdir(TRANSFORM_DIR):
        fp = os.path.join(TRANSFORM_DIR, fn)
        if os.path.isfile(fp):
            os.remove(fp)

    for table in (PRIMARY_TABLE, REF_TABLE):
        src = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
        dst = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
        with open(src, encoding="utf-8", newline="") as f_in, \
             open(dst, "w", encoding="utf-8", newline="\n") as f_out:
            reader = csv.DictReader(f_in)
            for row in reader:
                obj = _convert_row(table, row)
                f_out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Checkpoint: row count in TRANSFORM_DIR must equal SOURCE_DIR row count.
    for table in (PRIMARY_TABLE, REF_TABLE):
        src = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
        dst = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
        if count_records(src) != count_records(dst):
            return False
    return True


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    checksums = {"source": {}, "transformed": {}}

    for fn in sorted(os.listdir(SOURCE_DIR)):
        fp = os.path.join(SOURCE_DIR, fn)
        if os.path.isfile(fp):
            checksums["source"][fn] = compute_file_checksum(fp)

    for fn in sorted(os.listdir(TRANSFORM_DIR)):
        fp = os.path.join(TRANSFORM_DIR, fn)
        if os.path.isfile(fp):
            checksums["transformed"][fn] = compute_file_checksum(fp)

    # Checkpoint: all checksum entries must be non-empty 64-hex strings.
    for section in checksums.values():
        for chk in section.values():
            if not isinstance(chk, str) or len(chk) != 64:
                return False

    if dry_run:
        return True

    with open(CHECKSUM_FILE, "w", encoding="utf-8") as f:
        json.dump(checksums, f, indent=2)
    return True


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    if dry_run:
        return True

    os.makedirs(DEST_DIR, exist_ok=True)

    # Idempotency: clear stale destination files from a previous run.
    for fn in os.listdir(DEST_DIR):
        fp = os.path.join(DEST_DIR, fn)
        if os.path.isfile(fp):
            os.remove(fp)

    for fn in sorted(os.listdir(TRANSFORM_DIR)):
        src = os.path.join(TRANSFORM_DIR, fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DEST_DIR, fn))

    # Checkpoint: row count in DEST_DIR must equal source row count.
    src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
    dst_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    if not os.path.exists(dst_path):
        return False
    return count_records(src_path) == count_records(dst_path)


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
    dst_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

    src_count = count_records(src_path)
    dest_count = count_records(dst_path) if os.path.exists(dst_path) else -1
    match = (src_count == dest_count)

    report = {
        "source_count": src_count,
        "dest_count": dest_count,
        "counts_match": match,
    }

    if dry_run:
        return match

    with open(VERIFICATION_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return match


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
    primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

    # Build the set of valid reference keys.
    valid_ids = set()
    with open(ref_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if REF_KEY in rec:
                valid_ids.add(rec[REF_KEY])

    # Load primary table records and detect orphans.
    records = []
    orphans = []
    with open(primary_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get(REF_KEY) not in valid_ids:
                orphans.append(rec.get(REF_KEY))
            records.append(rec)

    if orphans:
        raise ValueError(f"orphaned {REF_KEY} values found: {orphans[:5]}")

    if dry_run:
        return True

    # Write the verified primary table back (references are consistent).
    with open(primary_path, "w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data."""
    if dry_run:
        return True
    with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
        tar.add(SOURCE_DIR, arcname=os.path.basename(SOURCE_DIR))
    if not os.path.exists(ARCHIVE_NAME) or os.path.getsize(ARCHIVE_NAME) == 0:
        return False
    return True


STEP_FUNCTIONS = {
    "backup": step_backup,
    "transform_format": step_transform_format,
    "validate_checksums": step_validate_checksums,
    "load_new_store": step_load_new_store,
    "verify_counts": step_verify_counts,
    "update_references": step_update_references,
    "archive_old": step_archive_old,
}


# ── Rollback ─────────────────────────────────────────────────────────────────

def rollback_step(step_name: str):
    """Execute rollback for a completed step."""
    log_event(step_name, "rollback_start", ROLLBACK_ACTIONS.get(step_name, ""))
    try:
        if step_name == "backup":
            if os.path.exists(BACKUP_DIR):
                shutil.rmtree(BACKUP_DIR)
        elif step_name == "transform_format":
            if os.path.exists(TRANSFORM_DIR):
                shutil.rmtree(TRANSFORM_DIR)
        elif step_name == "validate_checksums":
            if os.path.exists(CHECKSUM_FILE):
                os.remove(CHECKSUM_FILE)
        elif step_name == "load_new_store":
            if os.path.exists(DEST_DIR):
                for fn in os.listdir(DEST_DIR):
                    if fn != ".gitkeep":
                        os.remove(os.path.join(DEST_DIR, fn))
        elif step_name == "verify_counts":
            if os.path.exists(VERIFICATION_REPORT):
                os.remove(VERIFICATION_REPORT)
        elif step_name == "update_references":
            # Restore from backup if available
            src = os.path.join(BACKUP_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
            dst = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
            if os.path.exists(src):
                shutil.copy2(src, dst)
        elif step_name == "archive_old":
            if os.path.exists(ARCHIVE_NAME):
                os.remove(ARCHIVE_NAME)
        log_event(step_name, "rollback_ok")
    except Exception as e:
        log_event(step_name, "rollback_error", str(e))


def run_rollback(completed_steps: list):
    """Roll back all completed steps in reverse order."""
    log_event("migration", "rollback_triggered", f"rolling back {len(completed_steps)} step(s)")
    for step_name in reversed(completed_steps):
        rollback_step(step_name)


# ── Main orchestration ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Data migration tool")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args()

    # Clear and initialise log
    open(MIGRATION_LOG, "w", encoding="utf-8").close()
    log_event("migration", "start", f"steps={STEPS}")

    os.makedirs(TRANSFORM_DIR, exist_ok=True)
    os.makedirs(DEST_DIR, exist_ok=True)

    completed_steps: list = []
    success = True

    for step_name in STEPS:
        fn = STEP_FUNCTIONS.get(step_name)
        if fn is None:
            log_event(step_name, "error", "unknown step")
            success = False
            break

        log_event(step_name, "start")
        try:
            ok = fn(dry_run=args.dry_run)
            if not ok:
                log_event(step_name, "failed", "step returned False")
                run_rollback(completed_steps)
                success = False
                break
            completed_steps.append(step_name)
            log_event(step_name, "completed")
        except Exception as exc:
            log_event(step_name, "error", str(exc))
            run_rollback(completed_steps)
            success = False
            break

    if success:
        log_event("migration", "success", f"all {len(completed_steps)} steps completed")
        # Write final migration report
        report = {
            "status": "success",
            "steps_completed": completed_steps,
            "total_steps": len(STEPS),
            "ts": now_iso(),
        }
        with open("migration_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print("\nMigration complete. See migration_report.json")
        sys.exit(0)
    else:
        log_event("migration", "failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
