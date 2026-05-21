"""
MAME/kof94 Python 제어 유틸리티
================================
웹 MAME(Django API + Playwright)와 네이티브 MAME HTTP 서버를 Python으로 제어합니다.

== 방법1: Django API 제어 (게임 실행/세이브스테이트) ==
  pip install requests
  python tools/mame_control.py --api launch --game kof94
  python tools/mame_control.py --api list

== 방법2: 브라우저 자동화 (키 입력, 스크린샷) ==
  pip install playwright
  playwright install chromium
  python tools/mame_control.py --browser

== 방법3: 네이티브 MAME HTTP 서버 ==
  먼저 MAME 실행:
    mame.exe kof94 -http -httpport 8080 -httproot plugins
  그 다음:
    python tools/mame_control.py --native
"""

import argparse
import json
import sys
import time
from pathlib import Path

# ─────────────────────────────────────────────
# 공통 설정
# ─────────────────────────────────────────────
DJANGO_BASE = "http://127.0.0.1:8001"
MAME_HTTP   = "http://127.0.0.1:8080"


# ─────────────────────────────────────────────
# 방법1: Django API 제어
# ─────────────────────────────────────────────
class DjangoMAMEClient:
    """
    Django 백엔드 API를 통해 게임 실행/세이브스테이트를 제어.
    실제 게임 입력 제어는 불가 (브라우저 wasm 레이어에서만 동작).
    """
    def __init__(self, base_url=DJANGO_BASE):
        try:
            import requests
            self._requests = requests
        except ImportError:
            raise SystemExit("requests 가 필요합니다: pip install requests")
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        # CSRF 토큰 초기화
        r = self.session.get(f"{self.base}/")
        csrf = r.cookies.get("csrftoken", "")
        self.session.headers.update({"X-CSRFToken": csrf, "Referer": f"{self.base}/"})

    def list_games(self) -> list[dict]:
        r = self.session.get(f"{self.base}/api/games")
        r.raise_for_status()
        return r.json()

    def launch_game(self, game_id: int) -> dict:
        r = self.session.get(f"{self.base}/api/games/{game_id}/launch")
        r.raise_for_status()
        return r.json()

    def get_leaderboard(self, game_id: int, limit: int = 10) -> list[dict]:
        r = self.session.get(f"{self.base}/api/leaderboard?game_id={game_id}&limit={limit}")
        r.raise_for_status()
        return r.json()

    def sync_local_roms(self) -> dict:
        r = self.session.post(f"{self.base}/api/games/sync-local-roms")
        r.raise_for_status()
        return r.json()


def demo_django_api(game_filter: str = "kof94"):
    client = DjangoMAMEClient()

    print("=== 게임 목록 ===")
    games = client.list_games()
    for g in games:
        print(f"  [{g['id']}] {g.get('name','?')}  machine={g.get('machine_name','?')}")

    target = next(
        (g for g in games if game_filter in g.get("machine_name", "").lower()
                           or game_filter in g.get("name", "").lower()),
        None
    )
    if target:
        print(f"\n=== '{target['name']}' 실행 ===")
        result = client.launch_game(target["id"])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n'{game_filter}' 게임을 찾을 수 없습니다.")
        print("sync-local-roms 후 재시도:", client.sync_local_roms())


# ─────────────────────────────────────────────
# 방법2: Playwright 브라우저 자동화
# ─────────────────────────────────────────────
class BrowserMAMEController:
    """
    Playwright로 웹 MAME를 제어.
    - 키보드 입력 주입
    - 스크린샷 캡처
    - 화면 녹화(video)
    네오지오 기본 버튼 맵핑 (기본 MAME 키보드):
      방향키: 화살표
      버튼A=Z, B=X, C=A, D=S
      코인=5, 시작=1
    """
    # MAME 기본 키보드 → 네오지오 버튼 맵
    NEO_GEO_KEYS = {
        "coin":    "Digit5",
        "start":   "Digit1",
        "up":      "ArrowUp",
        "down":    "ArrowDown",
        "left":    "ArrowLeft",
        "right":   "ArrowRight",
        "A":       "KeyZ",   # 약펀치 / 선택
        "B":       "KeyX",   # 강펀치
        "C":       "KeyA",   # 약킥
        "D":       "KeyS",   # 강킥
    }

    def __init__(self, base_url=DJANGO_BASE, headless=False):
        try:
            from playwright.sync_api import sync_playwright
            self._playwright_mod = sync_playwright
        except ImportError:
            raise SystemExit(
                "playwright 가 필요합니다:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
        self.base_url = base_url
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        self._pw = self._playwright_mod().__enter__()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        return self

    def __exit__(self, *args):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.__exit__(*args)

    @property
    def page(self):
        return self._page

    def goto(self):
        self._page.goto(self.base_url, wait_until="networkidle")

    def screenshot(self, path: str = "mame_screen.png") -> Path:
        """현재 화면 스크린샷 저장."""
        self._page.screenshot(path=path, full_page=False)
        print(f"[스크린샷] → {path}")
        return Path(path)

    def press(self, button: str, hold_ms: int = 80):
        """
        네오지오 버튼을 누르고 뗌.
        button: 'A','B','C','D','up','down','left','right','coin','start'
        """
        key = self.NEO_GEO_KEYS.get(button, button)
        self._page.keyboard.down(key)
        time.sleep(hold_ms / 1000)
        self._page.keyboard.up(key)

    def insert_coin_and_start(self):
        """코인 투입 후 1P 스타트."""
        print("[조작] 코인 투입")
        self.press("coin")
        time.sleep(0.5)
        print("[조작] 1P 스타트")
        self.press("start")
        time.sleep(0.3)

    def capture_canvas_pixels(self) -> bytes | None:
        """
        MAME 캔버스에서 픽셀 데이터를 읽어 PNG bytes 반환.
        (canvas.toDataURL 방식 — 브라우저 내부에서 실행)
        """
        data_url = self._page.evaluate("""() => {
            const canvas = document.querySelector('canvas');
            if (!canvas) return null;
            return canvas.toDataURL('image/png');
        }""")
        if not data_url:
            return None
        import base64
        header, b64 = data_url.split(",", 1)
        return base64.b64decode(b64)

    def read_memory_via_js(self, address: int, length: int = 16) -> list[int] | None:
        """
        MAME wasm 메모리를 JavaScript를 통해 직접 읽기.
        (Module.HEAPU8 접근 — wasm 빌드 방식에 따라 가능 여부 다름)
        """
        result = self._page.evaluate(f"""() => {{
            if (typeof Module === 'undefined' || !Module.HEAPU8) return null;
            const arr = [];
            for (let i = 0; i < {length}; i++) {{
                arr.push(Module.HEAPU8[{address} + i]);
            }}
            return arr;
        }}""")
        return result


def demo_browser_control(headless=False):
    out_dir = Path("tools/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    with BrowserMAMEController(headless=headless) as ctrl:
        print("[브라우저] 페이지 로딩...")
        ctrl.goto()
        ctrl.screenshot(str(out_dir / "01_loaded.png"))

        # kof94 실행 버튼 클릭 (DOM에서 게임 카드 찾기)
        page = ctrl.page
        page.wait_for_selector("text=kof94", timeout=5000)
        page.click("text=kof94")
        time.sleep(3)
        ctrl.screenshot(str(out_dir / "02_after_launch.png"))

        print("[조작] 코인 투입 → 스타트")
        ctrl.insert_coin_and_start()
        time.sleep(2)
        ctrl.screenshot(str(out_dir / "03_game_start.png"))

        # 캔버스 픽셀 캡처
        png_bytes = ctrl.capture_canvas_pixels()
        if png_bytes:
            canvas_path = out_dir / "04_canvas_capture.png"
            canvas_path.write_bytes(png_bytes)
            print(f"[캔버스 캡처] → {canvas_path}")


# ─────────────────────────────────────────────
# 방법3: 네이티브 MAME HTTP Lua 서버
# ─────────────────────────────────────────────
class NativeMAMEClient:
    """
    네이티브 mame.exe를 -http 모드로 실행하면
    Lua 스크립트를 HTTP로 전송해 실행할 수 있습니다.

    실행 명령:
      mame.exe kof94 -http -httpport 8080 -httproot plugins
    """
    def __init__(self, base_url=MAME_HTTP):
        try:
            import requests
            self._requests = requests
        except ImportError:
            raise SystemExit("requests 가 필요합니다: pip install requests")
        self.base = base_url.rstrip("/")
        self.session = requests.Session()

    def lua(self, code: str) -> str:
        """Lua 코드를 MAME 내부에서 실행하고 결과 반환."""
        r = self.session.post(f"{self.base}/", data={"cmd": code})
        return r.text

    def press_key(self, input_port: str, hold_frames: int = 5):
        """
        입력 포트 이름으로 버튼 누르기.
        예: 'P1 Button 1', 'P1 Up', 'Coin 1'
        """
        return self.lua(f"""
            local port = manager.machine.ioport.ports['{input_port}']
            if port then
                port:field('{input_port}'):set_value(1)
                emu.wait({hold_frames})
                port:field('{input_port}'):set_value(0)
            end
        """)

    def read_memory(self, address: int, length: int = 16) -> list[int]:
        """메인 CPU 주소공간에서 메모리 읽기 (68000 기준)."""
        result = self.lua(f"""
            local cpu = manager.machine.devices[':maincpu']
            local space = cpu.spaces['program']
            local out = {{}}
            for i = 0, {length}-1 do
                table.insert(out, string.format('%02x', space:read_u8({address} + i)))
            end
            return table.concat(out, ' ')
        """)
        return [int(x, 16) for x in result.strip().split()]

    def get_game_info(self) -> dict:
        """현재 실행 중인 게임 정보."""
        name = self.lua("return manager.machine.system.name").strip()
        desc = self.lua("return manager.machine.system.description").strip()
        return {"name": name, "description": desc}

    def list_inputs(self) -> list[str]:
        """사용 가능한 입력 포트 목록."""
        result = self.lua("""
            local out = {}
            for name, _ in pairs(manager.machine.ioport.ports) do
                table.insert(out, name)
            end
            table.sort(out)
            return table.concat(out, '\\n')
        """)
        return [line for line in result.strip().splitlines() if line]

    def screenshot_lua(self, path: str = "mame_snapshot.png"):
        """MAME 내장 스냅샷 기능으로 현재 화면 저장."""
        return self.lua(f"manager.machine:snapshot('{path}')")

    def save_state(self, slot: int = 0):
        return self.lua(f"manager.machine:save_immediate('slot{slot}')")

    def load_state(self, slot: int = 0):
        return self.lua(f"manager.machine:load_immediate('slot{slot}')")


def demo_native_control():
    client = NativeMAMEClient()
    try:
        info = client.get_game_info()
        print(f"[연결됨] {info['description']} ({info['name']})")
    except Exception as e:
        print(f"[오류] MAME HTTP 서버에 연결할 수 없습니다: {e}")
        print("먼저 MAME를 다음과 같이 실행하세요:")
        print("  mame.exe kof94 -http -httpport 8080 -httproot plugins")
        return

    print("\n[입력 포트 목록]")
    for inp in client.list_inputs():
        print(f"  {inp}")

    print("\n[메모리 읽기] 0xFF0000 (팔레트 RAM 영역)")
    mem = client.read_memory(0xFF0000, 32)
    print("  " + " ".join(f"{b:02x}" for b in mem))

    client.screenshot_lua("snapshot.png")
    print("[스냅샷] snapshot.png 저장")


# ─────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MAME/kof94 Python 제어")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--api",     action="store_true", help="방법1: Django API 제어")
    group.add_argument("--browser", action="store_true", help="방법2: Playwright 브라우저 제어")
    group.add_argument("--native",  action="store_true", help="방법3: 네이티브 MAME HTTP Lua 서버")
    parser.add_argument("--game",   default="kof94",  help="게임 필터 (기본: kof94)")
    parser.add_argument("--headless", action="store_true", help="브라우저 headless 모드")
    args = parser.parse_args()

    if args.api:
        demo_django_api(args.game)
    elif args.browser:
        demo_browser_control(args.headless)
    elif args.native:
        demo_native_control()


if __name__ == "__main__":
    main()
