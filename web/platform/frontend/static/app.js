const logEl = document.getElementById("log");
const gamesEl = document.getElementById("games");
const emulatorStatusEl = document.getElementById("emulator-status");
const emulatorCanvasEl = document.getElementById("canvas");
const currentGameIdEl = document.getElementById("current-game-id");
const currentSessionIdEl = document.getElementById("current-session-id");
const scoreInputEl = document.getElementById("score-input");
const saveFileInputEl = document.getElementById("save-file-input");
const saveSlotInputEl = document.getElementById("save-slot-input");
const leaderboardGameEl = document.getElementById("leaderboard-game");
const leaderboardBodyEl = document.getElementById("leaderboard-body");
const errorSummaryEl = document.getElementById("error-summary");
const romDiagnosisSummaryEl = document.getElementById("rom-diagnosis-summary");
const fullscreenButtonEl = document.getElementById("toggle-fullscreen");
const touchControlButtons = Array.from(document.querySelectorAll(".touch-btn[data-key]"));
const touchActionButtonEls = [
  document.getElementById("touch-action-1"),
  document.getElementById("touch-action-2"),
  document.getElementById("touch-action-3"),
  document.getElementById("touch-action-4"),
  document.getElementById("touch-action-5"),
  document.getElementById("touch-action-6"),
].filter(Boolean);
const touchCoinButtonEl = document.getElementById("touch-coin");
const touchStartButtonEl = document.getElementById("touch-start");

const emulatorState = {
  booting: false,
  started: false,
  loadedCoreScriptUrl: null,
  currentGameId: null,
  currentPlaySessionId: null,
  sessionStartedAtMs: null,
  games: [],
};

const VIRTUAL_KEY_CODE_BY_CODE = {
  ArrowUp: 38,
  ArrowDown: 40,
  ArrowLeft: 37,
  ArrowRight: 39,
  ControlLeft: 17,
  AltLeft: 18,
  Space: 32,
  ShiftLeft: 16,
  KeyZ: 90,
  KeyX: 88,
  Digit1: 49,
  Digit5: 53,
};

const VIRTUAL_KEY_BY_CODE = {
  ArrowUp: "ArrowUp",
  ArrowDown: "ArrowDown",
  ArrowLeft: "ArrowLeft",
  ArrowRight: "ArrowRight",
  ControlLeft: "Control",
  AltLeft: "Alt",
  Space: " ",
  ShiftLeft: "Shift",
  KeyZ: "z",
  KeyX: "x",
  Digit1: "1",
  Digit5: "5",
};

const TOUCH_CONTROL_PROFILES = {
  default: {
    actions: [
      { label: "P1", code: "ControlLeft", visible: true },
      { label: "P2", code: "AltLeft", visible: true },
      { label: "P3", code: "Space", visible: true },
      { label: "K1", code: "ShiftLeft", visible: false },
      { label: "K2", code: "KeyZ", visible: false },
      { label: "K3", code: "KeyX", visible: false },
    ],
  },
  sf2ce: {
    actions: [
      { label: "LP", code: "ControlLeft", visible: true },
      { label: "MP", code: "AltLeft", visible: true },
      { label: "HP", code: "Space", visible: true },
      { label: "LK", code: "ShiftLeft", visible: true },
      { label: "MK", code: "KeyZ", visible: true },
      { label: "HK", code: "KeyX", visible: true },
    ],
  },
  kof94: {
    actions: [
      { label: "A", code: "ControlLeft", visible: true },
      { label: "B", code: "AltLeft", visible: true },
      { label: "C", code: "Space", visible: true },
      { label: "D", code: "ShiftLeft", visible: true },
      { label: "St", code: "KeyZ", visible: false },
      { label: "Se", code: "KeyX", visible: false },
    ],
  },
};

const pressedVirtualKeys = new Set();

function log(message) {
  logEl.textContent += `${message}\n`;
  const lines = logEl.textContent.trimEnd().split("\n");
  if (lines.length > 300) {
    logEl.textContent = `${lines.slice(-300).join("\n")}\n`;
  }
  logEl.scrollTop = logEl.scrollHeight;
}

function setEmulatorStatus(message) {
  emulatorStatusEl.textContent = message;
}

function setErrorSummary(message) {
  if (!message) {
    errorSummaryEl.hidden = true;
    errorSummaryEl.textContent = "";
    return;
  }
  errorSummaryEl.hidden = false;
  errorSummaryEl.textContent = message;
}

function setRomDiagnosisSummary(message, level = "ok") {
  if (!romDiagnosisSummaryEl) {
    return;
  }
  if (!message) {
    romDiagnosisSummaryEl.hidden = true;
    romDiagnosisSummaryEl.textContent = "";
    romDiagnosisSummaryEl.classList.remove("warn");
    return;
  }

  romDiagnosisSummaryEl.hidden = false;
  romDiagnosisSummaryEl.textContent = message;
  romDiagnosisSummaryEl.classList.toggle("warn", level === "warn");
}

function renderCurrentSession() {
  currentGameIdEl.textContent = emulatorState.currentGameId ?? "-";
  currentSessionIdEl.textContent = emulatorState.currentPlaySessionId ?? "-";
}

function readCsrfTokenFromCookie() {
  const tokenPrefix = "csrftoken=";
  const parts = document.cookie.split(";").map((part) => part.trim());
  for (const part of parts) {
    if (part.startsWith(tokenPrefix)) {
      return decodeURIComponent(part.slice(tokenPrefix.length));
    }
  }
  return "";
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = {
    ...(options.headers || {}),
  };
  const hasBody = Object.prototype.hasOwnProperty.call(options, "body") && options.body != null;
  if (hasBody && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrfToken = readCsrfTokenFromCookie();
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }
  }

  const response = await fetch(path, {
    credentials: "same-origin",
    headers,
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return {};
}

function createDetailLine(label, value) {
  const line = document.createElement("div");
  line.textContent = `${label}: ${value}`;
  return line;
}

function createGameItem(game) {
  const li = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = game.title;
  li.appendChild(title);
  li.appendChild(createDetailLine("ROM URL", game.rom_download_url));
  li.appendChild(createDetailLine("WASM Bundle", game.wasm_bundle_url));

  const checkButton = document.createElement("button");
  checkButton.textContent = "실행 준비 확인";
  checkButton.addEventListener("click", () => runPrototype(game));
  li.appendChild(checkButton);

  const launchButton = document.createElement("button");
  launchButton.textContent = "실행";
  launchButton.addEventListener("click", () => launchGame(game));
  li.appendChild(launchButton);
  return li;
}

function renderLeaderboard(rows) {
  leaderboardBodyEl.innerHTML = "";
  if (!rows || rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.textContent = "기록이 없습니다.";
    tr.appendChild(td);
    leaderboardBodyEl.appendChild(tr);
    return;
  }
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");

    const rankCell = document.createElement("td");
    rankCell.textContent = String(index + 1);
    tr.appendChild(rankCell);

    const userCell = document.createElement("td");
    userCell.textContent = row.username || "guest";
    tr.appendChild(userCell);

    const scoreCell = document.createElement("td");
    scoreCell.textContent = String(row.score);
    tr.appendChild(scoreCell);

    const timeCell = document.createElement("td");
    timeCell.textContent = row.submitted_at;
    tr.appendChild(timeCell);

    leaderboardBodyEl.appendChild(tr);
  });
}

function populateLeaderboardGameOptions(games) {
  const previousValue = leaderboardGameEl.value;
  leaderboardGameEl.innerHTML = "";
  if (!games || games.length === 0) {
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "게임 없음";
    leaderboardGameEl.appendChild(emptyOption);
    return;
  }
  games.forEach((game) => {
    const option = document.createElement("option");
    option.value = String(game.id);
    option.textContent = game.title;
    leaderboardGameEl.appendChild(option);
  });
  if (previousValue && games.some((game) => String(game.id) === previousValue)) {
    leaderboardGameEl.value = previousValue;
  }
}

async function refreshLeaderboard(gameId) {
  if (!gameId) {
    renderLeaderboard([]);
    return;
  }
  const payload = await api(`/api/leaderboard?game_id=${encodeURIComponent(gameId)}&limit=20`);
  renderLeaderboard(payload.leaderboard || []);
}

async function loadGames() {
  const payload = await api("/api/games");
  emulatorState.games = payload.games;
  gamesEl.innerHTML = "";
  for (const game of payload.games) {
    gamesEl.appendChild(createGameItem(game));
  }
  populateLeaderboardGameOptions(payload.games);
  if (payload.games.length > 0) {
    await refreshLeaderboard(leaderboardGameEl.value || payload.games[0].id);
  } else {
    renderLeaderboard([]);
  }
  log(`Loaded ${payload.games.length} games`);
}

async function syncLocalRoms() {
  const payload = await api("/api/games/sync-local-roms", { method: "POST" });
  log(`Synced local ROMs: ${payload.created} created, ${payload.updated} updated`);
  await loadGames();
}

async function checkResource(url) {
  const response = await fetch(url, { method: "HEAD", credentials: "same-origin" });
  return response.ok;
}

async function getLaunchConfig(game) {
  const payload = await api(`/api/games/${game.id}/launch`);
  return payload.launch;
}

async function getRomDiagnosis(gameId) {
  const response = await fetch(`/api/games/${gameId}/rom-diagnose`, {
    method: "GET",
    credentials: "same-origin",
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch (_) {
    payload = {};
  }

  if (response.ok) {
    return payload;
  }

  return {
    ...payload,
    error: true,
    status: response.status,
  };
}

function extractFilename(resourceUrl) {
  const url = new URL(resourceUrl, window.location.origin);
  return url.pathname.split("/").pop() || "";
}

function machineNameFromRomFilename(romFilename) {
  return romFilename.replace(/\.[^.]+$/, "");
}

function createVirtualKeyboardEvent(type, code) {
  const keyCode = VIRTUAL_KEY_CODE_BY_CODE[code] ?? 0;
  const key = VIRTUAL_KEY_BY_CODE[code] ?? code;
  return new KeyboardEvent(type, {
    key,
    code,
    keyCode,
    which: keyCode,
    bubbles: true,
    cancelable: true,
  });
}

function dispatchVirtualKey(code, pressed) {
  const hasKey = pressedVirtualKeys.has(code);
  if (pressed && hasKey) {
    return;
  }
  if (!pressed && !hasKey) {
    return;
  }
  if (pressed) {
    pressedVirtualKeys.add(code);
  } else {
    pressedVirtualKeys.delete(code);
  }
  const eventType = pressed ? "keydown" : "keyup";
  const target = emulatorCanvasEl || document;
  target.dispatchEvent(createVirtualKeyboardEvent(eventType, code));
  window.dispatchEvent(createVirtualKeyboardEvent(eventType, code));
}

function inferTouchProfile(game) {
  if (!game) {
    return "default";
  }
  const haystack = `${game.slug || ""} ${game.title || ""} ${game.rom_download_url || ""}`.toLowerCase();
  if (haystack.includes("sf2ce") || haystack.includes("street fighter")) {
    return "sf2ce";
  }
  if (haystack.includes("kof94") || haystack.includes("king of fighters")) {
    return "kof94";
  }
  return "default";
}

function applyTouchProfile(profileName) {
  const profile = TOUCH_CONTROL_PROFILES[profileName] || TOUCH_CONTROL_PROFILES.default;
  profile.actions.forEach((action, index) => {
    const button = touchActionButtonEls[index];
    if (!button) {
      return;
    }
    button.textContent = action.label;
    button.dataset.key = action.code;
    button.hidden = !action.visible;
  });

  if (touchCoinButtonEl) {
    touchCoinButtonEl.dataset.key = "Digit5";
    touchCoinButtonEl.textContent = "COIN";
    touchCoinButtonEl.hidden = false;
  }
  if (touchStartButtonEl) {
    touchStartButtonEl.dataset.key = "Digit1";
    touchStartButtonEl.textContent = "START";
    touchStartButtonEl.hidden = false;
  }
}

function releaseAllVirtualKeys() {
  for (const code of Array.from(pressedVirtualKeys)) {
    dispatchVirtualKey(code, false);
  }
}

function attachJoystick() {
  const base = document.getElementById("joystick-base");
  const knob = document.getElementById("joystick-knob");
  if (!base || !knob) {
    return;
  }

  let activePointerId = null;
  let prevKeys = new Set();
  const DEAD_ZONE = 0.22;
  const MAX_TRAVEL = 0.42;

  function updateJoystick(clientX, clientY) {
    const rect = base.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const r = rect.width / 2;

    const rawDx = clientX - cx;
    const rawDy = clientY - cy;
    const dist = Math.hypot(rawDx, rawDy);
    const maxDist = r * MAX_TRAVEL;

    const clampFactor = dist > maxDist ? maxDist / dist : 1;
    knob.style.transform = `translate(${rawDx * clampFactor}px, ${rawDy * clampFactor}px)`;

    const threshold = r * DEAD_ZONE;
    const newKeys = new Set();
    if (rawDy < -threshold) newKeys.add("ArrowUp");
    if (rawDy >  threshold) newKeys.add("ArrowDown");
    if (rawDx < -threshold) newKeys.add("ArrowLeft");
    if (rawDx >  threshold) newKeys.add("ArrowRight");

    for (const k of prevKeys) {
      if (!newKeys.has(k)) dispatchVirtualKey(k, false);
    }
    for (const k of newKeys) {
      if (!prevKeys.has(k)) dispatchVirtualKey(k, true);
    }
    prevKeys = newKeys;
  }

  function onMove(e) {
    if (e.pointerId !== activePointerId) return;
    e.preventDefault();
    updateJoystick(e.clientX, e.clientY);
  }

  function onEnd(e) {
    if (e.pointerId !== activePointerId) return;
    knob.style.transform = "translate(0, 0)";
    for (const k of prevKeys) dispatchVirtualKey(k, false);
    prevKeys = new Set();
    activePointerId = null;
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup",   onEnd);
    document.removeEventListener("pointercancel", onEnd);
  }

  base.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    if (activePointerId !== null) return;
    activePointerId = e.pointerId;
    updateJoystick(e.clientX, e.clientY);
    document.addEventListener("pointermove",   onMove,  { passive: false });
    document.addEventListener("pointerup",     onEnd);
    document.addEventListener("pointercancel", onEnd);
  }, { passive: false });

  window.addEventListener("blur", () => {
    if (activePointerId !== null) onEnd({ pointerId: activePointerId });
  });
}

function attachTouchControls() {
  if (touchControlButtons.length === 0) {
    return;
  }
  for (const button of touchControlButtons) {
    const press = (event) => {
      event.preventDefault();
      const code = button.dataset.key;
      if (!code) {
        return;
      }
      button.classList.add("pressed");
      dispatchVirtualKey(code, true);
    };
    const release = (event) => {
      event.preventDefault();
      const code = button.dataset.key;
      if (!code) {
        return;
      }
      button.classList.remove("pressed");
      dispatchVirtualKey(code, false);
    };

    button.addEventListener("pointerdown", press);
    button.addEventListener("pointerup", release);
    button.addEventListener("pointercancel", release);
    button.addEventListener("pointerleave", release);
  }

  window.addEventListener("blur", () => {
    releaseAllVirtualKeys();
    for (const button of touchControlButtons) {
      button.classList.remove("pressed");
    }
  });
}

async function toggleFullscreen() {
  if (!document.fullscreenElement) {
    const target = (emulatorCanvasEl && emulatorCanvasEl.closest(".emulator-wrap")) || document.documentElement;
    if (target.requestFullscreen) {
      await target.requestFullscreen();
      log("전체화면 모드 활성화");
    }
    return;
  }
  if (document.exitFullscreen) {
    await document.exitFullscreen();
    log("전체화면 모드 종료");
  }
}

async function runPrototype(game) {
  setErrorSummary("");
  setRomDiagnosisSummary("");
  const launch = await getLaunchConfig(game);
  const romReady = await checkResource(launch.rom_download_url);
  const wasmReady = await checkResource(launch.wasm_bundle_url);
  log(`[${game.slug}] ROM ${romReady ? "ready" : "missing"}: ${launch.rom_download_url}`);
  log(`[${game.slug}] WASM ${wasmReady ? "ready" : "missing"}: ${launch.wasm_bundle_url}`);
  if (launch.token_ttl_seconds) {
    log(`[${game.slug}] ROM token ttl: ${launch.token_ttl_seconds}s`);
  }
  if (launch.play_session_id) {
    log(`[${game.slug}] play session: ${launch.play_session_id}`);
  }

  const diagnosis = await getRomDiagnosis(game.id);
  if (diagnosis.error) {
    const message = diagnosis.message || `HTTP ${diagnosis.status}`;
    log(`[${game.slug}] ROM diagnose: ${message}`);
    setRomDiagnosisSummary(`ROM 진단 경고: ${message}`, "warn");
  } else if (diagnosis.local_rom) {
    log(
      `[${game.slug}] ROM diagnose: inferred=${diagnosis.inferred_machine}, likely=${diagnosis.likely_machine}, entries=${diagnosis.entry_count}`
    );
    const inferredMissing = diagnosis.missing_markers?.[diagnosis.inferred_machine] || [];
    if (inferredMissing.length > 0) {
      setRomDiagnosisSummary(
        `ROM 경고: ${diagnosis.inferred_machine} 기준 누락 marker ${inferredMissing.length}개`,
        "warn"
      );
    } else {
      setRomDiagnosisSummary(
        `ROM 진단 OK: inferred=${diagnosis.inferred_machine}, entries=${diagnosis.entry_count}`,
        "ok"
      );
    }
    if (inferredMissing.length > 0) {
      log(`[${game.slug}] missing markers (${diagnosis.inferred_machine}): ${inferredMissing.join(", ")}`);
    }
  } else {
    setRomDiagnosisSummary("외부 ROM URL은 marker 진단을 생략합니다.", "ok");
  }

  if (!wasmReady) {
    const message = `[${game.slug}] WASM 번들이 없습니다. ${launch.wasm_bundle_url} 파일을 실제로 배치해야 실행됩니다.`;
    setErrorSummary(message);
    log(message);
    return;
  }
  log(`[${game.slug}] 코어 실행 가능 상태입니다. 실행 버튼으로 구동해보세요.`);
}

async function loadRomBytes(romUrl) {
  const response = await fetch(romUrl, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`ROM 다운로드 실패: ${response.status} ${response.statusText}`);
  }
  return new Uint8Array(await response.arrayBuffer());
}

function ensureWasmImportShim(game) {
  if (window.__mameWasmImportShimInstalled) {
    return;
  }
  window.__mameWasmImportShimInstalled = true;

  const missingImportFallback = new Proxy(
    {},
    {
      get: (_target, key) => {
        return () => {
          throw new Error(`Missing wasm env import: ${String(key)}`);
        };
      },
    }
  );
  const functionLikeImportKeys = new Set([
    "abort",
    "strftime",
    "__emscripten_stack_alloc",
    "__emscripten_stack_restore",
    "__emscripten_stack_save",
  ]);

  // Some generated bundles reference these helpers directly on global scope.
  if (typeof window.__emscripten_stack_alloc !== "function") {
    window.__emscripten_stack_alloc = (size) => {
      if (window.Module && window.Module.asm && typeof window.Module.asm.stackAlloc === "function") {
        return window.Module.asm.stackAlloc(size);
      }
      throw new Error("stackAlloc helper is unavailable");
    };
  }
  if (typeof window.__emscripten_stack_restore !== "function") {
    window.__emscripten_stack_restore = (ptr) => {
      if (window.Module && window.Module.asm && typeof window.Module.asm.stackRestore === "function") {
        return window.Module.asm.stackRestore(ptr);
      }
      throw new Error("stackRestore helper is unavailable");
    };
  }
  if (typeof window.__emscripten_stack_save !== "function") {
    window.__emscripten_stack_save = () => {
      if (window.Module && window.Module.asm && typeof window.Module.asm.stackSave === "function") {
        return window.Module.asm.stackSave();
      }
      throw new Error("stackSave helper is unavailable");
    };
  }

  const wrapImports = (imports) => {
    if (!imports || !imports.env) {
      return imports;
    }
    const envWithFallback = new Proxy(imports.env, {
      get: (target, key, receiver) => {
        const value = Reflect.get(target, key, receiver);
        const keyName = String(key);
        const mustBeFunction = functionLikeImportKeys.has(keyName) || keyName.startsWith("__emscripten_stack_");
        if (typeof value === "undefined") {
          return Reflect.get(missingImportFallback, key);
        }
        if (mustBeFunction && typeof value !== "function") {
          return Reflect.get(missingImportFallback, key);
        }
        return value;
      },
    });

    return {
      ...imports,
      env: envWithFallback,
    };
  };

  const originalInstantiate = WebAssembly.instantiate.bind(WebAssembly);
  WebAssembly.instantiate = (binary, imports) => {
    return originalInstantiate(binary, wrapImports(imports));
  };

  if (typeof WebAssembly.instantiateStreaming === "function") {
    const originalInstantiateStreaming = WebAssembly.instantiateStreaming.bind(WebAssembly);
    WebAssembly.instantiateStreaming = (source, imports) => {
      return originalInstantiateStreaming(source, wrapImports(imports));
    };
  }

  log(`[${game.slug}] wasm import shim 설치 완료`);
}

function configureModule(game, wasmBundleUrl, machineName, romFilename, romBytes, biosRoms = []) {
  log(`[${game.slug}] machine="${machineName}" rom="${romFilename}" size=${romBytes.length}`);
  const mameArgs = [
    machineName,
    "-rompath",
    "/roms",
    "-skip_gameinfo",
    "-video",
    "soft",
    "-sound",
    "dummy",
    "-verbose",
  ];
  log(`[${game.slug}] MAME args: ${mameArgs.join(" ")}`);
  window.Module = {
    canvas: emulatorCanvasEl,
    arguments: mameArgs,
    print: (text) => log(`[mame] ${text}`),
    printErr: (text) => log(`[mame:err] ${text}`),
    locateFile: (path) => {
      const resolved = path.endsWith(".wasm") ? new URL(path, wasmBundleUrl).toString() : path;
      log(`[mame:locate] ${path} → ${resolved}`);
      return resolved;
    },
    preRun: [
      () => {
        if (!window.FS) {
          throw new Error("Emscripten FS를 찾을 수 없습니다.");
        }
        if (window.Module && window.Module.asm) {
          if (typeof window.Module.asm.stackAlloc === "function") {
            window.__emscripten_stack_alloc = window.Module.asm.stackAlloc;
          }
          if (typeof window.Module.asm.stackRestore === "function") {
            window.__emscripten_stack_restore = window.Module.asm.stackRestore;
          }
          if (typeof window.Module.asm.stackSave === "function") {
            window.__emscripten_stack_save = window.Module.asm.stackSave;
          }
        }
        try {
          window.FS.mkdir("/roms");
        } catch (error) {
          if (!String(error).includes("File exists")) {
            throw error;
          }
        }
        window.FS.writeFile(`/roms/${romFilename}`, romBytes);
        log(`[${game.slug}] FS에 /roms/${romFilename} 마운트 완료 (${romBytes.length} bytes)`);
        for (const bios of biosRoms) {
          window.FS.writeFile(`/roms/${bios.filename}`, bios.bytes);
          log(`[${game.slug}] FS에 /roms/${bios.filename} 마운트 완료 (${bios.bytes.length} bytes)`);
        }
        // 디버그: FS에 실제로 파일이 쓰였는지 확인
        try {
          const stat = window.FS.stat(`/roms/${romFilename}`);
          log(`[${game.slug}] FS stat: size=${stat.size}`);
        } catch (e) {
          log(`[${game.slug}] FS stat 실패: ${e}`);
        }
      },
    ],
    onRuntimeInitialized: () => {
      emulatorState.started = true;
      emulatorState.booting = false;
      setEmulatorStatus(`실행 중: ${game.title}`);
      log(`[${game.slug}] 코어 초기화 완료 — MAME main() 진입`);
    },
    onExit: (code) => {
      log(`[${game.slug}] MAME 종료 코드: ${code}`);
    },
    onAbort: (reason) => {
      emulatorState.booting = false;
      setEmulatorStatus("실행 중단됨");
      log(`[${game.slug}] 코어 중단 reason="${reason}" (type=${typeof reason})`);
      // 스택 트레이스 시도
      try {
        const err = new Error("abort trace");
        log(`[${game.slug}] abort stack: ${err.stack}`);
      } catch (_) {}
    },
  };
}

async function loadCoreScript(wasmBundleUrl) {
  if (emulatorState.loadedCoreScriptUrl) {
    if (emulatorState.loadedCoreScriptUrl !== wasmBundleUrl) {
      throw new Error("다른 코어 번들은 새로고침 후 실행 가능합니다.");
    }
    return;
  }
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = wasmBundleUrl + "?v=" + Date.now();
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`코어 스크립트 로드 실패: ${wasmBundleUrl}`));
    document.body.appendChild(script);
  });
  emulatorState.loadedCoreScriptUrl = wasmBundleUrl;
}

async function launchGame(game) {
  setErrorSummary("");
  applyTouchProfile(inferTouchProfile(game));
  if (emulatorState.booting) {
    log("이미 코어 초기화가 진행 중입니다.");
    return;
  }
  if (emulatorState.started) {
    log("이미 코어가 실행 중입니다. 다른 게임 실행은 페이지 새로고침 후 시도하세요.");
    return;
  }
  setEmulatorStatus(`실행 준비 중: ${game.title}`);
  emulatorState.booting = true;
  try {
    const launch = await getLaunchConfig(game);
    emulatorState.currentGameId = game.id;
    emulatorState.currentPlaySessionId = launch.play_session_id || null;
    emulatorState.sessionStartedAtMs = Date.now();
    renderCurrentSession();
    if (emulatorState.currentGameId) {
      leaderboardGameEl.value = String(emulatorState.currentGameId);
      await refreshLeaderboard(emulatorState.currentGameId);
    }
    const romReady = await checkResource(launch.rom_download_url);
    const wasmReady = await checkResource(launch.wasm_bundle_url);
    if (!romReady || !wasmReady) {
      throw new Error("ROM 또는 WASM 번들이 준비되지 않았습니다.");
    }
    const romFilename = launch.rom_filename || extractFilename(launch.rom_download_url);
    const machineName = launch.machine_name || machineNameFromRomFilename(romFilename);
    if (!romFilename) {
      throw new Error("ROM 파일명을 확인할 수 없습니다.");
    }
    const romBytes = await loadRomBytes(launch.rom_download_url);
    // Load BIOS ROMs (e.g. neogeo.zip for Neo Geo games) if the backend provides them.
    const biosRoms = [];
    if (Array.isArray(launch.bios_roms)) {
      for (const bios of launch.bios_roms) {
        log(`[${game.slug}] BIOS ROM 로드 중: ${bios.filename}`);
        const biosBytes = await loadRomBytes(bios.download_url);
        biosRoms.push({ filename: bios.filename, bytes: biosBytes });
        log(`[${game.slug}] BIOS ROM 로드 완료: ${bios.filename} (${biosBytes.length} bytes)`);
      }
    }
    ensureWasmImportShim(game);
    configureModule(game, launch.wasm_bundle_url, machineName, romFilename, romBytes, biosRoms);
    await loadCoreScript(launch.wasm_bundle_url);
    log(`[${game.slug}] 코어 로딩 시작`);
  } catch (error) {
    emulatorState.booting = false;
    emulatorState.currentGameId = null;
    emulatorState.currentPlaySessionId = null;
    emulatorState.sessionStartedAtMs = null;
    renderCurrentSession();
    setEmulatorStatus("대기 중");
    setErrorSummary(error.message);
    log(`[${game.slug}] 실행 실패: ${error.message}`);
  }
}

async function submitCurrentScore() {
  if (!emulatorState.currentGameId || !emulatorState.currentPlaySessionId || !emulatorState.sessionStartedAtMs) {
    log("점수 저장 전 먼저 게임을 실행해 세션을 생성하세요.");
    return;
  }
  const scoreValue = Number(scoreInputEl.value);
  if (!Number.isFinite(scoreValue) || scoreValue < 0) {
    log("유효한 점수를 입력하세요.");
    return;
  }
  const durationMs = Math.max(0, Date.now() - emulatorState.sessionStartedAtMs);
  const payload = {
    game_id: emulatorState.currentGameId,
    score: Math.floor(scoreValue),
    session_id: emulatorState.currentPlaySessionId,
    duration_ms: durationMs,
    metadata: {
      source: "web-ui",
    },
  };
  const result = await api("/api/highscores", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  log(`점수 저장 완료: highscore_id=${result.id}, duration_ms=${durationMs}`);
  await refreshLeaderboard(emulatorState.currentGameId);
}

async function uploadCurrentSaveFile() {
  if (!emulatorState.currentGameId) {
    log("세이브 업로드 전 먼저 게임을 실행하세요.");
    return;
  }
  if (!saveFileInputEl.files || saveFileInputEl.files.length === 0) {
    log("업로드할 세이브 파일을 선택하세요.");
    return;
  }
  const slotValue = Number(saveSlotInputEl.value);
  if (!Number.isInteger(slotValue) || slotValue < 0) {
    log("슬롯은 0 이상의 정수여야 합니다.");
    return;
  }
  const formData = new FormData();
  formData.append("game_id", String(emulatorState.currentGameId));
  formData.append("slot", String(slotValue));
  formData.append("state_file", saveFileInputEl.files[0]);

  const result = await api("/api/saves/upload", {
    method: "POST",
    body: formData,
  });
  log(`세이브 업로드 완료: state_id=${result.id}`);
}

document.getElementById("load-games").addEventListener("click", async () => {
  try {
    await loadGames();
  } catch (error) {
    log(`Failed to load games: ${error.message}`);
  }
});

document.getElementById("sync-local-roms").addEventListener("click", async () => {
  try {
    await syncLocalRoms();
  } catch (error) {
    log(`Failed to sync local ROMs: ${error.message}`);
  }
});

document.getElementById("submit-score").addEventListener("click", async () => {
  try {
    await submitCurrentScore();
  } catch (error) {
    log(`점수 저장 실패: ${error.message}`);
  }
});

document.getElementById("upload-save").addEventListener("click", async () => {
  try {
    await uploadCurrentSaveFile();
  } catch (error) {
    log(`세이브 업로드 실패: ${error.message}`);
  }
});

window.addEventListener("error", (event) => {
  if (event?.message) {
    setErrorSummary(event.message);
  }
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event?.reason;
  setErrorSummary(typeof reason === "string" ? reason : reason?.message || "알 수 없는 비동기 오류");
});

document.getElementById("refresh-leaderboard").addEventListener("click", async () => {
  try {
    await refreshLeaderboard(leaderboardGameEl.value);
  } catch (error) {
    log(`리더보드 조회 실패: ${error.message}`);
  }
});

leaderboardGameEl.addEventListener("change", async () => {
  try {
    await refreshLeaderboard(leaderboardGameEl.value);
  } catch (error) {
    log(`리더보드 조회 실패: ${error.message}`);
  }
});

if (fullscreenButtonEl) {
  fullscreenButtonEl.addEventListener("click", async () => {
    try {
      await toggleFullscreen();
    } catch (error) {
      log(`전체화면 전환 실패: ${error.message}`);
    }
  });
}

applyTouchProfile("default");
attachTouchControls();
attachJoystick();

renderCurrentSession();
