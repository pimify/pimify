"""Phase 4.1: render a Feed to FEEDS_ROOT and log the run.

Pull model: this command builds the file; commerce platforms fetch it via
the runs download endpoint. Failure records a failed FeedRun (with the
error) and exits non-zero, so cron/scheduler surfaces it. Thin wrapper
over catalog.feeds.run_feed (shared with the scheduler).
"""
from django.core.management.base import BaseCommand, CommandError

from catalog.feeds import run_feed
from catalog.models import Feed


class Command(BaseCommand):
    help = "Build a channel feed file and log the run (lookup by name or id)."

    def add_arguments(self, parser):
        parser.add_argument('feed', help='Feed name or id')

    def handle(self, *args, feed, **options):
        try:
            obj = Feed.objects.get(pk=feed) if feed.isdigit() else Feed.objects.get(name=feed)
        except Feed.DoesNotExist:
            raise CommandError(f'Feed {feed!r} not found.')
        if not obj.is_active:
            raise CommandError(f'Feed {obj.name!r} is inactive; not building.')
        try:
            run = run_feed(obj)
        except Exception as exc:  # noqa: BLE001 — run already logged as failed
            raise CommandError(f'Feed {obj.name!r} failed: {exc}') from exc
        skipped_total = sum(len(v) for v in run.skipped.values())
        skipped_msg = f' ({skipped_total} skipped)' if skipped_total else ''
        self.stdout.write(self.style.SUCCESS(
            f'Feed {obj.name!r}: {run.items} products -> {run.file}{skipped_msg} (run {run.pk})'))
