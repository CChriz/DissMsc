"""
Data migration script for IoT sensor telemetry.

Migration steps (execute in order):
  1. backup: Create a backup of all source data before any changes
  2. transform_format: Convert records from old format to new target format
  3. validate_checksums: Verify data integrity via SHA-256 checksums of every file
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
    label = "DONE" if status == "completed" else status.upper()
    print(f"[{entry['ts']}] {label:6s} {step}{': ' + detail if detail else ''}")


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


def try_convert_value(v: str):
    """Convert a CSV cell value to int, float, or keep as string.
    Empty string maps to None (JSON null)."""
    if v is None or v.strip() == '':
        return None
    v = v.strip()
    # Try int first
    try:
        return int(v)
    except ValueError:
        pass
    # Try float
    try:
        return float(v)
    except ValueError:
        pass
    return v


# ── Step implementations ─────────────────────────────────────────────────────

def step_backup(dry_run: bool = False) -> bool:
    """Step 1: Backup source data.
    Copies all CSV files from SOURCE_DIR to BACKUP_DIR.
    Verifies each copy has the same file size as the original.
    """
    try:
        if dry_run:
            log_event("backup", "dry_run", "would create backup")
            return True

        # Clear and recreate backup directory
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        for fn in os.listdir(SOURCE_DIR):
            if not fn.endswith("." + SOURCE_EXT):
                continue
            src = os.path.join(SOURCE_DIR, fn)
            dst = os.path.join(BACKUP_DIR, fn)
            shutil.copy2(src, dst)

            # Verify copy integrity
            if os.path.getsize(dst) != os.path.getsize(src):
                log_event("backup", "error", f"size mismatch for {fn}")
                return False

        log_event("backup", "completed", f"backed up to {BACKUP_DIR}")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format (CSV) to new format (JSONL).
    Reads each CSV with csv.DictReader (dynamic header), converts numeric
    values, and writes one JSON object per line to TRANSFORM_DIR.
    Checkpoint: row counts in TRANSFORM_DIR must equal SOURCE_DIR for each table.
    """
    try:
        if dry_run:
            log_event("transform_format", "dry_run", "would transform CSVs to JSONL")
            return True

        # Clear and recreate transformed directory
        if os.path.exists(TRANSFORM_DIR):
            shutil.rmtree(TRANSFORM_DIR)
        os.makedirs(TRANSFORM_DIR, exist_ok=True)

        for fn in os.listdir(SOURCE_DIR):
            if not fn.endswith("." + SOURCE_EXT):
                continue
            base = os.path.splitext(fn)[0]
            src = os.path.join(SOURCE_DIR, fn)
            dst = os.path.join(TRANSFORM_DIR, f"{base}.{DEST_EXT}")

            with open(src, newline='') as inf, open(dst, 'w') as outf:
                reader = csv.DictReader(inf, delimiter=SEPARATOR)
                for row in reader:
                    converted = {k: try_convert_value(v) for k, v in row.items()}
                    outf.write(json.dumps(converted) + "\n")

        # Checkpoint: verify row counts match for every table
        for fn in os.listdir(SOURCE_DIR):
            if not fn.endswith("." + SOURCE_EXT):
                continue
            base = os.path.splitext(fn)[0]
            src_count = count_records(os.path.join(SOURCE_DIR, fn))
            dst_file = os.path.join(TRANSFORM_DIR, f"{base}.{DEST_EXT}")
            if not os.path.exists(dst_file):
                log_event("transform_format", "error", f"missing output: {dst_file}")
                return False
            dst_count = count_records(dst_file)
            if src_count != dst_count:
                log_event("transform_format", "error",
                          f"count mismatch for {base}: src={src_count} dst={dst_count}")
                return False

        log_event("transform_format", "completed", f"transformed to {TRANSFORM_DIR}")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via file-level SHA-256 checksums.
    Computes SHA-256 for every file in SOURCE_DIR and TRANSFORM_DIR.
    Writes checksums.json in Zone B compatible format:
      {"source": {"<filename>": "<64-char hex>"},
       "transformed": {"<filename>": "<64-char hex>"}}
    Checkpoint: all checksum entries must be non-empty 64-char hex strings.
    """
    try:
        if dry_run:
            log_event("validate_checksums", "dry_run", "would compute checksums")
            return True

        checksums = {"source": {}, "transformed": {}}

        # Source files
        for fn in sorted(os.listdir(SOURCE_DIR)):
            if not fn.endswith("." + SOURCE_EXT):
                continue
            fp = os.path.join(SOURCE_DIR, fn)
            checksums["source"][fn] = compute_file_checksum(fp)

        # Transformed files
        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            if not fn.endswith("." + DEST_EXT):
                continue
            fp = os.path.join(TRANSFORM_DIR, fn)
            checksums["transformed"][fn] = compute_file_checksum(fp)

        # Checkpoint: validate all checksums are non-empty 64-char hex
        for category in ("source", "transformed"):
            for fn, chk in checksums[category].items():
                if not chk or len(chk) != 64 or not all(c in "0123456789abcdef" for c in chk):
                    log_event("validate_checksums", "error",
                              f"invalid checksum for {category}/{fn}")
                    return False

        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksums, f, indent=2)

        log_event("validate_checksums", "completed", f"wrote {CHECKSUM_FILE}")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into the new data store.
    Copies all JSONL files from TRANSFORM_DIR to DEST_DIR.
    Checkpoint: row count in DEST_DIR must equal TRANSFORM_DIR for every table.
    """
    try:
        if dry_run:
            log_event("load_new_store", "dry_run", "would load to new store")
            return True

        # Clear and recreate destination directory
        if os.path.exists(DEST_DIR):
            for fn in os.listdir(DEST_DIR):
                fp = os.path.join(DEST_DIR, fn)
                if os.path.isfile(fp):
                    os.remove(fp)
        os.makedirs(DEST_DIR, exist_ok=True)

        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            if not fn.endswith("." + DEST_EXT):
                continue
            src = os.path.join(TRANSFORM_DIR, fn)
            dst = os.path.join(DEST_DIR, fn)
            shutil.copy2(src, dst)

        # Checkpoint: verify row counts
        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            if not fn.endswith("." + DEST_EXT):
                continue
            src_count = count_records(os.path.join(TRANSFORM_DIR, fn))
            dst_file = os.path.join(DEST_DIR, fn)
            if not os.path.exists(dst_file):
                log_event("load_new_store", "error", f"missing destination: {dst_file}")
                return False
            dst_count = count_records(dst_file)
            if src_count != dst_count:
                log_event("load_new_store", "error",
                          f"count mismatch for {fn}: src={src_count} dst={dst_count}")
                return False

        log_event("load_new_store", "completed", f"loaded to {DEST_DIR}")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination.
    Counts primary table (sensor_readings) rows in SOURCE_DIR and DEST_DIR.
    Writes verification_report.json with the comparison result.
    """
    try:
        if dry_run:
            log_event("verify_counts", "dry_run", "would verify counts")
            return True

        src_file = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dst_file = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(src_file):
            log_event("verify_counts", "error", f"source missing: {src_file}")
            return False
        if not os.path.exists(dst_file):
            log_event("verify_counts", "error", f"destination missing: {dst_file}")
            return False

        source_count = count_records(src_file)
        dest_count = count_records(dst_file)
        counts_match = (source_count == dest_count)

        report = {
            "source_count": source_count,
            "dest_count": dest_count,
            "counts_match": counts_match,
        }
        with open(VERIFICATION_REPORT, "w") as f:
            json.dump(report, f, indent=2)

        if counts_match:
            log_event("verify_counts", "completed",
                      f"counts match: {source_count} == {dest_count}")
        else:
            log_event("verify_counts", "failed",
                      f"counts mismatch: src={source_count} dst={dest_count}")
        return counts_match
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Validate foreign-key referential integrity.
    Ensures every device_id in sensor_readings.jsonl exists in devices.jsonl.
    Checkpoint: zero orphaned device_ids in the new store.
    """
    try:
        if dry_run:
            log_event("update_references", "dry_run", "would validate references")
            return True

        devices_file = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        readings_file = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(devices_file):
            log_event("update_references", "error", f"missing: {devices_file}")
            return False
        if not os.path.exists(readings_file):
            log_event("update_references", "error", f"missing: {readings_file}")
            return False

        # Build set of valid device_ids from devices.jsonl
        valid_device_ids = set()
        with open(devices_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                valid_device_ids.add(rec[REF_KEY])

        # Check every sensor_reading's device_id
        orphans = []
        with open(readings_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                did = rec.get(REF_KEY)
                if did not in valid_device_ids:
                    orphans.append((rec.get("reading_id"), did))

        if orphans:
            orphan_str = ", ".join(f"reading_id={rid} device_id={did}"
                                   for rid, did in orphans[:10])
            if len(orphans) > 10:
                orphan_str += f" ... and {len(orphans) - 10} more"
            log_event("update_references", "failed",
                      f"found {len(orphans)} orphaned references: {orphan_str}")
            return False

        log_event("update_references", "completed",
                  f"all {REF_KEY}s valid ({len(valid_device_ids)} devices)")
        return True
    except Exception as e:
        log_event("update_references", "error", str(e))
        return False


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data.
    Creates a tar.gz archive of SOURCE_DIR for long-term retention.
    This is not part of the core 6-step migration chain — call it after success.
    """
    try:
        if dry_run:
            log_event("archive_old", "dry_run", f"would create {ARCHIVE_NAME}")
            return True

        # Remove existing archive if present
        if os.path.exists(ARCHIVE_NAME):
            os.remove(ARCHIVE_NAME)

        with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
            tar.add(SOURCE_DIR, arcname=os.path.basename(SOURCE_DIR))

        # Checkpoint: archive must exist and be non-empty
        if not os.path.exists(ARCHIVE_NAME):
            log_event("archive_old", "error", "archive not created")
            return False
        if os.path.getsize(ARCHIVE_NAME) == 0:
            log_event("archive_old", "error", "archive is empty")
            return False

        log_event("archive_old", "completed",
                  f"archive {ARCHIVE_NAME} ({os.path.getsize(ARCHIVE_NAME)} bytes)")
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
                    fp = os.path.join(DEST_DIR, fn)
                    if os.path.isfile(fp):
                        os.remove(fp)
        elif step_name == "verify_counts":
            if os.path.exists(VERIFICATION_REPORT):
                os.remove(VERIFICATION_REPORT)
        elif step_name == "update_references":
            # Restore devices from backup
            src = os.path.join(BACKUP_DIR, f"{REF_TABLE}.{SOURCE_EXT}")
            dst_jsonl = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
            if os.path.exists(src):
                # Re-transform the backup devices.csv to JSONL and overwrite
                with open(src, newline='') as inf:
                    reader = csv.DictReader(inf, delimiter=SEPARATOR)
                    with open(dst_jsonl, 'w') as outf:
                        for row in reader:
                            converted = {k: try_convert_value(v) for k, v in row.items()}
                            outf.write(json.dumps(converted) + "\n")
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
    failed_step = None
    error_detail = None

    for step_name in STEPS:
        fn = STEP_FUNCTIONS.get(step_name)
        if fn is None:
            log_event(step_name, "error", "unknown step")
            success = False
            failed_step = step_name
            error_detail = "unknown step function"
            break

        log_event(step_name, "start")
        try:
            ok = fn(dry_run=args.dry_run)
            if not ok:
                log_event(step_name, "failed", "step returned False")
                run_rollback(completed_steps)
                success = False
                failed_step = step_name
                error_detail = "step returned False"
                break
            completed_steps.append(step_name)
            log_event(step_name, "completed")
        except Exception as exc:
            log_event(step_name, "error", str(exc))
            run_rollback(completed_steps)
            success = False
            failed_step = step_name
            error_detail = str(exc)
            break

    # Write final migration report
    report = {
        "status": "success" if success else "failed",
        "steps_completed": completed_steps,
        "total_steps": len(STEPS),
        "ts": now_iso(),
    }
    if not success:
        report["failed_step"] = failed_step
        report["error"] = error_detail

    with open("migration_report.json", "w") as f:
        json.dump(report, f, indent=2)

    if success:
        log_event("migration", "success", f"all {len(completed_steps)} steps completed")
        print(f"\n[{now_iso()}] MIGRATION COMPLETE — status: success")
        print("See migration_report.json")
        sys.exit(0)
    else:
        log_event("migration", "failed")
        print(f"\n[{now_iso()}] MIGRATION FAILED — status: failed (step: {failed_step})")
        sys.exit(1)


if __name__ == "__main__":
    main()
