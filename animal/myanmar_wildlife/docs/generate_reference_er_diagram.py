"""Recreate the supplied logical ERD layout as sharp PNG and SVG artwork."""

from __future__ import annotations

from html import escape
from math import hypot
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent
W, H = 2500, 1840
BLUE = "#346789"
INK = "#17212B"
GRID = "#C7CFD5"
LOGICAL = "#626F78"
WHITE = "#FFFFFF"
SVG = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
im = Image.new("RGB", (W, H), WHITE)
draw = ImageDraw.Draw(im)


def font(size: int, bold=False, serif=False):
    folder = Path("C:/Windows/Fonts")
    name = ("georgiab.ttf" if bold else "georgia.ttf") if serif else ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(folder / name), size)


BODY = font(22)
HEAD = font(24, bold=True)
TITLE = font(38, bold=True, serif=True)
LABEL = font(20, serif=True)
SMALL = font(19)


def text(x, y, value, face=BODY, size=22, color=INK, anchor=None, bold=False, serif=False):
    draw.text((x, y), value, font=face, fill=color, anchor=anchor)
    family = "Georgia" if serif else "Segoe UI"
    weight = "bold" if bold else "normal"
    ax = ' text-anchor="middle"' if anchor and anchor.startswith("m") else ""
    baseline = ' dominant-baseline="middle"' if anchor and anchor.endswith("m") else ""
    SVG.append(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{color}"{ax}{baseline}>{escape(value)}</text>')


def rectangle(x1, y1, x2, y2, fill=WHITE, outline=GRID, width=2, radius=0):
    if radius:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill, outline=outline, width=width)
        SVG.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" rx="{radius}" fill="{fill}" stroke="{outline}" stroke-width="{width}"/>')
    else:
        draw.rectangle((x1, y1, x2, y2), fill=fill, outline=outline, width=width)
        SVG.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="{fill}" stroke="{outline}" stroke-width="{width}"/>')


def line(points, color=INK, width=3, dash=False, arrow=True):
    if dash:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            distance = hypot(x2-x1, y2-y1)
            ux, uy = (x2-x1)/distance, (y2-y1)/distance
            for start in range(0, int(distance), 24):
                end = min(start + 13, distance)
                draw.line((x1+ux*start, y1+uy*start, x1+ux*end, y1+uy*end), fill=color, width=width)
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    points_svg = " ".join(f"{x},{y}" for x, y in points)
    SVG.append(f'<polyline points="{points_svg}" fill="none" stroke="{color}" stroke-width="{width}" stroke-dasharray="13 11"/>' if dash else
               f'<polyline points="{points_svg}" fill="none" stroke="{color}" stroke-width="{width}"/>')
    if arrow:
        x1, y1 = points[-2]
        x2, y2 = points[-1]
        distance = hypot(x2-x1, y2-y1)
        ux, uy = (x2-x1)/distance, (y2-y1)/distance
        bx, by = x2 - ux*18, y2 - uy*18
        triangle = [(x2, y2), (bx - uy*8, by + ux*8), (bx + uy*8, by - ux*8)]
        draw.polygon(triangle, fill=color)
        SVG.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x,y in triangle) + f'" fill="{color}"/>')


def table(x, y, w, title, rows, row_h=39):
    height = 47 + len(rows)*row_h
    rectangle(x, y, x+w, y+height, outline="#54697A", width=2)
    rectangle(x, y, x+w, y+47, fill=BLUE, outline=BLUE, width=1)
    text(x+14, y+10, title, face=HEAD, size=24, color=WHITE, bold=True)
    for i, row in enumerate(rows):
        yy = y+47+i*row_h
        if i:
            line([(x, yy), (x+w, yy)], color=GRID, width=1, arrow=False)
        text(x+14, yy+7, row)
    return x, y, x+w, y+height


text(W//2, 54, "Smart Wildlife Encyclopedia — Logical Database Diagram",
     face=TITLE, size=38, anchor="mt", bold=True, serif=True)

# The boxes follow the position, white background, blue headers, and thin rules
# of the supplied image. All arrows finish exactly on a box border.
table(70, 205, 500, "categories", [
    "PK  id  INTEGER", "name_my  TEXT  NN", "name_en  TEXT  NN",
    "description_my  TEXT", "icon  TEXT",
])
table(70, 615, 500, "animal_aliases", [
    "PK  id  INTEGER", "FK  animal_id  INTEGER  NN", "alias_my  TEXT  NN",
])
table(70, 1050, 500, "animals_fts (FTS5)", [
    "rowid → animals.id", "name_my", "name_en", "scientific_name", "description_my",
])
table(690, 275, 650, "animals", [
    "PK  id  INTEGER", "FK  category_id  INTEGER (nullable)",
    "name_my / name_en  TEXT  NN", "scientific_name / taxon_rank",
    "habitat / description / diet", "IUCN / population fields",
    "legal protection fields", "cover / male / female photos",
    "source IDs, URLs and names", "portal_data / crawled_at",
], row_h=42)
table(1450, 205, 450, "users", [
    "PK  id  INTEGER", "name  TEXT  NN", "email  TEXT  NN  UNIQUE",
    "password_hash  TEXT  NN", "created_at  TEXT  NN", "is_admin  INTEGER  NN",
])
table(1990, 205, 450, "chat_messages", [
    "PK  id  INTEGER", "FK  user_id  INTEGER  NN", "animal_key  TEXT  NN",
    "role  TEXT  NN", "content  TEXT  NN", "created_at  TEXT  NN", "sources  TEXT",
])
table(1450, 800, 450, "embedding_vectors", [
    "PK  model  TEXT", "PK  text_hash  TEXT", "dims  INTEGER  NN",
    "vector  BLOB  NN", "created_at  TEXT  NN",
])
table(1990, 790, 450, "embedding_passages", [
    "PK/FK  model  TEXT", "PK  content_kind  TEXT", "PK  record_key  TEXT",
    "PK  position  INTEGER", "passage_label  TEXT  NN", "FK  text_hash  TEXT  NN",
    "updated_at  TEXT  NN",
])
table(1450, 1310, 450, "embedding_queries", [
    "PK  model  TEXT", "PK  text_hash  TEXT", "dims  INTEGER  NN",
    "vector  BLOB  NN", "created_at  TEXT  NN",
])
rectangle(1990, 1300, 2440, 1555, fill="#F5FAFD", outline="#6D8DA3", width=2, radius=15)
text(2215, 1322, "Local JSON Catalogs", face=HEAD, size=24, anchor="mt", bold=True)
for i, row in enumerate([
    "ecosystems.json", "protected_areas.json", "Import snapshots with stable slugs",
    "Runtime rows: catalog_records", "and catalog_state", "Passages use slug as record_key",
]):
    text(2015, 1367+i*28, row, face=SMALL, size=19)

# Declared foreign-key and derived-index connections.
line([(570, 342), (690, 342)])
text(618, 311, "1 : N", face=LABEL, size=20, serif=True)
line([(690, 593), (570, 682)])
text(606, 614, "1 : N", face=LABEL, size=20, serif=True)
line([(570, 1160), (690, 715)])
text(582, 951, "derived index", face=LABEL, size=20, serif=True)
line([(1900, 340), (1990, 340)])
text(1914, 309, "1 : N", face=LABEL, size=20, serif=True)
line([(1900, 899), (1990, 899)])
text(1914, 868, "1 : N", face=LABEL, size=20, serif=True)

# Logical associations are deliberately dashed, as in the reference image.
line([(1340, 590), (1835, 590), (1990, 520)], color=LOGICAL, dash=True)
text(1534, 559, "logical animal_key", face=LABEL, size=20, color=LOGICAL, serif=True)
line([(1340, 690), (1950, 690), (1950, 850), (1990, 850)], color=LOGICAL, dash=True)
text(1590, 659, "logical record key", face=LABEL, size=20, color=LOGICAL, serif=True)
line([(2215, 1300), (2215, 1110)], color=LOGICAL, dash=True)
text(2234, 1193, "slug key", face=LABEL, size=20, color=LOGICAL, serif=True)

text(W//2, 1748, "PK = Primary Key   FK = Foreign Key   NN = Not Null   ·   Dashed arrows = application-level associations",
     face=SMALL, size=19, anchor="mt")
text(W//2, 1782, "Arrows terminate at table borders. Local JSON files are import snapshots; catalog records are stored in SQLite.",
     face=SMALL, size=19, anchor="mt")

SVG.append("</svg>")
(OUT / "er_diagram_reference_style.svg").write_text("\n".join(SVG), encoding="utf-8")
im.save(OUT / "er_diagram_reference_style.png", optimize=True)
print("Wrote reference-style SVG and PNG")
