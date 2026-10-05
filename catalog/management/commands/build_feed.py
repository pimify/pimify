"""Phase 4: render a Feed to FEEDS_ROOT and log the run.

Pull model: this command builds the file; commerce platforms fetch it via
the runs download endpoint. Failure records a failed FeedRun (with the
error) and exits non-zero, so cron/scheduler surfaces it.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.feeds import build_feed_payload, render_csv, render_json
from catalog.models import Feed, FeedRun, FeedRunStatus


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
        root = Path(settings.FEEDS_ROOT)
        root.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        filename = f"{obj.id}_{stamp}.{obj.format}"
        try:
            payload, skipped = build_feed_payload(obj)
            body = render_json(payload) if obj.format == 'json' else render_csv(payload)
            (root / filename).write_text(body, encoding='utf-8')
        except Exception as exc:  # noqa: BLE001 — must log, then fail loudly
            FeedRun.objects.create(
                feed=obj, status=FeedRunStatus.FAILED, error=f'{type(exc).__name__}: {exc}')
            raise CommandError(f'Feed {obj.name!r} failed: {exc}') from exc
        run = FeedRun.objects.create(
            feed=obj, status=FeedRunStatus.SUCCESS,
            items=len(payload['products']), skipped=skipped, file=filename)
        skipped_msg = f' ({len(skipped)} skipped)' if skipped else ''
        self.stdout.write(self.style.SUCCESS(
            f'Feed {obj.name!r}: {run.items} products -> {filename}{skipped_msg} (run {run.pk})'))
