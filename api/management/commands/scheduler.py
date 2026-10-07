# Import necessary modules
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from django_apscheduler import util
from django.core.management import call_command
from django.core.management.base import BaseCommand

# Function to backup db
def backup_db_every_month():
    try:
        call_command('dbbackup', clean=True)
        print("Database backed up successfully.")
    except Exception as e:
        print(f"An error occurred during database backup: {e}")

# Funtion to backup media
def backup_media_every_month():
    try:
        call_command('mediabackup', clean=True)
        print("Media files backed up successfully.")
    except Exception as e:
        print(f"An error occurred during media backup: {e}")

# Scheduled channel feeds: one job per active feed with a crontab cadence.
# Runs in-process via catalog.feeds.run_feed (same path as `build_feed`);
# failures are already recorded as failed FeedRuns there.
@util.close_old_connections
def build_scheduled_feed(feed_id):
    from catalog.feeds import run_feed
    from catalog.models import Feed
    try:
        feed = Feed.objects.get(pk=feed_id, is_active=True)
    except Feed.DoesNotExist:
        print(f"Scheduled feed {feed_id} gone or inactive; skipping.")
        return
    try:
        run = run_feed(feed)
        print(f"Scheduled feed {feed.name!r}: {run.items} products (run {run.pk}).")
    except Exception as e:
        print(f"Scheduled feed {feed.name!r} failed: {e}")

def scheduled_feeds():
    """Active feeds with a crontab cadence (blank = manual builds only).

    Phase 4.3: feeds targeting an inactive Locale are excluded — run_feed
    refuses them, so scheduling them would append a failed FeedRun on every
    tick forever (FeedRun is append-only with no retention).
    """
    from catalog.models import Feed
    return (Feed.objects.filter(is_active=True)
            .exclude(schedule_cron='')
            .select_related('locale')
            .filter(locale__is_active=True))


def unschedulable_feeds():
    """Cron-configured feeds skipped because their locale is inactive
    (reported once at scheduler start instead of failing every tick)."""
    from catalog.models import Feed
    return (Feed.objects.filter(is_active=True)
            .exclude(schedule_cron='')
            .filter(locale__is_active=False))

# Function to delete old job executions
@util.close_old_connections  # Ensures database connections are closed properly
def delete_old_job_executions(max_age=7):
    DjangoJobExecution.objects.delete_old_job_executions(max_age)  # Delete jobs older than 'max_age' days

# Build the scheduler (testable without blocking); start() runs it.
def build_scheduler():
    scheduler = BackgroundScheduler()  # Create a background scheduler
    scheduler.add_jobstore(DjangoJobStore(), "default")  # Use Django's database as the job store

    # Add a job to backup db every month
    scheduler.add_job(
        backup_db_every_month,
        trigger=CronTrigger(day='last', hour=23, minute=59),  # Run on the last day of every month at 11:59 PM
        jobstore='default',
        id="db_backup",
        replace_existing=True,
    )

    # Add a job to backup media files every month
    scheduler.add_job(
        backup_media_every_month,
        trigger=CronTrigger(day='last', hour=23, minute=45),  # 15 mins before DB backup
        jobstore='default',
        id="media_backup",
        replace_existing=True,
    )

    # Add a job to delete old job executions every 7 days
    scheduler.add_job(
        delete_old_job_executions,
        'interval',
        days=7,
        jobstore='default',
        id="delete_old_job_executions",
        replace_existing=True,
    )

    # Feeds that can never build (inactive locale) are reported once here
    # rather than failing on every tick and appending a failed run each time.
    for feed in unschedulable_feeds():
        print(f"Feed {feed.name!r} targets inactive locale "
              f"{feed.locale_id!r}; not scheduled.")

    # One job per scheduled feed (cron validated at Feed.clean time, but
    # rows can bypass validation via shell/import — a single bad row must
    # never take down backups. Stale feed_* jobs (cron cleared, feed gone)
    # are removed so old cadences stop firing.)
    wanted = set()
    for feed in scheduled_feeds():
        try:
            trigger = CronTrigger.from_crontab(feed.schedule_cron)
        except ValueError as exc:
            print(f"Feed {feed.name!r} has invalid cron "
                  f"{feed.schedule_cron!r} ({exc}); skipping.")
            continue
        job_id = f"feed_{feed.pk}"
        wanted.add(job_id)
        scheduler.add_job(
            build_scheduled_feed,
            trigger=trigger,
            args=[feed.pk],
            jobstore='default',
            id=job_id,
            replace_existing=True,
        )
    for job in scheduler.get_jobs():
        if job.id.startswith('feed_') and job.id not in wanted:
            scheduler.remove_job(job.id, jobstore='default')
            print(f"Removed stale scheduled job {job.id}.")

    return scheduler

# Function to start the scheduler
def start():
    scheduler = build_scheduler()

    try:
        scheduler.start()  # Start the scheduler
        print("Scheduler started successfully.")
    except Exception as e:
        print(f"Failed to start scheduler: {e}")

# Management command to run the scheduler
class Command(BaseCommand):
    help = "Runs the background scheduler for periodic tasks"

    def handle(self, *args, **kwargs):
        start()
