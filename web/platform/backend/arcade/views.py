import json
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .models import Game, HighScore, SaveState


def _parse_json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("invalid json body")


def require_authenticated_user(view_func):
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication required"}, status=401)
        return view_func(request, *args, **kwargs)

    return _wrapped


def index(request: HttpRequest):
    return render(request, "index.html")


@require_POST
def register_user(request: HttpRequest):
    try:
        payload = _parse_json_body(request)
    except ValueError:
        return JsonResponse({"error": "invalid json body"}, status=400)
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    if not username or not password:
        return JsonResponse({"error": "username and password are required"}, status=400)
    try:
        user = User.objects.create_user(username=username, password=password)
    except IntegrityError:
        return JsonResponse({"error": "username already exists"}, status=409)
    login(request, user)
    return JsonResponse({"username": user.username}, status=201)


@require_POST
def login_user(request: HttpRequest):
    try:
        payload = _parse_json_body(request)
    except ValueError:
        return JsonResponse({"error": "invalid json body"}, status=400)
    user = authenticate(request, username=payload.get("username"), password=payload.get("password"))
    if user is None:
        return JsonResponse({"error": "invalid credentials"}, status=401)
    login(request, user)
    return JsonResponse({"username": user.username})


@require_POST
def logout_user(request: HttpRequest):
    logout(request)
    return JsonResponse({"ok": True})


@require_GET
def list_games(request: HttpRequest):
    games = Game.objects.filter(enabled=True).order_by("title")
    data = [
        {
            "id": game.id,
            "title": game.title,
            "slug": game.slug,
            "rom_download_url": game.rom_download_url,
            "wasm_bundle_url": game.wasm_bundle_url,
        }
        for game in games
    ]
    return JsonResponse({"games": data})


@require_authenticated_user
@require_POST
def upsert_save_state(request: HttpRequest):
    try:
        payload = _parse_json_body(request)
    except ValueError:
        return JsonResponse({"error": "invalid json body"}, status=400)
    game_id = payload.get("game_id")
    try:
        slot = int(payload.get("slot", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "slot must be an integer"}, status=400)
    if not game_id or "state_blob_url" not in payload:
        return JsonResponse({"error": "game_id and state_blob_url are required"}, status=400)
    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)

    state, _ = SaveState.objects.update_or_create(
        user=request.user,
        game=game,
        slot=slot,
        defaults={
            "state_blob_url": payload["state_blob_url"],
            "checksum": payload.get("checksum", ""),
            "metadata": payload.get("metadata", {}),
        },
    )
    return JsonResponse({"id": state.id, "updated_at": state.updated_at.isoformat()})


@require_authenticated_user
@require_GET
def list_save_states(request: HttpRequest):
    game_id = request.GET.get("game_id")
    qs = SaveState.objects.filter(user=request.user).select_related("game")
    if game_id:
        qs = qs.filter(game_id=game_id)
    data = [
        {
            "id": state.id,
            "game_id": state.game_id,
            "game_title": state.game.title,
            "slot": state.slot,
            "state_blob_url": state.state_blob_url,
            "checksum": state.checksum,
            "metadata": state.metadata,
            "updated_at": state.updated_at.isoformat(),
        }
        for state in qs.order_by("game__title", "slot")
    ]
    return JsonResponse({"save_states": data})


@require_POST
def submit_high_score(request: HttpRequest):
    try:
        payload = _parse_json_body(request)
    except ValueError:
        return JsonResponse({"error": "invalid json body"}, status=400)
    game_id = payload.get("game_id")
    score = payload.get("score")
    if not game_id or score is None:
        return JsonResponse({"error": "game_id and score are required"}, status=400)
    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)
    high_score = HighScore.objects.create(
        user=request.user if request.user.is_authenticated else None,
        game=game,
        score=int(score),
        metadata=payload.get("metadata", {}),
    )
    return JsonResponse({"id": high_score.id, "submitted_at": high_score.submitted_at.isoformat()}, status=201)


@require_GET
def leaderboard(request: HttpRequest):
    game_id = request.GET.get("game_id")
    try:
        limit = min(int(request.GET.get("limit", 20)), 100)
    except ValueError:
        return JsonResponse({"error": "limit must be an integer"}, status=400)
    if not game_id:
        return JsonResponse({"error": "game_id is required"}, status=400)
    rows = HighScore.objects.filter(game_id=game_id).select_related("user")[:limit]
    data = [
        {
            "id": row.id,
            "username": row.user.username if row.user else "guest",
            "score": row.score,
            "metadata": row.metadata,
            "submitted_at": row.submitted_at.isoformat(),
        }
        for row in rows
    ]
    return JsonResponse({"leaderboard": data})

# Create your views here.
