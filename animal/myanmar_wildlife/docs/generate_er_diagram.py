"""Generate the project ER diagram from the live SQLite schema.

Run from the project directory with: python docs/generate_er_diagram.py
"""

from __future__ import annotations

import sqlite3
from math import hypot
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
DB = ROOT / "wildlife.db"
TABLES = [
    "categories", "animals", "animal_aliases", "users", "chat_messages",
    "embedding_vectors", "embedding_passages", "embedding_queries",
    "catalog_records", "catalog_state",
]
EXPECTED_FKS = {
    ("animals", "category_id", "categories", "id"),
    ("animal_aliases", "animal_id", "animals", "id"),
    ("chat_messages", "user_id", "users", "id"),
    ("embedding_passages", "model", "embedding_vectors", "model"),
    ("embedding_passages", "text_hash", "embedding_vectors", "text_hash"),
}


def schema():
    conn = sqlite3.connect(DB)
    result = {}
    actual_fks = set()
    for table in TABLES:
        result[table] = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not result[table]:
            raise RuntimeError(f"Missing table: {table}")
        for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
            actual_fks.add((table, fk[3], fk[2], fk[4]))
    conn.close()
    if actual_fks != EXPECTED_FKS:
        raise RuntimeError(f"Foreign keys changed: {actual_fks ^ EXPECTED_FKS}")
    return result


def write_mermaid(tables):
    lines = [
        "%% Smart Wildlife Encyclopedia — physical SQLite ER diagram",
        "%% Generated from wildlife.db. Only the four declared FK constraints are edges.",
        "erDiagram",
        '    categories o|--o{ animals : "category_id (nullable)"',
        '    animals ||--o{ animal_aliases : "animal_id"',
        '    users ||--o{ chat_messages : "user_id; cascade delete"',
        '    embedding_vectors ||--o{ embedding_passages : "(model, text_hash); cascade delete"',
        "",
    ]
    fk_cols = {
        "animals": {"category_id"},
        "animal_aliases": {"animal_id"},
        "chat_messages": {"user_id"},
        "embedding_passages": {"model", "text_hash"},
    }
    for table in TABLES:
        lines.append(f"    {table} {{")
        for _, name, data_type, not_null, default, pk in tables[table]:
            markers = []
            if pk:
                markers.append("PK")
            if name in fk_cols.get(table, set()):
                markers.append("FK")
            suffix = " " + ",".join(markers) if markers else ""
            lines.append(f"        {data_type or 'ANY'} {name}{suffix}")
        lines.append("    }")
        lines.append("")
    lines += [
        "%% animals_fts is a derived FTS5 virtual index, not a relational entity.",
        "%% Its content_rowid=id points to animals.id and triggers maintain it.",
        "%% chat_messages.animal_key is an application-level lookup, not a FK:",
        "%%   COALESCE(animals.source_record_id, 'local-animal:' || animals.id).",
        "%% embedding_passages.(content_kind,record_key) resolves to an animal",
        "%%   or catalog record in application code; no SQLite FK enforces it.",
        "%% catalog_state.kind and catalog_records.kind are not linked by a FK.",
    ]
    (OUT / "er_diagram.mmd").write_text("\n".join(lines) + "\n", encoding="utf-8")


W, H = 2500, 2180
NAVY = "#17324D"
BLUE = "#27648A"
CYAN = "#4E9CBA"
INK = "#1B3042"
MUTED = "#536B7D"
BG = "#F5F9FC"
BORDER = "#C5D6E1"
WHITE = "#FFFFFF"


def font(size, bold=False):
    base = Path("C:/Windows/Fonts")
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = base / name
    if not path.exists():
        path = base / ("arialbd.ttf" if bold else "arial.ttf")
    return ImageFont.truetype(str(path), size)


F_TITLE = font(54, True)
F_SUB = font(25)
F_SECTION = font(28, True)
F_HEAD = font(31, True)
F_ROW = font(25)
F_NOTE = font(23)
F_SMALL = font(21)


def card(draw, x, y, w, title, rows, total=None, tint=BLUE):
    row_h = 38
    h = 74 + row_h * len(rows) + (35 if total and total > len(rows) else 0) + 24
    draw.rounded_rectangle((x + 5, y + 7, x + w + 5, y + h + 7), radius=18, fill="#DFE9F0")
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=WHITE, outline=BORDER, width=2)
    draw.rounded_rectangle((x, y, x + w, y + 64), radius=18, fill=tint)
    draw.rectangle((x, y + 35, x + w, y + 64), fill=tint)
    draw.text((x + 24, y + 14), title, font=F_HEAD, fill=WHITE)
    for i, row in enumerate(rows):
        yy = y + 81 + i * row_h
        if i % 2:
            draw.rectangle((x + 2, yy - 2, x + w - 2, yy + row_h - 2), fill="#F4F8FB")
        draw.text((x + 24, yy), row, font=F_ROW, fill=INK)
    if total and total > len(rows):
        draw.text((x + 24, y + 82 + len(rows) * row_h),
                  f"+ {total - len(rows)} more columns in editable source", font=F_SMALL, fill=MUTED)
    return x, y, x + w, y + h


def connector(draw, points, label, label_xy, dashed=False):
    color = MUTED if dashed else BLUE
    if dashed:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            length = hypot(x2 - x1, y2 - y1)
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            for start in range(0, int(length), 27):
                end = min(start + 15, length)
                draw.line((x1 + ux * start, y1 + uy * start,
                           x1 + ux * end, y1 + uy * end), fill=color, width=4)
    else:
        draw.line(points, fill=color, width=5, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    length = hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    size = 17
    base_x, base_y = x2 - ux * size, y2 - uy * size
    draw.polygon([(x2, y2), (base_x - uy * 9, base_y + ux * 9),
                  (base_x + uy * 9, base_y - ux * 9)], fill=color)
    x, y = label_xy
    box = draw.textbbox((x, y), label, font=F_SMALL)
    draw.rounded_rectangle((box[0] - 10, box[1] - 5, box[2] + 10, box[3] + 5),
                           radius=8, fill=WHITE, outline=BORDER, width=1)
    draw.text((x, y), label, font=F_SMALL, fill=color)


def write_png(tables):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 150), fill=NAVY)
    d.text((85, 30), "Smart Wildlife Encyclopedia", font=F_TITLE, fill=WHITE)
    d.text((89, 101), "SQLite entity relationship diagram  |  verified against wildlife.db", font=F_SUB, fill="#CDE8F3")
    d.text((90, 180), "CONTENT AND ACCOUNTS", font=F_SECTION, fill=BLUE)
    d.line((90, 230, 2410, 230), fill=BORDER, width=3)

    card(d, 90, 280, 510, "categories", ["id  INTEGER  PK", "name_my  TEXT  NOT NULL", "name_en  TEXT  NOT NULL", "description_my  TEXT", "icon  TEXT"])
    card(d, 90, 590, 510, "animal_aliases", ["id  INTEGER  PK", "animal_id  INTEGER  FK", "alias_my  TEXT  NOT NULL"])
    card(d, 735, 280, 750, "animals", [
        "id  INTEGER  PK", "category_id  INTEGER  FK, nullable", "name_my  TEXT  NOT NULL",
        "name_en  TEXT  NOT NULL", "scientific_name  TEXT", "source_record_id  TEXT  unique*",
        "linked_name  TEXT  unique*", "portal_data  TEXT (JSON)",
    ], total=len(tables["animals"]))
    card(d, 1740, 280, 665, "users", ["id  INTEGER  PK", "name  TEXT  NOT NULL", "email  TEXT  UNIQUE", "password_hash  TEXT  NOT NULL", "created_at  TEXT  NOT NULL", "is_admin  INTEGER  NOT NULL"])
    card(d, 1740, 650, 665, "chat_messages", ["id  INTEGER  PK", "user_id  INTEGER  FK", "animal_key  TEXT  NOT NULL", "role  TEXT  NOT NULL", "content  TEXT  NOT NULL", "created_at  TEXT  NOT NULL", "sources  TEXT (JSON)"])

    connector(d, [(600, 440), (735, 440)], "1:N", (641, 401))
    connector(d, [(735, 675), (600, 675)], "1:N", (641, 636))
    connector(d, [(2070, 606), (2070, 650)], "1:N", (2090, 607))
    connector(d, [(1485, 610), (1600, 610), (1600, 830), (1740, 830)],
              "animal_key", (1612, 744), dashed=True)
    d.text((90, 1070), "RETRIEVAL AND CATALOGS", font=F_SECTION, fill=BLUE)
    d.line((90, 1120, 2410, 1120), fill=BORDER, width=3)

    card(d, 90, 1170, 610, "embedding_vectors", ["model  TEXT  PK", "text_hash  TEXT  PK", "dims  INTEGER  NOT NULL", "vector  BLOB  NOT NULL", "created_at  TEXT  NOT NULL"])
    card(d, 815, 1170, 735, "embedding_passages", ["model  TEXT  PK, FK", "content_kind  TEXT  PK", "record_key  TEXT  PK", "position  INTEGER  PK", "passage_label  TEXT  NOT NULL", "text_hash  TEXT  FK", "updated_at  TEXT  NOT NULL"])
    card(d, 90, 1530, 610, "embedding_queries", ["model  TEXT  PK", "text_hash  TEXT  PK", "dims  INTEGER  NOT NULL", "vector  BLOB  NOT NULL", "created_at  TEXT  NOT NULL"])
    card(d, 815, 1620, 735, "animals_fts  (derived index)", ["FTS5 virtual table", "content=animals; content_rowid=id", "Maintained by animals triggers"], tint="#5C849B")
    card(d, 1695, 1170, 710, "catalog_records", ["kind  TEXT  PK", "slug  TEXT  PK", "data_json  TEXT  NOT NULL", "updated_at  TEXT  NOT NULL"])
    card(d, 1695, 1500, 710, "catalog_state", ["kind  TEXT  PK", "initialized_at  TEXT  NOT NULL"])
    connector(d, [(700, 1280), (815, 1280)], "1:N", (704, 1237))
    connector(d, [(1180, 717), (1180, 1170)], "animal record key", (1200, 900), dashed=True)
    connector(d, [(1695, 1300), (1550, 1300)], "catalog key", (1565, 1260), dashed=True)
    connector(d, [(2050, 1500), (2050, 1420)], "kind", (2080, 1447), dashed=True)
    connector(d, [(850, 717), (755, 717), (755, 1570), (1180, 1570), (1180, 1620)],
              "search index", (780, 1524), dashed=True)

    d.rounded_rectangle((90, 1950, 2410, 2130), radius=14, fill="#E7F1F7", outline=BORDER, width=2)
    d.text((115, 1967), "Solid arrow = declared SQLite FK, from parent to child (1:N). The category FK is nullable.", font=F_NOTE, fill=INK)
    d.text((115, 2012), "Dashed arrow = application-level association or derived search index; no FK constraint.", font=F_NOTE, fill=INK)
    d.text((115, 2057), "* Unique when non-NULL. Mermaid source contains every database column; this overview shows key fields.", font=F_NOTE, fill=INK)
    im.save(OUT / "er_diagram.png", optimize=True)


if __name__ == "__main__":
    tables = schema()
    write_mermaid(tables)
    write_png(tables)
    print(f"Wrote {OUT / 'er_diagram.mmd'} and {OUT / 'er_diagram.png'}")
