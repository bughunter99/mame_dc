const logEl = document.getElementById("log");
const gamesEl = document.getElementById("games");

function log(message) {
  logEl.textContent += `${message}\n`;
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

async function loadGames() {
  const payload = await api("/api/games");
  gamesEl.innerHTML = "";
  for (const game of payload.games) {
    const li = document.createElement("li");
    li.innerHTML = `
      <strong>${game.title}</strong>
      <div>ROM URL: ${game.rom_download_url}</div>
      <div>WASM Bundle: ${game.wasm_bundle_url}</div>
      <button data-id="${game.id}">실행 준비 확인</button>
    `;
    li.querySelector("button").addEventListener("click", () => runPrototype(game));
    gamesEl.appendChild(li);
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

async function runPrototype(game) {
  const romReady = await checkResource(game.rom_download_url);
  const wasmReady = await checkResource(game.wasm_bundle_url);
  log(`[${game.slug}] ROM ${romReady ? "ready" : "missing"}: ${game.rom_download_url}`);
  log(`[${game.slug}] WASM ${wasmReady ? "ready" : "missing"}: ${game.wasm_bundle_url}`);
  if (!wasmReady) {
    log(`[${game.slug}] 아직 실제 코어가 없어 실행은 불가합니다. static/wasm/mame.js를 배치하세요.`);
    return;
  }
  log(`[${game.slug}] 실행 훅 연결 완료 (실제 코어 연동 단계 필요)`);
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
