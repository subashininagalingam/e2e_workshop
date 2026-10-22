import re

from django import forms
from django.conf import settings

from . import certificates
from .models import Workshop

SKILL_LEVELS = ["Beginner", "Basic Knowledge", "Intermediate", "Advanced", "Other"]
DEMO_INTEREST = ["Yes, I want to attend a demo class to know more about my interested course", "Maybe", "Need more information", "No", "Other"]
DEMO_MODES = ["Online", "Offline", "Either is okay"]
DEMO_SLOTS = ["Morning", "Afternoon", "Evening", "Weekend", "Other"]
BLANK = [("", "Select…")]
# (field, max length): text answers that are cleaned and must have at least 2 characters
REQUIRED_TEXT = (("current_address", 300), ("education_qualification", 120), ("current_status", 120),
                 ("heard_from", 150), ("interest_domain", 150), ("referred_by", 120))
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def _text(value, limit):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", " ", str(value or ""))).strip()[:limit]


class RegistrationForm(forms.Form):
    workshop = forms.ChoiceField(label="Workshop", error_messages={"required": "Please select a workshop."})
    participation_mode = forms.ChoiceField(
        label="Participation mode", required=False,
        choices=[("online", "Online"), ("offline", "Offline (in person)")], widget=forms.RadioSelect,
    )
    full_name = forms.CharField(label="Full name", max_length=100)
    email = forms.CharField(label="Email address", max_length=150, widget=forms.EmailInput)
    phone = forms.CharField(label="Mobile number", max_length=20)
    current_address = forms.CharField(label="Current address", max_length=300, widget=forms.Textarea(attrs={"rows": 2}))
    college = forms.CharField(label="College / Institution name", max_length=200)
    education_qualification = forms.CharField(label="Education qualification", max_length=120)
    current_status = forms.CharField(label="Current status", max_length=120)
    heard_from = forms.CharField(label="Where did you hear about this workshop / bootcamp?", max_length=150)
    interest_domain = forms.CharField(label="Technology or career domain you are interested in", max_length=150)
    skill_level = forms.ChoiceField(label="Your current technical skill level", choices=BLANK + [(x, x) for x in SKILL_LEVELS])
    demo_interest = forms.ChoiceField(label="Would you like to attend a FREE demo class on your interested courses?",
                                      choices=BLANK + [(x, x) for x in DEMO_INTEREST])
    demo_mode = forms.ChoiceField(label="Preferred demo session mode", required=False, choices=BLANK + [(x, x) for x in DEMO_MODES])
    demo_slot = forms.ChoiceField(label="Preferred demo time slot", required=False, choices=BLANK + [(x, x) for x in DEMO_SLOTS])
    queries = forms.CharField(label="Any queries?", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))
    referred_by = forms.CharField(label="Referred by (person or source name)", max_length=120)
    wants_certificate = forms.ChoiceField(
        label="Do you want a certificate for this workshop?", required=False, widget=forms.RadioSelect,
        choices=[("yes", "Yes, I want a certificate"), ("no", "No, just register me")],
    )
    payment_reference = forms.CharField(label="UTR / transaction ID (optional)", max_length=60, required=False)
    payment_screenshot = forms.ImageField(
        label="Payment screenshot", required=False,
        error_messages={"invalid_image": "Upload a screenshot as a JPG, PNG or WebP image."},
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )
    consent = forms.BooleanField(
        label="I agree to be contacted by Errors2Experts IT Training & Services about training programs, demo classes, internships and workshops (including emails about new workshops).",
        error_messages={"required": "Consent is required to register."},
    )
    website = forms.CharField(required=False, label="Website")  # honeypot: humans never see it
    ts = forms.CharField(required=False, widget=forms.HiddenInput)  # signed time the form was shown

    def __init__(self, *args, workshops=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.workshops = {str(w.pk): w for w in workshops}
        blank = [("", "Select a workshop…")] if len(self.workshops) != 1 else []
        self.fields["workshop"].choices = blank + [
            (pk, f"{w.title} — {w.start_datetime:%d %b %Y}") for pk, w in self.workshops.items()
        ]
        for name, f in self.fields.items():
            w = f.widget
            if isinstance(w, forms.Select):
                w.attrs["class"] = "form-select"
            elif isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, forms.RadioSelect):
                w.attrs["class"] = "form-check-input"
            elif not isinstance(w, forms.HiddenInput):
                w.attrs["class"] = "form-control"
        self.fields["payment_screenshot"].widget.attrs["class"] = "form-control"
        self.fields["phone"].widget.attrs.update(inputmode="numeric", autocomplete="tel", placeholder="10-digit number")
        self.fields["full_name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].widget.attrs.update(autocomplete="email")
        self.fields["website"].widget.attrs.update(tabindex="-1", autocomplete="off")

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                cls = self.fields[name].widget.attrs.get("class", "")
                self.fields[name].widget.attrs["class"] = (cls + " is-invalid").strip()

    def clean_full_name(self):
        v = _text(self.cleaned_data["full_name"], 100)
        if len(v) < 2:
            raise forms.ValidationError("Please enter your full name.")
        return v

    def clean_email(self):
        v = _text(self.cleaned_data["email"], 150).replace(" ", "").lower()
        if not EMAIL_RE.match(v):
            raise forms.ValidationError("Enter a valid email address.")
        return v

    def clean_phone(self):
        v = re.sub(r"[\s\-()]", "", self.cleaned_data["phone"])
        v = re.sub(r"^\+?(91|0)?", "", v)
        if not re.fullmatch(r"[6-9]\d{9}", v):
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        return v

    def clean_college(self):
        v = _text(self.cleaned_data["college"], 200)
        if len(v) < 2:
            raise forms.ValidationError("Enter your college or institution.")
        return v

    def clean_payment_reference(self):
        return _text(self.cleaned_data.get("payment_reference"), 60)

    def clean_payment_screenshot(self):
        f = self.cleaned_data.get("payment_screenshot")
        if f and f.size > settings.MAX_SCREENSHOT_BYTES:
            raise forms.ValidationError("That image is too large. Please upload one under 4 MB.")
        return f

    def clean(self):
        cd = super().clean()
        for name, limit in REQUIRED_TEXT:
            if name in cd:
                cd[name] = _text(cd[name], limit)
                if len(cd[name]) < 2:
                    self.add_error(name, "Please fill this in.")
        if "queries" in cd:
            cd["queries"] = _text(cd["queries"], 500)
        w = self.workshops.get(cd.get("workshop", ""))
        if cd.get("workshop") and not w:
            self.add_error("workshop", "That workshop is not open for registration.")
        elif w:
            if w.mode == "hybrid":
                if cd.get("participation_mode") not in ("online", "offline"):
                    self.add_error("participation_mode", "Choose online or offline.")
            else:
                cd["participation_mode"] = w.mode
            if w.pay_optional:  # the fee buys the certificate: the student chooses Yes or No
                if cd.get("wants_certificate") not in ("yes", "no"):
                    self.add_error("wants_certificate", "Please choose Yes or No.")
            else:
                cd["wants_certificate"] = "yes"  # free workshop, or a fee everyone pays
            if w.needs_payment and cd.get("wants_certificate") == "yes":
                if not cd.get("payment_screenshot") and "payment_screenshot" not in self.errors:
                    self.add_error("payment_screenshot", "Attach your payment screenshot to finish registering.")
            elif cd.get("wants_certificate") == "no":
                cd["payment_screenshot"] = None  # nothing to pay: ignore anything attached
                cd["payment_reference"] = ""
        return cd


class FeedbackForm(forms.Form):
    workshop = forms.ChoiceField(label="Workshop you attended", error_messages={"required": "Please select the workshop."})
    name = forms.CharField(label="Your name", max_length=100)
    email = forms.CharField(label="Official email ID", max_length=150, widget=forms.EmailInput,
                            help_text="Use the email you registered with. It is never shown on the website.")
    rating = forms.ChoiceField(label="Your rating", choices=[(str(i), str(i)) for i in range(5, 0, -1)],
                               widget=forms.RadioSelect, error_messages={"required": "Choose a rating from 1 to 5 stars."})
    message = forms.CharField(label="Your feedback", max_length=1500, widget=forms.Textarea(attrs={"rows": 5}))
    website = forms.CharField(required=False, label="Website")  # honeypot
    ts = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, workshops=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.workshops = {str(w.pk): w for w in workshops}
        blank = [("", "Select a workshop…")] if len(self.workshops) != 1 else []
        self.fields["workshop"].choices = blank + [(pk, f"{w.title} — {w.start_datetime:%d %b %Y}") for pk, w in self.workshops.items()]
        self.fields["workshop"].widget.attrs["class"] = "form-select"
        for n in ("name", "email", "message"):
            self.fields[n].widget.attrs["class"] = "form-control"
        self.fields["name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].widget.attrs.update(autocomplete="email", placeholder="you@college.edu.in")
        self.fields["message"].widget.attrs["placeholder"] = "What did you learn? What could be better?"
        self.fields["website"].widget.attrs.update(tabindex="-1", autocomplete="off")

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields and name != "rating":
                cls = self.fields[name].widget.attrs.get("class", "")
                self.fields[name].widget.attrs["class"] = (cls + " is-invalid").strip()

    def clean_workshop(self):
        v = self.cleaned_data["workshop"]
        if v not in self.workshops:
            raise forms.ValidationError("That workshop is not available for feedback.")
        return v

    def clean_name(self):
        v = _text(self.cleaned_data["name"], 100)
        if len(v) < 2:
            raise forms.ValidationError("Please enter your name.")
        return v

    def clean_email(self):
        v = _text(self.cleaned_data["email"], 150).replace(" ", "").lower()
        if not EMAIL_RE.match(v):
            raise forms.ValidationError("Enter a valid email address.")
        return v

    def clean_message(self):
        v = _text(self.cleaned_data["message"], 1500)
        if len(v) < 10:
            raise forms.ValidationError("Please write at least a short sentence (10 characters).")
        return v


class CertificateSetupForm(forms.ModelForm):
    cert_font = forms.ChoiceField(label="Name font", required=False)
    cert_id_start = forms.CharField(
        label="First certificate ID", required=False, max_length=70,
        help_text="Type the first ID, for example E2E/WS/2026/500. The first certificate gets exactly this, "
                  "then 501, 502 and so on. Leave empty to print no ID.")

    class Meta:
        model = Workshop
        fields = ["cert_template", "cert_name_x", "cert_name_y", "cert_font_size", "cert_color", "cert_font",
                  "cert_id_x", "cert_id_y", "cert_id_size"]
        widgets = {
            "cert_template": forms.FileInput(attrs={"accept": "image/png,image/jpeg", "class": "form-control"}),
            "cert_name_x": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": 100, "class": "form-control"}),
            "cert_name_y": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": 100, "class": "form-control"}),
            "cert_font_size": forms.NumberInput(attrs={"step": "0.1", "min": 0.5, "max": 20, "class": "form-control"}),
            "cert_color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color"}),
            "cert_id_x": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": 100, "class": "form-control"}),
            "cert_id_y": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": 100, "class": "form-control"}),
            "cert_id_size": forms.NumberInput(attrs={"step": "0.1", "min": 0.5, "max": 10, "class": "form-control"}),
        }

    def __init__(self, *args, fonts=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cert_font"].choices = [("", "Default (serif, bold italic)")] + list(fonts)
        self.fields["cert_font"].widget.attrs["class"] = "form-select"
        self.fields["cert_template"].required = False
        self.fields["cert_id_start"].widget.attrs.update({"class": "form-control", "placeholder": "E2E/WS/2026/500"})
        self.current_id = self.instance.next_certificate_id() if self.instance and self.instance.pk else ""
        self.fields["cert_id_start"].initial = self.current_id

    def clean_cert_template(self):
        f = self.cleaned_data.get("cert_template")
        if f and hasattr(f, "size"):
            if f.size > settings.MAX_CERT_TEMPLATE_BYTES:
                raise forms.ValidationError("That file is larger than 15 MB. Please export a smaller JPG or PNG.")
            fmt = getattr(getattr(f, "image", None), "format", "")
            if fmt and fmt not in ("JPEG", "PNG"):
                raise forms.ValidationError("Upload the certificate as a JPG or PNG image.")
        return f

    def clean_cert_id_start(self):
        v = " ".join((self.cleaned_data.get("cert_id_start") or "").split())
        if v and v != self.current_id and certificates.parse_certificate_id(v) is None:
            raise forms.ValidationError("The ID must end with a number, for example E2E/WS/2026/500.")
        return v

    def save(self, commit=True):
        obj = super().save(commit=False)
        v = self.cleaned_data.get("cert_id_start", "")
        if v != self.current_id:  # changed by the user: restart the numbering from what they typed
            if not v:
                obj.cert_id_prefix = ""
            else:
                prefix, number, width = certificates.parse_certificate_id(v)
                obj.cert_id_prefix, obj.cert_id_next, obj.cert_id_width = prefix, number, width
        if commit:
            obj.save()
        return obj

    def clean_cert_color(self):
        v = (self.cleaned_data.get("cert_color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise forms.ValidationError("Choose a colour.")
        return v
