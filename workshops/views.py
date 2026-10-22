import csv
import logging
import secrets
import time
from collections import Counter
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.core.cache import cache
from django.db.models import Avg, Count
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

import math
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from django.utils.http import url_has_allowed_host_and_scheme

from . import announce as announce_mod
from . import certflow, certificates, mailer, storage
from .forms import CertificateSetupForm, FeedbackForm, RegistrationForm
from .models import Announcement, AnnouncementFile, Feedback, GalleryImage, Unsubscribed, Workshop
from .qr import make_qr_png, upi_link

log = logging.getLogger(__name__)
STAFF = staff_member_required(login_url="admin:login")
_QR_LINK = re.compile(r"^https?://[^\s]+$", re.I)
MIN_FILL_SECONDS = 3
MAX_FORM_AGE = 6 * 60 * 60


# ---------------------------------------------------------------- helpers
def annotate(workshops):
    """Attach live registration state (count, open/full/closed, remaining seats) to each workshop."""
    try:
        counts = storage.count_confirmed()
    except storage.StorageError as e:
        log.warning("Could not read registration counts: %s", e)
        counts = {}
    out = []
    for w in workshops:
        w.count = counts.get(str(w.pk), 0)
        w.reg = w.reg_state(w.count)
        w.remaining = max(w.capacity - w.count, 0) if w.capacity else None
        out.append(w)
    return out


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "unknown"


def rate_limited(request, name, limit, seconds):
    key = f"rl:{name}:{client_ip(request)}"
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key) > limit
    except ValueError:
        return False


def _back(request, default):
    """Where to go after a staff action. Only addresses on this site are accepted."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(default)


def new_registration_id():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return f"E2E-{timezone.localdate():%Y%m%d}-" + "".join(secrets.choice(alphabet) for _ in range(6))


# ---------------------------------------------------------------- public pages
def home(request):
    all_ws = annotate(Workshop.objects.filter(status="published").order_by("start_datetime"))
    live = [w for w in all_ws if w.phase != "completed"]
    done = [w for w in all_ws if w.phase == "completed"][::-1]
    feat = next((w for w in live if w.featured), None) or next((w for w in live if w.reg == "open"), None) or (live[0] if live else None)
    others = [w for w in live if w is not feat][:3]
    reviews = Feedback.objects.filter(show_on_site=True)
    agg = reviews.aggregate(avg=Avg("rating"), n=Count("id"))
    return render(request, "home.html", {
        "feat": feat, "upcoming": others, "previous": done[:3],
        "photos": GalleryImage.objects.filter(kind="attendees")[:9],
        "shots": GalleryImage.objects.filter(kind="feedback")[:8],
        "reviews": reviews[:6], "avg_rating": round(agg["avg"], 1) if agg["avg"] else None, "review_count": agg["n"],
    })


def workshop_list(request):
    all_ws = annotate(Workshop.objects.filter(status="published").order_by("start_datetime"))
    ctx = {
        "live": [w for w in all_ws if w.phase != "completed"],
        "done": [w for w in all_ws if w.phase == "completed"][::-1],
        "hidden": [],
    }
    if request.user.is_staff:  # staff see why a workshop is not listed for students
        for w in Workshop.objects.exclude(status="published").order_by("-start_datetime")[:10]:
            ctx["hidden"].append((w, "Draft: not published yet" if w.status == "draft" else "Archived"))
    return render(request, "workshops.html", ctx)


def gallery(request):
    return render(request, "gallery.html", {
        "photos": GalleryImage.objects.filter(kind="attendees").select_related("workshop")[:120],
        "shots": GalleryImage.objects.filter(kind="feedback")[:120],
    })


def workshop_detail(request, slug):
    w = get_object_or_404(Workshop, slug=slug)
    if w.status != "published" and not request.user.is_staff:
        raise Http404()
    w = annotate([w])[0]
    return render(request, "workshop_detail.html", {"w": w, "is_preview": w.status != "published"})


def register(request):
    open_ws = [w for w in annotate(Workshop.objects.filter(status="published").order_by("start_datetime")) if w.reg == "open"]
    asked = request.GET.get("w", "")
    notice = ""
    if asked:
        target = Workshop.objects.filter(slug=asked, status="published").first()
        if target and target not in open_ws:
            why = "has already taken place" if target.phase == "completed" else (
                "is full" if annotate([target])[0].reg == "full" else "is closed for registration")
            notice = f"“{target.title}” {why}." + (" You can register for another open workshop below." if open_ws else "")

    if request.method == "POST":
        posted = request.POST.get("workshop", "")
        if posted and posted not in {str(w.pk) for w in open_ws}:
            notice = "Sorry, that workshop is full or closed for registration. Nothing was saved."

    if not open_ws:
        return render(request, "register.html", {"form": None, "notice": notice})

    form = RegistrationForm(request.POST or None, request.FILES or None, workshops=open_ws)
    if request.method == "GET":
        pre = next((w for w in open_ws if w.slug == asked), None) or (open_ws[0] if len(open_ws) == 1 else None)
        if pre:
            form.initial["workshop"] = str(pre.pk)
    else:
        err = _spam_check(request)
        if err:
            form.add_error(None, err)
        elif form.is_valid():
            result = _save_registration(request, form)
            if result is True:
                return redirect("thank_you")
            form.add_error(*result)

    meta = {
        str(w.pk): {
            "title": w.title, "date": w.start_datetime.astimezone(timezone.get_current_timezone()).strftime("%a, %d %b %Y"),
            "time": w.time_range, "mode": w.mode, "venue": w.venue if w.mode != "online" else "",
            "seats": f"{w.remaining} seat{'s' if w.remaining != 1 else ''} left" if w.remaining is not None else "",
            "seats_low": w.remaining is not None and w.remaining <= 5,
            "poster": w.poster.url if w.poster else "", "hybrid": w.mode == "hybrid",
            "pay": w.needs_payment, "choice": w.pay_optional, "fee": _fee_text(w.fee),
            "upi": w.payment_upi,
            "payqr": w.payment_qr.url if w.payment_qr else (reverse("pay_qr", args=[w.pk]) if w.payment_upi else ""),
        } for w in open_ws
    }
    ts = signing.dumps(time.time(), salt="reg-form")
    return render(request, "register.html", {"form": form, "notice": notice, "meta": meta, "ts": ts, "has_errors": form.is_bound and bool(form.errors)})


def _spam_check(request, bucket="register"):
    if request.POST.get("website"):
        return "Submission rejected."
    try:
        started = signing.loads(request.POST.get("ts", ""), salt="reg-form", max_age=MAX_FORM_AGE)
    except signing.BadSignature:
        return "This form expired. Please reload the page and try again."
    if time.time() - float(started) < MIN_FILL_SECONDS:
        return "That was very fast. Please check your details and submit again."
    if rate_limited(request, bucket, 8, 600):
        return "Too many attempts. Please wait a few minutes and try again."
    return ""


def _amount_of(row, ws_map):
    """Rupees this student pays. Older rows without an amount use the workshop fee when a screenshot exists."""
    raw = str(row.get("amount", "") or "").strip()
    if not raw and row.get("payment_screenshot"):
        w = ws_map.get(str(row.get("workshop_id")))
        raw = str(w.fee) if w and w.fee else ""
    try:
        return Decimal(raw) if raw else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def _fee_text(fee):
    if not fee:
        return ""
    return f"{fee:.0f}" if fee == int(fee) else f"{fee:.2f}"


def _save_proof(upload, reg_id):
    """Keep the payment screenshot in a private folder. Returns the file name ('' if none)."""
    if not upload:
        return ""
    fmt = (getattr(getattr(upload, "image", None), "format", "") or "png").lower()
    ext = {"jpeg": "jpg"}.get(fmt, fmt)
    if ext not in ("jpg", "png", "webp", "gif"):
        ext = "png"
    name = f"{reg_id}.{ext}"
    folder = Path(settings.PAYMENTS_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    upload.seek(0)
    (folder / name).write_bytes(upload.read())
    return name


def _drop_proof(name):
    if name:
        try:
            (Path(settings.PAYMENTS_DIR) / name).unlink()
        except OSError:
            pass


def _save_registration(request, form):
    cd = form.cleaned_data
    w = form.workshops[cd["workshop"]]
    fresh = annotate([Workshop.objects.get(pk=w.pk)])[0]
    if fresh.reg != "open":
        return (None, "Registration for this workshop has just closed." if fresh.reg == "closed" else "Sorry, this workshop is full.")
    reg_id = new_registration_id()
    wants = cd.get("wants_certificate") or "yes"
    pays = w.needs_payment and wants == "yes"
    proof_name = _save_proof(cd.get("payment_screenshot"), reg_id) if pays else ""
    row = {
        "registration_id": reg_id,
        "registered_at": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
        "workshop_id": w.pk, "workshop_title": w.title,
        "full_name": cd["full_name"], "email": cd["email"], "phone": cd["phone"],
        "college": cd["college"],
        "participation_mode": cd["participation_mode"], "consent": "yes",
        "registration_status": "confirmed", "email_status": "pending", "source": "web",
        "payment_reference": cd.get("payment_reference", ""), "payment_screenshot": proof_name,
        "payment_status": "pending" if pays else ("none" if wants == "no" else "free"),
        "wants_certificate": wants, "amount": _fee_text(w.fee) if pays else "",
        "current_address": cd["current_address"], "education_qualification": cd["education_qualification"],
        "current_status": cd["current_status"], "heard_from": cd["heard_from"], "interest_domain": cd["interest_domain"],
        "skill_level": cd["skill_level"], "demo_interest": cd["demo_interest"], "demo_mode": cd.get("demo_mode", ""),
        "demo_slot": cd.get("demo_slot", ""), "queries": cd.get("queries", ""), "referred_by": cd["referred_by"],
    }
    try:
        storage.add_registration(row, w.capacity)  # saved to Excel before anything is reported as success
    except storage.DuplicateError:
        _drop_proof(proof_name)
        return ("email", "This email is already registered for this workshop.")
    except storage.FullError:
        _drop_proof(proof_name)
        return (None, "Sorry, this workshop just filled up.")
    except storage.StorageError as e:
        _drop_proof(proof_name)
        return (None, str(e))

    if w.capacity:  # the student who takes the last seat triggers one alert to the organisers
        try:
            if storage.count_confirmed().get(str(w.pk), 0) == w.capacity:
                mailer.send_seats_full_alert(w, w.capacity)
        except Exception as e:
            log.warning("Seats-full alert for %s failed: %s", w.title, e)

    status = mailer.send_all(row, w)
    try:
        storage.update_email_status(row["registration_id"], status)
    except storage.StorageError as e:
        log.warning("Saved registration %s but could not update email status: %s", row["registration_id"], e)
    request.session["last_registration"] = {
        "id": row["registration_id"], "name": row["full_name"], "email": row["email"],
        "mode": row["participation_mode"], "emailed": status.startswith("sent"), "workshop": w.pk,
        "paid": bool(proof_name), "certificate": wants,
    }
    return True


def thank_you(request):
    data = request.session.get("last_registration")
    w = Workshop.objects.filter(pk=data["workshop"]).first() if data else None
    return render(request, "thank_you.html", {"data": data, "w": w, "redirect_url": settings.POST_SUBMIT_REDIRECT_URL})


# ---------------------------------------------------------------- payment QR + proof
def pay_qr(request, pk):
    """QR made from the workshop's UPI ID and fee. Used when no QR image was uploaded for the workshop."""
    w = get_object_or_404(Workshop, pk=pk, status="published")
    if not (w.has_fee and w.payment_upi):
        raise Http404()
    link = upi_link(w.payment_upi, settings.ORG["short"], f"{w.fee:.2f}", w.title)
    return HttpResponse(make_qr_png(link, caption=f"Pay Rs. {_fee_text(w.fee)}"), content_type="image/png")


@STAFF
def payment_proof(request, reg_id):
    try:
        row = next((r for r in storage.list_registrations() if r["registration_id"] == reg_id), None)
    except storage.StorageError as e:
        raise Http404(str(e))
    name = str(row.get("payment_screenshot", "")) if row else ""
    if not re.fullmatch(r"E2E-\d{8}-[A-Z0-9]{6}\.(jpg|png|webp|gif)", name):
        raise Http404()
    f = Path(settings.PAYMENTS_DIR) / name
    if not f.is_file():
        raise Http404()
    return FileResponse(open(f, "rb"))


# ---------------------------------------------------------------- feedback
def _feedback_workshops():
    started = [w for w in Workshop.objects.filter(status="published").order_by("-start_datetime") if w.phase != "upcoming"]
    return started or list(Workshop.objects.filter(status="published").order_by("-start_datetime"))


def feedback(request):
    workshops = _feedback_workshops()
    if not workshops:
        return render(request, "feedback.html", {"form": None})
    form = FeedbackForm(request.POST or None, workshops=workshops)
    if request.method == "POST":
        err = _spam_check(request, "feedback")
        if err:
            form.add_error(None, err)
        elif form.is_valid():
            cd = form.cleaned_data
            w = form.workshops[cd["workshop"]]
            if Feedback.objects.filter(workshop=w, email=cd["email"]).exists():
                form.add_error("email", "Feedback from this email was already submitted for this workshop.")
            else:
                fb = Feedback.objects.create(workshop=w, workshop_title=w.title, name=cd["name"], email=cd["email"],
                                             rating=int(cd["rating"]), message=cd["message"])
                try:  # feedback is saved first; a certificate problem must never lose it
                    outcome = certflow.on_feedback(fb)
                except Exception as e:
                    log.warning("Certificate check after feedback failed: %s", e)
                    outcome = "waiting"
                request.session["feedback_name"] = cd["name"]
                request.session["feedback_outcome"] = outcome
                return redirect("feedback_thanks")
    else:
        asked = Workshop.objects.filter(slug=request.GET.get("w", "")).first()
        if asked and str(asked.pk) in form.workshops:
            form.initial["workshop"] = str(asked.pk)
        elif len(workshops) >= 1:
            form.initial["workshop"] = str(workshops[0].pk) if len(workshops) == 1 else ""
    return render(request, "feedback.html", {"form": form, "ts": signing.dumps(time.time(), salt="reg-form")})


def feedback_thanks(request):
    return render(request, "feedback_thanks.html", {
        "name": request.session.get("feedback_name", ""), "outcome": request.session.get("feedback_outcome", ""),
    })


# ---------------------------------------------------------------- QR codes
def _qr_target(slug):
    if slug == "permanent":
        return settings.SITE_URL + reverse("register"), "errors2experts-permanent-register-qr.png"
    w = get_object_or_404(Workshop, slug=slug, status="published")
    return f"{settings.SITE_URL}{reverse('register')}?w={w.slug}", f"qr-{w.slug}.png"


def qr_png(request, slug):
    url, filename = _qr_target(slug)
    resp = HttpResponse(make_qr_png(url), content_type="image/png")
    if request.GET.get("download"):
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def qr_print(request, slug):
    url, _ = _qr_target(slug)
    title = "Errors2Experts Workshops" if slug == "permanent" else get_object_or_404(Workshop, slug=slug).title
    return render(request, "qr_print.html", {"url": url, "title": title, "slug": slug})


# ---------------------------------------------------------------- staff dashboard
def _filtered(request):
    g = request.GET
    rows = [r for r in storage.list_registrations() if r["registration_status"] == "confirmed"]
    q = g.get("q", "").strip().lower()
    out = []
    for r in rows:
        day = str(r["registered_at"])[:10]
        if g.get("workshop") and str(r["workshop_id"]) != g["workshop"]:
            continue
        if g.get("college") and g["college"].lower() not in str(r["college"]).lower():
            continue
        if g.get("department") and g["department"].lower() not in str(r["department"]).lower():
            continue
        if g.get("payment") and storage.payment_state(r) != g["payment"]:
            continue
        sent_mail = str(r.get("email_status", "")).startswith("sent")
        if g.get("email") == "sent" and not sent_mail:
            continue
        if g.get("email") == "notsent" and sent_mail:
            continue
        if g.get("cert") in ("yes", "no") and (str(r.get("wants_certificate", "") or "yes").lower() == "no") != (g["cert"] == "no"):
            continue
        if g.get("from") and day < g["from"]:
            continue
        if g.get("to") and day > g["to"]:
            continue
        if q and q not in f"{r['full_name']} {r['email']} {r['college']} {r['registration_id']}".lower():
            continue
        out.append(r)
    out.sort(key=lambda r: str(r["registered_at"]), reverse=True)
    return out


@STAFF
def dashboard(request):
    ctx = {"error": ""}
    try:
        rows = [r for r in storage.list_registrations() if r["registration_status"] == "confirmed"]
    except storage.StorageError as e:
        return render(request, "dashboard.html", {"error": str(e)})
    per_day = Counter(str(r["registered_at"])[:10] for r in rows)
    per_ws = Counter(str(r["workshop_id"]) for r in rows)
    titles = {str(w.pk): w.title for w in Workshop.objects.all()}
    ws_map = {str(w.pk): w for w in Workshop.objects.all()}
    verified_rs = sum((_amount_of(r, ws_map) for r in rows if storage.payment_state(r) == "verified"), Decimal(0))
    pending_rs = sum((_amount_of(r, ws_map) for r in rows if storage.payment_state(r) == "pending"), Decimal(0))
    ctx.update(
        verified_rs=verified_rs, pending_rs=pending_rs,
        total=len(rows),
        email_failures=sum(1 for r in rows if str(r["email_status"]).startswith("failed")),
        workshop_count=Workshop.objects.count(),
        by_workshop=[(titles.get(k, f"(deleted workshop {k})"), n) for k, n in per_ws.most_common()],
        trend={"labels": sorted(per_day), "values": [per_day[d] for d in sorted(per_day)]},
        recent=sorted(rows, key=lambda r: str(r["registered_at"]), reverse=True)[:8],
        excel_path=str(storage.path()),
    )
    return render(request, "dashboard.html", ctx)


@STAFF
def registrations(request):
    try:
        rows = _filtered(request)
    except storage.StorageError as e:
        return render(request, "registrations.html", {"error": str(e), "workshops": Workshop.objects.all()})
    ws_map = {str(w.pk): w for w in Workshop.objects.all()}
    keys = certflow.feedback_keys()
    shown = rows[:1000]
    for r in shown:
        r["pay"] = storage.payment_state(r)
        r["amount_rs"] = _amount_of(r, ws_map)
        r["has_feedback"] = certflow.has_feedback(r, keys)
        r["cert_code"], r["cert_text"] = certflow.status_for(r, ws_map.get(str(r["workshop_id"])), keys)
    chosen = ws_map.get(request.GET.get("workshop", ""))
    ready = sum(1 for r in shown if r["cert_code"] == "ready") if chosen else 0
    return render(request, "registrations.html", {
        "rows": shown, "total": len(rows), "workshops": Workshop.objects.all(),
        "qs": request.GET.urlencode(), "g": request.GET, "error": "", "chosen": chosen, "ready": ready,
    })


@STAFF
def export_excel(request):
    try:
        data = storage.rows_to_xlsx(_filtered(request))
    except storage.StorageError as e:
        messages.error(request, str(e))
        return redirect("registrations")
    resp = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="registrations-{timezone.localdate()}.xlsx"'
    return resp


def _safe_cell(v):
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@STAFF
def export_csv(request):
    try:
        rows = _filtered(request)
    except storage.StorageError as e:
        messages.error(request, str(e))
        return redirect("registrations")
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="registrations-{timezone.localdate()}.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    w.writerow(storage.HEADERS)
    for r in rows:
        w.writerow([_safe_cell(r.get(h, "")) for h in storage.HEADERS])
    return resp


@STAFF
@require_POST
def retry_email(request, reg_id):
    try:
        row = next((r for r in storage.list_registrations() if r["registration_id"] == reg_id), None)
        if not row:
            messages.error(request, "Registration not found.")
        elif str(row["email_status"]).startswith("sent"):
            messages.info(request, "That confirmation was already sent, so it was not sent again.")
        else:
            w = Workshop.objects.filter(pk=row["workshop_id"]).first()
            if not w:
                messages.error(request, "The workshop for this registration no longer exists.")
            else:
                status = mailer.send_all(row, w)
                storage.update_email_status(reg_id, status)
                (messages.success if status.startswith("sent") else messages.warning)(request, f"Email status: {status}")
    except storage.StorageError as e:
        messages.error(request, str(e))
    return _back(request, "registrations")


@STAFF
def qr_admin(request):
    link = (request.GET.get("link") or "").strip()
    caption = " ".join((request.GET.get("caption") or "").split())[:60]
    custom, error = None, ""
    if link:
        if not _QR_LINK.match(link) or len(link) > 500:
            error = "Enter a full web link that starts with http:// or https://"
        else:
            custom = {"link": link, "qs": urlencode({"u": link, "caption": caption})}
    return render(request, "qr_admin.html", {
        "workshops": Workshop.objects.filter(status="published"), "custom": custom, "error": error,
        "link": link, "caption": caption,
    })


@STAFF
def qr_custom_png(request):
    """QR for any web link typed on the QR page."""
    link = (request.GET.get("u") or "").strip()
    if not _QR_LINK.match(link) or len(link) > 500:
        raise Http404()
    caption = " ".join((request.GET.get("caption") or "").split())[:60] or "Scan me"
    resp = HttpResponse(make_qr_png(link, caption=caption), content_type="image/png")
    if request.GET.get("download"):
        resp["Content-Disposition"] = 'attachment; filename="qr-code.png"'
    return resp


@STAFF
def feedback_admin(request):
    qs = Feedback.objects.all()
    wid = request.GET.get("workshop", "")
    if wid.isdigit():
        qs = qs.filter(workshop_id=int(wid))
    agg = qs.aggregate(avg=Avg("rating"), n=Count("id"))
    return render(request, "feedback_admin.html", {
        "items": qs, "workshops": Workshop.objects.all(), "g": request.GET,
        "avg": round(agg["avg"], 1) if agg["avg"] else None, "n": agg["n"],
    })


@STAFF
@require_POST
def feedback_delete(request, pk):
    item = Feedback.objects.filter(pk=pk).first()
    if item:
        item.delete()
        messages.success(request, "Feedback deleted.")
    else:
        messages.info(request, "That feedback was already removed.")
    return _back(request, "feedback_admin")


@STAFF
@require_POST
def feedback_toggle(request, pk):
    item = get_object_or_404(Feedback, pk=pk)
    item.show_on_site = not item.show_on_site
    item.save(update_fields=["show_on_site"])
    messages.success(request, "Feedback is now shown on the website." if item.show_on_site else "Feedback is now hidden from the website.")
    return _back(request, "feedback_admin")


# ---------------------------------------------------------------- payment check and certificates
@STAFF
@require_POST
def payment_set(request, reg_id):
    """The 'payment verified' tick box. Ticking it also sends the certificate if everything else is complete."""
    status = request.POST.get("status", "")
    if status not in ("verified", "pending", "rejected"):
        status = "verified" if request.POST.get("verified") else "pending"
    try:
        if not storage.update_fields(reg_id, payment_status=status):
            messages.error(request, "Registration not found.")
            return _back(request, "registrations")
        row = storage.get_registration(reg_id) or {}
        who = row.get("full_name", "the student")
        if status != "verified":
            messages.info(request, f"Payment for {who} marked {status}.")
        else:
            code, text = certflow.try_auto(reg_id)
            if code == "sent":
                messages.success(request, f"Payment verified for {who}. Certificate emailed to {row.get('email')}.")
            elif code == "failed":
                messages.warning(request, f"Payment verified for {who}, but the certificate email failed ({text}). Use Resend on this row.")
            elif code == "no_template":
                messages.info(request, f"Payment verified for {who}. Upload this workshop's certificate under Certificates to enable automatic sending.")
            else:
                messages.success(request, f"Payment verified for {who}. Certificate: {text.lower()}. It is emailed automatically as soon as that is done.")
    except storage.StorageError as e:
        messages.error(request, str(e))
    return _back(request, "registrations")


@STAFF
@require_POST
def certificate_send(request, reg_id):
    """Send or resend one certificate. 'force' skips the payment and feedback checks."""
    force = bool(request.POST.get("force"))
    try:
        row = storage.get_registration(reg_id)
        w = Workshop.objects.filter(pk=row["workshop_id"]).first() if row else None
        if not row or not w:
            messages.error(request, "Registration or workshop not found.")
        elif not w.has_certificate:
            messages.error(request, "Upload a certificate template for this workshop first (Certificates page).")
        else:
            if not force:
                code, text = certflow.status_for(row, w, certflow.feedback_keys())
                if code not in ("ready", "sent"):
                    messages.warning(request, f"Not sent: {text.lower()}. Use Send anyway to override.")
                    return _back(request, "registrations")
            result = certflow.send_certificate(reg_id, w, force=True if (force or str(row.get("certificate_status", "")).startswith("sent")) else False)
            if result == "sent":
                messages.success(request, f"Certificate emailed to {row['email']}.")
            elif result == "skipped":
                messages.info(request, "That certificate is already being sent.")
            else:
                messages.error(request, f"Certificate email failed: {result[7:]}")
    except storage.StorageError as e:
        messages.error(request, str(e))
    return _back(request, "registrations")


@STAFF
@require_POST
def certificate_send_all(request, pk):
    w = get_object_or_404(Workshop, pk=pk)
    if not w.has_certificate:
        messages.error(request, "Upload a certificate template for this workshop first.")
        return _back(request, "registrations")
    try:
        sent, failed, left = certflow.send_ready(w, limit=25)
    except storage.StorageError as e:
        messages.error(request, str(e))
        return _back(request, "registrations")
    msg = f"Certificates emailed: {sent}."
    if failed:
        msg += f" Failed: {failed} (see the status on each row)."
    if left:
        msg += f" {left} more are ready. Click again to send the next batch."
    (messages.warning if failed else messages.success)(request, msg)
    return _back(request, "registrations")


@STAFF
def certificate_download(request, reg_id):
    row = storage.get_registration(reg_id)
    w = Workshop.objects.filter(pk=row["workshop_id"]).first() if row else None
    if not row or not w or not w.has_certificate:
        raise Http404()
    try:
        pdf = certflow.render_pdf(w, certificates.pretty_name(row["full_name"]),
                                  str(row.get("certificate_id", "") or "") or w.next_certificate_id())
    except Exception:
        raise Http404()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="certificate-{reg_id}.pdf"'
    resp["Cache-Control"] = "private, no-store"
    return resp


@STAFF
def certificates_index(request):
    try:
        rows = storage.list_registrations()
    except storage.StorageError as e:
        return render(request, "certificates.html", {"error": str(e)})
    keys = certflow.feedback_keys()
    items = []
    for w in Workshop.objects.exclude(status="draft").order_by("-start_datetime"):
        mine = [r for r in rows if str(r["workshop_id"]) == str(w.pk) and r["registration_status"] == "confirmed"]
        codes = [certflow.status_for(r, w, keys)[0] for r in mine]
        items.append({
            "w": w, "registered": len(mine),
            "verified": sum(1 for r in mine if storage.payment_state(r) in ("verified", "free")),
            "feedback": sum(1 for r in mine if certflow.has_feedback(r, keys)),
            "sent": codes.count("sent"), "ready": codes.count("ready"),
        })
    return render(request, "certificates.html", {"items": items, "error": ""})


@STAFF
def certificate_setup(request, pk):
    w = get_object_or_404(Workshop, pk=pk)
    fonts = certificates.available_fonts(settings.CERT_FONT_DIR)
    form = CertificateSetupForm(request.POST or None, request.FILES or None, instance=w, fonts=fonts)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Certificate settings saved.")
        return redirect("certificate_setup", pk=w.pk)
    return render(request, "certificate_setup.html", {"w": w, "form": form, "sample_name": "Sample Student Name"})


def _num(value, default, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(v) else min(max(v, lo), hi)


@STAFF
def certificate_preview(request, pk):
    """PNG preview of the certificate with a sample name. The page's sliders change the query string."""
    w = get_object_or_404(Workshop, pk=pk)
    if not w.has_certificate:
        raise Http404()
    g = request.GET
    try:
        img = certificates.render(
            w.cert_template.path, g.get("name", "Sample Student Name")[:80],
            _num(g.get("x"), w.cert_name_x, 0, 100), _num(g.get("y"), w.cert_name_y, 0, 100),
            _num(g.get("size"), w.cert_font_size, 0.5, 20), g.get("color", w.cert_color),
            g.get("font", w.cert_font), settings.CERT_FONT_DIR,
            id_text=(g["idtext"] if "idtext" in g else w.next_certificate_id())[:70],
            id_x=_num(g.get("idx"), w.cert_id_x, 0, 100), id_y=_num(g.get("idy"), w.cert_id_y, 0, 100),
            id_size=_num(g.get("idsize"), w.cert_id_size, 0.5, 10))
    except Exception:
        raise Http404()
    resp = HttpResponse(certificates.to_png_bytes(img, max_width=1300), content_type="image/png")
    resp["Cache-Control"] = "private, no-store"
    return resp


@STAFF
@require_POST
def certificate_test(request, pk):
    w = get_object_or_404(Workshop, pk=pk)
    to = request.user.email or settings.ADMIN_NOTIFY_EMAIL or settings.ORG["email"]
    if not w.has_certificate:
        messages.error(request, "Upload a certificate template first.")
    else:
        try:
            certflow.send_test(w, to)
            messages.success(request, f"A sample certificate was emailed to {to}.")
        except Exception as e:
            messages.error(request, f"Could not send the sample: {str(e)[:150]}")
    return redirect("certificate_setup", pk=w.pk)


# ---------------------------------------------------------------- announce a workshop to past students
@STAFF
def announce_index(request):
    return render(request, "announce_index.html", {"workshops": Workshop.objects.exclude(status="archived").order_by("-start_datetime")[:20]})


@STAFF
def announce(request, pk):
    w = get_object_or_404(Workshop, pk=pk)
    draft = announce_mod.get_draft(w)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        for fid in request.POST.getlist("remove"):
            f = draft.files.filter(pk=int(fid)).first() if fid.isdigit() else None
            if f:
                f.file.delete(save=False)
                f.delete()
        draft.subject = " ".join(request.POST.get("subject", "").split())[:200] or announce_mod.default_subject(w)
        draft.message = request.POST.get("message", "").replace("\r\n", "\n").strip()[:4000]
        draft.save()
        for problem in _add_announce_files(draft, request.FILES.getlist("files")):
            messages.error(request, f"Not attached - {problem}")
        try:
            if action == "save":
                messages.success(request, "Saved. Nothing has been sent yet.")
            elif w.status != "published":
                messages.error(request, "Publish the workshop first, so the Register link in the email works.")
            elif action == "test":
                to = request.user.email or settings.ADMIN_NOTIFY_EMAIL or settings.ORG["email"]
                try:
                    mailer.send_announcement(w, request.user.get_username(), to, announce_mod.unsubscribe_url(to),
                                             subject=draft.subject, message=draft.message,
                                             attachments=announce_mod.load_attachments(draft))
                    messages.success(request, f"A test email was sent to {to}.")
                except Exception as e:
                    messages.error(request, f"Could not send the test: {str(e)[:150]}")
            elif action == "send":
                sent, failed = announce_mod.send_batch(w, settings.ANNOUNCE_BATCH)
                msg = f"Emailed {sent} student{'s' if sent != 1 else ''}."
                if failed:
                    msg += f" {failed} failed; they stay in the list and are tried again on the next send."
                (messages.warning if failed else messages.success)(request, msg)
        except storage.StorageError as e:
            messages.error(request, str(e))
        return redirect("announce", pk=w.pk)
    try:
        st = announce_mod.state(w)
        error = ""
    except storage.StorageError as e:
        st, error = None, str(e)
    return render(request, "announce.html", {
        "w": w, "st": st, "error": error, "batch": settings.ANNOUNCE_BATCH, "draft": draft, "files": draft.files.all(),
        "max_files": settings.MAX_ANNOUNCE_FILES, "max_mb": settings.MAX_ANNOUNCE_FILE_BYTES // (1024 * 1024),
    })


def unsubscribe(request):
    """Public page behind the link in every announcement email."""
    token = request.POST.get("t") or request.GET.get("t", "")
    try:
        email = signing.loads(token, salt="unsub")
    except signing.BadSignature:
        return render(request, "unsubscribe.html", {"bad": True})
    done = False
    if request.method == "POST":
        Unsubscribed.objects.get_or_create(email=email.lower())
        done = True
    return render(request, "unsubscribe.html", {"email": email, "token": token, "done": done})


# ---------------------------------------------------------------- money: amounts, manual screenshot
@STAFF
def payments(request):
    """How much money has come in, per workshop, from the payment screenshots."""
    try:
        rows = [r for r in storage.list_registrations() if r["registration_status"] == "confirmed"]
    except storage.StorageError as e:
        return render(request, "payments.html", {"error": str(e)})
    ws_map = {str(w.pk): w for w in Workshop.objects.all()}
    chosen = request.GET.get("workshop", "")
    if chosen:
        rows = [r for r in rows if str(r["workshop_id"]) == chosen]
    zero = Decimal(0)
    totals = {"verified": zero, "pending": zero, "rejected": zero, "screenshots": 0}
    per = {}
    entries = []
    for r in rows:
        st = storage.payment_state(r)
        amt = _amount_of(r, ws_map)
        w = ws_map.get(str(r["workshop_id"]))
        b = per.setdefault(str(r["workshop_id"]), {
            "title": w.title if w else r.get("workshop_title", "(deleted workshop)"), "fee": w.fee if w else None,
            "students": 0, "wants": 0, "screenshots": 0, "verified": zero, "pending": zero, "rejected": zero})
        b["students"] += 1
        if str(r.get("wants_certificate", "") or "yes").lower() != "no":
            b["wants"] += 1
        if r.get("payment_screenshot"):
            b["screenshots"] += 1
            totals["screenshots"] += 1
        if st in ("verified", "pending", "rejected") and amt > 0:
            b[st] += amt
            totals[st] += amt
            entries.append({**r, "pay": st, "amount_rs": amt})
    entries.sort(key=lambda r: str(r["registered_at"]), reverse=True)
    return render(request, "payments.html", {
        "totals": totals, "per": sorted(per.values(), key=lambda b: b["title"]), "entries": entries[:80],
        "workshops": Workshop.objects.all(), "chosen": chosen, "error": "",
    })


@STAFF
@require_POST
def payment_upload(request, reg_id):
    """Staff attach a payment screenshot for a student (for example one sent on WhatsApp)."""
    f = request.FILES.get("screenshot")
    if not f:
        messages.error(request, "Choose a screenshot image first.")
        return _back(request, "registrations")
    try:
        from PIL import Image
        if f.size > settings.MAX_SCREENSHOT_BYTES:
            raise ValueError("That image is too large. Please use one under 4 MB.")
        img = Image.open(f)
        img.verify()
        if img.format not in ("JPEG", "PNG", "WEBP", "GIF"):
            raise ValueError("Use a JPG, PNG or WebP image.")
        f.seek(0)
        f.image = img  # _save_proof reads the format from here
    except ValueError as e:
        messages.error(request, str(e))
        return _back(request, "registrations")
    except Exception:
        messages.error(request, "That file is not a valid image.")
        return _back(request, "registrations")
    try:
        row = storage.get_registration(reg_id)
        if not row:
            messages.error(request, "Registration not found.")
            return _back(request, "registrations")
        name = _save_proof(f, reg_id)
        if row.get("payment_screenshot") and row["payment_screenshot"] != name:
            _drop_proof(row["payment_screenshot"])
        w = Workshop.objects.filter(pk=row["workshop_id"]).first()
        status = "verified" if request.POST.get("verified") else "pending"
        changes = {"payment_screenshot": name, "wants_certificate": "yes", "payment_status": status}
        if not str(row.get("amount", "") or "").strip() and w and w.fee:
            changes["amount"] = _fee_text(w.fee)
        storage.update_fields(reg_id, **changes)
        messages.success(request, f"Screenshot saved for {row['full_name']}" + (" and payment marked verified." if status == "verified" else ". Tick Payment verified when you have checked it."))
        if status == "verified":
            code, text = certflow.try_auto(reg_id)
            if code == "sent":
                messages.success(request, f"Certificate emailed to {row['email']}.")
    except storage.StorageError as e:
        messages.error(request, str(e))
    return _back(request, "registrations")


# ---------------------------------------------------------------- announcement brochures
ANNOUNCE_TYPES = {".pdf": b"%PDF", ".docx": b"PK", ".pptx": b"PK", ".xlsx": b"PK",
                  ".doc": b"\xd0\xcf\x11\xe0", ".ppt": b"\xd0\xcf\x11\xe0"}
ANNOUNCE_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}


def _add_announce_files(draft, files):
    """Save uploaded brochures. Returns a list of problems (empty if all went well)."""
    from PIL import Image
    problems = []
    existing = list(draft.files.all())
    total = sum(f.size for f in existing)
    for f in files:
        name = re.sub(r"[^\w\-. ()]+", "", Path(f.name).name).strip()[:100] or "attachment"
        ext = Path(name).suffix.lower()
        if len(existing) >= settings.MAX_ANNOUNCE_FILES:
            problems.append(f"{name}: at most {settings.MAX_ANNOUNCE_FILES} files can be attached")
            continue
        if f.size > settings.MAX_ANNOUNCE_FILE_BYTES:
            problems.append(f"{name}: larger than {settings.MAX_ANNOUNCE_FILE_BYTES // (1024 * 1024)} MB")
            continue
        if total + f.size > settings.MAX_ANNOUNCE_TOTAL_BYTES:
            problems.append(f"{name}: the files together would be too big for one email")
            continue
        head = f.read(8)
        f.seek(0)
        if ext in ANNOUNCE_IMAGES:
            try:
                Image.open(f).verify()
                f.seek(0)
            except Exception:
                problems.append(f"{name}: not a valid image")
                continue
        elif ext in ANNOUNCE_TYPES:
            if not head.startswith(ANNOUNCE_TYPES[ext]):
                problems.append(f"{name}: the file does not look like a real {ext[1:].upper()}")
                continue
        else:
            problems.append(f"{name}: use PDF, JPG, PNG, WEBP, Word or PowerPoint files")
            continue
        obj = AnnouncementFile(draft=draft, original_name=name, size=f.size)
        obj.file.save(f"{uuid.uuid4().hex[:16]}{ext}", f, save=False)
        obj.save()
        existing.append(obj)
        total += f.size
    return problems
