from django.core.management.base import BaseCommand, CommandError

from workshops import announce
from workshops.models import Workshop


class Command(BaseCommand):
    help = "Email a published workshop to students of earlier workshops (each person once)."

    def add_arguments(self, parser):
        parser.add_argument("workshop_id", type=int)
        parser.add_argument("--batch", type=int, default=100, help="Maximum emails in this run (default 100)")

    def handle(self, *args, **opts):
        w = Workshop.objects.filter(pk=opts["workshop_id"]).first()
        if not w:
            raise CommandError("No such workshop")
        if w.status != "published":
            raise CommandError("Publish the workshop first")
        st = announce.state(w)
        self.stdout.write(f"{st['total']} past students, {st['sent']} already emailed, {st['remaining']} to go")
        sent, failed = announce.send_batch(w, opts["batch"])
        self.stdout.write(f"Sent {sent}, failed {failed}")
