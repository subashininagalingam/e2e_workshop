"""Draws a student's name onto a workshop's certificate template. No Django needed: it only uses Pillow."""
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = "LiberationSerif-BoldItalic.ttf"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def available_fonts(font_dir):
    """[(file name, label)] for every .ttf/.otf in the font folder."""
    out = []
    d = Path(font_dir)
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in (".ttf", ".otf"):
                out.append((p.name, p.stem.replace("-", " ")))
    return out


def pretty_name(name: str) -> str:
    """Tidy spacing; fix names typed in ALL CAPS or all lowercase. Mixed case is left alone."""
    name = " ".join(str(name or "").split())
    return name.title() if name and (name.islower() or name.isupper()) else name


def _load_font(font_dir, font_file, size):
    candidates = [font_file, DEFAULT_FONT]
    for f in candidates:
        if f:
            p = Path(font_dir) / Path(f).name  # plain file names only
            if p.is_file():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    pass
    return ImageFont.load_default(size=size)


def render(template_path, name, x_pct=50.0, y_pct=50.0, size_pct=5.0, color="#1f2937", font_file="", font_dir=".",
           max_width_pct=80.0, id_text="", id_x=50.0, id_y=88.0, id_size=1.6):
    """Return a PIL image: the template with `name` centred at (x%, y%) and, if given, the certificate ID.
    The name shrinks to fit the width."""
    with Image.open(template_path) as im:
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            img = Image.new("RGB", rgba.size, (255, 255, 255))
            img.paste(rgba, mask=rgba.split()[3])
        else:
            img = im.convert("RGB")
    w, h = img.size
    color = color if COLOR_RE.match(color or "") else "#1f2937"
    text = pretty_name(name) or " "
    size = max(10, int(w * float(size_pct) / 100))
    font = _load_font(font_dir, font_file, size)
    draw = ImageDraw.Draw(img)
    limit = w * max_width_pct / 100
    while size > 12 and draw.textlength(text, font=font) > limit:
        size = int(size * 0.94)
        font = _load_font(font_dir, font_file, size)
    cx, cy = w * float(x_pct) / 100, h * float(y_pct) / 100
    draw.text((cx, cy), text, font=font, fill=color, anchor="mm")
    id_text = " ".join(str(id_text or "").split())
    if id_text:
        id_font_size = max(8, int(w * float(id_size) / 100))
        id_font = _load_font(font_dir, font_file, id_font_size)
        while id_font_size > 8 and draw.textlength(id_text, font=id_font) > w * 0.6:
            id_font_size = int(id_font_size * 0.94)
            id_font = _load_font(font_dir, font_file, id_font_size)
        draw.text((w * float(id_x) / 100, h * float(id_y) / 100), id_text, font=id_font, fill=color, anchor="mm")
    return img


def to_pdf_bytes(img) -> bytes:
    """One-page PDF sized like A4 (landscape if the certificate is wider than tall)."""
    inches_wide = 11.69 if img.width >= img.height else 8.27
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=img.width / inches_wide)
    return buf.getvalue()


def to_png_bytes(img, max_width=None) -> bytes:
    if max_width and img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def parse_certificate_id(text: str):
    """'E2E/WS/2026/500' -> ('E2E/WS/2026/', 500, 0).  '...-0042' -> ('...-', 42, 4). None if there is no number at the end."""
    m = re.fullmatch(r"(.*?)(\d+)", " ".join(str(text or "").split()))
    if not m:
        return None
    digits = m.group(2)
    return m.group(1), int(digits), (len(digits) if digits.startswith("0") and len(digits) > 1 else 0)
