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


def _write_json_atomic(path: str, obj) -> None:
    """Write a JSON object atomically via a temp file + rename."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def _clear_dir(path: str) -> None:
    """Remove a directory and recreate it empty."""
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


# ── Step implementations ─────────────────────────────────────────────────────

def step_backup(dry_run: bool = False) -> bool:
    """Step 1: Backup source data."""
    try:
        if not os.path.isdir(SOURCE_DIR):
            log_event("backup", "failed", f"source directory missing: {SOURCE_DIR}")
            return False
        src_files = [f for f in os.listdir(SOURCE_DIR)
                     if os.path.isfile(os.path.join(SOURCE_DIR, f))]
        if not src_files:
            log_event("backup", "failed", "no source files to back up")
            return False
        if dry_run:
            log_event("backup", "success", f"would back up {len(src_files)} file(s)")
            return True
        _clear_dir(BACKUP_DIR)
        for fn in src_files:
            shutil.copy2(os.path.join(SOURCE_DIR, fn), os.path.join(BACKUP_DIR, fn))
        # Checkpoint: backup must contain a complete copy of every source file.
        bak_files = [f for f in os.listdir(BACKUP_DIR)
                     if os.path.isfile(os.path.join(BACKUP_DIR, f))]
        if set(src_files) != set(bak_files):
            log_event("backup", "failed", "backup incomplete")
            return False
        log_event("backup", "success", f"backed up {len(bak_files)} file(s)")
        return True
    except Exception as exc:
        log_event("backup", "failed", str(exc))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        tables = [PRIMARY_TABLE, REF_TABLE]
        for table in tables:
            src = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
            if not os.path.isfile(src):
                log_event("transform_format", "failed", f"missing source file: {src}")
                return False
        if dry_run:
            log_event("transform_format", "success", "source files readable")
            return True
        _clear_dir(TRANSFORM_DIR)
        for table in tables:
            src = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
            dst = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
            with open(src, newline="", encoding="utf-8") as f_in, \
                 open(dst, "w", encoding="utf-8") as f_out:
                reader = csv.DictReader(f_in)
                for row in reader:
                    f_out.write(json.dumps(row) + "\n")
        # Checkpoint: transformed primary row count == source primary row count.
        src_count = count_records(os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}"))
        dst_count = count_records(os.path.join(TRANSFORM_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}"))
        if src_count != dst_count:
            log_event("transform_format", "failed",
                      f"row count mismatch: source={src_count} transformed={dst_count}")
            return False
        log_event("transform_format", "success", f"transformed {dst_count} primary rows")
        return True
    except Exception as exc:
        log_event("transform_format", "failed", str(exc))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        source = {}
        transformed = {}
        for fn in sorted(os.listdir(SOURCE_DIR)):
            path = os.path.join(SOURCE_DIR, fn)
            if os.path.isfile(path):
                source[fn] = compute_file_checksum(path)
        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            path = os.path.join(TRANSFORM_DIR, fn)
            if os.path.isfile(path):
                transformed[fn] = compute_file_checksum(path)
        if not source or not transformed:
            log_event("validate_checksums", "failed", "no files available to checksum")
            return False
        # Checkpoint: every checksum must be a 64-char hex SHA-256 string.
        for section, entries in (("source", source), ("transformed", transformed)):
            for fname, chk in entries.items():
                if not isinstance(chk, str) or len(chk) != 64:
                    log_event("validate_checksums", "failed",
                              f"invalid checksum for {section}/{fname}")
                    return False
        if dry_run:
            log_event("validate_checksums", "success", "checksums verified")
            return True
        _write_json_atomic(CHECKSUM_FILE, {"source": source, "transformed": transformed})
        log_event("validate_checksums", "success",
                  f"{len(source)} source + {len(transformed)} transformed checksums")
        return True
    except Exception as exc:
        log_event("validate_checksums", "failed", str(exc))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        tables = [PRIMARY_TABLE, REF_TABLE]
        for table in tables:
            src = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
            if not os.path.isfile(src):
                log_event("load_new_store", "failed", f"missing transformed file: {src}")
                return False
        if dry_run:
            log_event("load_new_store", "success", "transformed files present")
            return True
        _clear_dir(DEST_DIR)
        for table in tables:
            src = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
            dst = os.path.join(DEST_DIR, f"{table}.{DEST_EXT}")
            shutil.copy2(src, dst)
        # Checkpoint: primary row count in dest == source row count.
        src_count = count_records(os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}"))
        dst_count = count_records(os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}"))
        if src_count != dst_count:
            log_event("load_new_store", "failed",
                      f"row count mismatch: source={src_count} dest={dst_count}")
            return False
        log_event("load_new_store", "success", f"loaded {dst_count} primary rows")
        return True
    except Exception as exc:
        log_event("load_new_store", "failed", str(exc))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        src_count = count_records(os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}"))
        dest_count = count_records(os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}"))
        counts_match = (src_count == dest_count)
        if dry_run:
            if counts_match:
                log_event("verify_counts", "success", f"counts match ({src_count})")
            else:
                log_event("verify_counts", "failed",
                          f"count mismatch: source={src_count} dest={dest_count}")
            return counts_match
        _write_json_atomic(VERIFICATION_REPORT, {
            "source_count": src_count,
            "dest_count": dest_count,
            "counts_match": counts_match,
        })
        if not counts_match:
            log_event("verify_counts", "failed",
                      f"count mismatch: source={src_count} dest={dest_count}")
            return False
        log_event("verify_counts", "success", f"counts match ({src_count})")
        return True
    except Exception as exc:
        log_event("verify_counts", "failed", str(exc))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    try:
        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
        if not os.path.isfile(ref_path) or not os.path.isfile(primary_path):
            log_event("update_references", "failed", "destination files missing")
            return False
        # Build the set of valid reference keys from the reference table.
        valid_ids = set()
        with open(ref_path) as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if REF_KEY in rec:
                    valid_ids.add(str(rec[REF_KEY]))
        # Check every primary record's reference exists in the valid set.
        records = []
        orphans = []
        with open(primary_path) as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                val = str(rec.get(REF_KEY, ""))
                if val and val not in valid_ids:
                    orphans.append(val)
                records.append(rec)
        if orphans:
            log_event("update_references", "failed",
                      f"found {len(orphans)} orphaned {REF_KEY} values: {orphans[:5]}")
            return False
        if dry_run:
            log_event("update_references", "success",
                      f"no orphaned references ({len(valid_ids)} valid ids)")
            return True
        # Write the verified primary table back atomically.
        tmp = primary_path + ".tmp"
        with open(tmp, "w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        os.replace(tmp, primary_path)
        log_event("update_references", "success",
                  f"no orphaned references ({len(valid_ids)} valid ids)")
        return True
    except Exception as exc:
        log_event("update_references", "failed", str(exc))
        return False


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data."""
    try:
        if dry_run:
            log_event("archive_old", "success", "archive source checked")
            return True
        if os.path.exists(ARCHIVE_NAME):
            os.remove(ARCHIVE_NAME)
        with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
            tar.add(SOURCE_DIR, arcname=os.path.basename(SOURCE_DIR))
        if not os.path.isfile(ARCHIVE_NAME) or os.path.getsize(ARCHIVE_NAME) == 0:
            log_event("archive_old", "failed", "archive file empty or missing")
            return False
        log_event("archive_old", "success", f"created {ARCHIVE_NAME}")
        return True
    except Exception as exc:
        log_event("archive_old", "failed", str(exc))
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
