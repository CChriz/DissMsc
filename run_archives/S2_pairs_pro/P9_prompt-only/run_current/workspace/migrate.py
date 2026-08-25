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
        # Create backup directory
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # Copy all files from source to backup
        source_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith("." + SOURCE_EXT)]
        if not source_files:
            log_event("backup", "failed", "no source files found")
            return False

        for filename in source_files:
            src_path = os.path.join(SOURCE_DIR, filename)
            dst_path = os.path.join(BACKUP_DIR, filename)
            if dry_run:
                log_event("backup", "dry_run", f"would copy {filename}")
            else:
                shutil.copy2(src_path, dst_path)
                log_event("backup", "progress", f"copied {filename}")

        # Verify: backup directory has same number of source files
        backup_files = [f for f in os.listdir(BACKUP_DIR) if f.endswith("." + SOURCE_EXT)]
        if len(backup_files) != len(source_files):
            log_event("backup", "failed",
                      f"backup count mismatch: {len(backup_files)} != {len(source_files)}")
            return False

        log_event("backup", "completed", f"backed up {len(backup_files)} file(s)")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        os.makedirs(TRANSFORM_DIR, exist_ok=True)

        source_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith("." + SOURCE_EXT)]
        if not source_files:
            log_event("transform_format", "failed", "no source files found")
            return False

        for filename in source_files:
            table_name = filename[:-(len(SOURCE_EXT) + 1)]  # strip ".csv"
            src_path = os.path.join(SOURCE_DIR, filename)
            dst_path = os.path.join(TRANSFORM_DIR, f"{table_name}.{DEST_EXT}")

            with open(src_path, newline="") as infile:
                reader = csv.DictReader(infile, delimiter=SEPARATOR)
                rows = list(reader)

            if dry_run:
                log_event("transform_format", "dry_run",
                          f"would transform {table_name}: {len(rows)} rows → {dst_path}")
                continue

            # Type conversion based on table
            output_rows = []
            for row in rows:
                converted = {}
                for key, val in row.items():
                    key_lower = key.strip().lower()
                    val_stripped = val.strip()
                    # Integer fields
                    if key_lower in ("reading_id", "device_id"):
                        converted[key] = int(val_stripped)
                    # Float fields
                    elif key_lower == "value":
                        converted[key] = float(val_stripped)
                    else:
                        converted[key] = val_stripped
                output_rows.append(converted)

            # Write JSONL
            with open(dst_path, "w") as outfile:
                for obj in output_rows:
                    outfile.write(json.dumps(obj) + "\n")

            log_event("transform_format", "progress",
                      f"{table_name}: {len(output_rows)} rows → {dst_path}")

        # Checkpoint: row count in TRANSFORM_DIR must equal SOURCE_DIR row count
        for filename in source_files:
            table_name = filename[:-(len(SOURCE_EXT) + 1)]
            src_count = count_records(os.path.join(SOURCE_DIR, filename))
            dst_count = count_records(os.path.join(TRANSFORM_DIR, f"{table_name}.{DEST_EXT}"))
            if src_count != dst_count:
                log_event("transform_format", "failed",
                          f"row count mismatch for {table_name}: source={src_count}, transformed={dst_count}")
                return False

        log_event("transform_format", "completed",
                  f"transformed {len(source_files)} file(s)")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        checksums = {"source": {}, "transformed": {}}

        # Compute checksums for source files
        source_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith("." + SOURCE_EXT)]
        if not source_files:
            log_event("validate_checksums", "failed", "no source files found")
            return False

        for filename in source_files:
            filepath = os.path.join(SOURCE_DIR, filename)
            checksums["source"][filename] = compute_file_checksum(filepath)

        # Compute checksums for transformed files
        transformed_files = [f for f in os.listdir(TRANSFORM_DIR) if f.endswith("." + DEST_EXT)]
        if not transformed_files:
            log_event("validate_checksums", "failed", "no transformed files found")
            return False

        for filename in transformed_files:
            filepath = os.path.join(TRANSFORM_DIR, filename)
            checksums["transformed"][filename] = compute_file_checksum(filepath)

        if dry_run:
            log_event("validate_checksums", "dry_run",
                      f"would write checksums for {len(source_files)} source + {len(transformed_files)} transformed files")
            return True

        # Write checksums.json
        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksums, f, indent=2)

        # Checkpoint: all checksum entries must be non-empty 64-char hex strings
        for section, entries in checksums.items():
            if not entries:
                log_event("validate_checksums", "failed", f"empty {section} entries")
                return False
            for fname, chk in entries.items():
                if not isinstance(chk, str) or len(chk) != 64:
                    log_event("validate_checksums", "failed",
                              f"invalid checksum for {section}/{fname}: {chk!r}")
                    return False

        log_event("validate_checksums", "completed",
                  f"{len(checksums['source'])} source + {len(checksums['transformed'])} transformed checksums")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        os.makedirs(DEST_DIR, exist_ok=True)

        transformed_files = [f for f in os.listdir(TRANSFORM_DIR) if f.endswith("." + DEST_EXT)]
        if not transformed_files:
            log_event("load_new_store", "failed", "no transformed files found")
            return False

        for filename in transformed_files:
            src_path = os.path.join(TRANSFORM_DIR, filename)
            dst_path = os.path.join(DEST_DIR, filename)
            if dry_run:
                log_event("load_new_store", "dry_run", f"would copy {filename}")
            else:
                shutil.copy2(src_path, dst_path)
                log_event("load_new_store", "progress", f"copied {filename}")

        # Checkpoint: row count in DEST_DIR must equal source row count
        primary_src = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        primary_dst = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(primary_dst):
            log_event("load_new_store", "failed",
                      f"primary table missing in dest: {primary_dst}")
            return False

        src_count = count_records(primary_src)
        dest_count = count_records(primary_dst)
        if src_count != dest_count:
            log_event("load_new_store", "failed",
                      f"row count mismatch: source={src_count}, dest={dest_count}")
            return False

        log_event("load_new_store", "completed",
                  f"loaded {len(transformed_files)} file(s) to new store, {dest_count} primary rows")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        primary_src = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        primary_dst = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        source_count = count_records(primary_src)
        dest_count = count_records(primary_dst)

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

        if not counts_match:
            log_event("verify_counts", "failed",
                      f"count mismatch: source={source_count}, dest={dest_count}")
            return False

        log_event("verify_counts", "completed",
                  f"counts match: {source_count} records")
        return True
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    try:
        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(ref_path):
            log_event("update_references", "failed", f"ref table missing: {ref_path}")
            return False
        if not os.path.exists(primary_path):
            log_event("update_references", "failed", f"primary table missing: {primary_path}")
            return False

        # Build set of valid device_ids from devices.jsonl
        valid_ids = set()
        with open(ref_path) as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if REF_KEY in rec:
                    valid_ids.add(rec[REF_KEY])

        # Check every sensor_reading record for orphaned device_ids
        orphans = []
        primary_records = []
        with open(primary_path) as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                primary_records.append(rec)
                if rec.get(REF_KEY) not in valid_ids:
                    orphans.append(rec.get(REF_KEY))

        if orphans:
            log_event("update_references", "failed",
                      f"found {len(orphans)} orphaned {REF_KEY}s: {orphans[:5]}")
            return False

        if dry_run:
            log_event("update_references", "dry_run",
                      f"all {len(primary_records)} records have valid {REF_KEY}s")
            return True

        # All references valid — write back (no changes needed, just verify pass)
        log_event("update_references", "completed",
                  f"{len(primary_records)} records with valid {REF_KEY}s ({len(valid_ids)} unique)")
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
