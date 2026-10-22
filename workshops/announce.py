"""Emailing a new workshop to students who attended earlier ones."""
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

import mimetypes
from pathlib import Path

from . import mailer, storage
from .models import Announcement, AnnouncementDraft, Unsubscribed, Workshop


def unsubscribe_url(email):
    return f"{settings.SITE_URL}{reverse('unsubscribe')}?t={signing.dumps(email.lower(), salt='unsub')}"


def audience(w):
    """People registered for an earlier (completed) workshop, once each. Leaves out anyone whose payment was
    rejected, who already registered for this workshop, or who unsubscribed."""
    past = {str(x.pk) for x in Workshop.objects.exclude(pk=w.pk).exclude(status="draft") if x.phase == "completed"}
    rows = storage.list_registrations()
    already = {str(r["email"]).strip().lower() for r in rows if str(r["workshop_id"]) == str(w.pk)}
    unsub = {e.lower() for e in Unsubscribed.objects.values_list("email", flat=True)}
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: str(r["registered_at"]), reverse=True):
        email = str(r["email"]).strip().lower()
        if (r["registration_status"] != "confirmed" or str(r["workshop_id"]) not in past or not email
                or storage.payment_state(r) == "rejected" or email in seen or email in already or email in unsub):
            continue
        seen.add(email)
        out.append({"email": email, "name": str(r["full_name"])})
    return out


DEFAULT_MESSAGE = ("Hi {name},\n\nThank you for being part of our earlier workshop. We are happy to invite you to our next one. "
                   "Please see the details below and register using the button. Seats are limited.\n\nSee you there!")


def default_subject(w):
    return f"New workshop: {w.title} - {w.start_datetime:%d %b %Y}"


def get_draft(w):
    """The saved email text for this workshop (created with sensible defaults on first use)."""
    draft, _ = AnnouncementDraft.objects.get_or_create(
        workshop=w, defaults={"subject": default_subject(w), "message": DEFAULT_MESSAGE})
    return draft


def load_attachments(draft):
    out = []
    for f in draft.files.all():
        try:
            with f.file.open("rb") as fh:
                data = fh.read()
        except (OSError, ValueError):
            continue  # file went missing: skip it rather than stop the whole announcement
        mime = mimetypes.guess_type(f.original_name)[0] or "application/octet-stream"
        out.append((f.original_name, data, mime))
    return out


def skipped_already_registered(w):
    """How many past students are NOT emailed because they are already registered for this workshop."""
    past = {str(x.pk) for x in Workshop.objects.exclude(pk=w.pk).exclude(status="draft") if x.phase == "completed"}
    rows = storage.list_registrations()
    here = {str(r["email"]).strip().lower() for r in rows if str(r["workshop_id"]) == str(w.pk)}
    there = {str(r["email"]).strip().lower() for r in rows if str(r["workshop_id"]) in past}
    return len(here & there)


def state(w):
    people = audience(w)
    log = {a.email.lower(): a.status for a in w.announcements.all()}
    sent = [p for p in people if log.get(p["email"], "").startswith("sent")]
    failed = [p for p in people if log.get(p["email"], "").startswith("failed")]
    fresh = [p for p in people if p["email"] not in log]
    return {"total": len(people), "sent": len(sent), "failed": len(failed), "fresh": len(fresh),
            "remaining": len(fresh) + len(failed), "queue": fresh + failed, "log": log,
            "skipped": skipped_already_registered(w)}


def send_batch(w, limit):
    """Email up to `limit` people who have not received it yet. Returns (sent, failed)."""
    st = state(w)
    draft = get_draft(w)
    attachments = load_attachments(draft)  # read once, reused for every email in this batch
    sent = failed = 0
    for p in st["queue"][:limit]:
        try:
            mailer.send_announcement(w, p["name"], p["email"], unsubscribe_url(p["email"]),
                                     subject=draft.subject, message=draft.message, attachments=attachments)
            status = "sent"
            sent += 1
        except Exception as e:
            status = f"failed: {str(e)[:150]}"
            failed += 1
        Announcement.objects.update_or_create(workshop=w, email=p["email"], defaults={"name": p["name"][:100], "status": status})
    if sent and not w.announced_at:
        Workshop.objects.filter(pk=w.pk).update(announced_at=timezone.now())
    return sent, failed
