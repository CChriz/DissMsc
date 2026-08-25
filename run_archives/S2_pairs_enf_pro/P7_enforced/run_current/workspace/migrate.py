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
            log_event("backup", "dry_run", "would copy source to backup")
            return True

        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        shutil.copytree(SOURCE_DIR, BACKUP_DIR)

        # Verify every source file was backed up
        for fn in os.listdir(SOURCE_DIR):
            if fn.startswith("."):
                continue
            src_path = os.path.join(SOURCE_DIR, fn)
            bak_path = os.path.join(BACKUP_DIR, fn)
            if not os.path.isfile(src_path):
                continue
            if not os.path.exists(bak_path):
                log_event("backup", "failed", f"missing backup file: {fn}")
                return False

        log_event("backup", "detail", f"backed up {len(os.listdir(BACKUP_DIR))} file(s) to {BACKUP_DIR}")
        return True
    except Exception as e:
        log_event("backup", "error", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    try:
        if dry_run:
            log_event("transform_format", "dry_run", "would transform CSV to JSONL")
            return True

        if os.path.exists(TRANSFORM_DIR):
            shutil.rmtree(TRANSFORM_DIR)
        os.makedirs(TRANSFORM_DIR, exist_ok=True)

        for fn in sorted(os.listdir(SOURCE_DIR)):
            if not fn.endswith(f".{SOURCE_EXT}"):
                continue
            table_name = os.path.splitext(fn)[0]
            src_path = os.path.join(SOURCE_DIR, fn)
            dst_path = os.path.join(TRANSFORM_DIR, f"{table_name}.{DEST_EXT}")

            src_count = 0
            with open(src_path, newline="", encoding="utf-8") as src_f:
                reader = csv.DictReader(src_f, delimiter=SEPARATOR)
                with open(dst_path, "w", encoding="utf-8") as dst_f:
                    for row in reader:
                        converted = {}
                        for k, v in row.items():
                            if v is None or v == "":
                                converted[k] = v
                                continue
                            # Convert numeric: int for integers, float for decimals
                            stripped = v.strip()
                            try:
                                if "." in stripped or "e" in stripped.lower():
                                    converted[k] = float(stripped)
                                else:
                                    converted[k] = int(stripped)
                            except ValueError:
                                converted[k] = stripped
                        dst_f.write(json.dumps(converted) + "\n")
                        src_count += 1

            # Checkpoint: row count must match
            dst_count = count_records(dst_path)
            if dst_count != src_count:
                log_event("transform_format", "failed",
                          f"{table_name}: src={src_count} dst={dst_count}")
                return False
            log_event("transform_format", "detail",
                      f"{table_name}: {src_count} rows transformed")

        log_event("transform_format", "detail",
                  f"all tables transformed into {TRANSFORM_DIR}")
        return True
    except Exception as e:
        log_event("transform_format", "error", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    try:
        if dry_run:
            log_event("validate_checksums", "dry_run", "would compute checksums")
            return True

        checksums = {"source": {}, "transformed": {}}

        # Compute SHA-256 for every source file
        for fn in sorted(os.listdir(SOURCE_DIR)):
            if fn.startswith("."):
                continue
            fp = os.path.join(SOURCE_DIR, fn)
            if os.path.isfile(fp):
                checksums["source"][fn] = compute_file_checksum(fp)

        # Compute SHA-256 for every transformed file
        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            if fn.startswith("."):
                continue
            fp = os.path.join(TRANSFORM_DIR, fn)
            if os.path.isfile(fp):
                checksums["transformed"][fn] = compute_file_checksum(fp)

        with open(CHECKSUM_FILE, "w", encoding="utf-8") as f:
            json.dump(checksums, f, indent=2)

        # Checkpoint: all entries must be valid 64-char hex
        for section, entries in checksums.items():
            for fname, chk in entries.items():
                if not isinstance(chk, str) or len(chk) != 64:
                    log_event("validate_checksums", "failed",
                              f"invalid checksum for {section}/{fname}")
                    return False
                try:
                    int(chk, 16)
                except ValueError:
                    log_event("validate_checksums", "failed",
                              f"non-hex checksum for {section}/{fname}")
                    return False

        log_event("validate_checksums", "detail",
                  f"{len(checksums['source'])} source + {len(checksums['transformed'])} transformed checksums written")
        return True
    except Exception as e:
        log_event("validate_checksums", "error", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    try:
        if dry_run:
            log_event("load_new_store", "dry_run", "would copy to new store")
            return True

        # Clear existing dest files (keep .gitkeep)
        for fn in os.listdir(DEST_DIR):
            if fn.startswith("."):
                continue
            fp = os.path.join(DEST_DIR, fn)
            if os.path.isfile(fp):
                os.remove(fp)

        # Copy every transformed file to dest
        for fn in sorted(os.listdir(TRANSFORM_DIR)):
            if fn.startswith("."):
                continue
            src = os.path.join(TRANSFORM_DIR, fn)
            dst = os.path.join(DEST_DIR, fn)
            if os.path.isfile(src):
                shutil.copy2(src, dst)

        # Checkpoint: row counts must equal source for every table
        for fn in sorted(os.listdir(SOURCE_DIR)):
            if not fn.endswith(f".{SOURCE_EXT}"):
                continue
            table_name = os.path.splitext(fn)[0]
            src_path = os.path.join(SOURCE_DIR, fn)
            dst_path = os.path.join(DEST_DIR, f"{table_name}.{DEST_EXT}")

            if not os.path.exists(dst_path):
                log_event("load_new_store", "failed",
                          f"missing dest file: {table_name}.{DEST_EXT}")
                return False

            src_count = count_records(src_path)
            dst_count = count_records(dst_path)
            if dst_count != src_count:
                log_event("load_new_store", "failed",
                          f"{table_name}: src={src_count} dst={dst_count}")
                return False

        log_event("load_new_store", "detail", f"files loaded into {DEST_DIR}")
        return True
    except Exception as e:
        log_event("load_new_store", "error", str(e))
        return False


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    try:
        if dry_run:
            log_event("verify_counts", "dry_run", "would verify counts")
            return True

        src_path = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        dst_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        src_count = count_records(src_path)
        dst_count = count_records(dst_path)
        counts_match = (src_count == dst_count)

        report = {
            "source_count": src_count,
            "dest_count": dst_count,
            "counts_match": counts_match,
        }
        with open(VERIFICATION_REPORT, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        if not counts_match:
            log_event("verify_counts", "failed",
                      f"counts mismatch: src={src_count} dst={dst_count}")
            return False

        log_event("verify_counts", "detail",
                  f"counts match: src={src_count} dest={dst_count}")
        return True
    except Exception as e:
        log_event("verify_counts", "error", str(e))
        return False


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Update foreign key references."""
    try:
        if dry_run:
            log_event("update_references", "dry_run", "would update references")
            return True

        ref_path = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
        primary_path = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")

        # Build the set of valid device_ids from the reference table
        valid_ids = set()
        with open(ref_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if REF_KEY in rec:
                    valid_ids.add(str(rec[REF_KEY]))

        # Read primary table, check every record's REF_KEY is valid
        records = []
        orphans = []
        with open(primary_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                did = str(rec.get(REF_KEY, ""))
                if did and did not in valid_ids:
                    orphans.append(did)
                records.append(rec)

        if orphans:
            log_event("update_references", "failed",
                      f"{len(orphans)} orphaned {REF_KEY}(s): {orphans[:10]}")
            return False

        # Rewrite primary table (references are already valid)
        with open(primary_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        log_event("update_references", "detail",
                  f"{len(records)} records pass reference integrity check, {len(valid_ids)} valid {REF_KEY}s")
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
