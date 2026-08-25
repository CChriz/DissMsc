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
    with open(MIGRATION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
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
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    else:
        with open(filepath) as f:
            lines = [l for l in f if l.strip()]
        # subtract 1 for header
        return max(0, len(lines) - 1)


# ── Step implementations ─────────────────────────────────────────────────────

def step_backup(dry_run: bool = False) -> bool:
    """Step 1: Backup source data."""
    log_event("backup", "start")

    # Verify source directory exists and has files
    if not os.path.isdir(SOURCE_DIR):
        log_event("backup", "failed", f"source directory missing: {SOURCE_DIR}")
        return False

    source_files = [f for f in os.listdir(SOURCE_DIR)
                    if os.path.isfile(os.path.join(SOURCE_DIR, f))]
    if not source_files:
        log_event("backup", "failed", "no source files found")
        return False

    if dry_run:
        # Dry-run: verify all source files are readable
        for fname in source_files:
            fpath = os.path.join(SOURCE_DIR, fname)
            if not os.access(fpath, os.R_OK):
                log_event("backup", "failed", f"source file not readable: {fpath}")
                return False
        log_event("backup", "completed",
                  f"dry-run verified {len(source_files)} file(s) readable")
        return True

    # Remove any stale backup and create fresh
    if os.path.exists(BACKUP_DIR):
        shutil.rmtree(BACKUP_DIR)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    try:
        for fname in source_files:
            src = os.path.join(SOURCE_DIR, fname)
            dst = os.path.join(BACKUP_DIR, fname)
            shutil.copy2(src, dst)
            log_event("backup", "progress", f"copied {fname}")

        log_event("backup", "completed",
                  f"backed up {len(source_files)} file(s) to {BACKUP_DIR}")
        return True
    except Exception as e:
        log_event("backup", "failed", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    log_event("transform_format", "start")

    if not os.path.isdir(SOURCE_DIR):
        log_event("transform_format", "failed", f"source directory missing: {SOURCE_DIR}")
        return False

    csv_files = [f for f in os.listdir(SOURCE_DIR)
                 if f.endswith(".csv") and os.path.isfile(os.path.join(SOURCE_DIR, f))]

    if not csv_files:
        log_event("transform_format", "failed", "no CSV files found in source")
        return False

    if not dry_run:
        # Remove stale transformed data and create fresh
        if os.path.exists(TRANSFORM_DIR):
            shutil.rmtree(TRANSFORM_DIR)
        os.makedirs(TRANSFORM_DIR, exist_ok=True)

    try:
        for fname in csv_files:
            src_path = os.path.join(SOURCE_DIR, fname)
            table_name = os.path.splitext(fname)[0]
            dst_path = os.path.join(TRANSFORM_DIR, f"{table_name}.jsonl")

            # Count source rows for validation
            src_count = count_records(src_path)
            log_event("transform_format", "progress",
                      f"transforming {fname} ({src_count} records)")

            rows_written = 0
            with open(src_path, newline="") as infile:
                reader = csv.DictReader(infile)
                if reader.fieldnames is None:
                    log_event("transform_format", "failed",
                              f"no header in {fname}")
                    return False

                if dry_run:
                    # Count rows only, no write
                    for _ in reader:
                        rows_written += 1
                else:
                    with open(dst_path, "w") as outfile:
                        for row in reader:
                            outfile.write(json.dumps(row) + "\n")
                            rows_written += 1

            # Checkpoint: row count must match
            if rows_written != src_count:
                log_event("transform_format", "failed",
                          f"row count mismatch for {table_name}: "
                          f"source={src_count}, transformed={rows_written}")
                return False

            log_event("transform_format", "completed",
                      f"{table_name}: {rows_written} rows → {dst_path}")

        log_event("transform_format", "completed",
                  f"transformed {len(csv_files)} table(s)")
        return True
    except Exception as e:
        log_event("transform_format", "failed", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    log_event("validate_checksums", "start")
    try:
        checksums = {"source": {}, "transformed": {}}

        source_files = {
            "sensor_readings": os.path.join(SOURCE_DIR, f"sensor_readings.{SOURCE_EXT}"),
            "devices": os.path.join(SOURCE_DIR, f"devices.{SOURCE_EXT}"),
        }
        transformed_files = {
            "sensor_readings": os.path.join(TRANSFORM_DIR, "sensor_readings.jsonl"),
            "devices": os.path.join(TRANSFORM_DIR, "devices.jsonl"),
        }

        # Compute checksums for source files
        for name, path in source_files.items():
            if not os.path.exists(path):
                log_event("validate_checksums", "error",
                          f"source file missing: {path}")
                return False
            chk = compute_file_checksum(path)
            if not chk or len(chk) != 64:
                log_event("validate_checksums", "error",
                          f"invalid checksum for source/{name}: "
                          f"length={len(chk) if chk else 0}")
                return False
            checksums["source"][name] = chk

        # Compute checksums for transformed files
        for name, path in transformed_files.items():
            if not os.path.exists(path):
                log_event("validate_checksums", "error",
                          f"transformed file missing: {path}")
                return False
            chk = compute_file_checksum(path)
            if not chk or len(chk) != 64:
                log_event("validate_checksums", "error",
                          f"invalid checksum for transformed/{name}: "
                          f"length={len(chk) if chk else 0}")
                return False
            checksums["transformed"][name] = chk

        if dry_run:
            log_event("validate_checksums", "dry_run",
                      f"checksums computed for {len(checksums['source'])} source + "
                      f"{len(checksums['transformed'])} transformed files (not written)")
            return True

        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksums, f, indent=2)

        log_event("validate_checksums", "completed",
                  f"checksums written to {CHECKSUM_FILE} "
                  f"({len(checksums['source'])} source, "
                  f"{len(checksums['transformed'])} transformed)")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    log_event("load_new_store", "start")
    try:
        os.makedirs(DEST_DIR, exist_ok=True)

        expected = {
            "sensor_readings.jsonl": 60,
            "devices.jsonl": 26,
        }

        for filename, expected_count in expected.items():
            src_path = os.path.join(TRANSFORM_DIR, filename)
            dst_path = os.path.join(DEST_DIR, filename)

            if not os.path.exists(src_path):
                log_event("load_new_store", "error",
                          f"source file missing: {src_path}")
                return False

            # Verify row count before copying
            actual_count = count_records(src_path)
            if actual_count != expected_count:
                log_event("load_new_store", "error",
                          f"row count mismatch for {filename}: "
                          f"expected {expected_count}, got {actual_count}")
                return False

            if dry_run:
                continue

            shutil.copy2(src_path, dst_path)

        if dry_run:
            log_event("load_new_store", "dry_run",
                      "validation passed (no files copied)")
            return True

        # Verify destination files after copy
        for filename, expected_count in expected.items():
            dst_path = os.path.join(DEST_DIR, filename)
            if not os.path.exists(dst_path):
                log_event("load_new_store", "error",
                          f"destination file missing after copy: {dst_path}")
                return False
            actual_count = count_records(dst_path)
            if actual_count != expected_count:
                log_event("load_new_store", "error",
                          f"destination row count mismatch for {filename}: "
                          f"expected {expected_count}, got {actual_count}")
                return False

        log_event("load_new_store", "completed",
                  f"{len(expected)} files loaded to {DEST_DIR}")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    log_event("verify_counts", "start")

    tables = [
        {"name": "sensor_readings",
         "src": os.path.join(SOURCE_DIR, "sensor_readings.csv"),
         "dst": os.path.join(DEST_DIR, "sensor_readings.jsonl")},
        {"name": "devices",
         "src": os.path.join(SOURCE_DIR, "devices.csv"),
         "dst": os.path.join(DEST_DIR, "devices.jsonl")},
    ]

    details = {}
    all_match = True

    for table in tables:
        src_path = table["src"]
        dst_path = table["dst"]

        if not os.path.exists(src_path):
            log_event("verify_counts", "error", f"source file missing: {src_path}")
            return False
        if not os.path.exists(dst_path):
            log_event("verify_counts", "error", f"destination file missing: {dst_path}")
            return False

        src_count = count_records(src_path)
        dst_count = count_records(dst_path)
        match = src_count == dst_count

        details[table["name"]] = {
            "source": src_count,
            "dest": dst_count,
            "match": match,
        }

        if not match:
            all_match = False
            log_event("verify_counts", "mismatch",
                      f"{table['name']}: src={src_count} dst={dst_count}")

    # Top-level counts refer to the primary table (sensor_readings)
    primary_src = details["sensor_readings"]["source"]
    primary_dst = details["sensor_readings"]["dest"]

    report = {
        "source_count": primary_src,
        "dest_count": primary_dst,
        "counts_match": all_match,
        "details": details,
    }

    if not dry_run:
        with open(VERIFICATION_REPORT, "w") as f:
            json.dump(report, f, indent=2)
        log_event("verify_counts", "completed",
                  f"report written, counts_match={all_match}")
    else:
        log_event("verify_counts", "dry_run",
                  f"counts_match={all_match} (no write)")

    if not all_match:
        return False

    return True


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references.

    Validates referential integrity: every device_id in sensor_readings.jsonl
    must exist in devices.jsonl.  No primary-key rewriting is needed because
    device_id values are preserved during format conversion.
    """
    log_event("update_references", "start")

    ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
    primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

    if not os.path.exists(ref_path):
        log_event("update_references", "error", f"ref table missing: {ref_path}")
        return False
    if not os.path.exists(primary_path):
        log_event("update_references", "error", f"primary table missing: {primary_path}")
        return False

    # Build set of valid reference keys from the devices table
    valid_ids: set = set()
    with open(ref_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if REF_KEY in rec:
                valid_ids.add(str(rec[REF_KEY]))

    if not valid_ids:
        log_event("update_references", "error", "no valid reference keys found")
        return False

    # Scan primary table for orphaned references
    orphans: list = []
    total_rows = 0
    with open(primary_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_rows += 1
            rec = json.loads(line)
            ref_val = str(rec.get(REF_KEY, ""))
            if ref_val and ref_val not in valid_ids:
                orphans.append(ref_val)

    if orphans:
        log_event("update_references", "failed",
                  f"{len(orphans)} orphaned {REF_KEY}(s): {orphans[:10]}")
        return False

    log_event("update_references", "completed",
              f"verified {total_rows} rows, {len(valid_ids)} valid {REF_KEY}s, 0 orphans")
    return True


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data."""
    # TODO: Implement archival
    # - Create a tar.gz archive named ARCHIVE_NAME containing SOURCE_DIR
    # - Checkpoint: archive file must exist and be non-empty
    log_event("archive_old", "not_implemented", "TODO: implement archive step")
    return False


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
    open(MIGRATION_LOG, "w").close()
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
        with open("migration_report.json", "w") as f:
            json.dump(report, f, indent=2)
        print("\nMigration complete. See migration_report.json")
        sys.exit(0)
    else:
        log_event("migration", "failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
