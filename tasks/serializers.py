import re

from rest_framework import serializers

from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "completed",
            "due_date",
            "priority",
            "recurrence",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "parent", "created_at", "updated_at"]

    def validate_title(self, value):
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError("must not be empty")
        return value.strip()

    def validate_description(self, value):
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError("must not be empty")
        return value.strip()

    def validate_completed(self, value):
        if not isinstance(value, bool):
            raise serializers.ValidationError("must be a boolean")
        return value

    def validate_due_date(self, value):
        if value is None:
            return value
        raw = self.initial_data.get("due_date")
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise serializers.ValidationError("must use YYYY-MM-DD")
        return value

    def validate_priority(self, value):
        if value not in ("low", "medium", "high"):
            raise serializers.ValidationError("must be one of: low, medium, high")
        return value
