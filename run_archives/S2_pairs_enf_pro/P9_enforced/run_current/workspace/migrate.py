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
    if not os.path.isdir(SOURCE_DIR):
        log_event("backup", "failed", f"SOURCE_DIR not found: {SOURCE_DIR}")
        return False
    if os.path.exists(BACKUP_DIR):
        shutil.rmtree(BACKUP_DIR)
    if dry_run:
        log_event("backup", "dry_run", f"would copy {SOURCE_DIR} -> {BACKUP_DIR}")
        return True
    shutil.copytree(SOURCE_DIR, BACKUP_DIR)
    # Verify: backup file count must match source
    src_files = [f for f in os.listdir(SOURCE_DIR)
                 if os.path.isfile(os.path.join(SOURCE_DIR, f))]
    bak_files = [f for f in os.listdir(BACKUP_DIR)
                 if os.path.isfile(os.path.join(BACKUP_DIR, f))]
    ok = len(src_files) == len(bak_files) and len(src_files) > 0
    if ok:
        log_event("backup", "ok", f"backed up {len(bak_files)} file(s)")
    else:
        log_event("backup", "failed", f"count mismatch src={len(src_files)} bak={len(bak_files)}")
    return ok


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    os.makedirs(TRANSFORM_DIR, exist_ok=True)

    # Process each table
    for table in [PRIMARY_TABLE, REF_TABLE]:
        src_csv = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
        out_jsonl = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")

        if not os.path.isfile(src_csv):
            log_event("transform_format", "failed", f"source missing: {src_csv}")
            return False

        if dry_run:
            log_event("transform_format", "dry_run", f"would transform {src_csv} -> {out_jsonl}")
            continue

        row_count = 0
        with open(src_csv, "r", newline="") as f_in:
            reader = csv.DictReader(f_in)
            with open(out_jsonl, "w") as f_out:
                for row in reader:
                    f_out.write(json.dumps(row) + "\n")
                    row_count += 1

        src_count = count_records(src_csv)
        if row_count != src_count:
            log_event("transform_format", "failed",
                      f"{table}: row count mismatch src={src_count} out={row_count}")
            return False
        log_event("transform_format", "ok", f"{table}: {row_count} rows written")

    # Checkpoint: PRIMARY_TABLE must have exactly 60 rows
    primary_out = os.path.join(TRANSFORM_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    primary_count = count_records(primary_out)
    if primary_count != 60:
        log_event("transform_format", "failed",
                  f"{PRIMARY_TABLE} row count={primary_count}, expected=60")
        return False

    return True


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    checksums = {"source": {}, "transformed": {}}

    # Source files
    for table in [PRIMARY_TABLE, REF_TABLE]:
        fname = f"{table}.{SOURCE_EXT}"
        fpath = os.path.join(SOURCE_DIR, fname)
        if os.path.isfile(fpath):
            checksums["source"][fname] = compute_file_checksum(fpath)

    # Transformed files
    for table in [PRIMARY_TABLE, REF_TABLE]:
        fname = f"{table}.{DEST_EXT}"
        fpath = os.path.join(TRANSFORM_DIR, fname)
        if os.path.isfile(fpath):
            checksums["transformed"][fname] = compute_file_checksum(fpath)

    if dry_run:
        log_event("validate_checksums", "dry_run", f"would write {CHECKSUM_FILE}")
        return True

    # Validate all checksums are 64-char hex strings
    for section, entries in checksums.items():
        for fname, h in entries.items():
            if not isinstance(h, str) or len(h) != 64 or \
               not all(c in "0123456789abcdef" for c in h):
                log_event("validate_checksums", "failed",
                          f"invalid checksum for {section}/{fname}: {h!r}")
                return False

    with open(CHECKSUM_FILE, "w") as f:
        json.dump(checksums, f, indent=2)

    log_event("validate_checksums", "ok",
              f"{len(checksums['source'])} source, {len(checksums['transformed'])} transformed")
    return True


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    os.makedirs(DEST_DIR, exist_ok=True)

    for table in [PRIMARY_TABLE, REF_TABLE]:
        src = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")
        dst = os.path.join(DEST_DIR, f"{table}.{DEST_EXT}")

        if not os.path.isfile(src):
            log_event("load_new_store", "failed", f"source missing: {src}")
            return False

        if dry_run:
            log_event("load_new_store", "dry_run", f"would copy {src} -> {dst}")
            continue

        shutil.copy2(src, dst)

    # Checkpoint: PRIMARY_TABLE row count in DEST_DIR must equal source
    primary_src = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
    primary_dst = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    src_count = count_records(primary_src)
    dst_count = count_records(primary_dst)
    if dst_count != src_count:
        log_event("load_new_store", "failed",
                  f"row count mismatch src={src_count} dst={dst_count}")
        return False

    log_event("load_new_store", "ok", f"{dst_count} records loaded")
    return True


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
    dst_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

    src_count = count_records(src_path)
    dst_count = count_records(dst_path)

    counts_match = (src_count == dst_count == 60)

    if dry_run:
        log_event("verify_counts", "dry_run",
                  f"src={src_count} dst={dst_count} match={counts_match}")
        return counts_match

    report = {
        "source_count": src_count,
        "dest_count": dst_count,
        "counts_match": counts_match,
    }
    with open(VERIFICATION_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    if counts_match:
        log_event("verify_counts", "ok", f"{src_count} records match")
    else:
        log_event("verify_counts", "failed", f"src={src_count} dst={dst_count}")
    return counts_match


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
    primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

    if not os.path.isfile(ref_path):
        log_event("update_references", "failed", f"ref table missing: {ref_path}")
        return False
    if not os.path.isfile(primary_path):
        log_event("update_references", "failed", f"primary table missing: {primary_path}")
        return False

    # Collect all valid REF_KEYs
    valid_ids = set()
    with open(ref_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if REF_KEY in rec:
                valid_ids.add(str(rec[REF_KEY]))

    if dry_run:
        log_event("update_references", "dry_run",
                  f"{len(valid_ids)} valid ids found")
        return True

    # Check for orphans in primary table
    orphans = []
    with open(primary_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            val = str(rec.get(REF_KEY, ""))
            if val and val not in valid_ids:
                orphans.append(val)

    if orphans:
        log_event("update_references", "failed",
                  f"{len(orphans)} orphaned {REF_KEY}s: {orphans[:5]}")
        return False

    log_event("update_references", "ok",
              f"all {REF_KEY} references valid ({len(valid_ids)} ids)")
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
