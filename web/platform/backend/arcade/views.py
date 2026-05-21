import json
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse, urlunparse
from datetime import timedelta
import zipfile

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.conf import settings
from django.db import IntegrityError
from django.core import signing
from django.utils import timezone
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import Game, HighScore, PlaySession, SaveState


ROM_TOKEN_SALT = "arcade.rom.download"
ROM_TOKEN_MAX_AGE_SECONDS = 120
SAVE_STATE_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
SAVE_STATE_ALLOWED_EXTENSIONS = {".state", ".sav", ".bin", ".zip"}

MACHINE_MARKER_GROUPS = {
    "sf2ce": [
        ("s92e_23b.8f",),
        ("s92_22b.7f", "s92e_22b.7f"),
        ("s92_21a.6f", "s92_21a.bin"),
        ("s92_09.11a", "s92_09.12a"),
        ("s92-13m.6c",),
    ],
    "sf2rb": [
        ("sf2ce.23",),
        ("sf2ce.22",),
        ("s92_21a.6f", "s92_21a.bin"),
        ("s92_09.11a", "s92_09.12a"),
        ("s92-13m.6c",),
    ],
}

# Neo Geo machines that require the neogeo.zip BIOS ROM.
NEO_GEO_MACHINES = {
    "kof94", "kof95", "kof96", "kof97", "kof98", "kof99", "kof2000", "kof2001",
    "kof2002", "kof2003", "kof10th",
    "mslug", "mslug2", "mslug3", "mslug4", "mslug5", "mslugx",
    "samsho", "samsho2", "samsho3", "samsho4", "samsho5",
    "lastbld2", "fatfury1", "fatfury2", "fatfury3", "fatfursp",
    "garou", "rbff1", "rbff2", "rbffspec",
    "ss", "ss2", "wh1", "wh2",
    "pulstar", "blazstar", "ironclad",
    "magician", "spinmast",
}


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


@ensure_csrf_cookie
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
            "launch_url": request.build_absolute_uri(f"/api/games/{game.id}/launch"),
        }
        for game in games
    ]
    return JsonResponse({"games": data})


def _issue_local_rom_token(game_id: int, rom_relative_path: str) -> str:
    payload = {
        "game_id": game_id,
        "rom_path": rom_relative_path,
    }
    return signing.dumps(payload, salt=ROM_TOKEN_SALT)


def _rewrite_local_url(request: HttpRequest, url: str) -> str:
    """Replace 127.0.0.1/localhost with the actual request host so mobile clients can reach the server."""
    parsed = urlparse(url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        return request.build_absolute_uri(parsed.path)
    return url


def _is_local_rom_url(url: str) -> bool:
    parsed = urlparse(url)
    # Relative URLs are considered local when they use the configured ROM prefix.
    if not parsed.scheme and not parsed.netloc:
        return parsed.path.startswith(settings.LOCAL_ROMS_URL_PREFIX)

    # Absolute URLs are considered local only for loopback hosts during local development.
    return parsed.hostname in {"127.0.0.1", "localhost", "testserver"} and parsed.path.startswith(
        settings.LOCAL_ROMS_URL_PREFIX
    )


def _extract_local_rom_relative_path(url: str) -> str:
    marker = settings.LOCAL_ROMS_URL_PREFIX
    index = url.find(marker)
    if index == -1:
        raise ValueError("not a local rom url")
    return url[index + len(marker):].lstrip("/")


def _read_zip_entry_names(rom_file_path: Path) -> set[str]:
    with zipfile.ZipFile(rom_file_path, "r") as zip_file:
        return {Path(name).name.lower() for name in zip_file.namelist()}


def _analyze_machine_markers(entry_names: set[str], default_machine: str) -> dict:
    scores: dict[str, int] = {}
    missing_markers: dict[str, list[str]] = {}

    for machine, marker_groups in MACHINE_MARKER_GROUPS.items():
        score = 0
        missing = []
        for group in marker_groups:
            if any(candidate in entry_names for candidate in group):
                score += 1
            else:
                # Report the canonical filename for the missing marker group.
                missing.append(group[0])
        scores[machine] = score
        missing_markers[machine] = missing

    best_machine, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score > 0 and list(scores.values()).count(best_score) == 1:
        inferred_machine = best_machine
    elif default_machine in MACHINE_MARKER_GROUPS:
        inferred_machine = default_machine
    else:
        inferred_machine = default_machine

    likely_machine = "undetermined"
    if list(scores.values()).count(best_score) == 1 and best_score > 0:
        likely_machine = best_machine

    return {
        "inferred_machine": inferred_machine,
        "likely_machine": likely_machine,
        "scores": scores,
        "missing_markers": missing_markers,
    }


def _infer_machine_name_from_local_rom(rom_relative_path: str) -> str:
    """Infer machine name from ROM archive contents when filename is ambiguous."""
    default_machine = Path(rom_relative_path).stem
    rom_file_path = (Path(settings.LOCAL_ROMS_DIR) / rom_relative_path).resolve()
    if rom_file_path.suffix.lower() != ".zip" or not rom_file_path.is_file():
        return default_machine

    try:
        names = _read_zip_entry_names(rom_file_path)
    except (OSError, zipfile.BadZipFile):
        return default_machine

    analysis = _analyze_machine_markers(names, default_machine)
    return analysis["inferred_machine"]


@require_GET
def diagnose_game_rom(request: HttpRequest, game_id: int):
    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)

    if not _is_local_rom_url(game.rom_download_url):
        return JsonResponse(
            {
                "game_id": game.id,
                "local_rom": False,
                "message": "diagnosis is available only for local rom urls",
            }
        )

    try:
        rom_relative_path = _extract_local_rom_relative_path(game.rom_download_url)
    except ValueError:
        return JsonResponse({"error": "invalid local rom url"}, status=500)

    rom_file_path = (Path(settings.LOCAL_ROMS_DIR) / rom_relative_path).resolve()
    if not rom_file_path.is_file():
        return JsonResponse(
            {
                "game_id": game.id,
                "local_rom": True,
                "rom_relative_path": rom_relative_path,
                "exists": False,
                "message": "rom file not found",
            },
            status=404,
        )

    default_machine = Path(rom_relative_path).stem
    if rom_file_path.suffix.lower() != ".zip":
        return JsonResponse(
            {
                "game_id": game.id,
                "local_rom": True,
                "rom_relative_path": rom_relative_path,
                "exists": True,
                "default_machine": default_machine,
                "inferred_machine": default_machine,
                "likely_machine": "undetermined",
                "entry_count": None,
                "scores": {},
                "missing_markers": {},
                "message": "marker diagnosis currently supports zip roms only",
            }
        )

    try:
        entry_names = _read_zip_entry_names(rom_file_path)
    except (OSError, zipfile.BadZipFile):
        return JsonResponse({"error": "failed to read rom zip"}, status=400)

    analysis = _analyze_machine_markers(entry_names, default_machine)
    return JsonResponse(
        {
            "game_id": game.id,
            "local_rom": True,
            "rom_relative_path": rom_relative_path,
            "exists": True,
            "default_machine": default_machine,
            "inferred_machine": analysis["inferred_machine"],
            "likely_machine": analysis["likely_machine"],
            "entry_count": len(entry_names),
            "scores": analysis["scores"],
            "missing_markers": analysis["missing_markers"],
        }
    )


@require_GET
def launch_game(request: HttpRequest, game_id: int):
    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)

    rom_download_url = game.rom_download_url
    machine_name = ""
    if _is_local_rom_url(game.rom_download_url):
        try:
            local_relative_path = _extract_local_rom_relative_path(game.rom_download_url)
        except ValueError:
            return JsonResponse({"error": "invalid local rom url"}, status=500)
        machine_name = _infer_machine_name_from_local_rom(local_relative_path)
        token = _issue_local_rom_token(game.id, local_relative_path)
        rom_download_url = request.build_absolute_uri(f"/api/roms/download/{token}")
    else:
        machine_name = Path(urlparse(game.rom_download_url).path).stem

    play_session = PlaySession.objects.create(
        user=request.user if request.user.is_authenticated else None,
        game=game,
    )

    # Determine the actual ROM filename so the frontend can write it correctly
    # regardless of whether the download URL is a token URL or a direct URL.
    if _is_local_rom_url(game.rom_download_url):
        try:
            rom_filename = Path(_extract_local_rom_relative_path(game.rom_download_url)).name
        except ValueError:
            rom_filename = ""
    else:
        rom_filename = game.rom_download_url.rstrip("/").split("/")[-1]

    # For Neo Geo games, also provide a tokenized download URL for the neogeo.zip BIOS ROM.
    bios_roms = []
    if machine_name in NEO_GEO_MACHINES:
        neogeo_bios_path = "neogeo.zip"
        neogeo_bios_file = (Path(settings.LOCAL_ROMS_DIR) / neogeo_bios_path).resolve()
        if neogeo_bios_file.is_file():
            bios_token = _issue_local_rom_token(game.id, neogeo_bios_path)
            bios_roms.append({
                "filename": "neogeo.zip",
                "download_url": request.build_absolute_uri(f"/api/roms/download/{bios_token}"),
            })

    return JsonResponse(
        {
            "game": {
                "id": game.id,
                "title": game.title,
                "slug": game.slug,
            },
            "launch": {
                "rom_download_url": rom_download_url,
                "rom_filename": rom_filename,
                "machine_name": machine_name,
                "wasm_bundle_url": _rewrite_local_url(request, game.wasm_bundle_url),
                "token_ttl_seconds": ROM_TOKEN_MAX_AGE_SECONDS if _is_local_rom_url(game.rom_download_url) else None,
                "play_session_id": str(play_session.id),
                "bios_roms": bios_roms,
            },
        }
    )


@require_http_methods(["GET", "HEAD"])
def download_local_rom_with_token(request: HttpRequest, token: str):
    try:
        payload = signing.loads(token, salt=ROM_TOKEN_SALT, max_age=ROM_TOKEN_MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        return JsonResponse({"error": "rom token expired"}, status=410)
    except signing.BadSignature:
        return JsonResponse({"error": "invalid rom token"}, status=400)

    game_id = payload.get("game_id")
    rom_relative_path = payload.get("rom_path", "")
    if not game_id or not rom_relative_path:
        return JsonResponse({"error": "invalid token payload"}, status=400)
    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)

    rom_file_path = (Path(settings.LOCAL_ROMS_DIR) / rom_relative_path).resolve()
    local_rom_root = Path(settings.LOCAL_ROMS_DIR).resolve()
    if not rom_file_path.is_file() or (rom_file_path.parent != local_rom_root and local_rom_root not in rom_file_path.parents):
        return JsonResponse({"error": "rom file not found"}, status=404)

    if request.method == "HEAD":
        # Frontend readiness checks only need existence validation.
        return HttpResponse(status=200)

    return FileResponse(rom_file_path.open("rb"), as_attachment=True, filename=rom_file_path.name)


def _iter_local_rom_files() -> list[Path]:
    roms_dir = Path(settings.LOCAL_ROMS_DIR)
    if not roms_dir.exists():
        return []
    allowed_extensions = {".zip", ".7z", ".chd", ".rom"}
    return [
        file_path for file_path in sorted(roms_dir.iterdir())
        if file_path.is_file() and file_path.suffix.lower() in allowed_extensions
    ]


@require_POST
def sync_local_roms(request: HttpRequest):
    rom_files = _iter_local_rom_files()
    created = 0
    updated = 0
    active_local_slugs = set()
    for rom_file in rom_files:
        slug_base = slugify(rom_file.stem) or "local-rom"
        slug = f"local-{slug_base}"[:50]
        active_local_slugs.add(slug)
        title = rom_file.stem.replace("_", " ").strip() or rom_file.name
        rom_download_url = request.build_absolute_uri(f"{settings.LOCAL_ROMS_URL_PREFIX}{rom_file.name}")
        wasm_bundle_url = request.build_absolute_uri(settings.LOCAL_WASM_BUNDLE_PATH)

        game, was_created = Game.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "rom_download_url": rom_download_url,
                "wasm_bundle_url": wasm_bundle_url,
                "enabled": True,
            },
        )
        created += int(was_created)
        updated += int(not was_created and game.enabled)

    stale_local_games = Game.objects.filter(enabled=True, rom_download_url__contains=settings.LOCAL_ROMS_URL_PREFIX)
    if active_local_slugs:
        stale_local_games = stale_local_games.exclude(slug__in=active_local_slugs)

    disabled = stale_local_games.update(enabled=False)

    return JsonResponse(
        {
            "created": created,
            "updated": updated,
            "disabled": disabled,
            "total_local_roms": len(rom_files),
        }
    )


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
@require_POST
def upload_save_state_file(request: HttpRequest):
    game_id = request.POST.get("game_id")
    slot_raw = request.POST.get("slot", "0")
    upload = request.FILES.get("state_file")

    if not game_id or upload is None:
        return JsonResponse({"error": "game_id and state_file are required"}, status=400)

    try:
        slot = int(slot_raw)
    except (TypeError, ValueError):
        return JsonResponse({"error": "slot must be an integer"}, status=400)

    if upload.size > SAVE_STATE_MAX_FILE_SIZE_BYTES:
        return JsonResponse({"error": "state_file is too large"}, status=413)

    suffix = Path(upload.name).suffix.lower()
    if suffix not in SAVE_STATE_ALLOWED_EXTENSIONS:
        return JsonResponse({"error": "unsupported state_file extension"}, status=400)

    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)

    safe_name = Path(upload.name).name
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    relative_path = (
        f"savestates/user_{request.user.id}/game_{game.id}/slot_{slot}/{timestamp}_{safe_name}"
    )
    absolute_path = Path(settings.MEDIA_ROOT) / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    with absolute_path.open("wb") as output_file:
        for chunk in upload.chunks():
            output_file.write(chunk)

    public_path = relative_path.replace("\\", "/")
    state_blob_url = request.build_absolute_uri(f"{settings.MEDIA_URL}{public_path}")
    state, _ = SaveState.objects.update_or_create(
        user=request.user,
        game=game,
        slot=slot,
        defaults={
            "state_blob_url": state_blob_url,
            "checksum": "",
            "metadata": {
                "source": "uploaded_file",
                "filename": safe_name,
                "size": upload.size,
            },
        },
    )
    return JsonResponse(
        {
            "id": state.id,
            "state_blob_url": state.state_blob_url,
            "updated_at": state.updated_at.isoformat(),
        },
        status=201,
    )


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
    session_id = payload.get("session_id")
    duration_ms = payload.get("duration_ms")
    if not game_id or score is None or not session_id or duration_ms is None:
        return JsonResponse({"error": "game_id, score, session_id and duration_ms are required"}, status=400)

    try:
        score_int = int(score)
        duration_ms_int = int(duration_ms)
    except (TypeError, ValueError):
        return JsonResponse({"error": "score and duration_ms must be integers"}, status=400)

    if duration_ms_int < 0:
        return JsonResponse({"error": "duration_ms must be non-negative"}, status=400)
    try:
        game = Game.objects.get(id=game_id, enabled=True)
    except Game.DoesNotExist:
        return JsonResponse({"error": "game not found"}, status=404)

    try:
        play_session = PlaySession.objects.get(id=session_id, game=game)
    except PlaySession.DoesNotExist:
        return JsonResponse({"error": "play session not found"}, status=404)

    if request.user.is_authenticated and play_session.user_id != request.user.id:
        return JsonResponse({"error": "play session does not belong to current user"}, status=403)

    session_elapsed_ms = int((timezone.now() - play_session.started_at).total_seconds() * 1000)
    # Allow small client/server drift and delayed score submit.
    if duration_ms_int > session_elapsed_ms + 5000:
        return JsonResponse({"error": "duration_ms exceeds server-observed play time"}, status=400)

    if play_session.ended_at is None:
        play_session.ended_at = play_session.started_at + timedelta(milliseconds=duration_ms_int)
        play_session.save(update_fields=["ended_at"])

    high_score = HighScore.objects.create(
        user=request.user if request.user.is_authenticated else None,
        game=game,
        score=score_int,
        metadata={
            **payload.get("metadata", {}),
            "session_id": str(play_session.id),
            "duration_ms": duration_ms_int,
        },
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
