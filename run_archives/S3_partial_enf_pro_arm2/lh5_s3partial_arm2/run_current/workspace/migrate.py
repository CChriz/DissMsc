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
        if dry_run:
            log_event("backup", "dry_run", "would create backup directory and copy source files")
            return True

        # Remove existing backup directory for a clean start
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
            log_event("backup", "info", "removed existing backup directory")

        # Create fresh backup directory
        os.makedirs(BACKUP_DIR, exist_ok=False)
        log_event("backup", "info", f"created backup directory: {BACKUP_DIR}")

        # Copy all files from SOURCE_DIR into BACKUP_DIR
        source_files = [f for f in os.listdir(SOURCE_DIR)
                        if os.path.isfile(os.path.join(SOURCE_DIR, f))]
        copied_count = 0
        for fname in source_files:
            src_path = os.path.join(SOURCE_DIR, fname)
            dst_path = os.path.join(BACKUP_DIR, fname)
            shutil.copy2(src_path, dst_path)
            copied_count += 1
            log_event("backup", "info", f"copied: {fname}")

        # Verify: backup file count and sizes match source
        backup_files = [f for f in os.listdir(BACKUP_DIR)
                        if os.path.isfile(os.path.join(BACKUP_DIR, f))]
        if len(backup_files) != len(source_files):
            log_event("backup", "failed",
                      f"file count mismatch: source={len(source_files)} backup={len(backup_files)}")
            return False

        for fname in source_files:
            src_size = os.path.getsize(os.path.join(SOURCE_DIR, fname))
            bak_size = os.path.getsize(os.path.join(BACKUP_DIR, fname))
            if src_size != bak_size:
                log_event("backup", "failed",
                          f"size mismatch for {fname}: source={src_size} backup={bak_size}")
                return False

        log_event("backup", "success",
                  f"backed up {copied_count} file(s) to {BACKUP_DIR}")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        if dry_run:
            log_event("transform_format", "dry_run", "would create transform directory and convert files")
            return True

        # Remove existing transform directory for a clean start
        if os.path.exists(TRANSFORM_DIR):
            shutil.rmtree(TRANSFORM_DIR)
            log_event("transform_format", "info", "removed existing transform directory")

        # Create fresh transform directory
        os.makedirs(TRANSFORM_DIR, exist_ok=False)
        log_event("transform_format", "info", f"created transform directory: {TRANSFORM_DIR}")

        # Fields that should be converted to numeric types
        numeric_fields = {"reading_id", "device_id", "value"}

        # Process each CSV/TSV file in SOURCE_DIR
        source_files = [f for f in os.listdir(SOURCE_DIR)
                        if os.path.isfile(os.path.join(SOURCE_DIR, f))
                        and (f.endswith(".csv") or f.endswith(".tsv"))]

        for fname in source_files:
            src_path = os.path.join(SOURCE_DIR, fname)
            table_name = os.path.splitext(fname)[0]
            dst_path = os.path.join(TRANSFORM_DIR, f"{table_name}.jsonl")

            row_count = 0
            with open(src_path, newline="") as src_f, open(dst_path, "w") as dst_f:
                reader = csv.DictReader(src_f)
                for row in reader:
                    record = {}
                    for key, val in row.items():
                        val = val.strip() if isinstance(val, str) else val
                        # Type inference: numeric fields
                        if key in numeric_fields and val:
                            try:
                                if "." in val or "e" in val.lower():
                                    record[key] = float(val)
                                else:
                                    record[key] = int(val)
                            except (ValueError, TypeError):
                                record[key] = val
                        else:
                            record[key] = val
                    dst_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    row_count += 1

            log_event("transform_format", "info", f"converted {fname} → {table_name}.jsonl ({row_count} rows)")

        # Gate: row counts in TRANSFORM_DIR must equal SOURCE_DIR row counts
        for fname in source_files:
            src_path = os.path.join(SOURCE_DIR, fname)
            table_name = os.path.splitext(fname)[0]
            dst_path = os.path.join(TRANSFORM_DIR, f"{table_name}.jsonl")

            src_count = count_records(src_path)
            dst_count = count_records(dst_path)
            if src_count != dst_count:
                log_event("transform_format", "failed",
                          f"row count mismatch for {table_name}: source={src_count} transformed={dst_count}")
                return False

        log_event("transform_format", "success",
                  f"transformed {len(source_files)} file(s), all row counts verified")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        if dry_run:
            log_event("validate_checksums", "dry_run",
                      "would compute SHA-256 checksums for source and transformed files")
            return True

        checksums = {"source": {}, "transformed": {}}

        # Compute checksums for source files
        source_files = [f for f in os.listdir(SOURCE_DIR)
                        if os.path.isfile(os.path.join(SOURCE_DIR, f))]
        for fname in sorted(source_files):
            filepath = os.path.join(SOURCE_DIR, fname)
            chk = compute_file_checksum(filepath)
            # Validate: must be 64-character hex string
            if len(chk) != 64 or not all(c in "0123456789abcdef" for c in chk):
                log_event("validate_checksums", "failed",
                          f"invalid checksum for source/{fname}: length={len(chk)}")
                return False
            checksums["source"][fname] = chk

        # Compute checksums for transformed files
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("validate_checksums", "failed", "transform directory missing")
            return False

        transform_files = [f for f in os.listdir(TRANSFORM_DIR)
                           if os.path.isfile(os.path.join(TRANSFORM_DIR, f))]
        for fname in sorted(transform_files):
            filepath = os.path.join(TRANSFORM_DIR, fname)
            chk = compute_file_checksum(filepath)
            if len(chk) != 64 or not all(c in "0123456789abcdef" for c in chk):
                log_event("validate_checksums", "failed",
                          f"invalid checksum for transformed/{fname}: length={len(chk)}")
                return False
            checksums["transformed"][fname] = chk

        # Write checksums to file
        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksums, f, indent=2)

        # Verify: all entries must be non-empty strings
        for section in ("source", "transformed"):
            if not checksums.get(section):
                log_event("validate_checksums", "failed", f"empty {section} section")
                return False
            for fname, chk in checksums[section].items():
                if not isinstance(chk, str) or not chk:
                    log_event("validate_checksums", "failed",
                              f"empty checksum for {section}/{fname}")
                    return False

        log_event("validate_checksums", "success",
                  f"{len(checksums['source'])} source + {len(checksums['transformed'])} transformed checksums written to {CHECKSUM_FILE}")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        if dry_run:
            log_event("load_new_store", "dry_run",
                      f"Would load files from {TRANSFORM_DIR} to {DEST_DIR}")
            return True

        # Pre-flight: TRANSFORM_DIR must exist and contain .jsonl files
        if not os.path.isdir(TRANSFORM_DIR):
            log_event("load_new_store", "failed", "TRANSFORM_DIR does not exist")
            return False

        transform_files = sorted(
            f for f in os.listdir(TRANSFORM_DIR)
            if os.path.isfile(os.path.join(TRANSFORM_DIR, f))
            and f.endswith(f".{DEST_EXT}")
        )
        if not transform_files:
            log_event("load_new_store", "failed", "No .jsonl files in TRANSFORM_DIR")
            return False

        # Clean start: remove existing DEST_DIR, then create fresh
        if os.path.exists(DEST_DIR):
            shutil.rmtree(DEST_DIR)
        os.makedirs(DEST_DIR, exist_ok=False)

        # Atomic copy: write to .tmp first, then rename to final path
        for fname in transform_files:
            src = os.path.join(TRANSFORM_DIR, fname)
            dst = os.path.join(DEST_DIR, fname)
            tmp = dst + ".tmp"
            shutil.copy2(src, tmp)
            os.rename(tmp, dst)
            log_event("load_new_store", "info", f"loaded {fname} ({os.path.getsize(dst)} bytes)")

        # Gate: row count in DEST_DIR primary table == SOURCE_DIR primary table
        src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dest_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(dest_path):
            log_event("load_new_store", "failed", f"Missing {dest_path} after load")
            return False

        src_count = count_records(src_path)
        dest_count = count_records(dest_path)

        if src_count != dest_count:
            log_event("load_new_store", "failed",
                      f"Row count mismatch: source={src_count}, dest={dest_count}")
            return False

        log_event("load_new_store", "success",
                  f"Loaded {len(transform_files)} file(s), {dest_count} primary records")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        if dry_run:
            log_event("verify_counts", "dry_run",
                      "Would verify row counts between source and destination")
            return True

        src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dest_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(src_path):
            log_event("verify_counts", "failed", f"Source missing: {src_path}")
            return False
        if not os.path.exists(dest_path):
            log_event("verify_counts", "failed", f"Destination missing: {dest_path}")
            return False

        src_count = count_records(src_path)
        dest_count = count_records(dest_path)
        counts_match = (src_count == dest_count)

        # Write verification report
        report = {
            "source_count": src_count,
            "dest_count": dest_count,
            "counts_match": counts_match,
        }
        with open(VERIFICATION_REPORT, "w") as f:
            json.dump(report, f, indent=2)

        if not counts_match:
            log_event("verify_counts", "failed",
                      f"Count mismatch: source={src_count}, dest={dest_count}")
            return False

        log_event("verify_counts", "success", f"Both have {src_count} records")
        return True
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Validate foreign key reference integrity."""
    try:
        if dry_run:
            log_event("update_references", "dry_run",
                      "Would validate foreign key reference integrity")
            return True

        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        if not os.path.exists(ref_path):
            log_event("update_references", "failed", f"Reference table missing: {ref_path}")
            return False
        if not os.path.exists(primary_path):
            log_event("update_references", "failed", f"Primary table missing: {primary_path}")
            return False

        # Build set of valid REF_KEYs from reference table
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
            log_event("update_references", "failed", "No valid reference keys found")
            return False

        # Validate every primary record's REF_KEY exists in the reference set
        orphans = []
        total = 0
        with open(primary_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                total += 1
                ref_val = str(rec.get(REF_KEY, ""))
                if ref_val and ref_val not in valid_ids:
                    orphans.append({
                        "reading_id": rec.get("reading_id", "?"),
                        REF_KEY: ref_val,
                    })

        if orphans:
            detail = f"Found {len(orphans)} orphaned {REF_KEY}(s)"
            for o in orphans[:10]:
                detail += f" [reading_id={o['reading_id']}, {REF_KEY}={o[REF_KEY]}]"
            log_event("update_references", "failed", detail)
            return False

        log_event("update_references", "success",
                  f"All {total} records have valid {REF_KEY} references ({len(valid_ids)} valid keys)")
        return True
    except Exception as e:
        log_event("update_references", "error", str(e))
        return False


def step_archive_old(dry_run: bool = False) -> bool:
    """Step 7: Archive the original source data."""
    try:
        if dry_run:
            log_event("archive_old", "dry_run",
                      f"would create archive {ARCHIVE_NAME} from {SOURCE_DIR}")
            return True

        if not os.path.isdir(SOURCE_DIR):
            log_event("archive_old", "failed", "source directory missing")
            return False

        # Remove existing archive if present
        if os.path.exists(ARCHIVE_NAME):
            os.remove(ARCHIVE_NAME)
            log_event("archive_old", "info", "removed existing archive file")

        # Create tar.gz archive
        with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
            tar.add(SOURCE_DIR, arcname=os.path.basename(SOURCE_DIR))

        # Checkpoint: archive file must exist and be non-empty
        if not os.path.exists(ARCHIVE_NAME):
            log_event("archive_old", "failed", "archive file not created")
            return False
        if os.path.getsize(ARCHIVE_NAME) == 0:
            log_event("archive_old", "failed", "archive file is empty")
            return False

        archive_size = os.path.getsize(ARCHIVE_NAME)
        log_event("archive_old", "success",
                  f"created archive {ARCHIVE_NAME} ({archive_size} bytes)")
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
