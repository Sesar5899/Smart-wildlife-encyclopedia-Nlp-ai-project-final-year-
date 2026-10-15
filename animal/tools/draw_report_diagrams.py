from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


OUT = Path("report-assets/diagrams")
OUT.mkdir(parents=True, exist_ok=True)
FONT_DIR = Path("/System/Library/Fonts/Supplemental")
REGULAR = FONT_DIR / "Times New Roman.ttf"
BOLD = FONT_DIR / "Times New Roman Bold.ttf"
ITALIC = FONT_DIR / "Times New Roman Italic.ttf"


def font(size: int, bold: bool = False, italic: bool = False):
    path = BOLD if bold else ITALIC if italic else REGULAR
    return ImageFont.truetype(str(path), size)


def rounded(draw, box, radius=20, fill="white", outline="#202020", width=3):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center_text(draw, xy, text, fnt, fill="#111111", spacing=8):
    box = draw.multiline_textbbox((0, 0), text, font=fnt, align="center", spacing=spacing)
    w = box[2] - box[0]
    h = box[3] - box[1]
    draw.multiline_text((xy[0] - w / 2, xy[1] - h / 2), text, font=fnt, fill=fill, align="center", spacing=spacing)


def wrap_pixels(draw, text: str, fnt, max_width: float) -> str:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), trial, font=fnt)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return "\n".join(lines)


def left_text(draw, xy, text, fnt, fill="#111111", spacing=7):
    draw.multiline_text(xy, text, font=fnt, fill=fill, spacing=spacing)


def arrow(draw, start, end, fill="#222222", width=4, head=14, dashed=False):
    x1, y1 = start
    x2, y2 = end
    if dashed:
        steps = max(1, int(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 / 24))
        for i in range(0, steps, 2):
            a = i / steps
            b = min(1, (i + 1) / steps)
            draw.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * b, y1 + (y2 - y1) * b), fill=fill, width=width)
    else:
        draw.line((x1, y1, x2, y2), fill=fill, width=width)
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    left = (x2 - head * math.cos(angle - 0.55), y2 - head * math.sin(angle - 0.55))
    right = (x2 - head * math.cos(angle + 0.55), y2 - head * math.sin(angle + 0.55))
    draw.polygon((end, left, right), fill=fill)


def architecture():
    img = Image.new("RGB", (2400, 3000), "white")
    d = ImageDraw.Draw(img)
    center_text(d, (1200, 82), "Smart Wildlife Encyclopedia using Retrieval-Augmented Generation & NLP", font(52, bold=True))
    center_text(d, (1200, 145), "System Architecture", font(42, bold=True))

    layers = [
        ("1. Client Layer", ["Desktop / Laptop Browser", "Responsive Member and Admin Interfaces"], "#f5f8fb"),
        ("2. Presentation Layer", ["Jinja2 Templates", "CSS Design System", "JavaScript Search, Chat and Markdown"], "#eef6f1"),
        ("3. Flask Web and\nSecurity Layer", ["Page Routes and JSON APIs", "Signed Sessions and Password Hashing", "Member Access Gate", "Admin RBAC, CSRF and Upload Validation"], "#f7f4ec"),
        ("4. Myanmar NLP and\nRetrieval Layer", ["Unicode Normalization and Syllable Units", "Myanmar-aware Fuzzy / FTS5 Search", "Subject, Scope and Photo Gates", "Passage Builder and Intent Detection", "Lexical Score + Cached Semantic Recall", "Grounded Prompt Builder and SSE Streaming"], "#f2f2fa"),
        ("5. AI and Integration Layer", ["Groq OpenAI-compatible Chat Completions", "OpenAI text-embedding-3-small (Admin Only)", "Catalog Importers and Source Adapters"], "#eef4f8"),
        ("6. Data and Media Layer", ["SQLite Core Tables and Chat History", "FTS5 Search Index", "Local Vector BLOB Cache", "JSON Ecosystem / Protected-Area Catalogs", "Verified Local WebP Photographs"], "#f1f7f2"),
        ("7. Published Sources\nand Delivery", ["Myanmar Biodiversity Portal", "Protected Wildlife List (2020)", "IUCN / Wikidata / GBIF / Wikimedia Sources", "Local Development Server or Production WSGI"], "#f8f3f0"),
    ]
    top = 220
    x1, x2 = 120, 2280
    layer_h = 330
    gap = 50
    for idx, (title, items, fill) in enumerate(layers):
        y1 = top + idx * (layer_h + gap)
        y2 = y1 + layer_h
        rounded(d, (x1, y1, x2, y2), radius=22, fill=fill, outline="#52636f", width=4)
        d.rectangle((x1, y1, x1 + 410, y2), fill="#d9e6ec", outline="#52636f", width=4)
        center_text(d, ((x1 + x1 + 410) / 2, (y1 + y2) / 2), title, font(30, bold=True), spacing=6)
        count = len(items)
        inner_left = x1 + 455
        inner_right = x2 - 45
        cols = 3 if count >= 5 else count
        rows = (count + cols - 1) // cols
        cell_w = (inner_right - inner_left - 30 * (cols - 1)) / cols
        cell_h = (layer_h - 80 - 22 * (rows - 1)) / rows
        for item_i, item in enumerate(items):
            row = item_i // cols
            col = item_i % cols
            bx1 = inner_left + col * (cell_w + 30)
            by1 = y1 + 40 + row * (cell_h + 22)
            bx2 = bx1 + cell_w
            by2 = by1 + cell_h
            rounded(d, (bx1, by1, bx2, by2), radius=15, fill="white", outline="#87949c", width=3)
            item_font = font(22)
            wrapped_item = wrap_pixels(d, item, item_font, cell_w - 34)
            center_text(d, ((bx1 + bx2) / 2, (by1 + by2) / 2), wrapped_item, item_font, spacing=6)
        if idx < len(layers) - 1:
            arrow(d, (1200, y2 + 4), (1200, y2 + gap - 6), fill="#465a63", width=5, head=18)
    img.save(OUT / "system-architecture.png", quality=95)


def actor(draw, x, y, label):
    draw.ellipse((x - 24, y, x + 24, y + 48), outline="#111111", width=4)
    draw.line((x, y + 48, x, y + 130), fill="#111111", width=4)
    draw.line((x - 55, y + 78, x + 55, y + 78), fill="#111111", width=4)
    draw.line((x, y + 130, x - 48, y + 190), fill="#111111", width=4)
    draw.line((x, y + 130, x + 48, y + 190), fill="#111111", width=4)
    center_text(draw, (x, y + 230), label, font(28, bold=True))


def ellipse(draw, center, size, text, fnt=None):
    x, y = center
    w, h = size
    draw.ellipse((x - w / 2, y - h / 2, x + w / 2, y + h / 2), fill="white", outline="#222222", width=3)
    center_text(draw, center, text, fnt or font(24), spacing=5)


def usecase():
    img = Image.new("RGB", (2800, 2050), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((290, 80, 2500, 1960), outline="#111111", width=5)
    center_text(d, (1395, 135), "Smart Wildlife Encyclopedia using Retrieval-Augmented Generation & NLP", font(42, bold=True))

    actor(d, 115, 520, "Visitor")
    actor(d, 115, 1120, "Member")
    actor(d, 2670, 640, "Administrator")
    actor(d, 2670, 1400, "AI Services")

    cases = {
        "landing": ((650, 270), (470, 115), "View public landing page"),
        "auth": ((650, 430), (470, 115), "Register and sign in"),
        "browse": ((680, 660), (510, 125), "Browse species by category"),
        "search": ((680, 830), (510, 125), "Search Myanmar / English names"),
        "detail": ((680, 1000), (510, 125), "View species facts, photos,\nIUCN and legal status"),
        "collections": ((680, 1190), (510, 125), "Browse ecosystems and\nprotected areas"),
        "chat": ((690, 1420), (540, 130), "Ask a species-specific\ngrounded question"),
        "history": ((680, 1620), (510, 120), "View or delete own\nchat history"),
        "sources": ((1340, 1040), (510, 120), "Show source-backed context\nand local photographs"),
        "retrieve": ((1350, 1390), (520, 120), "Normalize, detect intent\nand retrieve passages"),
        "answer": ((1940, 1420), (500, 120), "Stream grounded answer\nwith citations"),
        "admin": ((2060, 360), (470, 115), "Open Content Studio"),
        "publish": ((2010, 560), (540, 125), "Create, edit or delete\npublished records"),
        "upload": ((2010, 750), (540, 125), "Validate and upload\nrecord photographs"),
        "trace": ((2010, 960), (540, 125), "Inspect the 12-stage\nretrieval pipeline"),
        "index": ((2010, 1160), (540, 125), "Build / refresh the\nOpenAI embedding index"),
    }
    for _, (c, s, t) in cases.items():
        ellipse(d, c, s, t)

    def line(a, b, dashed=False, label=None, label_xy=None):
        if dashed:
            arrow(d, a, b, dashed=True, width=3, head=12)
        else:
            d.line((*a, *b), fill="#222222", width=3)
        if label:
            center_text(d, label_xy or ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 18), label, font(21, italic=True))

    for key in ("landing", "auth"):
        line((170, 560), (cases[key][0][0] - cases[key][1][0] / 2, cases[key][0][1]))
    for key in ("browse", "search", "detail", "collections", "chat", "history"):
        line((170, 1160), (cases[key][0][0] - cases[key][1][0] / 2, cases[key][0][1]))
    for key in ("admin", "publish", "upload", "trace", "index"):
        line((2610, 680), (cases[key][0][0] + cases[key][1][0] / 2, cases[key][0][1]))
    line((950, 1420), (1090, 1390), dashed=True, label="<<include>>", label_xy=(1030, 1365))
    line((1610, 1390), (1690, 1420), dashed=True, label="<<include>>", label_xy=(1640, 1355))
    line((940, 1000), (1085, 1040), dashed=True, label="<<include>>", label_xy=(1015, 970))
    line((2280, 1160), (2530, 1380), dashed=True, label="embedding API", label_xy=(2440, 1235))
    line((2190, 1420), (2530, 1420), dashed=True, label="chat API", label_xy=(2370, 1385))
    line((2010, 622), (2010, 687), dashed=True, label="<<include>>", label_xy=(1910, 655))
    line((2010, 1022), (2010, 1097), dashed=True, label="<<extend>>", label_xy=(1900, 1062))

    center_text(d, (1400, 2015), "Figure: Use Case Diagram", font(28))
    img.save(OUT / "use-case-diagram.png", quality=95)


def sequence():
    img = Image.new("RGB", (3200, 2100), "white")
    d = ImageDraw.Draw(img)
    center_text(d, (1600, 55), "Smart Wildlife Encyclopedia — Species-grounded Question Answering", font(42, bold=True))
    names = ["Member", "Browser UI", "Flask API", "Auth / Scope\nGates", "RAG\nRetriever", "SQLite / FTS5 /\nVector Cache", "Groq Chat\nCompletions", "Chat History"]
    xs = [180, 570, 960, 1350, 1740, 2160, 2590, 3000]
    top = 120
    box_w = 300
    box_h = 100
    for x, name in zip(xs, names):
        rounded(d, (x - box_w / 2, top, x + box_w / 2, top + box_h), radius=0, fill="#f8f8f8", outline="#222222", width=3)
        center_text(d, (x, top + box_h / 2), name, font(25, bold=True), spacing=4)
        d.line((x, top + box_h, x, 2010), fill="#555555", width=3)
        for yy in range(top + box_h + 15, 2010, 28):
            d.line((x, yy, x, min(yy + 14, 2010)), fill="white", width=4)

    y = 265
    step = 82
    def msg(a, b, text, dashed=False):
        nonlocal y
        arrow(d, (xs[a], y), (xs[b], y), width=3, head=12, dashed=dashed)
        center_text(d, ((xs[a] + xs[b]) / 2, y - 23), text, font(21), spacing=4)
        y += step

    msg(0, 1, "Open a species chat and submit a question")
    msg(1, 2, "POST /api/animal/{id}/chat")
    msg(2, 3, "Validate session, record and message")
    msg(3, 2, "401 or validation error", dashed=True)
    d.rectangle((355, y - 42, 3150, y + 185), outline="#777777", width=3)
    d.polygon(((355, y - 42), (520, y - 42), (555, y - 12), (355, y - 12)), fill="#eeeeee", outline="#777777")
    left_text(d, (375, y - 35), "alt  [authenticated valid request]", font(20, bold=True))
    msg(2, 3, "Detect different subject / photo / scope intent")
    msg(3, 2, "Deterministic redirect, photo or refusal branch", dashed=True)
    y += 40
    d.rectangle((750, y - 42, 3150, 1910), outline="#777777", width=3)
    d.polygon(((750, y - 42), (1000, y - 42), (1035, y - 12), (750, y - 12)), fill="#eeeeee", outline="#777777")
    left_text(d, (770, y - 35), "else  [species question is in scope]", font(20, bold=True))
    y += 45
    msg(2, 4, "Build labelled passages for the current species")
    msg(4, 5, "Read lexical index and cached vectors")
    msg(5, 4, "FTS candidates, passage vectors and cached query", dashed=True)
    msg(4, 4, "Normalize Myanmar text; score overlap + intent")
    msg(4, 4, "Add semantic recall above threshold; keep lexical order")
    msg(4, 2, "Selected passages, mode and source metadata", dashed=True)
    msg(2, 6, "OpenAI-compatible request with grounded prompt")
    msg(6, 2, "Stream answer deltas", dashed=True)
    msg(2, 7, "Save completed user / assistant exchange")
    msg(7, 2, "Saved timestamp", dashed=True)
    msg(2, 1, "Server-sent events: deltas, sources, done", dashed=True)
    msg(1, 0, "Render Markdown answer, sources and images", dashed=True)
    center_text(d, (1600, 2050), "Figure: Sequence Diagram", font(27))
    img.save(OUT / "sequence-diagram.png", quality=95)


@dataclass
class TableBox:
    title: str
    rows: list[str]
    xy: tuple[int, int]
    width: int


def db_table(draw, item: TableBox):
    x, y = item.xy
    row_h = 42
    header_h = 56
    h = header_h + row_h * len(item.rows)
    draw.rectangle((x, y, x + item.width, y + h), fill="#f7f7f7", outline="#53616a", width=3)
    draw.rectangle((x, y, x + item.width, y + header_h), fill="#386f98", outline="#386f98")
    left_text(draw, (x + 16, y + 11), item.title, font(25, bold=True), fill="white")
    for i, row in enumerate(item.rows):
        yy = y + header_h + i * row_h
        draw.line((x, yy, x + item.width, yy), fill="#d4d9dd", width=2)
        left_text(draw, (x + 14, yy + 9), row, font(20))
    return (x, y, x + item.width, y + h)


def database():
    img = Image.new("RGB", (3200, 2200), "white")
    d = ImageDraw.Draw(img)
    center_text(d, (1600, 55), "Smart Wildlife Encyclopedia — Logical Database Diagram", font(44, bold=True))
    items = [
        TableBox("categories", ["PK  id  INTEGER", "name_my  TEXT NN", "name_en  TEXT NN", "description_my  TEXT", "icon  TEXT"], (80, 180), 620),
        TableBox("animal_aliases", ["PK  id  INTEGER", "FK  animal_id  INTEGER NN", "alias_my  TEXT NN"], (80, 710), 620),
        TableBox("animals_fts (FTS5)", ["rowid → animals.id", "name_my", "name_en", "scientific_name", "description_my"], (80, 1160), 620),
        TableBox("animals", ["PK  id  INTEGER", "FK  category_id  INTEGER", "name_my / name_en  TEXT NN", "scientific_name / taxon_rank", "habitat / description / diet", "IUCN / population fields", "legal protection fields", "cover / male / female photos", "source IDs, URLs and credits", "portal_data / crawled_at"], (840, 310), 760),
        TableBox("users", ["PK  id  INTEGER", "name  TEXT NN", "email  TEXT NN UNIQUE", "password_hash  TEXT NN", "created_at  TEXT NN", "is_admin  INTEGER NN"], (1760, 180), 630),
        TableBox("chat_messages", ["PK  id  INTEGER", "FK  user_id  INTEGER NN", "animal_key  TEXT NN", "role  user|assistant", "content  TEXT NN", "created_at  TEXT NN"], (2490, 180), 630),
        TableBox("embedding_vectors", ["PK  model  TEXT", "PK  text_hash  TEXT", "dims  INTEGER NN", "vector  BLOB NN", "created_at  TEXT NN"], (1760, 900), 630),
        TableBox("embedding_passages", ["PK/FK  model", "PK  content_kind", "PK  record_key", "PK  position", "passage_label  TEXT NN", "FK  text_hash  TEXT NN", "updated_at  TEXT NN"], (2490, 850), 630),
        TableBox("embedding_queries", ["PK  model  TEXT", "PK  text_hash  TEXT", "dims  INTEGER NN", "vector  BLOB NN", "created_at  TEXT NN"], (1760, 1540), 630),
    ]
    boxes = {item.title: db_table(d, item) for item in items}
    # Relationship connectors are routed outside box text areas.
    arrow(d, (700, 330), (840, 390), width=4, head=14)
    center_text(d, (760, 330), "1 : N", font(20, bold=True))
    arrow(d, (700, 790), (840, 660), width=4, head=14)
    center_text(d, (760, 720), "N : 1", font(20, bold=True))
    arrow(d, (700, 1260), (840, 1020), width=4, head=14)
    center_text(d, (760, 1130), "content rowid", font(18))
    arrow(d, (2390, 350), (2490, 350), width=4, head=14)
    center_text(d, (2440, 315), "1 : N", font(20, bold=True))
    arrow(d, (2390, 1060), (2490, 1060), width=4, head=14)
    center_text(d, (2440, 1020), "1 : N", font(20, bold=True))
    # Logical, non-FK association from chats to stable animal key.
    arrow(d, (2490, 520), (1600, 620), width=3, head=12, dashed=True)
    center_text(d, (2050, 545), "logical animal_key", font(18, italic=True))
    # Passage records may refer to the animal table or JSON catalogs.
    arrow(d, (2490, 870), (1600, 780), width=3, head=12, dashed=True)
    center_text(d, (2050, 790), "logical record key", font(18, italic=True))
    rounded(d, (2440, 1580, 3120, 2000), radius=18, fill="#f2f6f8", outline="#607785", width=3)
    center_text(d, (2780, 1630), "Local JSON Catalogs", font(26, bold=True))
    left_text(d, (2480, 1695), "ecosystems.json\nprotected_areas.json\n\nEach record has a stable slug,\nsource URL and local image paths.\nEmbedding passages use the slug\nas record_key.", font(22), spacing=10)
    arrow(d, (2780, 1580), (2780, 1400), width=3, head=12, dashed=True)
    center_text(d, (1600, 2140), "PK = Primary Key, FK = Foreign Key, NN = Not Null; dotted lines are application-level associations.", font(24))
    img.save(OUT / "database-diagram.png", quality=95)


if __name__ == "__main__":
    architecture()
    usecase()
    sequence()
    database()
