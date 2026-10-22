import io

import qrcode
from django.contrib.staticfiles import finders
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H


def make_qr_png(url: str, caption: str = "Scan to Register") -> bytes:
    """QR with high error correction. The logo (if static/img/logo.png exists) covers well under 20% of the width."""
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=14, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111111", back_color="white").convert("RGB")

    logo_file = finders.find("img/favicon.png")
    if logo_file:
        try:
            logo = Image.open(logo_file).convert("RGBA")
            box = int(img.width * 0.18)
            logo.thumbnail((box, box))
            pad = 8
            bg = Image.new("RGB", (logo.width + pad * 2, logo.height + pad * 2), "white")
            x, y = (img.width - bg.width) // 2, (img.height - bg.height) // 2
            img.paste(bg, (x, y))
            img.paste(logo, (x + pad, y + pad), logo)
        except Exception:
            pass  # unreadable logo: the plain QR is still fully scannable

    pad, cap_h = 30, 80
    out = Image.new("RGB", (img.width + pad * 2, img.height + pad * 2 + cap_h), "white")
    out.paste(img, (pad, pad))
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), caption, font=font)
    draw.text(((out.width - (box[2] - box[0])) / 2, img.height + pad + 12), caption, fill="#b5202b", font=font)

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def upi_link(upi_id, name, amount, note):
    from urllib.parse import quote
    return f"upi://pay?pa={quote(upi_id)}&pn={quote(name)}&am={amount}&cu=INR&tn={quote(note[:60])}"
