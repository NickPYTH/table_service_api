import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

from tables.models import Row, Cell, Table

job_logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Yekaterinburg'))
scheduler.add_jobstore(DjangoJobStore(), 'default')

TZ = pytz.timezone('Asia/Yekaterinburg')



def clean_row():
    with transaction.atomic():
        today = timezone.now().date()
        one_year_ago_exact = today - relativedelta(years=1)
        job_logger.info('START')
        tables = Table.objects.filter(delete_row=True)
        job_logger.info(tables.count(),'Tables deleted')
        rows_to_delete = []
        cells_to_delete = []
        for table in tables:
            rows = Row.objects.filter(table=table,delete_date__lt=one_year_ago_exact).values_list('id', flat=True)
            cells = Cell.objects.filter(table_id=table.id,row__in=rows).values_list('id', flat=True)
            rows_to_delete.extend(rows)
            cells_to_delete.extend(cells)
        deleted_rows = Row.objects.filter(id__in=rows_to_delete).delete()
        deleted_cells =Cell.objects.filter(id__in=cells_to_delete).delete()
        job_logger.info('Deleted rows')
    job_logger.info('END')
    return deleted_rows,deleted_cells



def clean_old_job_executions():
    DjangoJobExecution.objects.delete_old_job_executions(0)


def clean_stale_jobs():
    from django_apscheduler.models import DjangoJob
    deleted, _ = DjangoJob.objects.filter(next_run_time__isnull=True).delete()
    job_logger.info(f"Удалено зависших задач: {deleted}")


def wakeuper():
    pass

def start_scheduler():
    if scheduler.running:
        job_logger.warning("Scheduler already running")
        return "Scheduler already running"
    try:
        # Будит его раз в 10 секунд
        scheduler.add_job(
            func=wakeuper,
            trigger='interval',
            seconds=10,
            id='_heartbeat',
            max_instances=1,
            replace_existing=True,
        )
        # Ежедневная очистка старых логов
        scheduler.add_job(
            func=clean_old_job_executions,
            trigger='interval',
            hours=5,
            id='_clean_old_job_executions',
            max_instances=1,
            replace_existing=True,
        )
        scheduler.add_job(
            func=clean_stale_jobs,
            trigger='interval',
            hours=2,
            id='_clean_stale_jobs',
            max_instances=1,
            replace_existing=True,
        )
        scheduler.start()
        job_logger.info("Scheduler started with heartbeat")
        return "Scheduler started"
    except Exception as e:
        job_logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        job_logger.info('Scheduler stopped')