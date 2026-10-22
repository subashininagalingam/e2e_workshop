from django.contrib import admin, messages
from django.utils.html import format_html

from . import storage
from django.urls import reverse

from .models import Announcement, Feedback, GalleryImage, Unsubscribed, Workshop


class GalleryInline(admin.TabularInline):
    model = GalleryImage
    extra = 3
    fields = ("kind", "image", "caption")
    verbose_name_plural = "Photos and feedback screenshots from this workshop (add many at once)"


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "workshop", "created_at", "thumb")
    list_filter = ("kind", "workshop")

    @admin.display(description="Image")
    def thumb(self, obj):
        return format_html('<img src="{}" style="height:48px;border-radius:6px">', obj.image.url) if obj.image else ""


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "workshop_title", "rating", "show_on_site", "created_at")
    list_filter = ("rating", "show_on_site", "workshop")
    search_fields = ("name", "email", "message")
    actions = ["hide", "show"]

    @admin.action(description="Hide selected feedback from the website")
    def hide(self, request, queryset):
        queryset.update(show_on_site=False)

    @admin.action(description="Show selected feedback on the website")
    def show(self, request, queryset):
        queryset.update(show_on_site=True)


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    inlines = [GalleryInline]
    list_display = ("title", "start_datetime", "mode", "status", "registration_status", "featured", "registrations", "preview")
    list_filter = ("status", "mode", "registration_status", "featured")
    search_fields = ("title",)
    readonly_fields = ("created_at", "updated_at", "certificate_tools")
    date_hierarchy = "start_datetime"
    fieldsets = (
        ("Basics", {"fields": ("title", "description", "poster", "status", "featured")}),
        ("Schedule", {"fields": ("start_datetime", "end_datetime", "registration_deadline")}),
        ("Mode and place", {"fields": ("mode", "venue", "meeting_link")}),
        ("Trainer", {"fields": ("trainer", "trainer_bio")}),
        ("Content", {"fields": ("topics", "outcomes")}),
        ("Registration", {"fields": ("registration_status", "capacity")}),
        ("Fee and payment QR (change every week)", {
            "description": "Fee ticked as 'for the certificate': students register free and choose Yes/No for a paid "
                           "certificate. Unticked: everyone must pay the fee to register.",
            "fields": ("fee", "fee_for_certificate", "payment_upi", "payment_qr")}),
        ("Certificate and announcement", {"fields": ("certificate_tools",)}),
        ("Info", {"fields": ("created_at", "updated_at")}),
    )
    actions = ["publish", "unpublish", "archive", "feature", "set_open", "set_full", "set_closed"]
    _counts = {}

    def changelist_view(self, request, extra_context=None):
        try:
            self._counts = storage.count_confirmed()
        except storage.StorageError:
            self._counts = {}
        return super().changelist_view(request, extra_context)

    @admin.display(description="Registrations")
    def registrations(self, obj):
        n = self._counts.get(str(obj.pk), 0)
        return f"{n} / {obj.capacity}" if obj.capacity else str(n)

    @admin.display(description="Certificate and announcement")
    def certificate_tools(self, obj):
        if not obj.pk:
            return "Save the workshop first, then come back here."
        return format_html(
            '<a href="{}">Certificate setup (upload template, place the name)</a> &nbsp;|&nbsp; <a href="{}">Announce to past students</a>',
            reverse("certificate_setup", args=[obj.pk]), reverse("announce", args=[obj.pk]))

    @admin.display(description="Preview")
    def preview(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">Preview</a>', obj.get_absolute_url())

    def _each(self, queryset, **changes):
        for w in queryset:
            for k, v in changes.items():
                setattr(w, k, v)
            w.save()

    @admin.action(description="Publish selected workshops")
    def publish(self, request, queryset):
        self._each(queryset, status="published")
        self.message_user(request, f"Published {queryset.count()} workshop(s).")

    @admin.action(description="Unpublish (hide) selected workshops")
    def unpublish(self, request, queryset):
        self._each(queryset, status="draft")
        self.message_user(request, f"Unpublished {queryset.count()} workshop(s).")

    @admin.action(description="Archive selected workshops (hidden and closed)")
    def archive(self, request, queryset):
        self._each(queryset, status="archived", registration_status="closed")
        self.message_user(request, f"Archived {queryset.count()} workshop(s).")

    @admin.action(description="Feature on home page (select exactly one published workshop)")
    def feature(self, request, queryset):
        if queryset.count() != 1 or queryset.first().status != "published":
            self.message_user(request, "Select exactly one published workshop.", level=messages.ERROR)
            return
        self._each(queryset, featured=True)
        self.message_user(request, "Featured on the home page.")

    @admin.action(description="Set registration: Open")
    def set_open(self, request, queryset):
        self._each(queryset, registration_status="open")

    @admin.action(description="Set registration: Full")
    def set_full(self, request, queryset):
        self._each(queryset, registration_status="full")

    @admin.action(description="Set registration: Closed")
    def set_closed(self, request, queryset):
        self._each(queryset, registration_status="closed")


@admin.register(Unsubscribed)
class UnsubscribedAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at")
    search_fields = ("email",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("email", "workshop", "status", "created_at")
    list_filter = ("workshop",)
    search_fields = ("email", "name")
    readonly_fields = ("workshop", "email", "name", "status", "created_at")

    def has_add_permission(self, request):
        return False
