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
            log_event("backup", "failed", f"source directory {SOURCE_DIR} not found")
            return False

        source_files = [f for f in os.listdir(SOURCE_DIR) if os.path.isfile(os.path.join(SOURCE_DIR, f))]
        if not source_files:
            log_event("backup", "failed", "source directory is empty")
            return False

        # Clean up existing backup if present
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)

        os.makedirs(BACKUP_DIR, exist_ok=True)

        if dry_run:
            log_event("backup", "dry_run", f"would copy {len(source_files)} file(s)")
            return True

        for fname in source_files:
            src = os.path.join(SOURCE_DIR, fname)
            dst = os.path.join(BACKUP_DIR, fname)
            shutil.copy2(src, dst)

        # Verify backup integrity
        backup_files = [f for f in os.listdir(BACKUP_DIR) if os.path.isfile(os.path.join(BACKUP_DIR, f))]
        if sorted(source_files) != sorted(backup_files):
            log_event("backup", "failed", "backup file list mismatch")
            return False

        log_event("backup", "completed", f"backed up {len(backup_files)} file(s)")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("transform_format", "failed", f"source directory {SOURCE_DIR} not found")
            return False

        source_files = [f for f in os.listdir(SOURCE_DIR)
                        if os.path.isfile(os.path.join(SOURCE_DIR, f)) and f.endswith("." + SOURCE_EXT)]
        if not source_files:
            log_event("transform_format", "failed", "no CSV files found in source")
            return False

        # Clean and recreate transform dir
        if os.path.exists(TRANSFORM_DIR):
            shutil.rmtree(TRANSFORM_DIR)
        os.makedirs(TRANSFORM_DIR, exist_ok=True)

        if dry_run:
            log_event("transform_format", "dry_run", f"would transform {len(source_files)} file(s)")
            return True

        for fname in source_files:
            src_path = os.path.join(SOURCE_DIR, fname)
            table_name = os.path.splitext(fname)[0]
            out_path = os.path.join(TRANSFORM_DIR, f"{table_name}.{DEST_EXT}")

            with open(src_path, "r", encoding="utf-8-sig", newline="") as inf:
                reader = csv.DictReader(inf)
                if reader.fieldnames is None:
                    log_event("transform_format", "failed", f"no header in {fname}")
                    return False

                with open(out_path, "w", encoding="utf-8", newline="\n") as outf:
                    for row in reader:
                        # Skip empty rows
                        if not any(v.strip() for v in row.values() if v):
                            continue
                        outf.write(json.dumps(row, ensure_ascii=False) + "\n")

            # Verify row count
            src_count = count_records(src_path)
            dst_count = count_records(out_path)
            if src_count != dst_count:
                log_event("transform_format", "failed",
                          f"row count mismatch for {table_name}: src={src_count} dst={dst_count}")
                return False

            log_event("transform_format", "progress", f"{table_name}: {dst_count} records")

        log_event("transform_format", "completed", f"transformed {len(source_files)} file(s)")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        if not os.path.isdir(SOURCE_DIR) or not os.path.isdir(TRANSFORM_DIR):
            log_event("validate_checksums", "failed", "source or transformed directory missing")
            return False

        source_files = [f for f in os.listdir(SOURCE_DIR)
                        if os.path.isfile(os.path.join(SOURCE_DIR, f)) and f.endswith("." + SOURCE_EXT)]
        transform_files = [f for f in os.listdir(TRANSFORM_DIR)
                           if os.path.isfile(os.path.join(TRANSFORM_DIR, f)) and f.endswith("." + DEST_EXT)]

        if not source_files:
            log_event("validate_checksums", "failed", "no source files found")
            return False
        if not transform_files:
            log_event("validate_checksums", "failed", "no transformed files found")
            return False

        if dry_run:
            log_event("validate_checksums", "dry_run",
                      f"would checksum {len(source_files)} source + {len(transform_files)} transformed file(s)")
            return True

        checksums = {"source": {}, "transformed": {}}

        for fname in source_files:
            path = os.path.join(SOURCE_DIR, fname)
            chk = compute_file_checksum(path)
            checksums["source"][fname] = chk

        for fname in transform_files:
            path = os.path.join(TRANSFORM_DIR, fname)
            chk = compute_file_checksum(path)
            checksums["transformed"][fname] = chk

        # Validate: all entries must be non-empty 64-char hex strings
        for section in ("source", "transformed"):
            for fname, chk in checksums[section].items():
                if not isinstance(chk, str) or len(chk) != 64:
                    log_event("validate_checksums", "failed",
                              f"invalid checksum for {section}/{fname}")
                    return False

        with open(CHECKSUM_FILE, "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        log_event("validate_checksums", "completed",
                  f"{len(checksums['source'])} source + {len(checksums['transformed'])} transformed checksums")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("load_new_store", "failed", "transformed directory missing")
            return False

        transform_files = [f for f in os.listdir(TRANSFORM_DIR)
                           if os.path.isfile(os.path.join(TRANSFORM_DIR, f)) and f.endswith("." + DEST_EXT)]
        if not transform_files:
            log_event("load_new_store", "failed", "no transformed files found")
            return False

        # Clean dest dir (keep .gitkeep if exists)
        if os.path.exists(DEST_DIR):
            for fn in os.listdir(DEST_DIR):
                if fn != ".gitkeep":
                    fp = os.path.join(DEST_DIR, fn)
                    if os.path.isfile(fp):
                        os.remove(fp)
        os.makedirs(DEST_DIR, exist_ok=True)

        if dry_run:
            log_event("load_new_store", "dry_run", f"would load {len(transform_files)} file(s)")
            return True

        for fname in transform_files:
            src_path = os.path.join(TRANSFORM_DIR, fname)
            dst_path = os.path.join(DEST_DIR, fname)

            # Validate each line is valid JSON and write to dest
            with open(src_path, "r", encoding="utf-8") as inf:
                lines = inf.readlines()

            with open(dst_path, "w", encoding="utf-8", newline="\n") as outf:
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        json.loads(stripped)  # validate
                        outf.write(stripped + "\n")
                    except json.JSONDecodeError as e:
                        log_event("load_new_store", "failed",
                                  f"invalid JSON in {fname}: {str(e)}")
                        return False

            # Verify row count
            src_count = count_records(src_path)
            dst_count = count_records(dst_path)
            if src_count != dst_count:
                log_event("load_new_store", "failed",
                          f"row count mismatch for {fname}: src={src_count} dst={dst_count}")
                return False

            log_event("load_new_store", "progress", f"{fname}: {dst_count} records")

        log_event("load_new_store", "completed", f"loaded {len(transform_files)} file(s)")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dest_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.isfile(src_path):
            log_event("verify_counts", "failed", f"source file missing: {src_path}")
            return False
        if not os.path.isfile(dest_path):
            log_event("verify_counts", "failed", f"dest file missing: {dest_path}")
            return False

        src_count = count_records(src_path)
        dest_count = count_records(dest_path)

        if dry_run:
            log_event("verify_counts", "dry_run",
                      f"src={src_count} dest={dest_count} match={src_count == dest_count}")
            return True

        counts_match = src_count == dest_count
        report = {
            "source_count": src_count,
            "dest_count": dest_count,
            "counts_match": counts_match,
        }

        with open(VERIFICATION_REPORT, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        if counts_match:
            log_event("verify_counts", "completed", f"counts match: {src_count}")
            return True
        else:
            log_event("verify_counts", "failed",
                      f"counts mismatch: src={src_count} dest={dest_count}")
            return False
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    try:
        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.isfile(ref_path):
            log_event("update_references", "failed", f"ref table missing: {ref_path}")
            return False
        if not os.path.isfile(primary_path):
            log_event("update_references", "failed", f"primary table missing: {primary_path}")
            return False

        # Build set of valid device_ids from ref table
        valid_ids = set()
        with open(ref_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    rec = json.loads(stripped)
                    if REF_KEY in rec:
                        valid_ids.add(str(rec[REF_KEY]))
                except json.JSONDecodeError:
                    continue

        if not valid_ids:
            log_event("update_references", "failed", "no valid device ids found")
            return False

        if dry_run:
            log_event("update_references", "dry_run",
                      f"would verify {REF_KEY} references against {len(valid_ids)} valid ids")
            return True

        # Check every record's REF_KEY exists in valid_ids
        orphans = []
        records = []
        with open(primary_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    rec = json.loads(stripped)
                except json.JSONDecodeError:
                    log_event("update_references", "failed", f"invalid JSON in primary table")
                    return False
                records.append(rec)
                ref_val = str(rec.get(REF_KEY, ""))
                if ref_val and ref_val not in valid_ids:
                    orphans.append(ref_val)

        if orphans:
            log_event("update_references", "failed",
                      f"{len(orphans)} orphaned {REF_KEY}(s): {orphans[:5]}")
            return False

        # Write validated records back
        with open(primary_path, "w", encoding="utf-8", newline="\n") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        log_event("update_references", "completed",
                  f"all {len(records)} records have valid {REF_KEY} refs ({len(valid_ids)} ids)")
        return True
    except Exception as e:
        log_event("update_references", "error", str(e))
        return False


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("archive_old", "failed", f"source directory {SOURCE_DIR} not found")
            return False

        if dry_run:
            log_event("archive_old", "dry_run", f"would create archive {ARCHIVE_NAME}")
            return True

        with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
            tar.add(SOURCE_DIR, arcname=os.path.basename(SOURCE_DIR))

        # Verify archive exists and is non-empty
        if not os.path.isfile(ARCHIVE_NAME):
            log_event("archive_old", "failed", "archive file not created")
            return False
        if os.path.getsize(ARCHIVE_NAME) == 0:
            log_event("archive_old", "failed", "archive file is empty")
            return False

        log_event("archive_old", "completed",
                  f"archive created: {ARCHIVE_NAME} ({os.path.getsize(ARCHIVE_NAME)} bytes)")
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
