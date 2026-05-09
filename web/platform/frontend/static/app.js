const logEl = document.getElementById("log");
const gamesEl = document.getElementById("games");
const emulatorStatusEl = document.getElementById("emulator-status");
const emulatorCanvasEl = document.getElementById("emulator-canvas");

const emulatorState = {
  booting: false,
  started: false,
  loadedCoreScriptUrl: null,
};

function log(message) {
  logEl.textContent += `${message}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function setEmulatorStatus(message) {
  emulatorStatusEl.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
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

async function loadGames() {
  const payload = await api("/api/games");
  gamesEl.innerHTML = "";
  for (const game of payload.games) {
    gamesEl.appendChild(createGameItem(game));
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

function extractFilename(resourceUrl) {
  const url = new URL(resourceUrl, window.location.origin);
  return url.pathname.split("/").pop() || "";
}

function machineNameFromRomFilename(romFilename) {
  return romFilename.replace(/\.[^.]+$/, "");
}

async function runPrototype(game) {
  const romReady = await checkResource(game.rom_download_url);
  const wasmReady = await checkResource(game.wasm_bundle_url);
  log(`[${game.slug}] ROM ${romReady ? "ready" : "missing"}: ${game.rom_download_url}`);
  log(`[${game.slug}] WASM ${wasmReady ? "ready" : "missing"}: ${game.wasm_bundle_url}`);
  if (!wasmReady) {
    log(`[${game.slug}] 아직 실제 코어가 없어 실행은 불가합니다. static/wasm/mame.js를 배치하세요.`);
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

function configureModule(game, romFilename, romBytes) {
  const machineName = machineNameFromRomFilename(romFilename);
  window.Module = {
    canvas: emulatorCanvasEl,
    arguments: [machineName, "-rompath", "/roms", "-skip_gameinfo"],
    print: (text) => log(`[mame] ${text}`),
    printErr: (text) => log(`[mame:err] ${text}`),
    locateFile: (path) => {
      if (path.endsWith(".wasm")) {
        return new URL(path, game.wasm_bundle_url).toString();
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
    const romReady = await checkResource(game.rom_download_url);
    const wasmReady = await checkResource(game.wasm_bundle_url);
    if (!romReady || !wasmReady) {
      throw new Error("ROM 또는 WASM 번들이 준비되지 않았습니다.");
    }
    const romFilename = extractFilename(game.rom_download_url);
    if (!romFilename) {
      throw new Error("ROM 파일명을 확인할 수 없습니다.");
    }
    const romBytes = await loadRomBytes(game.rom_download_url);
    configureModule(game, romFilename, romBytes);
    await loadCoreScript(game.wasm_bundle_url);
    log(`[${game.slug}] 코어 로딩 시작`);
  } catch (error) {
    emulatorState.booting = false;
    setEmulatorStatus("대기 중");
    log(`[${game.slug}] 실행 실패: ${error.message}`);
  }
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
