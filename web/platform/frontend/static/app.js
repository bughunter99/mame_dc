const logEl = document.getElementById("log");
const gamesEl = document.getElementById("games");
const emulatorStatusEl = document.getElementById("emulator-status");
const emulatorCanvasEl = document.getElementById("emulator-canvas");
const currentGameIdEl = document.getElementById("current-game-id");
const currentSessionIdEl = document.getElementById("current-session-id");
const scoreInputEl = document.getElementById("score-input");
const saveFileInputEl = document.getElementById("save-file-input");
const saveSlotInputEl = document.getElementById("save-slot-input");
const leaderboardGameEl = document.getElementById("leaderboard-game");
const leaderboardBodyEl = document.getElementById("leaderboard-body");
const errorSummaryEl = document.getElementById("error-summary");

const emulatorState = {
  booting: false,
  started: false,
  loadedCoreScriptUrl: null,
  currentGameId: null,
  currentPlaySessionId: null,
  sessionStartedAtMs: null,
  games: [],
};

function log(message) {
  logEl.textContent += `${message}\n`;
  const lines = logEl.textContent.trimEnd().split("\n");
  if (lines.length > 80) {
    logEl.textContent = `${lines.slice(-80).join("\n")}\n`;
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

function extractFilename(resourceUrl) {
  const url = new URL(resourceUrl, window.location.origin);
  return url.pathname.split("/").pop() || "";
}

function machineNameFromRomFilename(romFilename) {
  return romFilename.replace(/\.[^.]+$/, "");
}

async function runPrototype(game) {
  setErrorSummary("");
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

function configureModule(game, wasmBundleUrl, romFilename, romBytes) {
  const machineName = machineNameFromRomFilename(romFilename);
  window.Module = {
    canvas: emulatorCanvasEl,
    arguments: [machineName, "-rompath", "/roms", "-skip_gameinfo"],
    print: (text) => log(`[mame] ${text}`),
    printErr: (text) => log(`[mame:err] ${text}`),
    locateFile: (path) => {
      if (path.endsWith(".wasm")) {
        return new URL(path, wasmBundleUrl).toString();
      }
      return path;
    },
    preRun: [
      () => {
        if (!window.FS) {
          throw new Error("Emscripten FS를 찾을 수 없습니다.");
        }
        try {
          window.FS.mkdir("/roms");
        } catch (error) {
          if (!String(error).includes("File exists")) {
            throw error;
          }
        }
        window.FS.writeFile(`/roms/${romFilename}`, romBytes);
      },
    ],
    onRuntimeInitialized: () => {
      emulatorState.started = true;
      emulatorState.booting = false;
      setEmulatorStatus(`실행 중: ${game.title}`);
      log(`[${game.slug}] 코어 초기화 완료`);
    },
    onAbort: (reason) => {
      emulatorState.booting = false;
      setEmulatorStatus("실행 중단됨");
      log(`[${game.slug}] 코어 중단: ${reason}`);
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
    script.src = wasmBundleUrl;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`코어 스크립트 로드 실패: ${wasmBundleUrl}`));
    document.body.appendChild(script);
  });
  emulatorState.loadedCoreScriptUrl = wasmBundleUrl;
}

async function launchGame(game) {
  setErrorSummary("");
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
    const romFilename = extractFilename(launch.rom_download_url);
    if (!romFilename) {
      throw new Error("ROM 파일명을 확인할 수 없습니다.");
    }
    const romBytes = await loadRomBytes(launch.rom_download_url);
    configureModule(game, launch.wasm_bundle_url, romFilename, romBytes);
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

renderCurrentSession();
