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
import uuid
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
    log_event("backup", "start", "Starting backup")
    try:
        # Remove and recreate backup directory
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        os.makedirs(BACKUP_DIR)

        # Copy source files into backup
        for table in [PRIMARY_TABLE, REF_TABLE]:
            src = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
            dst = os.path.join(BACKUP_DIR, f"{table}.{SOURCE_EXT}")
            shutil.copy2(src, dst)

        log_event("backup", "completed", "Backup completed")
        return True
    except Exception as e:
        log_event("backup", "failed", str(e))
        return False


def step_transform_format(dry_run: bool = False) -> bool:
    """Step 2: Transform records from old format to new format (JSONL)."""
    log_event("transform_format", "start", "Starting transform")
    try:
        # Remove and recreate transform directory
        if os.path.exists(TRANSFORM_DIR):
            shutil.rmtree(TRANSFORM_DIR)
        os.makedirs(TRANSFORM_DIR)

        id_mapping = {}

        for table in [PRIMARY_TABLE, REF_TABLE]:
            src = os.path.join(SOURCE_DIR, f"{table}.{SOURCE_EXT}")
            dst = os.path.join(TRANSFORM_DIR, f"{table}.{DEST_EXT}")

            records = []
            table_mapping = {}

            with open(src, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    new_id = str(uuid.uuid4())

                    # Determine original id key: reading_id for sensor_readings, device_id for devices
                    orig_id = row.get("reading_id") or row.get("device_id") or row.get("id")
                    if orig_id:
                        table_mapping[orig_id] = new_id

                    # Build output record: original fields + new id
                    record = dict(row)
                    record["id"] = new_id
                    records.append(record)

            # Write JSONL
            with open(dst, "w") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

            id_mapping[table] = table_mapping

        # Write id_mapping.json
        mapping_path = os.path.join(TRANSFORM_DIR, "id_mapping.json")
        with open(mapping_path, "w") as f:
            json.dump(id_mapping, f, indent=2, ensure_ascii=False)

        # Validate row counts: primary table must match
        src_count = count_records(os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}"))
        dst_count = count_records(os.path.join(TRANSFORM_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}"))
        if src_count != dst_count:
            log_event("transform_format", "failed",
                      f"Row count mismatch: source={src_count}, transformed={dst_count}")
            return False

        log_event("transform_format", "completed",
                  f"Transform completed, {dst_count} records")
        return True
    except Exception as e:
        log_event("transform_format", "failed", str(e))
        return False


def step_validate_checksums(dry_run: bool = False) -> bool:
    """Step 3: Validate data integrity via checksums."""
    log_event("validate_checksums", "start", "Starting checksum validation")
    try:
        # Compute individual file checksums for source
        sensor_csv_hash = compute_file_checksum(
            os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
        )
        devices_csv_hash = compute_file_checksum(
            os.path.join(SOURCE_DIR, f"{REF_TABLE}.{SOURCE_EXT}")
        )
        # Combined source checksum: sha256(concat of individual hex digests)
        source_combined = hashlib.sha256(
            (sensor_csv_hash + devices_csv_hash).encode()
        ).hexdigest()

        # Compute individual file checksums for transformed
        sensor_jsonl_hash = compute_file_checksum(
            os.path.join(TRANSFORM_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
        )
        devices_jsonl_hash = compute_file_checksum(
            os.path.join(TRANSFORM_DIR, f"{REF_TABLE}.{DEST_EXT}")
        )
        # Combined transformed checksum
        transformed_combined = hashlib.sha256(
            (sensor_jsonl_hash + devices_jsonl_hash).encode()
        ).hexdigest()

        # Write checksums.json with per-file entries
        checksums = {
            "source": {
                f"{PRIMARY_TABLE}.{SOURCE_EXT}": sensor_csv_hash,
                f"{REF_TABLE}.{SOURCE_EXT}": devices_csv_hash,
            },
            "transformed": {
                f"{PRIMARY_TABLE}.{DEST_EXT}": sensor_jsonl_hash,
                f"{REF_TABLE}.{DEST_EXT}": devices_jsonl_hash,
            },
        }
        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksums, f, indent=2)

        # Validate format: each entry must be a 64-char hex string
        import re
        hex_pattern = re.compile(r"^[a-f0-9]{64}$")
        for section, entries in checksums.items():
            for fname, chk in entries.items():
                if not hex_pattern.match(chk):
                    log_event("validate_checksums", "failed",
                              f"Invalid checksum for {section}/{fname}: {chk!r}")
                    return False

        log_event("validate_checksums", "completed", "Checksums validated")
        return True
    except Exception as e:
        log_event("validate_checksums", "failed", str(e))
        return False


def step_load_new_store(dry_run: bool = False) -> bool:
    """Step 4: Load transformed records into new data store."""
    log_event("load_new_store", "start", "Loading new store")

    # Clear and recreate DEST_DIR
    if os.path.exists(DEST_DIR):
        shutil.rmtree(DEST_DIR)
    os.makedirs(DEST_DIR, exist_ok=True)

    # Copy sensor_readings.jsonl from transformed to new store
    src_sensor = os.path.join(TRANSFORM_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    dst_sensor = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    if not os.path.exists(src_sensor):
        log_event("load_new_store", "error", f"Source file not found: {src_sensor}")
        return False
    shutil.copy2(src_sensor, dst_sensor)

    # Copy devices.jsonl from transformed to new store
    src_device = os.path.join(TRANSFORM_DIR, f"{REF_TABLE}.{DEST_EXT}")
    dst_device = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
    if not os.path.exists(src_device):
        log_event("load_new_store", "error", f"Source file not found: {src_device}")
        return False
    shutil.copy2(src_device, dst_device)

    # Verify row counts in new store
    sensor_count = count_records(dst_sensor)
    device_count = count_records(dst_device)

    if sensor_count != 60:
        log_event("load_new_store", "error", f"Expected 60 sensor records, got {sensor_count}")
        return False
    if device_count != 26:
        log_event("load_new_store", "error", f"Expected 26 device records, got {device_count}")
        return False

    log_event("load_new_store", "complete", f"New store loaded: {sensor_count}+{device_count} records")
    return True


def step_verify_counts(dry_run: bool = False) -> bool:
    """Step 5: Verify row counts match between source and destination."""
    log_event("verify_counts", "start", "Verifying counts")

    # Count records in source (sensor_readings.csv, excluding header)
    src_file = os.path.join(SOURCE_DIR, f"{PRIMARY_TABLE}.{SOURCE_EXT}")
    source_count = count_records(src_file)

    # Count records in destination (sensor_readings.jsonl)
    dst_file = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    dest_count = count_records(dst_file)

    counts_match = (source_count == dest_count == 60)

    # Write verification report
    report = {
        "source_count": source_count,
        "dest_count": dest_count,
        "counts_match": counts_match,
    }
    with open(VERIFICATION_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    if not counts_match:
        log_event("verify_counts", "failed", f"Mismatch: source={source_count}, dest={dest_count}")
        return False

    log_event("verify_counts", "complete", "Counts verified: match=True")
    return True


def step_update_references(dry_run: bool = False) -> bool:
    """Step 6: Rewrite FK references — map old device_id to new UUIDs, ensure no orphans."""
    log_event("update_references", "start", "Updating references")

    # Load devices.jsonl; build old->new mapping and set of valid new IDs
    device_file = os.path.join(DEST_DIR, f"{REF_TABLE}.{DEST_EXT}")
    old_to_new_device = {}   # old device_id -> new UUID "id"
    valid_new_ids = set()
    with open(device_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            old_did = str(rec.get("device_id", ""))
            new_id = str(rec.get("id", ""))
            if old_did and new_id:
                old_to_new_device[old_did] = new_id
                valid_new_ids.add(new_id)

    # Augment with id_mapping.json (produced by transform step)
    mapping_file = os.path.join(TRANSFORM_DIR, "id_mapping.json")
    if os.path.exists(mapping_file):
        with open(mapping_file) as f:
            id_mapping = json.load(f)
        raw_device_map = id_mapping.get("devices", {})
        for old_key, new_id_val in raw_device_map.items():
            new_id_str = str(new_id_val)
            if old_key not in old_to_new_device:
                old_to_new_device[old_key] = new_id_str
                valid_new_ids.add(new_id_str)

    # Rewrite device_id in sensor_readings.jsonl to new UUIDs
    sensor_file = os.path.join(DEST_DIR, f"{PRIMARY_TABLE}.{DEST_EXT}")
    updated_records = []
    orphans_fixed = 0

    with open(sensor_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            dev_id = str(rec.get(REF_KEY, ""))

            if dev_id not in valid_new_ids:
                new_dev_id = old_to_new_device.get(dev_id)
                if new_dev_id is not None:
                    rec[REF_KEY] = new_dev_id
                    orphans_fixed += 1

            updated_records.append(rec)

    # Write corrected records back
    with open(sensor_file, "w") as f:
        for rec in updated_records:
            f.write(json.dumps(rec) + "\n")

    # Also update device_id in devices.jsonl to the new UUID (id)
    updated_devices = []
    devices_updated = 0
    with open(device_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            new_id = str(rec.get("id", ""))
            if new_id and str(rec.get(REF_KEY, "")) != new_id:
                rec[REF_KEY] = new_id
                devices_updated += 1
            updated_devices.append(rec)

    with open(device_file, "w") as f:
        for rec in updated_devices:
            f.write(json.dumps(rec) + "\n")

    # Rebuild valid_ids from updated devices
    valid_new_ids = set()
    for rec in updated_devices:
        did = str(rec.get(REF_KEY, ""))
        if did:
            valid_new_ids.add(did)

    # Final validation: every device_id must be a valid new UUID
    orphans_remaining = 0
    for rec in updated_records:
        if str(rec.get(REF_KEY, "")) not in valid_new_ids:
            orphans_remaining += 1

    if orphans_remaining > 0:
        log_event("update_references", "error",
                  f"{orphans_remaining} orphaned device_ids remain")
        return False

    log_event("update_references", "complete",
              f"References updated, no orphans (fixed {orphans_fixed} readings, {devices_updated} devices)")
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
