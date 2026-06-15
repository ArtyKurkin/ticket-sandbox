from django.contrib import admin

from .models import CheckRun, Queue, Task, TaskAttempt, TraineeProfile


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "queue",
        "title",
        "slug",
        "priority",
        "requires_manual_review",
        "is_active",
    )

    list_editable = (
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

    prepopulated_fields = {
        "slug": ("title",)
    }

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


@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "name",
        "slug",
        "required_level",
        "is_active",
    )
    list_editable = ("required_level", "is_active")
    search_fields = ("name", "slug")


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
