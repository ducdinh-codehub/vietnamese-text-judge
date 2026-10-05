import json
import math

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import analyzer, emotion, limits, live, scam
from .models import LiveComment

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
    # Pages keep their inputs disabled until a model is loaded, so make sure loading has begun even
    # when the server started without the warm-up (e.g. gunicorn or runserver --noreload).
    analyzer.start_warm_up()
    return JsonResponse({"loaded": analyzer.loaded_checkpoints()})


# ---------- livestream ----------

MAX_COMMENT_CHARS = 200
MAX_AUTHOR_CHARS = 40
FEED_LIMIT = 100
MODERATE = "judge.moderate_live"


def _can_moderate(request):
    return request.user.has_perm(MODERATE)


def _can_reset(request):
    return settings.LIVE_DEMO or _can_moderate(request)


def _comment_json(c, moderator):
    """A comment as the page shows it. Viewers never learn what a hidden comment said, or why it was
    hidden: "complaint" alone would tell the whole chat that an order went wrong."""
    if not c.visible and not moderator:
        return {"id": c.id, "visible": False, "time": c.created_at.isoformat()}
    data = {
        "id": c.id,
        "author": c.author,
        "kind": c.kind,
        "label": live.KINDS[c.kind]["label"],
        "emoji": live.KINDS[c.kind]["emoji"],
        "visible": c.visible,
        "queued": c.queued,
        "time": c.created_at.isoformat(),
        "text": c.text,
    }
    if moderator:
        data.update({
            "match": c.match,
            "source": c.source,
            "laya_negative": c.laya_negative,
            "restored": c.restored,
            "status": c.status,
            "assigned_to": c.assigned_to.get_username() if c.assigned_to else None,
            "handled_at": c.handled_at.isoformat() if c.handled_at else None,
        })
    return data


def _forbidden():
    return JsonResponse({"error": "Bạn không có quyền quản lý phiên live. (Moderator permission required)"}, status=403)


def live_page(request):
    return render(
        request, "judge/live.html", {"can_moderate": _can_moderate(request), "can_reset": _can_reset(request)}
    )


@require_POST
@limits.rate_limited
def live_post(request):
    try:
        data = _read_json(request)
        author = _text(data, "author")[:MAX_AUTHOR_CHARS] or "Khách"
        text = _text(data, "text")
        # The simulated audience runs in the host's browser but must be checked like real viewers.
        as_viewer = data.get("as_viewer") is True
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    if not text:
        return JsonResponse({"error": "Tin nhắn trống."}, status=400)
    if len(text) > MAX_COMMENT_CHARS:
        return JsonResponse({"error": f"Tin nhắn quá dài (tối đa {MAX_COMMENT_CHARS} ký tự)."}, status=400)
    moderator = _can_moderate(request)
    if moderator and not as_viewer:
        result = {"kind": "host", "match": None, "source": "host", "laya_negative": 0.0}
    else:
        try:
            result = limits.run_model(limits.cache_key("live", text), lambda: live.classify(text))
        except limits.Busy:
            return limits.busy_response()
    comment = LiveComment.objects.create(
        author=author,
        text=text,
        kind=result["kind"],
        match=(result["match"] or "")[:300],
        source=result["source"],
        laya_negative=result["laya_negative"],
    )
    return JsonResponse(_comment_json(comment, moderator), json_dumps_params={"ensure_ascii": False})


@require_GET
def live_feed(request):
    """Comments after ?after=<id>, oldest first. Viewers get hidden ones without their text."""
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        return JsonResponse({"error": "after must be a number."}, status=400)
    moderator = _can_moderate(request)
    comments = LiveComment.objects.select_related("assigned_to").filter(id__gt=after)
    if after == 0:
        # First load: only the latest comments, not the whole history.
        comments = list(comments.order_by("-id")[:FEED_LIMIT])[::-1]
    else:
        comments = list(comments[:FEED_LIMIT])
    oldest = LiveComment.objects.order_by("id").values_list("id", flat=True).first()
    stats = {
        "queued": LiveComment.objects.filter(kind__in=live.QUEUE_KINDS, status="new").count(),
        "hidden": LiveComment.objects.filter(kind__in=live.HIDDEN_KINDS, restored=False).count(),
        # Lets open pages notice a reset: everything they show is older than this, or it is None.
        "oldest": oldest,
    }
    return JsonResponse(
        {"comments": [_comment_json(c, moderator) for c in comments], "stats": stats},
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
def live_queue_page(request):
    if not _can_moderate(request):
        return render(request, "judge/live_forbidden.html", status=403)
    return render(request, "judge/live_queue.html", {"kinds": live.QUEUE_KINDS})


@require_GET
def live_queue(request):
    if not _can_moderate(request):
        return _forbidden()
    view = request.GET.get("view", "open")
    comments = LiveComment.objects.select_related("assigned_to")
    if view == "open":
        comments = comments.filter(kind__in=live.QUEUE_KINDS, status="new").order_by("id")
    elif view == "done":
        comments = comments.filter(kind__in=live.QUEUE_KINDS, status="done").order_by("-handled_at")[:FEED_LIMIT]
    elif view == "hidden":
        comments = comments.filter(kind__in=live.BLOCKED_KINDS).order_by("-id")[:FEED_LIMIT]
    else:
        return JsonResponse({"error": "view must be open, done or hidden."}, status=400)
    counts = {
        "open": LiveComment.objects.filter(kind__in=live.QUEUE_KINDS, status="new").count(),
        "hidden": LiveComment.objects.filter(kind__in=live.BLOCKED_KINDS, restored=False).count(),
    }
    return JsonResponse(
        {"comments": [_comment_json(c, True) for c in comments], "counts": counts, "me": request.user.get_username()},
        json_dumps_params={"ensure_ascii": False},
    )


@require_POST
def live_queue_action(request, comment_id):
    if not _can_moderate(request):
        return _forbidden()
    try:
        action = _text(_read_json(request), "action")
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    comment = get_object_or_404(LiveComment, id=comment_id)
    if action == "claim":
        comment.assigned_to = request.user
    elif action == "unclaim":
        comment.assigned_to = None
    elif action == "done":
        comment.status, comment.handled_at = "done", timezone.now()
        comment.assigned_to = comment.assigned_to or request.user
    elif action == "reopen":
        comment.status, comment.handled_at = "new", None
    elif action == "restore":
        comment.restored = True
    elif action == "hide":
        comment.restored = False
    else:
        return JsonResponse({"error": "Unknown action."}, status=400)
    comment.save()
    return JsonResponse(_comment_json(comment, True), json_dumps_params={"ensure_ascii": False})


@require_POST
def live_reset(request):
    """Start the session over: delete every comment, so the chat and the queue are empty."""
    if not _can_reset(request):
        return _forbidden()
    deleted, _ = LiveComment.objects.all().delete()
    return JsonResponse({"deleted": deleted})
