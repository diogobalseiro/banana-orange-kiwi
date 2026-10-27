"""
Generation manifest and atomic dataset publication module.
Ensures publication is all-or-nothing, maintains provenance, and allows rollback.
"""

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
SCORER_VERSION = "2.0-biological-reliable"

MANIFEST_FILENAME = "manifest.json"
REJECTED_FILENAME = "last_rejected_candidate.json"

def get_manifest_path(data_dir: str) -> str:
    return os.path.join(data_dir, MANIFEST_FILENAME)

def get_rejected_path(data_dir: str) -> str:
    return os.path.join(data_dir, REJECTED_FILENAME)

def atomic_replace(src_path: str, dst_path: str):
    """
    Atomically replaces dst_path with src_path.
    Guaranteed atomic on POSIX systems when on the same filesystem.
    """
    os.replace(src_path, dst_path)

def atomic_save_json(filepath: str, data: Any):
    """
    Atomically writes JSON data to a file via temporary file and atomic swap.
    """
    dir_name = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_name, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_json_")
    try:
        with open(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        atomic_replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def atomic_save_csv(filepath: str, rows: List[Dict[str, Any]], fieldnames: List[str]):
    """
    Atomically writes CSV rows to a file via temporary file and atomic swap.
    """
    if not rows:
        return
    dir_name = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_name, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_csv_")
    try:
        with open(temp_fd, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            cleaned_rows = []
            for r in rows:
                cleaned = {}
                for fn in fieldnames:
                    v = r.get(fn)
                    if v is None:
                        cleaned[fn] = ""
                    elif isinstance(v, bool):
                        cleaned[fn] = "true" if v else "false"
                    elif isinstance(v, list):
                        cleaned[fn] = "; ".join(str(item) for item in v)
                    else:
                        cleaned[fn] = v
                cleaned_rows.append(cleaned)
            writer.writerows(cleaned_rows)
        atomic_replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def load_manifest(data_dir: str) -> Dict[str, Any]:
    """
    Loads the current active generation manifest, or returns a fresh baseline manifest.
    """
    path = get_manifest_path(data_dir)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Manifest] Warning: could not parse existing manifest: {e}. Creating baseline.")

    # Default manifest
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "scorer_version": SCORER_VERSION,
        "active_generation_id": "initial",
        "last_accepted_timestamp": now_iso,
        "datasets": {},
        "previous_generation_id": None
    }

def save_manifest(data_dir: str, manifest: Dict[str, Any]):
    """
    Atomically persists manifest to data_dir/manifest.json.
    """
    path = get_manifest_path(data_dir)
    atomic_save_json(path, manifest)

def load_last_rejection(data_dir: str) -> Optional[Dict[str, Any]]:
    """
    Loads last rejected candidate diagnostics if present.
    """
    path = get_rejected_path(data_dir)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_snapshot(data_dir: str, dataset_key: str, generation_id: str, data: Any) -> str:
    """
    Saves a snapshot copy of a dataset under data_dir/snapshots/.
    Returns the relative path to the snapshot file.
    """
    snapshots_dir = os.path.join(data_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    filename = f"{generation_id}_{dataset_key}.json"
    filepath = os.path.join(snapshots_dir, filename)
    atomic_save_json(filepath, data)
    return os.path.join("snapshots", filename)

def prune_old_snapshots(data_dir: str, keep_generation_ids: List[str]):
    """
    Prunes snapshots older than the specified generation IDs to avoid unbounded disk growth.
    Keeps at least active and previous generations.
    """
    snapshots_dir = os.path.join(data_dir, "snapshots")
    if not os.path.exists(snapshots_dir):
        return
    valid_prefixes = tuple(f"{gid}_" for gid in keep_generation_ids if gid)
    for fname in os.listdir(snapshots_dir):
        if not fname.endswith(".json"):
            continue
        if not any(fname.startswith(pfx) for pfx in valid_prefixes):
            try:
                os.remove(os.path.join(snapshots_dir, fname))
            except OSError:
                pass

def update_manifest_dataset(manifest: Dict[str, Any], 
                            dataset_key: str, 
                            metadata: Dict[str, Any], 
                            generation_id: str):
    """
    Updates or inserts a dataset snapshot entry in the manifest.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    if manifest.get("active_generation_id") != generation_id:
        manifest["previous_generation_id"] = manifest.get("active_generation_id")
        manifest["active_generation_id"] = generation_id
    manifest["last_accepted_timestamp"] = now_iso
    manifest["scorer_version"] = SCORER_VERSION
    manifest["schema_version"] = SCHEMA_VERSION

    if "datasets" not in manifest:
        manifest["datasets"] = {}

    entry = dict(metadata)
    entry["generation_id"] = generation_id
    if "retrieved_at" not in entry:
        entry["retrieved_at"] = now_iso
    entry["status"] = "accepted"

    manifest["datasets"][dataset_key] = entry

    # If this dataset had a recorded rejection, clear it now that it succeeded
    if manifest.get("last_rejection", {}).get("dataset_key") == dataset_key:
        manifest.pop("last_rejection", None)

def record_rejection(data_dir: str, 
                     dataset_key: str, 
                     candidate_summary: Dict[str, Any], 
                     reason: str,
                     manifest: Optional[Dict[str, Any]] = None):
    """
    Records a rejected candidate with diagnostic reasons for inspection without publishing it.
    """
    rejected_data = {
        "dataset_key": dataset_key,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": reason,
        "candidate_summary": candidate_summary
    }
    rejected_path = get_rejected_path(data_dir)
    try:
        atomic_save_json(rejected_path, rejected_data)
        print(f"[Publication Gate] Candidate rejected. Reason saved to {rejected_path}")
    except Exception as e:
        print(f"[Publication Gate] Warning: could not write rejection log: {e}")

    try:
        if manifest is not None:
            manifest["last_rejection"] = rejected_data
            save_manifest(data_dir, manifest)
        else:
            loaded_manifest = load_manifest(data_dir)
            loaded_manifest["last_rejection"] = rejected_data
            save_manifest(data_dir, loaded_manifest)
    except Exception as e:
        print(f"[Publication Gate] Warning: could not update manifest with rejection: {e}")
