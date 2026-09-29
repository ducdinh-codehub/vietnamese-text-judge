import json
import math

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import analyzer

MAX_BODY_CHARS = 20_000


def _json_safe(value):
    """JSON has no Infinity: odds of p=1 become None."""
    if isinstance(value, float) and math.isinf(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _options(spec):
    """Option names in the order the page lists them, matching the keys in each result."""
    if spec["type"] == "choice":
        return list(spec["criteria"])
    if spec["type"] == "score":
        return list(spec["criteria"])
    return ["yes", "no"]


def _layout():
    """Every question the page shows, so it can draw the full list before any analysis runs."""
    return {
        "groups": analyzer.GROUPS,
        "total_questions": len(analyzer.QUESTIONS),
        "questions": [
            {
                "id": qid,
                "label": spec["label"],
                "group": spec["group"],
                "type": spec["type"],
                "experimental": spec["type"] == "score",
                "options": _options(spec),
            }
            for qid, spec in analyzer.QUESTIONS.items()
        ],
    }


def index(request):
    return render(
        request,
        "judge/index.html",
        {
            "groups": [
                (key, name, sum(q["group"] == key for q in analyzer.QUESTIONS.values()))
                for key, name in analyzer.GROUPS.items()
            ],
            "default_threshold": analyzer.DEFAULT_THRESHOLD,
            "layout": _layout(),
        },
    )


@require_POST
def analyze(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be JSON."}, status=400)

    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not body:
        return JsonResponse({"error": "Please enter some text to analyze."}, status=400)
    if len(body) > MAX_BODY_CHARS:
        return JsonResponse({"error": f"Text is too long (max {MAX_BODY_CHARS} characters)."}, status=400)

    try:
        threshold = float(data.get("threshold", analyzer.DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Threshold must be a number."}, status=400)
    threshold = min(max(threshold, 0.5), 0.99)

    try:
        result = analyzer.analyze(
            subject,
            body,
            checkpoint=data.get("checkpoint", "multilingual"),
            threshold=threshold,
            groups=data.get("groups"),
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_json_safe(result), json_dumps_params={"ensure_ascii": False})


@require_GET
def status(request):
    return JsonResponse({"loaded": analyzer.loaded_checkpoints()})
