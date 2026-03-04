#!/usr/bin/env python3
"""
One-time migration: Split Startup Brain into Pitch Brain + Ops Brain.

Run: python scripts/migrate_brain_split.py

Actions:
1. Rename living_document._id "startup_brain" → "pitch_brain"
2. Tag all existing claims and sessions with brain="pitch"
3. Seed ops_brain document in MongoDB
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Must set a minimal streamlit context for mongo_client imports
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")


def migrate():
    from pymongo import MongoClient

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        print("ERROR: MONGODB_URI environment variable not set.")
        sys.exit(1)

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client["startup_brain"]

    # 1. Rename living document _id
    old_doc = db["living_document"].find_one({"_id": "startup_brain"})
    if old_doc:
        old_doc["_id"] = "pitch_brain"
        replace_result = db["living_document"].replace_one({"_id": "pitch_brain"}, old_doc, upsert=True)
        if replace_result.upserted_id or replace_result.matched_count:
            db["living_document"].delete_one({"_id": "startup_brain"})
            print("✓ Renamed living_document _id: startup_brain → pitch_brain")
        else:
            print("ERROR: replace_one did not upsert or match — skipping delete for safety")
            sys.exit(1)
    else:
        existing = db["living_document"].find_one({"_id": "pitch_brain"})
        if existing:
            print("· living_document _id already renamed to pitch_brain")
        else:
            print("· No living_document found with _id startup_brain or pitch_brain")

    # 2. Tag existing claims with brain="pitch"
    result = db["claims"].update_many(
        {"brain": {"$exists": False}},
        {"$set": {"brain": "pitch"}},
    )
    print(f"✓ Tagged {result.modified_count} claims with brain=pitch")

    # 3. Tag existing sessions with brain="pitch"
    result = db["sessions"].update_many(
        {"brain": {"$exists": False}},
        {"$set": {"brain": "pitch"}},
    )
    print(f"✓ Tagged {result.modified_count} sessions with brain=pitch")

    # 4. Seed ops_brain document
    ops_brain_path = Path(__file__).parent.parent / "documents" / "ops_brain.md"
    if ops_brain_path.exists():
        with open(ops_brain_path, "r", encoding="utf-8") as f:
            ops_content = f.read()
        db["living_document"].replace_one(
            {"_id": "ops_brain"},
            {"_id": "ops_brain", "content": ops_content, "metadata": {"last_updated": "2026-03-04"}},
            upsert=True,
        )
        print("✓ Seeded ops_brain document in MongoDB")
    else:
        print("· ops_brain.md not found — skipping seed")

    print("\nMigration complete!")


if __name__ == "__main__":
    migrate()
