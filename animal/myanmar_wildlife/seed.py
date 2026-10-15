"""Restore the verified Myanmar Biodiversity crawl on a fresh database."""

from crawler import CACHE_PATH, import_records, load_cache
from db import get_db, init_db


def seed_data() -> None:
    init_db()
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) AS count FROM animals").fetchone()["count"]
    conn.close()

    if count:
        return
    if not CACHE_PATH.exists():
        print("No cached portal data found. Run: python crawler.py")
        return

    records = load_cache()
    import_records(records, backup=False)
    print(f"Restored {len(records)} Myanmar Biodiversity Portal records from cache.")


if __name__ == "__main__":
    seed_data()
