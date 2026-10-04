import json
import math

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import analyzer, emotion, limits, scam

# The model reads about 2,500 Vietnamese characters; longer text only costs time. Keep in sync with
# the maxlength of the text boxes in the templates.
MAX_BODY_CHARS = 3_000
MAX_SUBJECT_CHARS = 300


def _json_safe(value):
    """JSON has no Infinity: odds of p=1 become None."""
    if isinstance(value, float) and math.isinf(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


class BadRequest(Exception):
    pass


def _read_json(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BadRequest("Request body must be JSON.")
    if not isinstance(data, dict):
        raise BadRequest("Request body must be a JSON object.")
    return data


def _text(data, field):
    value = data.get(field) or ""
    if not isinstance(value, str):
        raise BadRequest(f"{field} must be text.")
    return value.strip()


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
            "default_threshold": analyzer.DEFAULT_THRESHOLD,
            "layout": _layout(),
        },
    )


@require_POST
@limits.rate_limited
def analyze(request):
    try:
        data = _read_json(request)
        subject = _text(data, "subject")
        body = _text(data, "body")
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    if not body:
        return JsonResponse({"error": "Please enter some text to analyze."}, status=400)
    if len(body) > MAX_BODY_CHARS:
        return JsonResponse({"error": f"Text is too long (max {MAX_BODY_CHARS} characters)."}, status=400)
    if len(subject) > MAX_SUBJECT_CHARS:
        return JsonResponse({"error": f"Subject is too long (max {MAX_SUBJECT_CHARS} characters)."}, status=400)

    try:
        threshold = float(data.get("threshold", analyzer.DEFAULT_THRESHOLD))
        if not math.isfinite(threshold):
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"error": "Threshold must be a number."}, status=400)
    threshold = min(max(threshold, 0.5), 0.99)

    checkpoint = data.get("checkpoint", "multilingual")
    groups = data.get("groups")
    if groups is not None and not (isinstance(groups, list) and all(isinstance(g, str) for g in groups)):
        return JsonResponse({"error": "groups must be a list of names."}, status=400)
    key = limits.cache_key("analyze", [subject, body, checkpoint, threshold, sorted(groups or [])])
    try:
        result = limits.run_model(
            key, lambda: analyzer.analyze(subject, body, checkpoint=checkpoint, threshold=threshold, groups=groups)
        )
    except limits.Busy:
        return limits.busy_response()
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_json_safe(result), json_dumps_params={"ensure_ascii": False})


def scam_page(request):
    return render(request, "judge/scam.html")


def _check_body(request, kind, check):
    """Shared by the scam and emotion checkers: read {"body": ...}, validate it, run `check`."""
    try:
        body = _text(_read_json(request), "body")
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    if not body:
        return JsonResponse({"error": "Vui lòng nhập nội dung cần kiểm tra."}, status=400)
    if len(body) > MAX_BODY_CHARS:
        return JsonResponse({"error": f"Nội dung quá dài (tối đa {MAX_BODY_CHARS} ký tự)."}, status=400)
    try:
        result = limits.run_model(limits.cache_key(kind, body), lambda: check(body))
    except limits.Busy:
        return limits.busy_response()
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})


@require_POST
@limits.rate_limited
def scam_check(request):
    return _check_body(request, "scam", scam.check)


def emotion_page(request):
    return render(request, "judge/emotion.html")


@require_POST
@limits.rate_limited
def emotion_check(request):
    return _check_body(request, "emotion", emotion.check)


@require_GET
def status(request):
    return JsonResponse({"loaded": analyzer.loaded_checkpoints()})
