"""
kof94 웹 MAME Python 입력 제어
================================
Playwright로 브라우저를 열고, 게임 내 dispatchVirtualKey() 함수를
직접 호출해 레버/버튼 입력을 주입합니다.

설치:
  pip install playwright
  playwright install chromium

사용 예:
  python tools/kof94_input.py                 # 대화형 콘솔
  python tools/kof94_input.py --demo          # 자동 데모 (코인→스타트→이동)
  python tools/kof94_input.py --headless      # 화면 없이 실행
"""

import argparse
import time
from pathlib import Path

DJANGO_BASE = "http://127.0.0.1:8001"

# ── kof94 키코드 맵 ────────────────────────────────────────
# app.js TOUCH_CONTROL_PROFILES["kof94"] 와 VIRTUAL_KEY_CODE_BY_CODE 에서 추출
KOF94_KEYS = {
    # 레버
    "up":    "ArrowUp",
    "down":  "ArrowDown",
    "left":  "ArrowLeft",
    "right": "ArrowRight",
    # 대각선 (동시 입력)
    "ul":    ("ArrowUp",   "ArrowLeft"),
    "ur":    ("ArrowUp",   "ArrowRight"),
    "dl":    ("ArrowDown", "ArrowLeft"),
    "dr":    ("ArrowDown", "ArrowRight"),
    # 4버튼 (VIRTUAL_KEY_CODE_BY_CODE 에 있는 코드만 동작)
    "A":     "ControlLeft",   # 약펀치
    "B":     "AltLeft",       # 약킥
    "C":     "Space",         # 강펀치
    "D":     "ShiftLeft",     # 강킥
    # 시스템 — MAME 기본: 5=코인, 1=1P스타트
    "coin":  "Digit5",
    "start": "Digit1",
}

# ── 필살기 커맨드 단축키 (프레임 타이밍 예시) ───────────────
SPECIAL_MOVES = {
    # 이오리 야가미 기본기 커맨드 (근사치)
    "iori_rekka":   [("down",), ("dr",), ("right",), ("A",)],     # 236+A
    "iori_dp":      [("right",), ("down",), ("dr",), ("A",)],      # 623+A
    # 쿠사나기 쿄
    "kyo_rekka":    [("down",), ("dr",), ("right",), ("A",)],
    # 공통
    "qcf":          [("down",), ("dr",), ("right",)],              # 236
    "qcb":          [("down",), ("dl",), ("left",)],               # 214
    "dp":           [("right",), ("down",), ("dr",)],              # 623
}


def launch_kof94(page, timeout_sec: int = 60) -> bool:
    """
    1. '게임 목록 불러오기' 클릭
    2. kof94 '실행' 버튼 클릭
    3. emulatorState.started === true 될 때까지 대기
    반환: 성공 여부
    """
    print("[1단계] 게임 목록 불러오기...")
    page.click("#load-games")
    # 게임 목록 <li> 가 렌더링될 때까지 대기
    page.wait_for_selector("#games li", timeout=10_000)

    # kof94 항목 찾기 — 제목 또는 텍스트에 kof94 포함
    items = page.query_selector_all("#games li")
    launch_btn = None
    for item in items:
        text = item.inner_text().lower()
        if "kof94" in text or "king of fighters" in text:
            # 각 li 안의 두 번째 버튼이 "실행"
            btns = item.query_selector_all("button")
            for btn in btns:
                if btn.inner_text().strip() in ("실행", "Launch", "Run"):
                    launch_btn = btn
                    break
            if not launch_btn and btns:
                # 마지막 버튼 = 실행 버튼
                launch_btn = btns[-1]
            break

    if not launch_btn:
        print("[오류] kof94 실행 버튼을 찾을 수 없습니다.")
        print("  게임 목록:", [i.query_selector("strong").inner_text() for i in items])
        return False

    print(f"[2단계] kof94 실행 버튼 클릭...")
    launch_btn.click()

    # emulatorState.started === true 될 때까지 폴링
    print(f"[3단계] MAME wasm 부팅 대기 (최대 {timeout_sec}초)...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        status_text = page.evaluate(
            "() => document.getElementById('emulator-status').textContent"
        )
        # "실행 중" 텍스트가 나오면 부팅 완료
        # (emulatorState는 const라 window.emulatorState로 접근 불가)
        if "실행 중" in status_text:
            print(f"[완료] MAME 부팅 완료 — {status_text}")
            return True
        # 에러 메시지 확인
        err = page.evaluate(
            "() => { const el = document.getElementById('error-summary'); "
            "return el && !el.hidden ? el.textContent : null; }"
        )
        if err:
            print(f"[오류] 에뮬레이터 에러: {err}")
            return False
        time.sleep(1)
        print(f"  ... {status_text}")

    print("[타임아웃] MAME가 시작되지 않았습니다.")
    return False


class KOF94Controller:
    """
    Playwright 페이지를 통해 kof94 웹 MAME에 입력을 주입.

    핵심 원리:
      page.evaluate("dispatchVirtualKey(code, true/false)")
      → app.js 가 canvas 에 keydown/keyup 이벤트를 전달
      → MAME wasm 이 해당 키를 읽어 게임 내 입력으로 처리
    """

    def __init__(self, page, frame_ms: int = 16):
        """
        page      : Playwright Page 객체
        frame_ms  : 1프레임 = ~16ms (60fps 기준)
        """
        self.page = page
        self.frame_ms = frame_ms  # 버튼 유지 최소 단위

    # ── 저수준 API ──────────────────────────────────────────

    def _key_down(self, code: str):
        """키 누름 (app.js 의 dispatchVirtualKey 직접 호출)."""
        self.page.evaluate(f"dispatchVirtualKey('{code}', true)")

    def _key_up(self, code: str):
        """키 뗌."""
        self.page.evaluate(f"dispatchVirtualKey('{code}', false)")

    def _release_all(self):
        """모든 키 해제 (안전 초기화)."""
        for code in set(KOF94_KEYS.values()):
            if isinstance(code, str):
                self._key_up(code)

    # ── 고수준 API ──────────────────────────────────────────

    def press(self, *buttons: str, frames: int = 6):
        """
        하나 이상의 버튼을 동시에 frames 프레임 동안 누름.

        press("right")              → 우 방향 6프레임
        press("down", "right")      → ↘ 대각선 6프레임
        press("right", "C")         → 우 + 강펀치 동시
        press("A", frames=2)        → A버튼 2프레임
        """
        codes = []
        for btn in buttons:
            key = KOF94_KEYS.get(btn, btn)
            if isinstance(key, tuple):
                codes.extend(key)
            else:
                codes.append(key)

        for c in codes:
            self._key_down(c)
        time.sleep(self.frame_ms * frames / 1000)
        for c in codes:
            self._key_up(c)

    def tap(self, *buttons: str):
        """최소 입력 (2프레임) — 빠른 버튼 연타용."""
        self.press(*buttons, frames=2)

    def hold(self, *buttons: str):
        """길게 누르기 (12프레임) — 차지 커맨드용."""
        self.press(*buttons, frames=12)

    def wait(self, frames: int = 6):
        """프레임 단위 대기."""
        time.sleep(self.frame_ms * frames / 1000)

    def coin(self):
        """코인 투입."""
        self.press("coin", frames=3)
        self.wait(30)  # 코인 처리 대기

    def start(self):
        """1P 스타트."""
        self.press("start", frames=3)
        self.wait(10)

    # ── 커맨드 헬퍼 ─────────────────────────────────────────

    def motion(self, *steps: str, step_frames: int = 4):
        """
        레버 커맨드 순서 입력 (각 스텝 사이 자동 릴리스).

        motion("down", "dr", "right")  → 236 커맨드
        motion("right", "down", "dr") → 623 커맨드
        """
        for step in steps:
            self.press(step, frames=step_frames)
            self.wait(1)  # 스텝 간 1프레임 간격

    def qcf(self, button: str = "A"):
        """↓↘→ + 버튼 (236 커맨드)."""
        self.motion("down", "dr", "right")
        self.press(button, frames=3)

    def qcb(self, button: str = "A"):
        """↓↙← + 버튼 (214 커맨드)."""
        self.motion("down", "dl", "left")
        self.press(button, frames=3)

    def dp(self, button: str = "A"):
        """→↓↘ + 버튼 (623 커맨드, 승룡류)."""
        self.motion("right", "down", "dr")
        self.press(button, frames=3)

    def hcf(self, button: str = "A"):
        """←↙↓↘→ + 버튼 (41236 커맨드)."""
        self.motion("left", "dl", "down", "dr", "right")
        self.press(button, frames=3)

    def hcb(self, button: str = "A"):
        """→↘↓↙← + 버튼 (63214 커맨드)."""
        self.motion("right", "dr", "down", "dl", "left")
        self.press(button, frames=3)

    # ── 스크린샷 ────────────────────────────────────────────

    def screenshot(self, path: str = "kof94_screen.png") -> Path:
        """현재 화면 스크린샷."""
        self.page.screenshot(path=path)
        print(f"[스크린샷] {path}")
        return Path(path)

    def capture_canvas(self, path: str = "kof94_canvas.png") -> Path | None:
        """
        캔버스 영역만 잘라서 PNG로 저장.
        WebGL 캔버스는 toDataURL()이 검정 반환(preserveDrawingBuffer=false)이므로
        page.screenshot()으로 전체 캡처 후 캔버스 영역만 crop.
        """
        canvas_rect = self.page.evaluate("""() => {
            const c = document.querySelector('canvas');
            if (!c) return null;
            const r = c.getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }""")
        if not canvas_rect or canvas_rect['width'] == 0:
            # 캔버스 크기 0이면 전체 페이지 캡처
            self.page.screenshot(path=path)
            print(f"[스크린샷] {path}")
            return Path(path)
        self.page.screenshot(
            path=path,
            clip={
                "x":      canvas_rect["x"],
                "y":      canvas_rect["y"],
                "width":  canvas_rect["width"],
                "height": canvas_rect["height"],
            }
        )
        print(f"[캔버스] {path}")
        return Path(path)


# ── 대화형 콘솔 ──────────────────────────────────────────────

CONSOLE_HELP = """
=== kof94 입력 콘솔 ===
레버:   up / down / left / right / ul / ur / dl / dr
버튼:   A  / B    / C    / D
시스템: coin / start
커맨드: qcf [A/B/C/D]   qcb [A/B/C/D]   dp [A/B/C/D]
        hcf [A/B/C/D]   hcb [A/B/C/D]
연사:   spam A 10        → A버튼 10회 연타
연속:   seq right right down dr right C  → 순서 입력
스크린샷: ss [파일명]
대기:   wait [프레임수]
종료:   q / quit
"""

def interactive_console(ctrl: KOF94Controller):
    print(CONSOLE_HELP)
    out_dir = Path("tools/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_count = 0

    while True:
        try:
            line = input("kof94> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료")
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()

        try:
            if cmd in ("q", "quit", "exit"):
                break
            elif cmd == "coin":
                ctrl.coin()
                print("코인 투입")
            elif cmd == "start":
                ctrl.start()
                print("스타트")
            elif cmd in KOF94_KEYS:
                frames = int(parts[1]) if len(parts) > 1 else 6
                ctrl.press(cmd, frames=frames)
                print(f"{cmd} ({frames}f)")
            elif cmd == "qcf":
                btn = parts[1] if len(parts) > 1 else "A"
                ctrl.qcf(btn)
                print(f"236+{btn}")
            elif cmd == "qcb":
                btn = parts[1] if len(parts) > 1 else "A"
                ctrl.qcb(btn)
                print(f"214+{btn}")
            elif cmd == "dp":
                btn = parts[1] if len(parts) > 1 else "A"
                ctrl.dp(btn)
                print(f"623+{btn}")
            elif cmd == "hcf":
                btn = parts[1] if len(parts) > 1 else "A"
                ctrl.hcf(btn)
                print(f"41236+{btn}")
            elif cmd == "hcb":
                btn = parts[1] if len(parts) > 1 else "A"
                ctrl.hcb(btn)
                print(f"63214+{btn}")
            elif cmd == "spam":
                btn = parts[1] if len(parts) > 1 else "A"
                count = int(parts[2]) if len(parts) > 2 else 5
                for _ in range(count):
                    ctrl.tap(btn)
                    ctrl.wait(4)
                print(f"{btn} × {count}")
            elif cmd == "seq":
                # seq right right down dr right C  → 순서대로 tap
                for step in parts[1:]:
                    ctrl.tap(step)
                    ctrl.wait(2)
                print(f"seq: {' '.join(parts[1:])}")
            elif cmd == "wait":
                f = int(parts[1]) if len(parts) > 1 else 30
                ctrl.wait(f)
                print(f"{f}프레임 대기")
            elif cmd == "ss":
                fname = parts[1] if len(parts) > 1 else f"ss_{shot_count:03d}.png"
                shot_count += 1
                ctrl.capture_canvas(str(out_dir / fname))
            else:
                print(f"알 수 없는 명령: {cmd}  (h로 도움말)")
        except Exception as e:
            print(f"[오류] {e}")


# ── 자동 데모 ────────────────────────────────────────────────

def run_demo(ctrl: KOF94Controller):
    out = Path("tools/screenshots")
    out.mkdir(parents=True, exist_ok=True)

    # ── 게임 실행 + 부팅 대기 ─────────────────────────────
    if not launch_kof94(ctrl.page, timeout_sec=60):
        print("[중단] 게임 실행 실패")
        return

    print("1) 타이틀 화면 대기 (Neo Geo 부팅 ~ 20초)...")
    # onRuntimeInitialized 이후에도 Neo Geo BIOS 부팅 + ROM 로드에 시간 필요
    ctrl.wait(1200)                             # 20초
    ctrl.capture_canvas(str(out / "00_title.png"))

    ctrl.capture_canvas(str(out / "00_title.png"))

    print("2) 코인 투입")
    ctrl.coin()
    ctrl.wait(240)                              # 4초 대기 (코인 투입 연출)
    ctrl.capture_canvas(str(out / "01_after_coin.png"))

    print("3) 1P 스타트")
    ctrl.start()
    ctrl.wait(480)                              # 8초 (팀 선택/캐릭터 선택 화면)
    ctrl.capture_canvas(str(out / "02_char_select.png"))

    print("4) 캐릭터 선택 (우→하→A)")
    ctrl.press("right")
    ctrl.wait(15)
    ctrl.press("down")
    ctrl.wait(15)
    ctrl.press("A")
    ctrl.wait(480)                              # 8초 (선택 확정 + 전환 연출)
    ctrl.capture_canvas(str(out / "03_after_select.png"))

    print("5) 이동 테스트")
    ctrl.press("right", frames=30)
    ctrl.wait(10)
    ctrl.press("left",  frames=30)
    ctrl.wait(10)
    ctrl.capture_canvas(str(out / "04_moving.png"))

    print("6) 기본기 연타 (A × 5)")
    for _ in range(5):
        ctrl.tap("A")
        ctrl.wait(10)

    print("7) 필살기 커맨드 (236+A)")
    ctrl.qcf("A")
    ctrl.wait(90)
    ctrl.capture_canvas(str(out / "05_special.png"))

    print("데모 완료 — screenshots: tools/screenshots/")


# ── 진입점 ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="kof94 웹 MAME 입력 제어")
    parser.add_argument("--demo",     action="store_true", help="자동 데모 실행")
    parser.add_argument("--headless", action="store_true", help="화면 없이 실행")
    parser.add_argument("--url",      default=DJANGO_BASE, help="Django 서버 URL")
    parser.add_argument("--diag",     action="store_true", help="진단 정보만 출력")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "playwright 가 필요합니다:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    print(f"[연결] {args.url}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=args.headless,
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        page = ctx.new_page()
        page.goto(args.url, wait_until="networkidle")
        print("[로딩] 완료")

        ctrl = KOF94Controller(page, frame_ms=16)

        if args.diag:
            # 현재 페이지 상태 진단
            status = page.evaluate("() => document.getElementById('emulator-status').textContent")
            started = page.evaluate("() => typeof emulatorState !== 'undefined' ? emulatorState.started : 'N/A'")
            booting = page.evaluate("() => typeof emulatorState !== 'undefined' ? emulatorState.booting : 'N/A'")
            canvas = page.evaluate("() => !!document.querySelector('canvas')")
            disp_fn = page.evaluate("() => typeof dispatchVirtualKey")
            print(f"  emulator-status : {status}")
            print(f"  started         : {started}")
            print(f"  booting         : {booting}")
            print(f"  canvas 존재     : {canvas}")
            print(f"  dispatchVirtualKey 함수 타입: {disp_fn}")
        elif args.demo:
            run_demo(ctrl)
        else:
            # 대화형 모드: 먼저 게임 실행
            if launch_kof94(page, timeout_sec=60):
                interactive_console(ctrl)
            else:
                print("게임 실행에 실패했습니다. 브라우저를 수동으로 확인하세요.")

        input("Enter를 누르면 브라우저를 닫습니다...")
        browser.close()


if __name__ == "__main__":
    main()
