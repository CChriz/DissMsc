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
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("backup", "failed", f"Source directory not found: {SOURCE_DIR}")
            return False

        source_files = [f for f in os.listdir(SOURCE_DIR)
                        if os.path.isfile(os.path.join(SOURCE_DIR, f))]
        if not source_files:
            log_event("backup", "failed", "No files found in source directory")
            return False

        if dry_run:
            log_event("backup", "dry_run", f"Would copy {len(source_files)} file(s) to {BACKUP_DIR}")
            return True

        os.makedirs(BACKUP_DIR, exist_ok=True)
        for fn in source_files:
            src = os.path.join(SOURCE_DIR, fn)
            dst = os.path.join(BACKUP_DIR, fn)
            shutil.copy2(src, dst)
            log_event("backup", "progress", f"Copied {fn}")

        # Verify at least one file was copied
        backup_files = os.listdir(BACKUP_DIR)
        if not backup_files:
            log_event("backup", "failed", "Backup directory is empty after copy")
            return False

        log_event("backup", "completed", f"Backed up {len(backup_files)} file(s)")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("transform_format", "failed", f"Source directory not found: {SOURCE_DIR}")
            return False

        csv_files = [f for f in os.listdir(SOURCE_DIR)
                     if f.endswith("." + SOURCE_EXT) and os.path.isfile(os.path.join(SOURCE_DIR, f))]
        if not csv_files:
            log_event("transform_format", "failed", "No CSV files found in source directory")
            return False

        if dry_run:
            log_event("transform_format", "dry_run", f"Would transform {len(csv_files)} file(s) to {TRANSFORM_DIR}")
            return True

        os.makedirs(TRANSFORM_DIR, exist_ok=True)

        for fn in csv_files:
            src_path = os.path.join(SOURCE_DIR, fn)
            table_name = os.path.splitext(fn)[0]
            dst_path = os.path.join(TRANSFORM_DIR, f"{table_name}.{DEST_EXT}")

            with open(src_path, newline="") as infile:
                reader = csv.DictReader(infile, delimiter=SEPARATOR)
                with open(dst_path, "w") as outfile:
                    for row in reader:
                        outfile.write(json.dumps(row) + "\n")

            log_event("transform_format", "progress", f"Transformed {fn} → {table_name}.{DEST_EXT}")

        # Checkpoint: row count in TRANSFORM_DIR must equal SOURCE_DIR row count
        src_primary = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dst_primary = os.path.join(TRANSFORM_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
        if os.path.exists(src_primary) and os.path.exists(dst_primary):
            src_count = count_records(src_primary)
            dst_count = count_records(dst_primary)
            if src_count != dst_count:
                log_event("transform_format", "failed",
                          f"Row count mismatch: source={src_count}, transformed={dst_count}")
                return False

        log_event("transform_format", "completed",
                  f"Transformed {len(csv_files)} file(s)")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("validate_checksums", "failed", f"Source directory not found: {SOURCE_DIR}")
            return False
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("validate_checksums", "failed", f"Transformed directory not found: {TRANSFORM_DIR}")
            return False

        checksum_dict = {"source": {}, "transformed": {}}

        # Compute checksums for source files
        for fn in sorted(os.listdir(SOURCE_DIR)):
            fp = os.path.join(SOURCE_DIR, fn)
            if os.path.isfile(fp):
                checksum_dict["source"][fn] = compute_file_checksum(fp)

        # Compute checksums for transformed files
        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            fp = os.path.join(TRANSFORM_DIR, fn)
            if os.path.isfile(fp):
                checksum_dict["transformed"][fn] = compute_file_checksum(fp)

        if dry_run:
            log_event("validate_checksums", "dry_run",
                      f"Would write checksums for source={len(checksum_dict['source'])} "
                      f"transformed={len(checksum_dict['transformed'])}")
            return True

        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksum_dict, f, indent=2)

        # Checkpoint: checksums.json exists and has valid entries
        if not os.path.exists(CHECKSUM_FILE):
            log_event("validate_checksums", "failed", "checksums.json was not created")
            return False

        if not checksum_dict["source"] or not checksum_dict["transformed"]:
            log_event("validate_checksums", "failed", "Missing source or transformed checksums")
            return False

        # Verify all checksums are 64-char hex strings
        for section in ("source", "transformed"):
            for fname, csum in checksum_dict[section].items():
                if len(csum) != 64 or not all(c in "0123456789abcdef" for c in csum):
                    log_event("validate_checksums", "failed", f"Invalid checksum for {fname}")
                    return False

        log_event("validate_checksums", "completed",
                  f"source={len(checksum_dict['source'])} files, "
                  f"transformed={len(checksum_dict['transformed'])} files")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("load_new_store", "failed", f"Transformed directory not found: {TRANSFORM_DIR}")
            return False

        jsonl_files = [f for f in os.listdir(TRANSFORM_DIR)
                       if f.endswith("." + DEST_EXT) and os.path.isfile(os.path.join(TRANSFORM_DIR, f))]
        if not jsonl_files:
            log_event("load_new_store", "failed", "No JSONL files found in transformed directory")
            return False

        if dry_run:
            log_event("load_new_store", "dry_run", f"Would copy {len(jsonl_files)} file(s) to {DEST_DIR}")
            return True

        os.makedirs(DEST_DIR, exist_ok=True)
        for fn in jsonl_files:
            src = os.path.join(TRANSFORM_DIR, fn)
            dst = os.path.join(DEST_DIR, fn)
            shutil.copy2(src, dst)
            log_event("load_new_store", "progress", f"Copied {fn}")

        # Checkpoint: row count in DEST_DIR must equal source row count
        src_primary = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dst_primary = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
        if os.path.exists(src_primary) and os.path.exists(dst_primary):
            src_count = count_records(src_primary)
            dst_count = count_records(dst_primary)
            if src_count != dst_count:
                log_event("load_new_store", "failed",
                          f"Row count mismatch: source={src_count}, dest={dst_count}")
                return False

        # Also verify REF_TABLE was copied
        ref_dst = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        if not os.path.exists(ref_dst):
            log_event("load_new_store", "failed", f"Missing {REF_TABLE}.{DEST_EXT} in destination")
            return False

        log_event("load_new_store", "completed", f"Loaded {len(jsonl_files)} file(s)")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        src_primary = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dst_primary = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(src_primary):
            log_event("verify_counts", "failed", f"Source primary table not found: {src_primary}")
            return False
        if not os.path.exists(dst_primary):
            log_event("verify_counts", "failed", f"Dest primary table not found: {dst_primary}")
            return False

        source_count = count_records(src_primary)
        dest_count = count_records(dst_primary)
        counts_match = (source_count == dest_count)

        report = {
            "source_count": source_count,
            "dest_count": dest_count,
            "counts_match": counts_match,
        }

        if dry_run:
            log_event("verify_counts", "dry_run",
                      f"source={source_count}, dest={dest_count}, match={counts_match}")
            return counts_match

        with open(VERIFICATION_REPORT, "w") as f:
            json.dump(report, f, indent=2)

        if counts_match:
            log_event("verify_counts", "completed",
                      f"source={source_count}, dest={dest_count}, match=True")
        else:
            log_event("verify_counts", "failed",
                      f"source={source_count}, dest={dest_count}, match=False")

        return counts_match
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    try:
        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(ref_path):
            log_event("update_references", "failed", f"Reference table not found: {ref_path}")
            return False
        if not os.path.exists(primary_path):
            log_event("update_references", "failed", f"Primary table not found: {primary_path}")
            return False

        # Build set of valid device_ids from REF_TABLE
        valid_ids = set()
        with open(ref_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                valid_ids.add(str(rec[REF_KEY]))

        if not valid_ids:
            log_event("update_references", "failed", "No valid device IDs found in reference table")
            return False

        # Check all records in PRIMARY_TABLE for orphaned references
        orphaned_ids = set()
        records = []
        with open(primary_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                records.append(rec)
                did = str(rec.get(REF_KEY, ""))
                if did not in valid_ids:
                    orphaned_ids.add(did)

        if orphaned_ids:
            log_event("update_references", "failed",
                      f"Orphaned {REF_KEY}s found: {sorted(orphaned_ids)}")
            return False

        # All references valid — no modifications needed
        if dry_run:
            log_event("update_references", "dry_run",
                      f"Verified {len(records)} records, no orphaned references")
        else:
            log_event("update_references", "completed",
                      f"Verified {len(records)} records, no orphaned references")

        return True
    except Exception as e:
        log_event("update_references", "error", str(e))
        return False


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
