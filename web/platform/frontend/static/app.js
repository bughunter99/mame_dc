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
      <button data-id="${game.id}">에뮬레이터 실행(프로토타입)</button>
    `;
    li.querySelector("button").addEventListener("click", () => runPrototype(game));
    gamesEl.appendChild(li);
  }
  log(`Loaded ${payload.games.length} games`);
}

async function runPrototype(game) {
  log(`[${game.slug}] fetching ROM manifest from ${game.rom_download_url}`);
  log(`[${game.slug}] loading wasm bundle from ${game.wasm_bundle_url}`);
  log(`[${game.slug}] browser runtime execution placeholder`);
}

document.getElementById("load-games").addEventListener("click", async () => {
  try {
    await loadGames();
  } catch (error) {
    log(`Failed to load games: ${error.message}`);
  }
});
