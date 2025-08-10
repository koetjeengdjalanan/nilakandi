"""Celery task handler for Nilakandi operations."""

import json
from uuid import UUID

from celery import Task
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from nilakandi.models import GenerationStatusEnum
from nilakandi.models import Operation as OperationsModel


class NilakandiTaskHandler(Task):
    """A custom Celery Task handler for Nilakandi that tracks task execution.

    This class extends Celery's Task class to provide automatic tracking of
    task execution in the OperationsModel database. It handles the lifecycle
    of tasks by recording their start time, completion status, duration, and
    results or errors.

    The handler gives special treatment to report generation tasks
    ("nilakandi.tasks.make_report"), creating more descriptive task names
    that include subscription ID and report type.

    Methods:
        before_start: Creates a record when a task begins execution
        on_success: Updates the record when a task completes successfully
        on_failure: Updates the record when a task fails with an error

    Usage:
        Define Celery tasks with this as the base class to automatically
        track their execution in the database.
    """

    def before_start(self, task_id, args, kwargs):
        """Executes before a task starts running to record its metadata in the database.

        This method creates a record in the OperationsModel to track the task execution.
        For report generation tasks, a custom name is created using the subscription_id
        and report_type from kwargs.

        Args:
            task_id (str): The unique identifier of the task
            args (tuple): Positional arguments passed to the task
            kwargs (dict): Keyword arguments passed to the task, may contain
                          'subscription_id' and 'report_type' for report generation tasks

        Returns:
            None

        Side effects:
            Creates and saves a new OperationsModel record with status 'IN_PROGRESS'
        """
        task_name: str = (
            f"{kwargs.get('subscription_id', 'all')} - {kwargs.get('report_type', 'all')} Report"
            if "nilakandi.tasks.make_report" in self.name
            else self.name
        )
        OperationsModel.objects.create(
            id=UUID(str(task_id)),
            name=task_name,
            type="report_generation",
            status=GenerationStatusEnum.IN_PROGRESS.value,
            started=timezone.now(),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Handle successful completion of a Celery task by updating the corresponding operation record.

        This method is called when a Celery task completes successfully. It updates the operation's
        status to COMPLETED, sets the finished timestamp, calculates the duration, and stores the result.

        Args:
            retval: The return value of the task.
            task_id (str): The ID of the completed task, which corresponds to an OperationsModel ID.
            args: The positional arguments that were passed to the task.
            kwargs: The keyword arguments that were passed to the task.

        Side effects:
            Updates the corresponding OperationsModel record in the database with completion information.
        """
        task_operation = OperationsModel.objects.get(id=UUID(str(task_id)))
        task_operation.status = GenerationStatusEnum.COMPLETED.value
        task_operation.completed = timezone.now()
        task_operation.duration = task_operation.completed - task_operation.started
        task_operation.output = json.loads(json.dumps(retval, cls=DjangoJSONEncoder))
        task_operation.save(update_fields=["status", "completed", "duration", "output"])

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handler for task failure events.

        This method is called by Celery when a task fails. It updates the corresponding
        operation record in the database with failure information.

        Args:
            exc: The exception that caused the task to fail
            task_id: The ID of the failed task (matches operation ID in database)
            args: Positional arguments that were passed to the task
            kwargs: Keyword arguments that were passed to the task
            einfo: Exception info object containing traceback information

        Returns:
            None
        """
        task_operation = OperationsModel.objects.get(id=UUID(str(task_id)))
        task_operation.status = GenerationStatusEnum.FAILED.value
        task_operation.completed = timezone.now()
        task_operation.duration = task_operation.completed - task_operation.started
        tb = getattr(einfo, "traceback", None)
        task_operation.error = f"{exc}\n{tb}" if tb else str(exc)
        task_operation.save(update_fields=["status", "completed", "duration", "error"])
