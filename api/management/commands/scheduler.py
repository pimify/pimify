# Import necessary modules
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from django_apscheduler import util
from djmoney.contrib.exchange.backends import OpenExchangeRatesBackend
from django.core.management import call_command
from django.core.management.base import BaseCommand

# Function to update exchange rates
def sync_exchange_rates():
    try:
        backend = OpenExchangeRatesBackend()  # Initialize the exchange rates backend
        backend.update_rates()  # Update rates from OpenExchangeRates
        print("Exchange rates updated successfully.")
    except Exception as e:
        print(f"Failed to update exchange rates: {e}")

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

# Function to delete old job executions
@util.close_old_connections  # Ensures database connections are closed properly
def delete_old_job_executions(max_age=7):
    DjangoJobExecution.objects.delete_old_job_executions(max_age)  # Delete jobs older than 'max_age' days

# Function to start the scheduler
def start():
    scheduler = BackgroundScheduler()  # Create a background scheduler
    scheduler.add_jobstore(DjangoJobStore(), "default")  # Use Django's database as the job store

    # Add a job to update exchange rates every hour
    scheduler.add_job(
        sync_exchange_rates,
        'interval',
        hours=1,
        jobstore='default',
        id="update_exchange_rates",
        replace_existing=True,
    )

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

    try:
        scheduler.start()  # Start the scheduler
        print("Scheduler started successfully.")
        sync_exchange_rates()  # Perform an initial sync of exchange rates
    except Exception as e:
        print(f"Failed to start scheduler: {e}")

# Management command to run the scheduler
class Command(BaseCommand):
    help = "Runs the background scheduler for periodic tasks"

    def handle(self, *args, **kwargs):
        start()
