from io import StringIO

from django.contrib import admin, messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponseForbidden
from django.template.response import TemplateResponse
from django.urls import path

from .models import CheckRun, Queue, Task, TaskAttempt, TraineeProfile


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    change_list_template = "admin/sandbox/task/change_list.html"

    list_display = (
        "order",
        "queue",
        "title",
        "slug",
        "priority",
        "requires_manual_review",
        "is_active",
    )

    list_display_links = ("title",)

    list_editable = (
        "order",
        "priority",
        "requires_manual_review",
        "is_active",
    )

    list_filter = (
        "queue",
        "priority",
        "requires_manual_review",
        "is_active",
    )

    search_fields = (
        "title",
        "slug",
        "ticket_title",
        "description",
        "client_name",
        "client_email",
    )

    ordering = (
        "queue__order",
        "order",
        "title",
    )

    prepopulated_fields = {
        "slug": ("title",)
    }

    actions = (
        "activate_tasks",
        "deactivate_tasks",
        "enable_manual_review",
        "disable_manual_review",
    )

    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "queue",
                    "title",
                    "slug",
                    "order",
                    "is_active",
                    "requires_manual_review",
                )
            },
        ),
        (
            "Тикет",
            {
                "fields": (
                    "ticket_title",
                    "description",
                    "client_name",
                    "client_email",
                    "priority",
                )
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "sync-training-tasks/",
                self.admin_site.admin_view(self.sync_training_tasks_view),
                name="sandbox_task_sync_training_tasks",
            ),
        ]

        return custom_urls + urls

    def sync_training_tasks_view(self, request):
        if not request.user.is_superuser:
            return HttpResponseForbidden(
                "sync_training_tasks доступен только superuser."
            )

        output = StringIO()
        has_error = False
        error_message = ""

        if request.method == "POST":
            title = "Синхронизация training_tasks"
            is_dry_run = False

            try:
                call_command(
                    "sync_training_tasks",
                    "--strict",
                    stdout=output,
                )
            except CommandError as error:
                has_error = True
                error_message = str(error)
                self.message_user(
                    request,
                    f"sync_training_tasks --strict завершился с ошибкой: {error_message}",
                    level=messages.ERROR,
                )
            else:
                self.message_user(
                    request,
                    "sync_training_tasks успешно выполнен.",
                    level=messages.SUCCESS,
                )
        else:
            title = "Проверка sync_training_tasks"
            is_dry_run = True

            try:
                call_command(
                    "sync_training_tasks",
                    "--dry-run",
                    "--strict",
                    stdout=output,
                )
            except CommandError as error:
                has_error = True
                error_message = str(error)
                self.message_user(
                    request,
                    f"sync_training_tasks --dry-run --strict завершился с ошибкой: {error_message}",
                    level=messages.ERROR,
                )

        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.model._meta,
            "output": output.getvalue(),
            "is_dry_run": is_dry_run,
            "has_error": has_error,
            "error_message": error_message,
        }

        return TemplateResponse(
            request,
            "admin/sandbox/task/sync_training_tasks.html",
            context,
        )

    @admin.action(description="Включить выбранные задания")
    def activate_tasks(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Включено заданий: {updated}")

    @admin.action(description="Выключить выбранные задания")
    def deactivate_tasks(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Выключено заданий: {updated}")

    @admin.action(description="Включить ручную проверку")
    def enable_manual_review(self, request, queryset):
        updated = queryset.update(requires_manual_review=True)
        self.message_user(
            request,
            f"Ручная проверка включена для заданий: {updated}",
        )

    @admin.action(description="Отключить ручную проверку")
    def disable_manual_review(self, request, queryset):
        updated = queryset.update(requires_manual_review=False)
        self.message_user(
            request,
            f"Ручная проверка отключена для заданий: {updated}",
        )


@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "name",
        "slug",
        "required_level",
        "is_active",
    )

    list_display_links = ("name",)

    list_editable = (
        "order",
        "required_level",
        "is_active",
    )

    list_filter = (
        "required_level",
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
    )

    ordering = (
        "order",
        "name",
    )


@admin.register(TraineeProfile)
class TraineeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "level",
        "mentor_status",
    )

    list_editable = ("level",)
    list_filter = ("level", "user__is_staff")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )

    @admin.display(boolean=True, description="Наставник")
    def mentor_status(self, obj):
        return obj.user.is_staff


class CheckRunInline(admin.TabularInline):
    model = CheckRun
    extra = 0
    can_delete = False

    fields = (
        "result",
        "exit_code",
        "created_at",
        "output",
    )

    readonly_fields = (
        "result",
        "exit_code",
        "created_at",
        "output",
    )

    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TaskAttempt)
class TaskAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "task",
        "task_queue",
        "attempt_number",
        "attempt_type",
        "is_current",
        "status",
        "attempts_count",
        "restart_count",
        "technical_passed_at",
        "mentor_decision",
        "mentor_reviewed_by",
        "mentor_reviewed_at",
    )

    list_filter = (
        "status",
        "task__queue",
        "attempt_number",
        "is_current",
        "technical_passed_at",
        "mentor_decision",
        "started_at",
        "finished_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "task__title",
        "task__slug",
        "client_answer",
        "trainee_report",
        "last_check_output",
    )

    readonly_fields = (
        "attempt_number",
        "is_current",
        "created_at",
        "started_at",
        "technical_passed_at",
        "finished_at",
        "last_check_output",
        "container_id",
        "container_name",
        "terminal_container_name",
        "terminal_url",
        "terminal_port",
        "shell_command",
        "mentor_reviewed_by",
        "mentor_feedback_seen_at",
        "mentor_reviewed_at",
    )

    fieldsets = (
        (
            "Попытка",
            {
                "fields": (
                    "user",
                    "task",
                    "attempt_number",
                    "is_current",
                    "status",
                    "created_at",
                    "started_at",
                    "technical_passed_at",
                    "finished_at",
                )
            },
        ),
        (
            "Проверки",
            {
                "fields": (
                    "attempts_count",
                    "restart_count",
                    "last_check_output",
                )
            },
        ),
        (
            "Ответ стажера",
            {
                "fields": (
                    "client_answer",
                    "trainee_report",
                )
            },
        ),
        (
            "Наставник",
            {
                "fields": (
                    "mentor_decision",
                    "mentor_feedback",
                    "mentor_reviewed_by",
                    "mentor_reviewed_at",
                    "mentor_feedback_seen_at",
                )
            },
        ),
        (
            "Окружение",
            {
                "classes": ("collapse",),
                "fields": (
                    "container_id",
                    "container_name",
                    "shell_command",
                    "terminal_container_name",
                    "terminal_url",
                    "terminal_port",
                ),
            },
        ),
    )

    inlines = (CheckRunInline,)

    @admin.display(description="Очередь", ordering="task__queue__order")
    def task_queue(self, obj):
        return obj.task.queue

    @admin.display(description="Тип попытки")
    def attempt_type(self, obj):
        if obj.is_extra_attempt:
            return "Тренировочная"

        return "Зачетная"


@admin.register(CheckRun)
class CheckRunAdmin(admin.ModelAdmin):
    list_display = (
        "attempt",
        "result",
        "exit_code",
        "created_at",
    )

    list_filter = (
        "result",
        "created_at",
    )

    search_fields = (
        "attempt__user__username",
        "attempt__task__title",
        "attempt__task__slug",
        "output",
    )

    readonly_fields = (
        "attempt",
        "result",
        "output",
        "exit_code",
        "created_at",
    )
