"""
Bootstrap script for Startup Brain MongoDB setup.
Run once to initialize collections, indexes, and seed the living document.

Usage:
    python scripts/bootstrap.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from pymongo import MongoClient, ASCENDING
    from pymongo.errors import CollectionInvalid
except ImportError:
    print("ERROR: pymongo is not installed. Run: pip install pymongo[srv]")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional here

COLLECTIONS = [
    "sessions",
    "claims",
    "whiteboard_extractions",
    "feedback",
    "book_frameworks",
    "living_document",
    "cost_log",
]

# Standard indexes: (collection, field, index_name)
INDEXES = [
    ("sessions", "created_at", "sessions_created_at"),
    ("sessions", "source_type", "sessions_source_type"),
    ("claims", "session_id", "claims_session_id"),
    ("claims", "created_at", "claims_created_at"),
    ("claims", "source_type", "claims_source_type"),
    ("whiteboard_extractions", "session_id", "whiteboard_session_id"),
    ("whiteboard_extractions", "created_at", "whiteboard_created_at"),
    ("feedback", "source_type", "feedback_source_type"),
    ("feedback", "created_at", "feedback_created_at"),
    ("cost_log", "created_at", "cost_log_created_at"),
]

LIVING_DOC_PATH = Path(__file__).parent.parent / "documents" / "startup_brain.md"


def get_uri() -> str:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        print("ERROR: MONGODB_URI environment variable not set.")
        print("Create a .env file with MONGODB_URI=mongodb+srv://... or set it directly.")
        sys.exit(1)
    return uri


def create_collections(db) -> None:
    print("\n--- Creating collections ---")
    existing = db.list_collection_names()
    for name in COLLECTIONS:
        if name in existing:
            print(f"  [skip] {name} already exists")
        else:
            db.create_collection(name)
            print(f"  [ok]   {name} created")


def create_indexes(db) -> None:
    print("\n--- Creating standard indexes ---")
    for collection_name, field, index_name in INDEXES:
        try:
            db[collection_name].create_index(
                [(field, ASCENDING)],
                name=index_name,
                background=True,
            )
            print(f"  [ok]   {collection_name}.{field} ({index_name})")
        except Exception as e:
            print(f"  [warn] {collection_name}.{field}: {e}")


def print_vector_search_instructions() -> None:
    print("\n--- Atlas Vector Search (OPTIONAL — requires M10+ tier) ---")
    print("""
Vector search is NOT required. The system uses time-based retrieval by default
and monitors claim count — it will alert you when an upgrade is worthwhile
(currently at 200+ claims).

If you upgrade to Atlas M10+ ($57/mo), you can enable Voyage AI automated
embedding for semantic search. Create indexes via the Atlas UI:

1. Go to https://cloud.mongodb.com → your cluster → Search & Vector Search
2. Click "Create Search Index" → "JSON Editor"
3. Select database: startup_brain, collection: claims
4. Index name: claims_vector_index
5. Paste:

{
  "fields": [
    {
      "type": "autoEmbed",
      "path": "claim_text",
      "model": "voyage-4"
    },
    {
      "type": "filter",
      "path": "source_type"
    }
  ]
}

Note: autoEmbed is NOT available on free/flex tier (M0). If you see an error
about tier requirements, skip this step — time-based retrieval works fine.
""")


def seed_living_document(db) -> None:
    print("\n--- Seeding living document ---")
    if not LIVING_DOC_PATH.exists():
        print(f"  [warn] {LIVING_DOC_PATH} not found — skipping seed.")
        return

    content = LIVING_DOC_PATH.read_text(encoding="utf-8")
    collection = db["living_document"]

    existing = collection.find_one({"_id": "startup_brain"})
    if existing:
        print("  [skip] living_document already seeded")
    else:
        collection.update_one(
            {"_id": "startup_brain"},
            {
                "$set": {
                    "content": content,
                    "source_file": "documents/startup_brain.md",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        print(f"  [ok]   living document seeded ({len(content)} chars)")


def main() -> None:
    print("=== Startup Brain Bootstrap ===")
    uri = get_uri()

    print(f"\nConnecting to MongoDB...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        print("  [ok]   Connected successfully")
    except Exception as e:
        print(f"  ERROR: Could not connect: {e}")
        sys.exit(1)

    db = client["startup_brain"]

    create_collections(db)
    create_indexes(db)
    seed_living_document(db)
    print_vector_search_instructions()

    print("\n=== Bootstrap complete ===")
    print("Next steps:")
    print("  1. Create Atlas Vector Search indexes (see instructions above)")
    print("  2. Set ANTHROPIC_API_KEY in your environment or .env file")
    print("  3. Run: streamlit run app/main.py")


if __name__ == "__main__":
    main()
