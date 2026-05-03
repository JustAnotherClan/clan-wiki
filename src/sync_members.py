#!/usr/bin/env python3
"""
sync_members.py

Fetch the clan roster from the Clash of Clans API and keep data/members/*.json
in sync. Creates or updates member JSON files and marks missing members as archived.

Requirements:
  - Python 3.8+
  - requests (pip install requests)

Environment variables:
  - COC_API_TOKEN : Clash of Clans API token
  - CLAN_TAG      : Clan tag (include # or URL-encoded)

Run from repository root so paths are relative to the repo.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import requests
from typing import Dict, Any, List

# Ensure Python prints UTF-8 to the console (works on Python 3.7+)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_MEMBERS = REPO_ROOT / "data" / "members"
BACKUP_DIR = DATA_MEMBERS / "_backups"
API_BASE = "https://api.clashofclans.com/v1"

# Read environment
API_TOKEN = os.environ.get("COC_API_TOKEN")
CLAN_TAG = os.environ.get("CLAN_TAG")

if not API_TOKEN:
    print("ERROR: Environment variable COC_API_TOKEN is not set.", flush=True)
    sys.exit(1)

if not CLAN_TAG:
    print("ERROR: Environment variable CLAN_TAG is not set.", flush=True)
    sys.exit(1)

# Normalize clan tag for URL (API expects %23 for #)
def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("#"):
        tag = tag.replace("#", "%23")
    return tag

CLAN_TAG_ENCODED = normalize_tag(CLAN_TAG)

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {API_TOKEN}"
}

# Ensure directories exist
DATA_MEMBERS.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def backup_file(path: Path) -> None:
    if not path.exists():
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"{path.name}.{ts}.bak"
    try:
        dest.write_bytes(path.read_bytes())
    except Exception as e:
        print(f"Warning: failed to backup {path}: {e}", flush=True)

def load_member_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_member_json(path: Path, data: Dict[str, Any]) -> None:
    # Pretty print for readability and preserve Unicode
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def fetch_clan_roster() -> List[Dict[str, Any]]:
    url = f"{API_BASE}/clans/{CLAN_TAG_ENCODED}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 200:
        clan = resp.json()
        members = clan.get("memberList", [])
        return members
    else:
        print(f"ERROR: Failed to fetch clan data: {resp.status_code} {resp.text}", flush=True)
        resp.raise_for_status()

def member_filename_from_tag(tag: str) -> str:
    # Use tag as filename but remove leading # if present
    safe = tag.replace("#", "")
    return f"{safe}.json"

def build_member_record(api_member: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge API member info with existing record while preserving history.
    Fields updated: name, playerTag, townHallLevel, role, lastSeen
    Preserved: history, archived, leftDate (unless rejoined)
    """
    player_tag = api_member.get("tag")
    name = api_member.get("name")
    town_hall = api_member.get("townHallLevel")
    role = api_member.get("role")  # e.g., "member", "coLeader"
    now = now_iso()

    record = existing.copy() if existing else {}

    # Basic fields
    record["playerTag"] = player_tag
    record["name"] = name
    record["townHallLevel"] = town_hall
    record["role"] = role
    record["lastSeen"] = now

    # If this is a new record, ensure history exists
    if "history" not in record or not isinstance(record["history"], list):
        record["history"] = []

    # If previously archived but now present again, un-archive
    if record.get("archived", False):
        record["archived"] = False
        record.pop("leftDate", None)
        record.setdefault("rejoinedDate", now)

    # Keep createdDate if present, otherwise set it
    if "createdDate" not in record:
        record["createdDate"] = now

    return record

def main():
    print("Starting member sync:", datetime.now(timezone.utc).isoformat(), "UTC", flush=True)
    try:
        members = fetch_clan_roster()
    except Exception as e:
        print("Aborting due to fetch error:", e, flush=True)
        sys.exit(1)

    api_tags = set()
    created = []
    updated = []
    unchanged = []
    # Process current members
    for m in members:
        tag = m.get("tag")
        if not tag:
            continue
        api_tags.add(tag)
        filename = DATA_MEMBERS / member_filename_from_tag(tag)
        existing = load_member_json(filename) if filename.exists() else {}
        new_record = build_member_record(m, existing)

        # Decide if update is needed
        needs_write = False
        if not filename.exists():
            needs_write = True
        else:
            # Compare fields
            for key in ("name", "townHallLevel", "role"):
                if existing.get(key) != new_record.get(key):
                    needs_write = True
                    break
            # Update lastSeen always
            needs_write = True

        if needs_write:
            backup_file(filename)
            write_member_json(filename, new_record)
            if filename.exists() and existing:
                updated.append(tag)
            else:
                created.append(tag)
            # Print safely with UTF-8
            try:
                print(f"Saved member: {tag} ({new_record.get('name')})", flush=True)
            except Exception:
                # Fallback: print tag only
                print(f"Saved member: {tag}", flush=True)
        else:
            unchanged.append(tag)

    # Detect archived members (files present but not in API roster)
    stored_files = list(DATA_MEMBERS.glob("*.json"))
    archived = []
    for f in stored_files:
        try:
            data = load_member_json(f)
            tag = data.get("playerTag") or ("#" + f.stem)
            if tag not in api_tags:
                # If already archived, skip
                if data.get("archived"):
                    continue
                # Mark archived
                backup_file(f)
                data["archived"] = True
                data["leftDate"] = now_iso()
                write_member_json(f, data)
                archived.append(tag)
                try:
                    print(f"Archived member: {tag}", flush=True)
                except Exception:
                    print(f"Archived member: {tag}", flush=True)
        except Exception as e:
            print(f"Warning: failed to process stored file {f}: {e}", flush=True)

    # Summary
    print("Sync complete.", flush=True)
    print(f"Members fetched: {len(members)}", flush=True)
    print(f"Created: {len(created)} Updated: {len(updated)} Unchanged: {len(unchanged)} Archived: {len(archived)}", flush=True)
    if created:
        print("Created:", ", ".join(created), flush=True)
    if updated:
        print("Updated:", ", ".join(updated), flush=True)
    if archived:
        print("Archived:", ", ".join(archived), flush=True)

if __name__ == "__main__":
    main()
