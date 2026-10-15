import json
import provenance
import re
import sqlite3
import sys
from array import array
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from config import Config

# The application is intentionally runnable from ``myanmar_wildlife/`` (as
# documented in README.md), while the reusable Myanmar text package lives at
# the repository root.  Put that root on the import path for both the Flask
# entry point and direct module/test execution.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from myanmar import (
    Key, contains_myanmar, normalize_mm, phonetic_key, similarity,
    syllable_keys, syllables,
)
from myanmar_places import ecosystem_names_my, protected_area_names_my, region_names_my


# The full search page should be able to show every relevant species; the
# suggestion API applies its own five-result limit.
SEARCH_RESULT_LIMIT = 50
SEARCH_SCORE_THRESHOLD = 0.72
MYANMAR_BASE_LETTERS = re.compile(r"[က-အဿဢ-ဧဩဪ]")
MYANMAR_VOWEL_SIGNS = frozenset("ါာိီုူေဲံ")
# A bare consonant/medial cluster is useful for progressive search, but this
# one otherwise fills the first five suggestions with ကြောင် compounds before
# a member has typed the distinct ောင် vowel ending. Full ကြောင် searches are
# unaffected.
INCOMPLETE_PREFIX_EXCLUSIONS = {
    "ကြ": ("ကြောင်",),
}
ANIMAL_FTS_FIELDS = (
    "name_my", "name_en", "scientific_name", "description_my",
    "iucn_justification_my", "physical_description_my", "habitat_my",
    "diet_my", "distribution_my", "behaviour_my", "threats_my",
    "conservation_actions_my", "conservation_needs_my", "use_trade_my",
    "wild_population_my", "fun_facts_my", "protected_areas_my",
    "ecosystems_my", "kba_my",
)


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _animal_record(row):
    """Return one animal with empty optional database strings normalized."""
    return {
        key: (None if value == "" and key not in {"name_my", "name_en"} else value)
        for key, value in dict(row).items()
    }


def init_db():
    """Initialize database with schema."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_my TEXT NOT NULL,
            name_en TEXT NOT NULL,
            description_my TEXT,
            icon TEXT
        );

        CREATE TABLE IF NOT EXISTS animals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_my TEXT NOT NULL,
            name_en TEXT NOT NULL,
            scientific_name TEXT,
            category_id INTEGER,
            habitat_my TEXT,
            description_my TEXT,
            diet_my TEXT,
            conservation_status TEXT,
            image_url TEXT,
            fun_facts_my TEXT,
            size_my TEXT,
            lifespan_my TEXT,
            region_my TEXT,
            source_record_id TEXT,
            source_url TEXT,
            field_sources TEXT,
            source_name TEXT,
            source_image_url TEXT,
            linked_name TEXT,
            other_name TEXT,
            species_order TEXT,
            species_family TEXT,
            global_iucn_status TEXT,
            population_trend TEXT,
            myanmar_population TEXT,
            global_population TEXT,
            portal_data TEXT,
            crawled_at TEXT,
            protection_status_my TEXT,
            protection_status_en TEXT,
            protection_law_my TEXT,
            protection_basis_my TEXT,
            image_credit TEXT,
            taxon_rank TEXT,
            iucn_justification_my TEXT,
            physical_description_my TEXT,
            distribution_my TEXT,
            behaviour_my TEXT,
            threats_my TEXT,
            conservation_actions_my TEXT,
            conservation_needs_my TEXT,
            use_trade_my TEXT,
            wild_population_my TEXT,
            protected_areas_my TEXT,
            ecosystems_my TEXT,
            kba_my TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS animal_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            animal_id INTEGER NOT NULL,
            alias_my TEXT NOT NULL,
            FOREIGN KEY (animal_id) REFERENCES animals(id)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS animals_fts USING fts5(
            name_my, name_en, scientific_name, description_my,
            content=animals, content_rowid=id
        );

        CREATE TRIGGER IF NOT EXISTS animals_ai AFTER INSERT ON animals BEGIN
            INSERT INTO animals_fts(rowid, name_my, name_en, scientific_name, description_my)
            VALUES (new.id, new.name_my, new.name_en, new.scientific_name, new.description_my);
        END;

        CREATE TRIGGER IF NOT EXISTS animals_ad AFTER DELETE ON animals BEGIN
            INSERT INTO animals_fts(animals_fts, rowid, name_my, name_en, scientific_name, description_my)
            VALUES ('delete', old.id, old.name_my, old.name_en, old.scientific_name, old.description_my);
        END;

        CREATE TRIGGER IF NOT EXISTS animals_au AFTER UPDATE ON animals BEGIN
            INSERT INTO animals_fts(animals_fts, rowid, name_my, name_en, scientific_name, description_my)
            VALUES ('delete', old.id, old.name_my, old.name_en, old.scientific_name, old.description_my);
            INSERT INTO animals_fts(rowid, name_my, name_en, scientific_name, description_my)
            VALUES (new.id, new.name_my, new.name_en, new.scientific_name, new.description_my);
        END;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            animal_key TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            -- The links an answer actually cited, as JSON, for the answers
            -- that did not come from this site's own record.  NULL means the
            -- record answered, and the page's own source list applies.
            sources TEXT,
            model_knowledge INTEGER NOT NULL DEFAULT 0,
            -- Navigation metadata for a hand-over to another catalog record.
            -- Kept as JSON so the redirect button survives a page refresh.
            redirect_data TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_animal_id
        ON chat_messages(user_id, animal_key, id);

        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_recent
        ON chat_messages(user_id, id DESC);

        -- Vector store for semantic retrieval.  Keyed by (model, text hash)
        -- rather than by record, which makes it self-invalidating: an edited
        -- passage hashes differently and simply misses, and switching the
        -- embedding model misses everything.  Nothing has to be purged when
        -- an administrator republishes a record.
        CREATE TABLE IF NOT EXISTS embedding_vectors (
            model TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            dims INTEGER NOT NULL,
            vector BLOB NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (model, text_hash)
        );

        -- Passage-to-record metadata makes the vector cache a complete,
        -- inspectable index for all three content types.  The vector itself is
        -- still deduplicated by text hash, while this table records every place
        -- that text is published.
        CREATE TABLE IF NOT EXISTS embedding_passages (
            model TEXT NOT NULL,
            content_kind TEXT NOT NULL CHECK (
                content_kind IN ('animal', 'ecosystem', 'protected-area')
            ),
            record_key TEXT NOT NULL,
            position INTEGER NOT NULL,
            passage_label TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (model, content_kind, record_key, position),
            FOREIGN KEY (model, text_hash)
                REFERENCES embedding_vectors(model, text_hash) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_embedding_passages_hash
        ON embedding_passages(model, text_hash);

        -- Only administrators may create these cached query vectors.  Member
        -- chat never calls an online embedding service; an exact cached query
        -- can use semantic retrieval and every other query falls back to the
        -- local lexical pipeline.
        CREATE TABLE IF NOT EXISTS embedding_queries (
            model TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            dims INTEGER NOT NULL,
            vector BLOB NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (model, text_hash)
        );

        -- Environmental catalogs use the same SQLite database as species,
        -- accounts, and chat. JSON files are import snapshots only; Content
        -- Studio and member pages both read these rows.
        CREATE TABLE IF NOT EXISTS catalog_records (
            kind TEXT NOT NULL CHECK (kind IN ('ecosystems', 'protected_areas')),
            slug TEXT NOT NULL,
            data_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (kind, slug)
        );

        CREATE TABLE IF NOT EXISTS catalog_state (
            kind TEXT PRIMARY KEY CHECK (kind IN ('ecosystems', 'protected_areas')),
            initialized_at TEXT NOT NULL
        );
    """)

    # Existing databases may predate the FTS table and therefore have content
    # rows without a corresponding search index.  Rebuild is deterministic,
    # cheap for this small catalog, and leaves the triggers to maintain it
    # after startup.
    cursor.execute("INSERT INTO animals_fts(animals_fts) VALUES ('rebuild')")

    # SQLite does not apply new CREATE TABLE columns to an existing database.
    # Keep older local installs forward-compatible without deleting their data.
    animal_columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(animals)").fetchall()
    }
    migrations = {
        "source_record_id": "TEXT",
        "source_url": "TEXT",
        "source_name": "TEXT",
        "source_image_url": "TEXT",
        "linked_name": "TEXT",
        "other_name": "TEXT",
        "species_order": "TEXT",
        "species_family": "TEXT",
        "global_iucn_status": "TEXT",
        "population_trend": "TEXT",
        "myanmar_population": "TEXT",
        "global_population": "TEXT",
        "portal_data": "TEXT",
        "crawled_at": "TEXT",
        "male_image_url": "TEXT",
        "female_image_url": "TEXT",
        "source_urls": "TEXT",
        "field_sources": "TEXT",
        # Legal status under the Protected Wildlife List (2020).  Kept apart
        # from the IUCN columns: a species can be of Least Concern globally and
        # still be totally protected in Myanmar, and only the legal status
        # decides what a member may lawfully do.
        "protection_status_my": "TEXT",
        "protection_status_en": "TEXT",
        "protection_law_my": "TEXT",
        # Why this record is protected: named in the schedule itself, or covered
        # by the family, order or genus the schedule names.
        "protection_basis_my": "TEXT",
        # Photographs imported from Wikimedia Commons carry a licence that
        # requires the photographer to be named wherever the picture is shown.
        "image_credit": "TEXT",
        # Notification 690/2020 protects birds by family, order and genus as
        # well as by species, so a record is not always a species.  NULL means
        # species, which is what every portal record is.
        "taxon_rank": "TEXT",
        # Canonical published content.  ``portal_data`` remains the untouched
        # source snapshot, while these columns are what the editor, public page
        # and AI all read and write.
        "iucn_justification_my": "TEXT",
        "physical_description_my": "TEXT",
        "distribution_my": "TEXT",
        "behaviour_my": "TEXT",
        "threats_my": "TEXT",
        "conservation_actions_my": "TEXT",
        "conservation_needs_my": "TEXT",
        "use_trade_my": "TEXT",
        "wild_population_my": "TEXT",
        "protected_areas_my": "TEXT",
        "ecosystems_my": "TEXT",
        "kba_my": "TEXT",
    }
    added_animal_columns = set()
    for column, column_type in migrations.items():
        if column not in animal_columns:
            cursor.execute(f"ALTER TABLE animals ADD COLUMN {column} {column_type}")
            added_animal_columns.add(column)

    # Backfill the newly introduced published fields once.  Imported JSON is
    # deliberately not consulted during normal reads, otherwise an old source
    # value could silently override an administrator's correction.
    canonical_columns = {
        "iucn_justification_my", "physical_description_my", "distribution_my",
        "behaviour_my", "threats_my", "conservation_actions_my",
        "conservation_needs_my", "use_trade_my", "wild_population_my",
        "protected_areas_my", "ecosystems_my", "kba_my",
    }
    if added_animal_columns & canonical_columns:
        rows = cursor.execute(
            "SELECT id, description_my, fun_facts_my, portal_data FROM animals"
        ).fetchall()
        for row in rows:
            try:
                portal = json.loads(row["portal_data"] or "{}")
            except (TypeError, json.JSONDecodeError):
                portal = {}

            def portal_value(*names):
                for name in names:
                    value = portal.get(name)
                    if value not in (None, "", [], {}):
                        return str(value).strip()
                return None

            justification = portal_value("justification_mm", "justification")
            values = {
                "iucn_justification_my": justification,
                "physical_description_my": portal_value("physical_description"),
                "distribution_my": portal_value("distribution_mm", "distribution"),
                "behaviour_my": portal_value("behaviour"),
                "threats_my": portal_value(
                    "threats_to_survival_mm", "threats_to_survival"
                ),
                "conservation_actions_my": portal_value(
                    "conservation_research_undertaken_mm",
                    "conservation_research_undertaken",
                ),
                "conservation_needs_my": portal_value(
                    "conservation_research_needed_mm",
                    "conservation_research_needed",
                ),
                "use_trade_my": portal_value("use_and_trade_mm", "use_and_trade"),
                "wild_population_my": row["fun_facts_my"] or portal_value(
                    "wild_population_mm", "wild_population"
                ),
                "protected_areas_my": protected_area_names_my(
                    portal_value("in_protected_area")
                ),
                "ecosystems_my": ecosystem_names_my(portal_value("in_ecosytems")),
                "kba_my": protected_area_names_my(portal_value("in_kba")),
            }
            cursor.execute(
                """UPDATE animals SET
                       iucn_justification_my = ?, physical_description_my = ?,
                       distribution_my = ?, behaviour_my = ?, threats_my = ?,
                       conservation_actions_my = ?, conservation_needs_my = ?,
                       use_trade_my = ?, wild_population_my = ?,
                       protected_areas_my = ?, ecosystems_my = ?, kba_my = ?,
                       fun_facts_my = CASE WHEN fun_facts_my = ? THEN NULL ELSE fun_facts_my END,
                       description_my = CASE WHEN description_my = ? THEN NULL ELSE description_my END
                   WHERE id = ?""",
                (
                    values["iucn_justification_my"],
                    values["physical_description_my"],
                    values["distribution_my"], values["behaviour_my"],
                    values["threats_my"], values["conservation_actions_my"],
                    values["conservation_needs_my"], values["use_trade_my"],
                    values["wild_population_my"], values["protected_areas_my"],
                    values["ecosystems_my"], values["kba_my"],
                    values["wild_population_my"], justification, row["id"],
                ),
            )

    if "field_sources" in added_animal_columns:
        for row in cursor.execute("SELECT * FROM animals").fetchall():
            verified = provenance.portal_field_sources(dict(row))
            verified.update(provenance.imported_field_sources(dict(row)))
            if verified:
                cursor.execute(
                    "UPDATE animals SET field_sources = ? WHERE id = ?",
                    (json.dumps(verified, ensure_ascii=False), row["id"]),
                )

    # Expand full-text search to every field an administrator can publish.
    # FTS5 virtual tables cannot be altered, so replace only the index and its
    # maintenance triggers; the animal records themselves are untouched.
    fts_fields = ANIMAL_FTS_FIELDS
    indexed_fields = {
        row["name"] for row in cursor.execute("PRAGMA table_info(animals_fts)")
    }
    if not set(fts_fields).issubset(indexed_fields):
        cursor.executescript(
            """DROP TRIGGER IF EXISTS animals_ai;
               DROP TRIGGER IF EXISTS animals_ad;
               DROP TRIGGER IF EXISTS animals_au;
               DROP TABLE IF EXISTS animals_fts;"""
        )
        fields_sql = ", ".join(fts_fields)
        new_values = ", ".join(f"new.{field}" for field in fts_fields)
        old_values = ", ".join(f"old.{field}" for field in fts_fields)
        cursor.execute(
            f"CREATE VIRTUAL TABLE animals_fts USING fts5("
            f"{fields_sql}, content=animals, content_rowid=id)"
        )
        cursor.executescript(
            f"""CREATE TRIGGER animals_ai AFTER INSERT ON animals BEGIN
                    INSERT INTO animals_fts(rowid, {fields_sql})
                    VALUES (new.id, {new_values});
                END;
                CREATE TRIGGER animals_ad AFTER DELETE ON animals BEGIN
                    INSERT INTO animals_fts(animals_fts, rowid, {fields_sql})
                    VALUES ('delete', old.id, {old_values});
                END;
                CREATE TRIGGER animals_au AFTER UPDATE ON animals BEGIN
                    INSERT INTO animals_fts(animals_fts, rowid, {fields_sql})
                    VALUES ('delete', old.id, {old_values});
                    INSERT INTO animals_fts(rowid, {fields_sql})
                    VALUES (new.id, {new_values});
                END;"""
        )
        cursor.execute("INSERT INTO animals_fts(animals_fts) VALUES ('rebuild')")

    chat_columns = {
        row["name"]
        for row in cursor.execute("PRAGMA table_info(chat_messages)").fetchall()
    }
    if "sources" not in chat_columns:
        cursor.execute("ALTER TABLE chat_messages ADD COLUMN sources TEXT")
    if "model_knowledge" not in chat_columns:
        cursor.execute(
            "ALTER TABLE chat_messages ADD COLUMN model_knowledge INTEGER NOT NULL DEFAULT 0"
        )
    if "redirect_data" not in chat_columns:
        cursor.execute("ALTER TABLE chat_messages ADD COLUMN redirect_data TEXT")

    user_columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(users)").fetchall()
    }
    if "is_admin" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
        )

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS animals_source_record_id_idx "
        "ON animals(source_record_id) WHERE source_record_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS animals_linked_name_idx "
        "ON animals(linked_name) WHERE linked_name IS NOT NULL"
    )

    conn.commit()
    conn.close()


def get_animal_by_id(animal_id):
    """Get single animal by ID."""
    conn = get_db()
    animal = conn.execute(
        """SELECT a.*, c.name_my as category_name_my, c.name_en as category_name_en
           FROM animals a LEFT JOIN categories c ON a.category_id = c.id
           WHERE a.id = ?""", (animal_id,)
    ).fetchone()
    if animal:
        aliases = conn.execute(
            "SELECT alias_my FROM animal_aliases WHERE animal_id = ?",
            (animal_id,)
        ).fetchall()
        animal = _animal_record(animal)
        animal['aliases'] = [row['alias_my'] for row in aliases]
        if animal.get('portal_data'):
            try:
                animal['portal'] = json.loads(animal['portal_data'])
            except (TypeError, json.JSONDecodeError):
                animal['portal'] = {}
        else:
            animal['portal'] = {}
        # The portal names states and protected areas in English only.  Both
        # have exact Myanmar names — the states officially, the protected areas
        # in this site's own cached catalog — so they are resolved on the way
        # out rather than rewritten into the stored source snapshot.
        if animal['portal'].get('in_protected_area'):
            animal['portal']['in_protected_area_my'] = protected_area_names_my(
                animal['portal']['in_protected_area']
            )
        animal['region_my'] = region_names_my(animal.get('region_my'))
        animal['taxon_rank_label_my'] = {
            'species': 'မျိုးစိတ်',
            'genus': 'မျိုးရင်း',
            'subfamily': 'မျိုးရင်းခွဲ',
            'family': 'မိသားစု',
            'order': 'မျိုးစဉ်',
        }.get((animal.get('taxon_rank') or 'species').casefold(), animal.get('taxon_rank'))
        sources = []
        if animal.get('source_urls'):
            try:
                decoded_sources = json.loads(animal['source_urls'])
                if isinstance(decoded_sources, list):
                    sources = [
                        source for source in decoded_sources
                        if isinstance(source, dict) and source.get('url')
                    ]
            except (TypeError, json.JSONDecodeError):
                pass
        if not sources and animal.get('source_url'):
            sources = [{
                'label': animal.get('source_name') or 'Original source',
                'url': animal['source_url'],
            }]
        animal['sources'] = sources
        animal['field_sources'] = provenance.decode_field_sources(
            animal.get('field_sources')
        )
    conn.close()
    return animal


def get_all_animals():
    """Get all animals."""
    conn = get_db()
    animals = conn.execute(
        """SELECT a.*, c.name_my as category_name_my
           FROM animals a LEFT JOIN categories c ON a.category_id = c.id
           ORDER BY a.name_my"""
    ).fetchall()
    conn.close()
    return [_animal_record(a) for a in animals]


def get_animals_by_category(category_id):
    """Get animals by category."""
    conn = get_db()
    animals = conn.execute(
        """SELECT a.*, c.name_my as category_name_my
           FROM animals a LEFT JOIN categories c ON a.category_id = c.id
           WHERE a.category_id = ? ORDER BY a.name_my""",
        (category_id,)
    ).fetchall()
    conn.close()
    return [_animal_record(a) for a in animals]


def get_taxon_members(animal):
    """Species in this catalog that fall inside a taxon-group record.

    Notification 690/2020 protects whole families and orders, so a record such as
    "ခရုစုတ်ငှက်မျိုးများ (Ciconiidae)" is not a species and has no photograph of
    its own; what it can honestly show is the species already published here that
    the entry covers. Matching is by the order and family every record stores,
    plus the genus its scientific name begins with.
    """
    rank = (animal.get("taxon_rank") or "species").casefold()
    taxon = (animal.get("scientific_name") or "").strip()
    if rank == "species" or not taxon:
        return []

    column = {"order": "a.species_order", "family": "a.species_family"}.get(rank)
    conn = get_db()
    if column:
        rows = conn.execute(
            f"""SELECT a.*, c.name_my AS category_name_my
                FROM animals a LEFT JOIN categories c ON a.category_id = c.id
                WHERE a.id != ? AND (a.taxon_rank IS NULL OR a.taxon_rank = 'species')
                  AND {column} = ? COLLATE NOCASE
                ORDER BY a.name_my""",
            (animal["id"], taxon),
        ).fetchall()
    else:
        # Genus and subfamily are not stored on a record, so the genus is read
        # off the scientific name; a subfamily falls back to its parent family,
        # which the group record itself carries.
        prefix = taxon if rank == "genus" else (animal.get("species_family") or "")
        if not prefix:
            conn.close()
            return []
        field = "a.scientific_name" if rank == "genus" else "a.species_family"
        pattern = f"{prefix} %" if rank == "genus" else prefix
        rows = conn.execute(
            f"""SELECT a.*, c.name_my AS category_name_my
                FROM animals a LEFT JOIN categories c ON a.category_id = c.id
                WHERE a.id != ? AND (a.taxon_rank IS NULL OR a.taxon_rank = 'species')
                  AND {field} LIKE ? COLLATE NOCASE
                ORDER BY a.name_my""",
            (animal["id"], pattern),
        ).fetchall()
    conn.close()
    return [_animal_record(row) for row in rows]


def get_animal_count():
    """Total number of species rows currently in the encyclopedia."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) AS count FROM animals").fetchone()["count"]
    conn.close()
    return count


def get_categories():
    """Get all categories with animal counts."""
    conn = get_db()
    categories = conn.execute(
        """SELECT c.*, COUNT(a.id) as animal_count
           FROM categories c LEFT JOIN animals a ON c.id = a.category_id
           GROUP BY c.id ORDER BY c.name_my"""
    ).fetchall()
    conn.close()
    return [dict(c) for c in categories]


ANIMAL_EDITABLE_FIELDS = (
    "name_my", "name_en", "scientific_name", "category_id", "habitat_my",
    "description_my", "diet_my", "conservation_status", "image_url",
    "fun_facts_my", "size_my", "lifespan_my", "region_my", "source_url",
    "source_name", "species_order", "species_family", "global_iucn_status",
    "population_trend", "myanmar_population", "global_population",
    "male_image_url", "female_image_url", "source_urls", "field_sources",
    "protection_status_my", "protection_status_en", "protection_law_my",
    "protection_basis_my", "image_credit", "taxon_rank",
    "iucn_justification_my", "physical_description_my", "distribution_my",
    "behaviour_my", "threats_my", "conservation_actions_my",
    "conservation_needs_my", "use_trade_my", "wild_population_my",
    "protected_areas_my", "ecosystems_my", "kba_my",
)


def save_animal(values, animal_id=None):
    """Create or update an admin-authored species record."""
    payload = {field: values.get(field) for field in ANIMAL_EDITABLE_FIELDS}
    payload["field_sources"] = json.dumps(
        provenance.decode_field_sources(payload.get("field_sources")),
        ensure_ascii=False,
    )
    payload["category_id"] = payload.get("category_id") or None
    aliases = [
        item.strip()
        for item in str(values.get("aliases") or "").replace("၊", ",").split(",")
        if item.strip()
    ]
    conn = get_db()
    try:
        conn.execute("BEGIN")
        if animal_id is None:
            columns = ", ".join(payload)
            placeholders = ", ".join("?" for _ in payload)
            cursor = conn.execute(
                f"INSERT INTO animals ({columns}) VALUES ({placeholders})",
                tuple(payload.values()),
            )
            animal_id = cursor.lastrowid
        else:
            assignments = ", ".join(f"{field} = ?" for field in payload)
            cursor = conn.execute(
                f"UPDATE animals SET {assignments} WHERE id = ?",
                (*payload.values(), animal_id),
            )
            if not cursor.rowcount:
                raise LookupError("Animal not found")
            conn.execute("DELETE FROM animal_aliases WHERE animal_id = ?", (animal_id,))
        conn.executemany(
            "INSERT INTO animal_aliases (animal_id, alias_my) VALUES (?, ?)",
            ((animal_id, alias) for alias in aliases),
        )
        conn.commit()
        return animal_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_external_population_answer(animal_id, answer, sources):
    """Publish one source-backed external population answer into local data.

    Only HTTP(S) pages actually cited by the external-answer flow are stored.
    The generated answer becomes (or is appended to) ``wild_population_my``;
    the same URLs are attached to that field and merged into the animal's
    visible source list in one transaction.
    """
    text = str(answer or "").strip()[:50000]
    if not text:
        return False

    cited = []
    seen_urls = set()
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not url.startswith(("https://", "http://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        cited.append({
            "label": str(source.get("label") or "External source").strip()[:200],
            "url": url,
        })
    if not cited:
        return False

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT wild_population_my, field_sources, source_urls,
                      source_name, source_url
               FROM animals WHERE id = ?""",
            (animal_id,),
        ).fetchone()
        if not row:
            conn.rollback()
            return False

        existing_text = str(row["wild_population_my"] or "").strip()
        if not existing_text:
            population_text = text
        elif text in existing_text:
            population_text = existing_text
        else:
            population_text = f"{existing_text}\n\n{text}"

        try:
            existing_sources = json.loads(row["source_urls"] or "[]")
        except (TypeError, json.JSONDecodeError):
            existing_sources = []
        if not isinstance(existing_sources, list):
            existing_sources = []
        if not existing_sources and row["source_url"]:
            existing_sources = [{
                "label": row["source_name"] or "Original source",
                "url": row["source_url"],
            }]
        merged_sources, source_urls = [], set()
        for source in [*existing_sources, *cited]:
            if not isinstance(source, dict) or not source.get("url"):
                continue
            url = str(source["url"]).strip()
            if url in source_urls:
                continue
            source_urls.add(url)
            merged_sources.append({
                "label": str(source.get("label") or "Source").strip()[:200],
                "url": url,
            })

        field_sources = provenance.decode_field_sources(row["field_sources"])
        previous_urls = field_sources.get("wild_population_my", [])
        field_sources["wild_population_my"] = list(dict.fromkeys([
            *previous_urls,
            *(source["url"] for source in cited),
        ]))

        conn.execute(
            """UPDATE animals
               SET wild_population_my = ?, source_urls = ?, field_sources = ?
               WHERE id = ?""",
            (
                population_text,
                json.dumps(merged_sources, ensure_ascii=False),
                json.dumps(field_sources, ensure_ascii=False),
                animal_id,
            ),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_animal(animal_id):
    """Delete a species and its aliases; return whether a row was removed."""
    conn = get_db()
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM animal_aliases WHERE animal_id = ?", (animal_id,))
        cursor = conn.execute("DELETE FROM animals WHERE id = ?", (animal_id,))
        conn.commit()
        return bool(cursor.rowcount)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fts_query(query):
    """Build a literal, prefix-aware FTS5 query without exposing its syntax."""
    terms = []
    for token in normalize_mm(query).split():
        escaped = token.replace('"', '""')
        if escaped:
            terms.append(f'"{escaped}"*')
    return " AND ".join(terms)


def _fts_matches(conn, query):
    """Return FTS row IDs in BM25 relevance order.

    FTS is an accelerator and content-search signal, not the sole search path:
    SQLite's tokenizer does not understand every Myanmar word boundary, while
    the phonetic index below is deliberately Myanmar-aware.
    """
    expression = _fts_query(query)
    if not expression:
        return {}
    try:
        rows = conn.execute(
            """SELECT rowid, bm25(animals_fts) AS rank
               FROM animals_fts
               WHERE animals_fts MATCH ?
               ORDER BY rank
               LIMIT 50""",
            (expression,),
        ).fetchall()
    except sqlite3.OperationalError:
        # A malformed or unusually punctuated user query must behave like no
        # FTS result; name/alias phonetic matching still runs below.
        return {}
    return {row["rowid"]: position for position, row in enumerate(rows)}


def _literal_contains(query_text, candidate_text):
    """Match normalized text without treating an asat form as its bare base.

    In Unicode, ``က်`` starts with the same code point as ``က``. A plain
    substring check therefore treats the killed consonant ``က်`` as a match
    for the open consonant ``က``. Keep normal prefix/substring behaviour for
    Myanmar spelling completion, but reject an occurrence when the candidate
    immediately extends the query with an asat.
    """
    if not query_text or not candidate_text:
        return False

    start = candidate_text.find(query_text)
    while start != -1:
        end = start + len(query_text)
        if (
            not contains_myanmar(query_text)
            or query_text.endswith("်")
            or end == len(candidate_text)
            or (
                candidate_text[end] != "်"
                and not (
                    query_text[-1] in MYANMAR_VOWEL_SIGNS
                    and candidate_text[end] in MYANMAR_VOWEL_SIGNS
                )
            )
        ):
            return True
        start = candidate_text.find(query_text, start + 1)
    return False


def _literal_startswith(query_text, candidate_text):
    """Return whether the candidate has a boundary-safe literal prefix."""
    if not candidate_text.startswith(query_text):
        return False
    end = len(query_text)
    return (
        not contains_myanmar(query_text)
        or query_text.endswith("်")
        or end == len(candidate_text)
        or (
            candidate_text[end] != "်"
            and not (
                query_text[-1] in MYANMAR_VOWEL_SIGNS
                and candidate_text[end] in MYANMAR_VOWEL_SIGNS
            )
        )
    )


def _literal_fts_match(query_text, animal):
    """Reject matches created only by SQLite splitting Myanmar vowel marks.

    FTS5's default unicode tokenizer does not keep every Myanmar combining mark
    inside a token. For example, ကတိုး can be reduced to a ကတ prefix and
    accidentally match အာဖရိကတိုက်. FTS remains useful for ordering multi-term
    and prefix matches, but every normalized query term must also be present in
    the record's real published text.
    """
    terms = query_text.split()
    if not terms:
        return False
    searchable = normalize_mm(" ".join(
        str(animal.get(field) or "") for field in ANIMAL_FTS_FIELDS
    )).casefold()
    return all(_literal_contains(term, searchable) for term in terms)


def _name_score(query_key, query_text, candidate):
    """Score a name or alias, preserving deterministic exact/prefix priority."""
    if not candidate:
        return 0.0

    candidate_text = normalize_mm(candidate).casefold()
    if not candidate_text:
        return 0.0
    if query_text == candidate_text:
        return 1.0
    if _literal_startswith(query_text, candidate_text):
        return 0.96
    if _literal_contains(query_text, candidate_text):
        return 0.92

    candidate_key = Key(candidate)

    # Do not compare unrelated scripts phonetically.  The Myanmar key is a
    # compact ASCII transcription, so comparing it with a real Latin name can
    # otherwise create accidental substring matches.
    query_is_myanmar = contains_myanmar(query_text)
    if query_is_myanmar != contains_myanmar(candidate_text):
        return 0.0

    if query_is_myanmar:
        # An unfinished Myanmar syllable has too little evidence for a sound
        # match. A short, closed syllable may differ only by ျ/ြ, though:
        # ဖြံ and ဖျံ should find the same animal without opening up other
        # consonant or vowel substitutions for short queries.
        if len(query_text) < 4:
            if (
                len(query_text) >= 3
                and any(medial in query_text for medial in "ျြ")
                and query_text[-1] in "ံ်း့"
            ):
                folded_query = query_text.replace("ြ", "ျ")
                if any(
                    folded_query == syllable.replace("ြ", "ျ")
                    for syllable in syllables(candidate_text)
                ):
                    return 0.95
            return 0.0
        if query_key.strict == candidate_key.strict:
            return 0.99
        if len(query_key.strict) >= 4 and query_key.loose == candidate_key.loose:
            return 0.97

        # Match a complete spoken syllable sequence inside a longer name.
        # A raw substring of the compact phonetic key can cross a syllable
        # boundary and accidentally connect unrelated animal names.
        query_syllables = syllable_keys(query_text)
        candidate_syllables = syllable_keys(candidate_text)
        if len(query_key.strict) >= 4 and query_syllables:
            width = len(query_syllables)
            if any(
                candidate_syllables[index:index + width] == query_syllables
                for index in range(len(candidate_syllables) - width + 1)
            ):
                return 0.95
        return 0.0

    score = similarity(query_key, candidate_key)

    # Latin names can use a partial phonetic score below a real prefix match.
    if (
        len(query_key.strict) >= 4
        and len(query_key.strict) < len(candidate_key.strict)
    ):
        score = max(
            score,
            similarity(query_key, candidate_key, partial=True) * 0.94,
        )
    return score


def _one_edit_away(left, right):
    """Accept one missing, extra, or replaced Unicode character."""
    if abs(len(left) - len(right)) > 1 or left == right:
        return False
    i = j = errors = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        errors += 1
        if errors > 1:
            return False
        if len(left) > len(right):
            i += 1
        elif len(right) > len(left):
            j += 1
        else:
            i += 1
            j += 1
    return errors + (i < len(left)) + (j < len(right)) == 1


def _two_mark_omissions(left, right):
    """Allow two missing vowel/medial/asat marks in a longer name."""
    if abs(len(left) - len(right)) != 2:
        return False
    shorter, longer = sorted((left, right), key=len)
    i = j = missing = 0
    marks = "ာါိီုူေဲံ့း်ျြွှ"
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        elif longer[j] in marks and missing < 2:
            j += 1
            missing += 1
        else:
            return False
    return missing + len(longer) - j == 2 and all(
        character in marks for character in longer[j:]
    )


@lru_cache(maxsize=128)
def _base_sound(character):
    """Use the search phonetic class for one Myanmar base letter."""
    return phonetic_key(character)[:1] or character


def _sound_bases(text):
    return tuple(
        _base_sound(character)
        for character in text
        if MYANMAR_BASE_LETTERS.fullmatch(character)
    )


def _fold_typo_text(text):
    return "".join(
        _base_sound(character) if MYANMAR_BASE_LETTERS.fullmatch(character)
        else "ျ" if character == "ြ" else character
        for character in text
    )


def _myanmar_typo_fragment(query_text, candidate):
    """Find a same-sounding name fragment with at most one mark error."""
    if not contains_myanmar(query_text) or not contains_myanmar(candidate):
        return False
    query_syllables = syllables(query_text)
    candidate_syllables = syllables(candidate)
    query_compact = "".join(query_syllables)
    if len(query_compact) < 3 or not candidate_syllables:
        return False
    query_bases = _sound_bases(query_compact)
    folded_query = _fold_typo_text(query_compact)
    short_query = len(query_compact) < 5 and len(query_bases) < 3
    allow_two_marks = len(query_compact) >= 6 and len(query_bases) >= 3

    for start in range(len(candidate_syllables)):
        if short_query and start:
            break
        fragment = ""
        for index in range(start, len(candidate_syllables)):
            fragment += candidate_syllables[index]
            if len(fragment) > len(query_compact) + (2 if allow_two_marks else 1):
                break
            if short_query and index != len(candidate_syllables) - 1:
                continue
            if _sound_bases(fragment) != query_bases:
                continue
            folded_fragment = _fold_typo_text(fragment)
            if folded_fragment == folded_query:
                return True
            if _one_edit_away(folded_query, folded_fragment):
                return True
            if allow_two_marks and _two_mark_omissions(
                folded_query, folded_fragment
            ):
                return True
    return False


def fuzzy_search_animals(query, limit=SEARCH_RESULT_LIMIT, *, include_content=True):
    """Rank canonical, phonetic, alias and FTS matches as one result set.

    ``limit=None`` returns every match, which is what the Content Studio needs:
    a member browsing suggestions wants the best few, but an administrator
    searching the library must not be shown a silently truncated list.

    ``include_content=False`` is for animal-name autocomplete.  It searches
    canonical names and aliases without suggesting an animal merely because its
    article mentions the query (for example, a bird whose diet includes snakes).
    """
    if not isinstance(query, str):
        return []
    query_text = normalize_mm(query).casefold()
    if not query_text:
        return []

    query_key = Key(query_text)
    conn = get_db()
    try:
        animals = conn.execute(
            """SELECT a.*, c.name_my as category_name_my
               FROM animals a LEFT JOIN categories c ON a.category_id = c.id"""
        ).fetchall()
        aliases = conn.execute(
            "SELECT animal_id, alias_my FROM animal_aliases"
        ).fetchall()
        fts_positions = _fts_matches(conn, query_text) if include_content else {}
    finally:
        conn.close()

    aliases_by_animal = {}
    for alias in aliases:
        aliases_by_animal.setdefault(alias["animal_id"], []).append(alias["alias_my"])

    results = []
    canonical_literal_ids = set()
    exact_canonical_ids = set()
    exact_name_ids = set()
    literal_name_ids = set()
    for row in animals:
        animal = _animal_record(row)
        names = [
            animal.get("name_my"),
            animal.get("name_en"),
            animal.get("scientific_name"),
            *aliases_by_animal.get(animal["id"], []),
        ]
        normalized_names = [
            normalize_mm(name).casefold() for name in names if name
        ]
        normalized_canonical_names = [
            normalize_mm(name).casefold() for name in names[:3] if name
        ]
        if any(
            _literal_contains(query_text, name)
            for name in normalized_canonical_names
        ):
            canonical_literal_ids.add(animal["id"])
        if query_text in normalized_canonical_names:
            exact_canonical_ids.add(animal["id"])
        if query_text in normalized_names:
            exact_name_ids.add(animal["id"])
        if any(_literal_contains(query_text, name) for name in normalized_names):
            literal_name_ids.add(animal["id"])
        name_score = max(
            (_name_score(query_key, query_text, name) for name in names),
            default=0.0,
        )
        best_score = name_score
        match_source = "name"

        if animal["id"] in fts_positions and _literal_fts_match(query_text, animal):
            # BM25 establishes order; keep content below any credible name
            # match.  Position has only a small effect because the catalog is
            # small and name relevance should dominate.
            fts_score = max(0.76, 0.84 - fts_positions[animal["id"]] * 0.002)
            if fts_score > best_score:
                best_score = fts_score
                match_source = "fts"

        # Published detail fields beyond the compact FTS schema remain searchable
        # through canonical containment.
        if include_content:
            for content in (
                animal.get("description_my"),
                animal.get("iucn_justification_my"),
                animal.get("physical_description_my"),
                animal.get("habitat_my"),
                animal.get("diet_my"),
                animal.get("distribution_my"),
                animal.get("behaviour_my"),
                animal.get("threats_my"),
                animal.get("conservation_actions_my"),
                animal.get("conservation_needs_my"),
                animal.get("use_trade_my"),
                animal.get("wild_population_my"),
                animal.get("fun_facts_my"),
                animal.get("protected_areas_my"),
                animal.get("ecosystems_my"),
                animal.get("kba_my"),
            ):
                if content and _literal_contains(
                    query_text, normalize_mm(content).casefold()
                ):
                    if 0.78 > best_score:
                        best_score = 0.78
                        match_source = "content"
                    break

        if best_score >= SEARCH_SCORE_THRESHOLD:
            animal["match_score"] = round(best_score, 4)
            animal["match_source"] = match_source
            results.append(animal)

    # Member-facing name search prefers literal canonical names. Aliases become
    # the primary result only when no canonical name contains the query; exact
    # aliases win over partial aliases, and phonetics remain the final fallback.
    # An exact canonical-name filter below then narrows an unambiguous query;
    # aliases and partial names still work when the query is not itself a full
    # canonical name.
    if not include_content:
        preferred_ids = (
            canonical_literal_ids or exact_name_ids or literal_name_ids
        )
        if preferred_ids:
            results = [animal for animal in results if animal["id"] in preferred_ids]

    # An exact canonical animal name is an unambiguous request for that animal.
    # Do not expand it into longer names that merely contain the same word
    # (ကျား must mean Tiger, not ကျားသစ်/အင်းကျား/သစ်တက်ကျား). Partial-name
    # search remains available whenever there is no exact canonical match.
    if exact_canonical_ids:
        results = [
            animal for animal in results
            if animal["id"] in exact_canonical_ids
        ]

    # For a complete short Myanmar animal term, show only the strongest
    # literal-name tier. This keeps a direct alias or prefix useful without
    # expanding it into every longer compound that happens to contain it:
    # ဆင် -> အာရှဆင် (not ကြံ့ဆင်), ကတိုး -> ကတိုးသမင် (not ကြောင်ကတိုး).
    # A one-letter incremental query remains broad while the member is typing.
    if (
        not include_content
        and not exact_canonical_ids
        and canonical_literal_ids
        and contains_myanmar(query_text)
        and len(query_text) >= 2
        and results
    ):
        strongest_name_score = max(
            animal["match_score"]
            for animal in results
            if animal["match_source"] == "name"
        )
        results = [
            animal for animal in results
            if animal["match_source"] == "name"
            and animal["match_score"] == strongest_name_score
        ]

    excluded_completions = INCOMPLETE_PREFIX_EXCLUSIONS.get(query_text, ())
    if not include_content and excluded_completions:
        results = [
            animal for animal in results
            if not any(
                completion in normalize_mm(animal.get("name_my") or "").casefold()
                for completion in excluded_completions
            )
        ]

    # A canonical exact/prefix or full phonetic-name hit expresses clear user
    # intent.  In that case, description matches only add apparently unrelated
    # animals to suggestions; retain other name/alias matches but suppress FTS
    # and long-content fallbacks.
    if any(
        animal["match_source"] == "name" and animal["match_score"] >= 0.95
        for animal in results
    ):
        results = [animal for animal in results if animal["match_source"] == "name"]

    # A same-sounding consonant sequence may survive one vowel/asat typo.
    # Search names before accepting article-only hits, so a misspelled animal
    # name works in Content Studio as well as member autocomplete.
    if (
        contains_myanmar(query_text)
        and not any(animal["match_source"] == "name" for animal in results)
    ):
        typo_results = []
        for row in animals:
            animal = _animal_record(row)
            names = [
                animal.get("name_my"),
                *aliases_by_animal.get(animal["id"], []),
            ]
            if any(_myanmar_typo_fragment(query_text, name) for name in names if name):
                animal["match_score"] = 0.8
                animal["match_source"] = "typo"
                typo_results.append(animal)
        if typo_results:
            results = typo_results

    results.sort(
        key=lambda animal: (
            -animal["match_score"],
            normalize_mm(animal.get("name_my") or animal.get("name_en") or "").casefold(),
        )
    )
    return results if limit is None else results[:limit]


def search_animals(query, limit=SEARCH_RESULT_LIMIT):
    """Compatibility entry point for the unified Myanmar-aware search."""
    return fuzzy_search_animals(query, limit=limit)


def get_vectors(model, hashes):
    """The cached vectors for these text hashes, as ``{hash: [float, ...]}``.

    Missing hashes are simply absent: the caller embeds those and stores them.
    """
    hashes = list(hashes)
    if not hashes:
        return {}
    conn = get_db()
    try:
        found = {}
        # SQLite caps the number of bound variables, and one record can hold
        # a few dozen passages, so read in chunks rather than one huge IN.
        for start in range(0, len(hashes), 400):
            chunk = hashes[start:start + 400]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"""SELECT text_hash, vector FROM embedding_vectors
                    WHERE model = ? AND text_hash IN ({placeholders})""",
                (model, *chunk),
            ).fetchall()
            for row in rows:
                found[row["text_hash"]] = array("f", row["vector"]).tolist()
        return found
    finally:
        conn.close()


def save_vectors(model, items):
    """Persist ``[(text_hash, vector), ...]`` for one embedding model."""
    if not items:
        return 0
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO embedding_vectors
               (model, text_hash, dims, vector, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (model, text_hash, len(vector), array("f", vector).tobytes(), created_at)
                for text_hash, vector in items
            ],
        )
        conn.commit()
        return len(items)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def vector_store_stats(model):
    """How much of the vector store belongs to one model — for the console."""
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS rows, COALESCE(MAX(dims), 0) AS dims,
                      COALESCE(SUM(LENGTH(vector)), 0) AS bytes
               FROM embedding_vectors WHERE model = ?""",
            (model,),
        ).fetchone()
        return {"rows": row["rows"], "dims": row["dims"], "bytes": row["bytes"]}
    finally:
        conn.close()


def replace_vector_index(model, content_kind, record_key, passages):
    """Replace one record's passage metadata after all vectors are stored.

    ``passages`` is ``[(position, label, text_hash), ...]``.  Keeping this
    operation separate from vector insertion lets identical passages across
    records share one vector without losing per-record completeness data.
    """
    if content_kind not in {"animal", "ecosystem", "protected-area"}:
        raise ValueError("Unknown vector index content kind")
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """DELETE FROM embedding_passages
               WHERE model = ? AND content_kind = ? AND record_key = ?""",
            (model, content_kind, str(record_key)),
        )
        conn.executemany(
            """INSERT INTO embedding_passages
               (model, content_kind, record_key, position, passage_label,
                text_hash, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    model, content_kind, str(record_key), int(position), label,
                    text_hash, updated_at,
                )
                for position, label, text_hash in passages
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def remove_vector_index(model, content_kind, record_key):
    """Remove one deleted or renamed record from the passage index."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """DELETE FROM embedding_passages
               WHERE model = ? AND content_kind = ? AND record_key = ?""",
            (model, content_kind, str(record_key)),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def prune_vector_index(model, valid_records):
    """Drop stale record mappings and unreferenced passage vectors.

    Called only after a successful full index. ``valid_records`` contains
    ``(content_kind, record_key)`` pairs for the complete current catalog.
    """
    valid = {(kind, str(key)) for kind, key in valid_records}
    conn = get_db()
    try:
        conn.execute("BEGIN")
        indexed = conn.execute(
            """SELECT DISTINCT content_kind, record_key
               FROM embedding_passages WHERE model = ?""",
            (model,),
        ).fetchall()
        stale = [
            (row["content_kind"], row["record_key"])
            for row in indexed
            if (row["content_kind"], row["record_key"]) not in valid
        ]
        for content_kind, record_key in stale:
            conn.execute(
                """DELETE FROM embedding_passages
                   WHERE model = ? AND content_kind = ? AND record_key = ?""",
                (model, content_kind, record_key),
            )
        removed_vectors = conn.execute(
            """DELETE FROM embedding_vectors
               WHERE model = ? AND NOT EXISTS (
                   SELECT 1 FROM embedding_passages p
                   WHERE p.model = embedding_vectors.model
                     AND p.text_hash = embedding_vectors.text_hash
               )""",
            (model,),
        ).rowcount
        conn.commit()
        return {"records": len(stale), "vectors": removed_vectors}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_query_vectors(model, hashes):
    """Return cached administrator-created query vectors."""
    hashes = list(hashes)
    if not hashes:
        return {}
    conn = get_db()
    try:
        found = {}
        for start in range(0, len(hashes), 400):
            chunk = hashes[start:start + 400]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"""SELECT text_hash, vector FROM embedding_queries
                    WHERE model = ? AND text_hash IN ({placeholders})""",
                (model, *chunk),
            ).fetchall()
            for row in rows:
                found[row["text_hash"]] = array("f", row["vector"]).tolist()
        return found
    finally:
        conn.close()


def save_query_vectors(model, items):
    """Persist administrator-created query vectors separately from passages."""
    if not items:
        return 0
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO embedding_queries
               (model, text_hash, dims, vector, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (model, text_hash, len(vector), array("f", vector).tobytes(), created_at)
                for text_hash, vector in items
            ],
        )
        conn.commit()
        return len(items)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def vector_index_stats(model):
    """Coverage of the complete passage index, grouped by content type."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT content_kind, COUNT(DISTINCT record_key) AS records,
                      COUNT(*) AS passages
               FROM embedding_passages
               WHERE model = ? GROUP BY content_kind""",
            (model,),
        ).fetchall()
        query_count = conn.execute(
            "SELECT COUNT(*) AS count FROM embedding_queries WHERE model = ?",
            (model,),
        ).fetchone()["count"]
        by_kind = {
            row["content_kind"]: {
                "records": row["records"], "passages": row["passages"]
            }
            for row in rows
        }
        return {
            "indexed_records": sum(item["records"] for item in by_kind.values()),
            "indexed_passages": sum(item["passages"] for item in by_kind.values()),
            "cached_queries": query_count,
            "by_kind": by_kind,
        }
    finally:
        conn.close()


def animal_chat_key(animal):
    """Stable history key that survives a catalog rebuild and row-ID changes."""
    return animal.get("source_record_id") or f"local-animal:{animal['id']}"


def get_chat_history(user_id, animal_key, limit=100):
    """Return one member's species messages in chronological order."""
    limit = max(1, min(int(limit), 200))
    conn = get_db()
    rows = conn.execute(
        """SELECT id, role, content, created_at, sources, model_knowledge, redirect_data
           FROM (
               SELECT id, role, content, created_at, sources, model_knowledge, redirect_data
               FROM chat_messages
               WHERE user_id = ? AND animal_key = ?
               ORDER BY id DESC
               LIMIT ?
           )
           ORDER BY id""",
        (user_id, animal_key, limit),
    ).fetchall()
    conn.close()
    messages = []
    for row in rows:
        message = dict(row)
        message["model_knowledge"] = bool(message["model_knowledge"])
        # Stored as JSON so a reopened thread credits the pages that answered
        # it rather than the record that did not.  Anything unreadable is
        # dropped: the page then falls back to its own source list.
        raw = message.pop("sources", None)
        if raw:
            try:
                decoded = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                decoded = None
            if isinstance(decoded, list):
                message["sources"] = decoded
        raw_redirect = message.pop("redirect_data", None)
        if raw_redirect:
            try:
                decoded_redirect = json.loads(raw_redirect)
            except (TypeError, json.JSONDecodeError):
                decoded_redirect = None
            if isinstance(decoded_redirect, dict):
                message["redirect"] = decoded_redirect
        messages.append(message)
    return messages


def save_chat_exchange(user_id, animal_key, user_content, assistant_content,
                       sources=None, *, model_knowledge=False, redirect=None):
    """Persist a completed user/assistant exchange atomically.

    ``sources`` holds the links actually credited to the answer. An explicit
    empty list records an answer with no verified links. ``model_knowledge``
    distinguishes a general-knowledge answer when the chat is reopened.
    ``redirect`` persists the target used by a catalog hand-over button.
    """
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """INSERT INTO chat_messages
               (user_id, animal_key, role, content, created_at)
               VALUES (?, ?, 'user', ?, ?)""",
            (user_id, animal_key, user_content, created_at),
        )
        conn.execute(
            """INSERT INTO chat_messages
               (user_id, animal_key, role, content, created_at, sources,
                model_knowledge, redirect_data)
               VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)""",
            (
                user_id,
                animal_key,
                assistant_content,
                created_at,
                (
                    json.dumps(sources, ensure_ascii=False)
                    if sources is not None else None
                ),
                int(model_knowledge),
                (
                    json.dumps(redirect, ensure_ascii=False)
                    if redirect is not None else None
                ),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return created_at


def clear_chat_history(user_id, animal_key):
    """Delete only the signed-in member's history for one species."""
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM chat_messages WHERE user_id = ? AND animal_key = ?",
        (user_id, animal_key),
    )
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted


def get_recent_chat_threads(user_id, limit=6):
    """Summarize the member's most recently active species threads."""
    limit = max(1, min(int(limit), 20))
    conn = get_db()
    rows = conn.execute(
        """WITH latest AS (
               SELECT animal_key, MAX(id) AS last_message_id, COUNT(*) AS message_count
               FROM chat_messages
               WHERE user_id = ?
               GROUP BY animal_key
           )
           SELECT
               a.id AS animal_id,
               a.name_my,
               a.name_en,
               a.image_url,
               latest.message_count,
               -- Enough of the reply that a Markdown table can be stripped
               -- off it and a readable snippet still remains.
               substr(message.content, 1, 400) AS last_message,
               message.created_at AS updated_at
           FROM latest
           JOIN chat_messages message ON message.id = latest.last_message_id
           JOIN animals a
             ON latest.animal_key = COALESCE(a.source_record_id, 'local-animal:' || a.id)
           ORDER BY latest.last_message_id DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_animals_with_aliases():
    """Every species together with the names it may be called by.

    Name matching across the site — search suggestions and chat scoping —
    needs the aliases alongside the canonical names, in one read.
    """
    conn = get_db()
    animals = conn.execute(
        """SELECT a.*, c.name_my as category_name_my
           FROM animals a LEFT JOIN categories c ON a.category_id = c.id"""
    ).fetchall()
    aliases = conn.execute("SELECT animal_id, alias_my FROM animal_aliases").fetchall()
    conn.close()

    aliases_by_animal = {}
    for alias in aliases:
        aliases_by_animal.setdefault(alias["animal_id"], []).append(alias["alias_my"])

    records = []
    for row in animals:
        animal = _animal_record(row)
        animal["aliases"] = aliases_by_animal.get(animal["id"], [])
        records.append(animal)
    return records


def create_user(name, email, password_hash, is_admin=False):
    """Create a new user."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO users (name, email, password_hash, created_at, is_admin)
               VALUES (?, ?, ?, ?, ?)""",
            (
                name, email, password_hash,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                int(bool(is_admin)),
            )
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user_by_email(email):
    """Get user by email."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    """Get user by ID."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def set_user_admin(user_id, is_admin=True):
    """Explicitly grant or revoke publishing access for an account."""
    conn = get_db()
    cursor = conn.execute(
        "UPDATE users SET is_admin = ? WHERE id = ?", (int(bool(is_admin)), user_id)
    )
    conn.commit()
    changed = bool(cursor.rowcount)
    conn.close()
    return changed


def get_catalog_records(kind):
    """Return one environmental catalog from SQLite."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT data_json FROM catalog_records WHERE kind = ? ORDER BY slug",
            (kind,),
        ).fetchall()
        initialized = conn.execute(
            "SELECT 1 FROM catalog_state WHERE kind = ?", (kind,)
        ).fetchone()
        return [json.loads(row["data_json"]) for row in rows], bool(initialized)
    finally:
        conn.close()


def seed_catalog_records(kind, records):
    """Import a committed JSON snapshot once; never overwrite live edits."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        if conn.execute(
            "SELECT 1 FROM catalog_state WHERE kind = ?", (kind,)
        ).fetchone():
            return False
        conn.executemany(
            """INSERT INTO catalog_records (kind, slug, data_json, updated_at)
               VALUES (?, ?, ?, ?)""",
            [
                (kind, record["slug"], json.dumps(record, ensure_ascii=False), now)
                for record in records
            ],
        )
        conn.execute(
            "INSERT INTO catalog_state (kind, initialized_at) VALUES (?, ?)",
            (kind, now),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def replace_catalog_records(kind, records):
    """Replace a catalog during an explicit importer refresh."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute("DELETE FROM catalog_records WHERE kind = ?", (kind,))
        conn.executemany(
            """INSERT INTO catalog_records (kind, slug, data_json, updated_at)
               VALUES (?, ?, ?, ?)""",
            [
                (kind, record["slug"], json.dumps(record, ensure_ascii=False), now)
                for record in records
            ],
        )
        conn.execute(
            """INSERT INTO catalog_state (kind, initialized_at) VALUES (?, ?)
               ON CONFLICT(kind) DO UPDATE SET initialized_at = excluded.initialized_at""",
            (kind, now),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_catalog_record(kind, record, original_slug=None):
    """Atomically publish one Content Studio record."""
    slug = record["slug"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        collision = conn.execute(
            "SELECT 1 FROM catalog_records WHERE kind = ? AND slug = ?",
            (kind, slug),
        ).fetchone()
        if collision and slug != original_slug:
            raise ValueError("That slug is already in use")
        if original_slug and original_slug != slug:
            conn.execute(
                "DELETE FROM catalog_records WHERE kind = ? AND slug = ?",
                (kind, original_slug),
            )
        conn.execute(
            """INSERT INTO catalog_records (kind, slug, data_json, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(kind, slug) DO UPDATE SET
                   data_json = excluded.data_json,
                   updated_at = excluded.updated_at""",
            (kind, slug, json.dumps(record, ensure_ascii=False), now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_catalog_record(kind, slug):
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM catalog_records WHERE kind = ? AND slug = ?", (kind, slug)
        )
        conn.commit()
        return bool(cursor.rowcount)
    finally:
        conn.close()
