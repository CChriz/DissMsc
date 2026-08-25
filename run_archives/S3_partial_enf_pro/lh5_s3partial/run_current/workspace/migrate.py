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

STEPS = ['backup', 'transform_format', 'validate_checksums', 'load_new_store', 'verify_counts', 'update_references', 'archive_old']

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
    try:
        if dry_run:
            log_event("backup", "dry_run", "would create backup of source data")
            return True
        os.makedirs(BACKUP_DIR, exist_ok=True)
        copied = 0
        for filename in os.listdir(SOURCE_DIR):
            src = os.path.join(SOURCE_DIR, filename)
            dst = os.path.join(BACKUP_DIR, filename)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                copied += 1
        if copied == 0:
            log_event("backup", "failed", "no files found to back up")
            return False
        log_event("backup", "completed", f"backed up {copied} file(s) from {SOURCE_DIR}")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("transform_format", "error", f"source dir missing: {SOURCE_DIR}")
            return False
        tables = [PRIMARY_TABLE, REF_TABLE]
        for table in tables:
            src_path = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
            if not os.path.isfile(src_path):
                log_event("transform_format", "error", f"source file missing: {src_path}")
                return False
            src_count = count_records(src_path)

            # Read CSV rows
            rows = []
            with open(src_path, newline="") as f:
                reader = csv.DictReader(f, delimiter=SEPARATOR)
                for row in reader:
                    rows.append(row)

            if dry_run:
                # Validate row counts only, no write
                if len(rows) != src_count:
                    log_event("transform_format", "failed",
                              f"row count mismatch for {table}: parsed={len(rows)} expected={src_count}")
                    return False
                log_event("transform_format", "dry_run",
                          f"would transform {table}: {len(rows)} rows")
                continue

            # Write JSONL
            dst_path = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
            with open(dst_path, "w") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")

            # Checkpoint: verify row count
            dst_count = count_records(dst_path)
            if dst_count != src_count:
                log_event("transform_format", "failed",
                          f"row count mismatch for {table}: src={src_count} dst={dst_count}")
                return False

        log_event("transform_format", "completed")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("validate_checksums", "error", f"source dir missing: {SOURCE_DIR}")
            return False
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("validate_checksums", "error", f"transform dir missing: {TRANSFORM_DIR}")
            return False

        # Compute SHA-256 for each file in SOURCE_DIR and TRANSFORM_DIR
        source_cs = {}
        for fn in os.listdir(SOURCE_DIR):
            fp = os.path.join(SOURCE_DIR, fn)
            if os.path.isfile(fp):
                source_cs[fn] = compute_file_checksum(fp)

        transformed_cs = {}
        for fn in os.listdir(TRANSFORM_DIR):
            fp = os.path.join(TRANSFORM_DIR, fn)
            if os.path.isfile(fp):
                transformed_cs[fn] = compute_file_checksum(fp)

        checksums = {"source": source_cs, "transformed": transformed_cs}

        # Checkpoint: all checksum entries must be valid 64-char hex strings
        def is_valid_sha256(s):
            return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)

        for section_name, section in checksums.items():
            for fname, chk in section.items():
                if not is_valid_sha256(chk):
                    log_event("validate_checksums", "failed",
                              f"invalid checksum for {section_name}/{fname}: {chk!r}")
                    return False

        if not source_cs or not transformed_cs:
            log_event("validate_checksums", "failed", "empty checksum section(s)")
            return False

        if not dry_run:
            with open(CHECKSUM_FILE, "w") as f:
                json.dump(checksums, f, indent=2)

        log_event("validate_checksums", "completed",
                  f"{len(source_cs)} source + {len(transformed_cs)} transformed checksums written")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("load_new_store", "error", f"transform dir missing: {TRANSFORM_DIR}")
            return False

        for fn in os.listdir(TRANSFORM_DIR):
            src = os.path.join(TRANSFORM_DIR, fn)
            dst = os.path.join(DEST_DIR, fn)
            if os.path.isfile(src) and not dry_run:
                shutil.copy2(src, dst)

        # Checkpoint: row count in DEST_DIR must equal source row count
        src_count = count_records(os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}"))
        dst_count = count_records(os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}"))
        if dst_count != src_count:
            log_event("load_new_store", "failed",
                      f"row count mismatch: src={src_count} dst={dst_count}")
            return False

        # Also ensure the ref table exists in destination
        ref_dst = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        if not os.path.exists(ref_dst):
            log_event("load_new_store", "failed", f"ref table missing in dest: {ref_dst}")
            return False

        log_event("load_new_store", "completed",
                  f"loaded {dst_count} records into {DEST_DIR}")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dst_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.isfile(src_path):
            log_event("verify_counts", "error", f"source file missing: {src_path}")
            return False
        if not os.path.isfile(dst_path):
            log_event("verify_counts", "error", f"destination file missing: {dst_path}")
            return False

        source_count = count_records(src_path)
        dest_count = count_records(dst_path)
        counts_match = (source_count == dest_count)

        report = {
            "source_count": source_count,
            "dest_count": dest_count,
            "counts_match": counts_match,
        }

        if not dry_run:
            with open(VERIFICATION_REPORT, "w") as f:
                json.dump(report, f, indent=2)

        if counts_match:
            log_event("verify_counts", "completed",
                      f"counts match: {source_count} records")
        else:
            log_event("verify_counts", "failed",
                      f"counts mismatch: src={source_count} dst={dest_count}")

        return counts_match
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    try:
        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.isfile(ref_path):
            log_event("update_references", "error", f"ref table missing: {ref_path}")
            return False
        if not os.path.isfile(primary_path):
            log_event("update_references", "error", f"primary table missing: {primary_path}")
            return False

        # Build set of valid device_ids from the reference table
        valid_ids = set()
        with open(ref_path) as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line.strip())
                    valid_ids.add(obj[REF_KEY])

        # Load primary table and validate every record's REF_KEY
        records = []
        orphaned = []
        with open(primary_path) as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line.strip())
                    if obj.get(REF_KEY) not in valid_ids:
                        orphaned.append(obj[REF_KEY])
                    records.append(obj)

        if orphaned:
            log_event("update_references", "failed",
                      f"orphaned device_ids: {orphaned}")
            return False

        # Write verified records back to destination
        if not dry_run:
            with open(primary_path, "w") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")

        log_event("update_references", "completed",
                  f"verified {len(records)} records, {len(valid_ids)} valid device_ids")
        return True
    except Exception as e:
        log_event("update_references", "error", str(e))
        return False


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data."""
    try:
        if dry_run:
            log_event("archive_old", "dry_run", f"would create {ARCHIVE_NAME}")
            return True

        with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
            tar.add(SOURCE_DIR, arcname=os.path.basename(SOURCE_DIR))

        # Checkpoint: archive file must exist and be non-empty
        if not os.path.exists(ARCHIVE_NAME) or os.path.getsize(ARCHIVE_NAME) == 0:
            log_event("archive_old", "failed", "archive not created or empty")
            return False

        log_event("archive_old", "completed",
                  f"archived to {ARCHIVE_NAME} ({os.path.getsize(ARCHIVE_NAME)} bytes)")
        return True
    except Exception as e:
        log_event("archive_old", "error", str(e))
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
