from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "completed", "priority", "due_date", "parent")
    list_filter = ("completed", "priority")
    search_fields = ("title", "description")
