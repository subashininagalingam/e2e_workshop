"""When a certificate is sent, and how.

A certificate is emailed automatically once ALL of these are true for a registered student:
  1. the workshop has a certificate template,
  2. the workshop has started,
  3. the payment is verified (or the workshop is free),
  4. the student has submitted feedback for that workshop (matched by email).
It is checked again whenever staff tick "payment verified" and whenever a student submits feedback.
Each certificate is sent once; staff can resend from the Registrations page.
"""
import logging
import re

from django.conf import settings
from django.db import transaction

from . import certificates, mailer, storage
from .models import Feedback, Workshop

log = logging.getLogger(__name__)


def feedback_keys():
    """{(workshop id, email)} for every feedback received."""
    return {(str(wid), (em or "").strip().lower()) for wid, em in Feedback.objects.values_list("workshop_id", "email")}


def has_feedback(row, keys):
    return (str(row.get("workshop_id")), str(row.get("email", "")).strip().lower()) in keys


def status_for(row, w, keys):
    """(code, text) describing where this student's certificate stands."""
    st = str(row.get("certificate_status", "") or "").strip()
    if st.startswith("sent"):
        return "sent", "Sent " + str(row.get("certificate_sent_at", "") or "")
    if st.startswith("sending"):
        return "sending", "Sending now"
    pay = storage.payment_state(row)
    if str(row.get("wants_certificate", "") or "").strip().lower() == "no" or pay == "none":
        return "not_requested", "Did not ask for a certificate"
    if w is None or not w.has_certificate:
        return "no_template", "No certificate template for this workshop"
    if pay == "rejected":
        return "blocked", "Payment rejected"
    if w.phase == "upcoming":
        return "waiting", "Workshop has not started"
    if pay not in ("verified", "free"):
        return "waiting_payment", "Waiting for payment check"
    if not has_feedback(row, keys):
        return "waiting_feedback", "Waiting for feedback"
    if st.startswith("failed"):
        return "ready", "Ready (last try failed: " + st[7:90].strip() + ")"
    return "ready", "Ready to send"


def _file_name(name, w):
    return re.sub(r"[^\w\-. ]+", "", f"Certificate - {name} - {w.title}").strip()[:120] + ".pdf"


def render_pdf(w, name, cert_id=""):
    img = certificates.render(
        w.cert_template.path, name, w.cert_name_x, w.cert_name_y, w.cert_font_size, w.cert_color, w.cert_font,
        settings.CERT_FONT_DIR, id_text=cert_id, id_x=w.cert_id_x, id_y=w.cert_id_y, id_size=w.cert_id_size)
    return certificates.to_pdf_bytes(img)


def allocate_certificate_id(w):
    """Hand out the next number for this workshop (E2E/WS/2026/500, then 501, 502 ...). One number is never used twice."""
    with transaction.atomic():
        locked = Workshop.objects.select_for_update().get(pk=w.pk)
        if not locked.cert_id_prefix:
            return ""
        text = locked.next_certificate_id()
        locked.cert_id_next += 1
        locked.save(update_fields=["cert_id_next"])
        return text


def send_certificate(registration_id, w, force=False):
    """Send one certificate. Returns 'sent', 'skipped' (already sent / being sent) or 'failed: reason'."""
    claimed = storage.claim_certificate(registration_id, force=force)
    if claimed is None:
        return "skipped"
    try:
        if not w.has_certificate:
            raise RuntimeError("No certificate template uploaded")
        name = certificates.pretty_name(claimed["full_name"])
        cert_id = str(claimed.get("certificate_id", "") or "")
        if not cert_id:  # keep the same ID if this certificate is resent or a failed send is retried
            cert_id = allocate_certificate_id(w)
            if cert_id:
                storage.update_fields(registration_id, certificate_id=cert_id)
        claimed["certificate_id"] = cert_id
        mailer.send_certificate(claimed, w, render_pdf(w, name, cert_id), _file_name(name, w))
        status = "sent"
    except Exception as e:  # missing template file, SMTP problem, bad font ...
        log.warning("Certificate for %s failed: %s", registration_id, e)
        status = f"failed: {str(e)[:120]}"
    try:
        storage.finish_certificate(registration_id, status)
    except storage.StorageError as e:
        log.warning("Certificate for %s was %s but the Excel file could not be updated: %s", registration_id, status, e)
    return status


def try_auto(registration_id):
    """Send the certificate if the student is eligible now. Returns (code, text)."""
    row = storage.get_registration(registration_id)
    if not row:
        return "missing", "Registration not found"
    w = Workshop.objects.filter(pk=row["workshop_id"]).first()
    code, text = status_for(row, w, feedback_keys())
    if code != "ready":
        return code, text
    result = send_certificate(registration_id, w)
    if result == "sent":
        return "sent", "Certificate emailed"
    if result == "skipped":
        return "sending", "Already being sent"
    return "failed", result


def on_feedback(fb):
    """Call after a student submits feedback. Returns 'sent', 'waiting', or 'no_template'."""
    w = fb.workshop
    if w is None or not w.has_certificate:
        return "no_template"
    outcome = "waiting"
    for row in storage.list_registrations():
        if (str(row["workshop_id"]) == str(w.pk) and row["registration_status"] == "confirmed"
                and str(row["email"]).strip().lower() == fb.email.strip().lower()):
            code, _ = try_auto(row["registration_id"])
            if code == "sent":
                outcome = "sent"
    return outcome


def send_ready(w, limit=25):
    """Send every certificate that is ready for one workshop (at most `limit`). Returns (sent, failed, left)."""
    keys = feedback_keys()
    sent = failed = left = 0
    for row in storage.list_registrations():
        if str(row["workshop_id"]) != str(w.pk) or row["registration_status"] != "confirmed":
            continue
        code, _ = status_for(row, w, keys)
        if code != "ready":
            continue
        if sent + failed >= limit:
            left += 1
            continue
        if send_certificate(row["registration_id"], w) == "sent":
            sent += 1
        else:
            failed += 1
    return sent, failed, left


def send_test(w, to):
    """Send a sample certificate to `to` so staff can check the placement and the email."""
    name = "Sample Student Name"
    cert_id = w.next_certificate_id()  # shown as a sample; it does not use up a number
    mailer.send_certificate({"full_name": name, "registration_id": "TEST", "email": to, "certificate_id": cert_id},
                            w, render_pdf(w, name, cert_id), _file_name(name, w), to=to)
