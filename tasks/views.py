import copy
import json
from datetime import date

from django.db import transaction
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from .ai import break_down_task, parse_task_text
from .models import Task
from .serializers import TaskSerializer


IDEMPOTENCY_STORE = {}


def error_response(code, message, details=None, http_status=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            "error": {
                "code": str(code),
                "message": str(message),
                "details": details or [],
            }
        },
        status=http_status,
    )


def serializer_details(errors):
    details = []
    if isinstance(errors, dict):
        for field, issues in errors.items():
            if isinstance(issues, (list, tuple)):
                for issue in issues:
                    details.append({"field": str(field), "issue": str(issue)})
            else:
                details.append({"field": str(field), "issue": str(issues)})
    return details


def canonical_body(request):
    return json.dumps(request.data, sort_keys=True, default=str)


def idempotency_result(request):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return None
    body = canonical_body(request)
    saved = IDEMPOTENCY_STORE.get(key)
    if saved is None:
        return key, body, None
    if saved["body"] != body:
        return key, body, error_response(
            "IDEMPOTENCY_KEY_CONFLICT",
            "Idempotency-Key was reused with a different request body",
            [{"field": "Idempotency-Key", "issue": "must reuse with the same body"}],
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return key, body, Response(copy.deepcopy(saved["response"]), status=saved["status"])


def save_idempotency(key, body, http_status, response):
    if key:
        IDEMPOTENCY_STORE[key] = {
            "body": body,
            "status": http_status,
            "response": copy.deepcopy(response),
        }


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all().select_related("parent")
    serializer_class = TaskSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["completed", "priority", "due_date", "parent"]
    search_fields = ["title", "description"]
    ordering_fields = ["id", "title", "due_date", "priority", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def create(self, request, *args, **kwargs):
        idem = idempotency_result(request)
        if idem:
            key, body, result = idem
            if result is not None:
                return result
        else:
            key = body = None

        serializer = TaskSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "VALIDATION_ERROR",
                "Validation failed",
                serializer_details(serializer.errors),
            )
        instance = serializer.save()
        response_data = TaskSerializer(instance).data
        save_idempotency(key, body, status.HTTP_201_CREATED, response_data)
        return Response(response_data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        return Response(TaskSerializer(instance).data)

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        serializer = TaskSerializer(instance, data=request.data)
        if not serializer.is_valid():
            return error_response(
                "VALIDATION_ERROR",
                "Validation failed",
                serializer_details(serializer.errors),
            )
        instance = serializer.save()
        return Response(TaskSerializer(instance).data)

    def partial_update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        serializer = TaskSerializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                "VALIDATION_ERROR",
                "Validation failed",
                serializer_details(serializer.errors),
            )
        instance = serializer.save()
        return Response(TaskSerializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="from-text")
    def from_text(self, request):
        idem = idempotency_result(request)
        if idem:
            key, body, result = idem
            if result is not None:
                return result
        else:
            key = body = None

        text = request.data.get("text")
        if not isinstance(text, str) or not text.strip():
            return error_response(
                "VALIDATION_ERROR",
                "Validation failed",
                [{"field": "text", "issue": "must not be empty"}],
            )
        try:
            parsed = parse_task_text(text, date.today())
        except Exception:
            return error_response(
                "PARSER_ERROR",
                "Natural-language parsing failed",
                [],
                status.HTTP_502_BAD_GATEWAY,
            )

        serializer = TaskSerializer(data=parsed)
        if not serializer.is_valid():
            return error_response(
                "PARSER_OUTPUT_INVALID",
                "Parsed task validation failed",
                serializer_details(serializer.errors),
                status.HTTP_502_BAD_GATEWAY,
            )
        instance = serializer.save()
        response_data = TaskSerializer(instance).data
        save_idempotency(key, body, status.HTTP_201_CREATED, response_data)
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="subtasks")
    def create_subtask(self, request, pk=None):
        try:
            parent = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        if parent.parent_id is not None:
            return error_response(
                "SUBTASK_RULE",
                "A subtask cannot have subtasks",
                [{"field": "parent", "issue": "task is already a subtask"}],
            )

        payload = dict(request.data)
        payload.setdefault("completed", False)
        payload.setdefault("priority", "medium")
        payload.setdefault("description", "")
        payload.setdefault("recurrence", "")
        serializer = TaskSerializer(data=payload)
        if not serializer.is_valid():
            return error_response(
                "VALIDATION_ERROR",
                "Validation failed",
                serializer_details(serializer.errors),
            )
        instance = serializer.save(parent=parent)
        return Response(TaskSerializer(instance).data, status=status.HTTP_201_CREATED)

    @create_subtask.mapping.get
    def list_subtasks(self, request, pk=None):
        try:
            parent = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        return Response(TaskSerializer(parent.subtasks.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="breakdown")
    def breakdown(self, request, pk=None):
        idem = idempotency_result(request)
        if idem:
            key, body, result = idem
            if result is not None:
                return result
        else:
            key = body = None

        try:
            task = self.get_object()
        except (Task.DoesNotExist, Http404):
            return error_response(
                "NOT_FOUND",
                "Task not found",
                [{"field": "id", "issue": "unknown task id"}],
                status.HTTP_404_NOT_FOUND,
            )
        if task.parent_id is not None:
            return error_response(
                "SUBTASK_RULE",
                "A subtask cannot be broken down",
                [{"field": "parent", "issue": "task is already a subtask"}],
            )

        items = break_down_task(task)
        validated = []
        details = []
        for index, item in enumerate(items):
            serializer = TaskSerializer(data=item)
            if not serializer.is_valid():
                for detail in serializer_details(serializer.errors):
                    details.append({
                        "field": f"items[{index}].{detail['field']}",
                        "issue": detail["issue"],
                    })
            else:
                validated.append(serializer.validated_data)

        if details:
            return error_response(
                "VALIDATION_ERROR",
                "Validation failed",
                details,
            )

        with transaction.atomic():
            created = [
                Task.objects.create(parent=task, **data)
                for data in validated
            ]

        response_data = TaskSerializer(created, many=True).data
        save_idempotency(key, body, status.HTTP_201_CREATED, response_data)
        return Response(response_data, status=status.HTTP_201_CREATED)
