from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def _one_line(s):
    return " ".join(str(s).split())


def _joining(reg, w):
    if w.mode == "online" or reg.get("participation_mode") == "online":
        return f"Join link: {w.meeting_link}" if w.meeting_link else "The joining link will be shared before the workshop."
    return f"Venue: {w.venue}" if w.venue else ""


def _send(subject, template, ctx, to):
    html = render_to_string(template, ctx)
    msg = EmailMultiAlternatives(
        subject=_one_line(subject), body=strip_tags(html), from_email=settings.DEFAULT_FROM_EMAIL, to=[to],
        reply_to=[settings.ORG["email"]] if settings.ORG.get("email") else None,
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def send_all(reg: dict, w) -> str:
    """Send the student email, then the admin notice. Returns the status text stored in Excel. Never raises."""
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        return "failed: Email is not configured"
    ctx = {"reg": reg, "w": w, "ORG": settings.ORG, "joining": _joining(reg, w), "SITE_URL": settings.SITE_URL}
    try:
        _send(f"Registration Confirmed – {w.title}", "emails/student.html", ctx, reg["email"])
    except Exception as e:  # network, auth, bad address...
        return f"failed: {str(e)[:120]}"
    if settings.ADMIN_NOTIFY_EMAIL:
        try:
            _send(f"New Workshop Registration – {w.title}", "emails/admin.html", ctx, settings.ADMIN_NOTIFY_EMAIL)
        except Exception as e:
            return f"sent (admin notice failed: {str(e)[:80]})"
    return "sent"


def _require_email():
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        raise RuntimeError("Email is not configured")


def send_certificate(reg: dict, w, pdf: bytes, filename: str, to=None):
    """Email a student's certificate (PDF attached). Raises if it cannot be sent."""
    _require_email()
    ctx = {"reg": reg, "w": w, "ORG": settings.ORG, "SITE_URL": settings.SITE_URL}
    html = render_to_string("emails/certificate.html", ctx)
    msg = EmailMultiAlternatives(
        subject=_one_line(f"Your certificate - {w.title}"), body=strip_tags(html), from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to or reg["email"]], reply_to=[settings.ORG["email"]] if settings.ORG.get("email") else None,
    )
    msg.attach_alternative(html, "text/html")
    msg.attach(filename, pdf, "application/pdf")
    msg.send(fail_silently=False)


def send_announcement(w, name: str, email: str, unsubscribe_url: str, subject: str = "", message: str = "",
                      attachments=()):
    """Tell a past student about a new workshop. `attachments` is [(file name, bytes, mime type)].
    `{name}` in the message is replaced by the student's name. Raises if it cannot be sent."""
    _require_email()
    register_url = f"{settings.SITE_URL}/register/?w={w.slug}"
    poster = f"{settings.SITE_URL}{w.poster.url}" if w.poster else ""
    message = (message or "").replace("{name}", name or "there").strip()
    ctx = {"name": name, "w": w, "ORG": settings.ORG, "register_url": register_url, "poster_url": poster,
           "unsubscribe_url": unsubscribe_url, "SITE_URL": settings.SITE_URL, "message": message,
           "has_attachments": bool(attachments)}
    html = render_to_string("emails/announce.html", ctx)
    text = strip_tags(html) + f"\n\nRegister: {register_url}\nStop these emails: {unsubscribe_url}"
    msg = EmailMultiAlternatives(
        subject=_one_line(subject or f"New workshop: {w.title} - {w.start_datetime:%d %b %Y}"), body=text,
        from_email=settings.DEFAULT_FROM_EMAIL, to=[email],
        reply_to=[settings.ORG["email"]] if settings.ORG.get("email") else None,
    )
    msg.attach_alternative(html, "text/html")
    msg.extra_headers = {"List-Unsubscribe": f"<{unsubscribe_url}>"}
    for fname, data, mime in attachments:
        msg.attach(fname, data, mime)
    msg.send(fail_silently=False)


def send_seats_full_alert(w, count: int):
    """Tell the organisers that the last seat was taken. Does nothing if no alert address is set."""
    to = settings.ADMIN_NOTIFY_EMAIL
    if not to or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        return
    body = (f"All {w.capacity} seats for \"{w.title}\" ({w.start_datetime:%d %b %Y}) are now taken.\n\n"
            f"Registration is closed automatically. To take more students, raise the seat limit in the admin: "
            f"{settings.SITE_URL}/admin/workshops/workshop/{w.pk}/change/\n\n"
            f"Students: {settings.SITE_URL}/dashboard/registrations/?workshop={w.pk}")
    EmailMultiAlternatives(
        subject=_one_line(f"Seats full: {w.title}"), body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[to],
    ).send(fail_silently=False)
