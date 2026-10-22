from django.core.management.base import BaseCommand

from workshops import certflow, storage
from workshops.models import Workshop


class Command(BaseCommand):
    help = "Email every certificate that is ready (payment verified + feedback received). Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--workshop", type=int, help="Only this workshop id")
        parser.add_argument("--dry-run", action="store_true", help="Show how many are ready without sending")

    def handle(self, *args, **opts):
        qs = Workshop.objects.exclude(status="draft")
        if opts["workshop"]:
            qs = qs.filter(pk=opts["workshop"])
        keys = certflow.feedback_keys()
        rows = storage.list_registrations()
        for w in qs:
            if not w.has_certificate:
                self.stdout.write(f"{w.title}: no certificate template, skipped")
                continue
            ready = [r for r in rows if str(r["workshop_id"]) == str(w.pk) and r["registration_status"] == "confirmed"
                     and certflow.status_for(r, w, keys)[0] == "ready"]
            if opts["dry_run"]:
                self.stdout.write(f"{w.title}: {len(ready)} ready")
                continue
            sent, failed, left = certflow.send_ready(w, limit=100000)
            self.stdout.write(f"{w.title}: sent {sent}, failed {failed}")
