from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont


source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/private/tmp/wildlife-doc/template-render")
output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/private/tmp/wildlife-doc/contact-sheets")
output.mkdir(parents=True, exist_ok=True)
pages = sorted(source.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
font = ImageFont.load_default()
thumb_width = 310
label_height = 24
cols = 3
rows = 3

for batch_start in range(0, len(pages), cols * rows):
    batch = pages[batch_start : batch_start + cols * rows]
    thumbs = []
    for path in batch:
        image = Image.open(path).convert("RGB")
        ratio = thumb_width / image.width
        thumb = image.resize((thumb_width, int(image.height * ratio)))
        thumbs.append((path, thumb))
    cell_height = max(thumb.height for _, thumb in thumbs) + label_height
    canvas = Image.new("RGB", (cols * thumb_width, rows * cell_height), "#d6d6d6")
    draw = ImageDraw.Draw(canvas)
    for index, (path, thumb) in enumerate(thumbs):
        x = (index % cols) * thumb_width
        y = (index // cols) * cell_height
        canvas.paste(thumb, (x, y + label_height))
        draw.rectangle((x, y, x + thumb_width, y + label_height), fill="white")
        draw.text((8, y + 6), path.name, fill="black", font=font)
    end_page = batch_start + len(batch)
    canvas.save(output / f"pages-{batch_start + 1:02d}-{end_page:02d}.jpg", quality=88)
