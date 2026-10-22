import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from cloudinary.models import CloudinaryField

RESERVED_SLUGS = {"permanent"}


class _PrivateCertStorage(FileSystemStorage):
    """Looks up the folder from settings each time, so changing CERT_TEMPLATES_DIR always takes effect."""

    @property
    def base_location(self):
        return str(settings.CERT_TEMPLATES_DIR)

    @property
    def location(self):
        return os.path.abspath(self.base_location)


class _PrivateAnnounceStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(settings.ANNOUNCE_FILES_DIR)

    @property
    def location(self):
        return os.path.abspath(self.base_location)


def private_announce_storage():
    return _PrivateAnnounceStorage()


def private_cert_storage():
    """Certificate templates live outside media/, so they are never served as public files."""
    return _PrivateCertStorage()


def _lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


class Workshop(models.Model):
    MODE_CHOICES = [("online", "Online"), ("offline", "Offline"), ("hybrid", "Hybrid")]
    STATUS_CHOICES = [("draft", "Draft (hidden)"), ("published", "Published"), ("archived", "Archived")]
    REG_CHOICES = [("open", "Open"), ("full", "Full"), ("closed", "Closed")]

    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True, blank=True, editable=False)
    description = models.TextField(blank=True)
    start_datetime = models.DateTimeField("Start (IST)")
    end_datetime = models.DateTimeField("End (IST)", null=True, blank=True)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default="online")
    venue = models.CharField("Venue (offline / hybrid)", max_length=250, blank=True)
    meeting_link = models.URLField("Meeting link (online / hybrid)", blank=True,
                                   help_text="Only emailed to registered students. Never shown on the website.")
    poster = CloudinaryField("Poster / banner", folder="posters", use_filename=True, unique_filename=True, blank=True)
    trainer = models.CharField(max_length=150, blank=True)
    trainer_bio = models.TextField(blank=True)
    topics = models.TextField(blank=True, help_text="One topic per line.")
    outcomes = models.TextField("Learning outcomes", blank=True, help_text="One outcome per line.")
    registration_deadline = models.DateTimeField(null=True, blank=True,
                                                 help_text="Blank means registration closes when the workshop starts.")
    capacity = models.PositiveIntegerField("Seat limit", null=True, blank=True,
                                           help_text="Leave blank for no limit. Remaining seats are shown only if set.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    registration_status = models.CharField(max_length=10, choices=REG_CHOICES, default="open")
    featured = models.BooleanField(default=False, help_text="Shown first on the home page. Only one can be featured.")
    fee = models.DecimalField("Fee (₹)", max_digits=8, decimal_places=2, null=True, blank=True,
                              help_text="Blank or 0 means free. Change this every week with the workshop.")
    payment_upi = models.CharField("UPI ID", max_length=100, blank=True)
    payment_qr = CloudinaryField("Payment QR image", folder="payment", use_filename=True, unique_filename=True, blank=True,
                                   help_text="Upload this week's QR. If left empty, a QR is made from the UPI ID and the fee.")
    # ---- certificate (every workshop has its own template) ----
    cert_template = CloudinaryField(
        "Certificate template", folder="certificates", use_filename=True, unique_filename=True, blank=True,
        help_text="This workshop's blank certificate as a JPG or PNG. The student's name is written on it automatically.")
    cert_name_x = models.FloatField("Name position, left to right (%)", default=50.0,
                                    validators=[MinValueValidator(0), MaxValueValidator(100)])
    cert_name_y = models.FloatField("Name position, top to bottom (%)", default=50.0,
                                    validators=[MinValueValidator(0), MaxValueValidator(100)])
    cert_font_size = models.FloatField("Name size (% of certificate width)", default=5.0,
                                       validators=[MinValueValidator(0.5), MaxValueValidator(20)])
    cert_color = models.CharField("Name colour", max_length=7, default="#1f2937")
    cert_font = models.CharField("Name font file", max_length=80, blank=True)
    cert_id_prefix = models.CharField("Certificate ID prefix", max_length=60, blank=True)
    cert_id_next = models.PositiveIntegerField("Next certificate number", default=1)
    cert_id_width = models.PositiveSmallIntegerField("Certificate number digits", default=0)
    cert_id_x = models.FloatField("ID position, left to right (%)", default=50.0,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    cert_id_y = models.FloatField("ID position, top to bottom (%)", default=88.0,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    cert_id_size = models.FloatField("ID size (% of certificate width)", default=1.6,
                                     validators=[MinValueValidator(0.5), MaxValueValidator(10)])
    fee_for_certificate = models.BooleanField(
        "Fee is for the certificate (optional)", default=True,
        help_text="Ticked: the workshop is free to join, and students choose Yes/No for a paid certificate. "
                  "Unticked: everyone must pay the fee to register.")
    announced_at = models.DateTimeField("First announced to past attendees", null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("workshop_detail", args=[self.slug])

    def clean(self):
        errors = {}
        if self.end_datetime and self.start_datetime and self.end_datetime < self.start_datetime:
            errors["end_datetime"] = "End must be after the start."
        if self.mode in ("offline", "hybrid") and not self.venue:
            errors["venue"] = "Venue is required for offline or hybrid workshops."
        if self.registration_deadline and self.start_datetime and self.registration_deadline > self.start_datetime:
            errors["registration_deadline"] = "Deadline cannot be after the workshop starts."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.title}-{self.start_datetime:%Y-%m-%d}")[:70] or "workshop"
            if base in RESERVED_SLUGS:
                base += "-w"
            slug, n = base, 2
            while Workshop.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        if self.status != "published":
            self.featured = False
        super().save(*args, **kwargs)
        if self.featured:
            Workshop.objects.exclude(pk=self.pk).filter(featured=True).update(featured=False)

    # ---- computed state ----
    @property
    def topics_list(self):
        return _lines(self.topics)

    @property
    def outcomes_list(self):
        return _lines(self.outcomes)

    @property
    def phase(self):
        now = timezone.now()
        end = self.end_datetime or self.start_datetime
        if now > end:
            return "completed"
        return "ongoing" if now >= self.start_datetime else "upcoming"

    @property
    def cutoff(self):
        return self.registration_deadline or self.start_datetime

    def reg_state(self, confirmed_count=0):
        """Effective registration state: 'open', 'full' or 'closed'."""
        if self.status != "published" or self.phase == "completed" or timezone.now() > self.cutoff:
            return "closed"
        if self.registration_status == "open":
            return "full" if self.capacity and confirmed_count >= self.capacity else "open"
        return "full" if self.registration_status == "full" else "closed"

    @property
    def duration_text(self):
        if not self.end_datetime:
            return ""
        mins = int((self.end_datetime - self.start_datetime).total_seconds() // 60)
        if mins <= 0:
            return ""
        h, m = divmod(mins, 60)
        return " ".join(p for p in (f"{h} hr" if h else "", f"{m} min" if m else "") if p)

    @property
    def time_range(self):
        def f(dt):
            return timezone.localtime(dt).strftime("%I:%M %p").lstrip("0")
        s = f(self.start_datetime)
        return f"{s} – {f(self.end_datetime)} IST" if self.end_datetime else f"{s} IST"

    @property
    def has_fee(self):
        return bool(self.fee and self.fee > 0)

    @property
    def needs_payment(self):
        """Students must pay and attach a screenshot when there is a fee and a way to pay."""
        return self.has_fee and bool(self.payment_upi or self.payment_qr)

    needs_payment_ref = needs_payment  # older name, kept so nothing else breaks

    @property
    def has_certificate(self):
        return bool(self.cert_template)

    @property
    def pay_optional(self):
        """The fee only buys the certificate, so the student chooses Yes or No."""
        return self.needs_payment and self.fee_for_certificate

    def next_certificate_id(self):
        if not self.cert_id_prefix:
            return ""
        return f"{self.cert_id_prefix}{str(self.cert_id_next).zfill(self.cert_id_width)}"


class GalleryImage(models.Model):
    """Photos from past workshops: students who attended, and screenshots of student feedback."""
    KIND_CHOICES = [("attendees", "Students at the workshop"), ("feedback", "Student feedback screenshot")]

    workshop = models.ForeignKey(Workshop, null=True, blank=True, on_delete=models.SET_NULL, related_name="gallery")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="attendees")
    image = CloudinaryField("Image", folder="gallery", use_filename=True, unique_filename=True, blank=True)
    caption = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Gallery image"

    def __str__(self):
        return self.caption or f"{self.get_kind_display()} #{self.pk}"


class Feedback(models.Model):
    """Feedback a student submits after a workshop. Staff can hide or delete it."""
    workshop = models.ForeignKey(Workshop, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback")
    workshop_title = models.CharField(max_length=150, blank=True)  # kept even if the workshop is deleted
    name = models.CharField(max_length=100)
    email = models.EmailField("Official email ID", max_length=150)
    rating = models.PositiveSmallIntegerField(choices=[(i, f"{i} star{'s' if i > 1 else ''}") for i in range(1, 6)])
    message = models.TextField("Feedback")
    show_on_site = models.BooleanField("Show on website", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "Feedback"

    def __str__(self):
        return f"{self.name} ({self.rating}/5) - {self.workshop_title}"


class Unsubscribed(models.Model):
    """People who asked not to get new-workshop emails."""
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Unsubscribed emails"

    def __str__(self):
        return self.email


class Announcement(models.Model):
    """One row per person emailed about a workshop. It stops anyone getting the same announcement twice."""
    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name="announcements")
    email = models.EmailField()
    name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=200)   # "sent" or "failed: reason"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workshop", "email"], name="one_announcement_per_person")]

    def __str__(self):
        return f"{self.email} - {self.workshop} - {self.status}"


class AnnouncementDraft(models.Model):
    """The email text and brochures for announcing one workshop."""
    workshop = models.OneToOneField(Workshop, on_delete=models.CASCADE, related_name="announce_draft")
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Announcement for {self.workshop}"


class AnnouncementFile(models.Model):
    draft = models.ForeignKey(AnnouncementDraft, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="", storage=private_announce_storage)
    original_name = models.CharField(max_length=150)
    size = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.original_name
