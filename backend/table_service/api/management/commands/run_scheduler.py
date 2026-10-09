from django.core.management.base import BaseCommand
from api.scheduler import start_scheduler, stop_scheduler
import time
import sys

class Command(BaseCommand):
    help = "Runs scheduler on all apps"
    def handle(self, *args, **options):
        test = start_scheduler()
        message = test if isinstance(test, str) else "WARN"
        self.stdout.write(self.style.SUCCESS(f"{message}"))
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            stop_scheduler()
            sys.exit(0)