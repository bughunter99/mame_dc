# MAME Web Platform MVP

이 디렉터리는 MAME 코어와 별도로 웹 서비스 레이어를 구축하기 위한 최소 MVP 골격입니다.

## 구조

- `backend/` (Django)
  - 사용자 인증(등록/로그인/로그아웃)
  - 게임 메타데이터 및 ROM/WASM 전달 URL 관리
  - 세이브 상태(State) 메타데이터 저장 API
  - 하이스코어 제출/리더보드 API
- `frontend/` (JavaScript)
  - 게임 목록 조회
  - ROM/WASM 로딩 플로우 프로토타입
  - 백엔드 API 연동 시작점

## 빠른 시작

```bash
cd /home/runner/work/mame_dc/mame_dc/web/platform
python3 -m pip install -r requirements.txt
cd backend
python3 manage.py migrate
python3 manage.py loaddata arcade/fixtures/games.json
python3 manage.py runserver
```

브라우저에서 `http://127.0.0.1:8000/` 접속.

## WASM 코어 만들기

이 프로젝트는 `mame.js`와 `mame.wasm`를 저장소에 포함하지 않습니다. 먼저 MAME 루트에서 Emscripten으로 빌드한 뒤, 결과물을 웹 정적 폴더로 복사해야 합니다.

1. Emscripten 3.1.35 이상을 설치하고 `emsdk_env.bat`로 환경을 활성화합니다.
2. PowerShell에서 저장소 루트 기준으로 다음 스크립트를 실행합니다.

```powershell
cd D:\data3\mame_dc
Set-ExecutionPolicy -Scope Process Bypass
.\web\platform\scripts\build-wasm.ps1
```

3. 성공하면 다음 파일이 생성됩니다.
  - [web/platform/frontend/static/wasm/mame.js](web/platform/frontend/static/wasm/mame.js)
  - [web/platform/frontend/static/wasm/mame.wasm](web/platform/frontend/static/wasm/mame.wasm)

4. 그 다음 Django 서버를 재시작하고 웹 페이지에서 게임을 실행합니다.

기본값은 `SUBTARGET=sf2ce`, `SOURCES=src/mame/capcom/fcrash.cpp` 입니다. 다른 게임을 빌드하려면 스크립트 인자를 바꾸면 됩니다.

## 로컬 ROM으로 확인하기 (개발용)

1. `web/platform/roms/` 폴더를 만들고 ROM 파일(`.zip`, `.7z`, `.chd`, `.rom`)을 넣습니다.
2. 서버 실행 후 메인 페이지에서 **로컬 ROM 동기화** 버튼을 누릅니다.
3. 목록에 나타난 게임에서 **실행 준비 확인** 버튼을 누르면:
    - ROM 파일 접근 가능 여부
    - WASM 번들(`/static/wasm/mame.js`) 존재 여부
  - 로컬 zip ROM인 경우 marker 기반 머신 추정/누락 marker 목록
    를 로그에서 확인할 수 있습니다.
4. **실행** 버튼을 누르면:
   - ROM 파일을 브라우저 메모리 FS(`/roms`)로 로드
   - `mame.js` 코어 스크립트를 동적으로 로드
   - 캔버스에서 코어 초기화를 시작
5. 하단 **플레이 데이터** 패널에서:
  - `점수 저장` 버튼으로 현재 세션(`play_session_id`) 기준 하이스코어 저장
  - `세이브 업로드` 버튼으로 상태 파일을 서버 `/media/savestates/...`에 업로드
6. **리더보드** 패널에서 게임을 선택하면 서버 점수표를 즉시 확인할 수 있습니다.

> 참고: MVP 실행 흐름은 연결되었지만, 코어/ROM 조합별 옵션 튜닝(머신명, BIOS, 추가 아규먼트 등)은 개별 게임에 맞춰 추가 조정이 필요합니다.

## 모바일(스마트폰) 실행 팁

- 에뮬레이터 영역에 `전체화면` 버튼을 추가했습니다.
- 화면 하단에 터치 컨트롤(방향키/버튼/코인/스타트)이 표시됩니다.
  - 방향키: `Arrow` 계열
  - 기본 액션: `ControlLeft`, `AltLeft`, `Space`
  - `sf2ce`는 자동으로 6버튼 프리셋(LP/MP/HP/LK/MK/HK)으로 전환됩니다.
    - LP/MP/HP: `ControlLeft` / `AltLeft` / `Space`
    - LK/MK/HK: `ShiftLeft` / `KeyZ` / `KeyX`
  - 시스템: `Digit5`(코인), `Digit1`(스타트)
- 모바일 브라우저는 가로 모드가 더 안정적입니다.
- 터치 입력은 키보드 이벤트로 변환되어 기존 MAME 키 입력 경로를 그대로 사용합니다.

## sf2ce ROM 빠른 점검 스크립트

`sf2ce.zip`이 웹/모바일 테스트 가능한 상태인지 빠르게 확인하려면 다음 스크립트를 사용합니다.

```powershell
cd D:\data3\mame_dc
.\web\platform\scripts\check-rom-feasibility.ps1 -RomZipPath "web/platform/roms/sf2ce.zip" -Machine sf2ce
```

머신을 자동으로 선택하고 JSON 리포트를 남기려면:

```powershell
.\web\platform\scripts\check-rom-feasibility.ps1 \
  -RomZipPath "web/platform/roms/sf2ce.zip" \
  -AutoSelectMachine \
  -JsonOutputPath "web/platform/rom-report.json"
```

런타임 로그 파일이 있으면 함께 분석할 수 있습니다.

```powershell
.\web\platform\scripts\check-rom-feasibility.ps1 \
  -RomZipPath "web/platform/roms/sf2ce.zip" \
  -Machine sf2ce \
  -RuntimeLogPath "web/platform/frontend/static/wasm/runtime.log"
```

출력 항목:
- target 머신 기준 marker 파일 누락 여부
- 현재 zip이 sf2ce/sf2rb 중 어느 쪽에 더 가까운지 추정
- 로그에서 missing/bad 단서가 발견되면 파일명 목록 출력

주의:
- 게임별 기본 키맵이 다를 수 있어 버튼 매핑은 추후 게임별 프리셋으로 분리하는 것을 권장합니다.
- 실제 기동 성공 여부는 ROM 세트 CRC 정합성에 영향을 받습니다.

## API 개요

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/games`
- `GET /api/games/<id>/launch`
  - 응답 `launch.play_session_id`를 점수 제출 시 사용
- `GET /api/games/<id>/rom-diagnose`
  - 로컬 zip ROM 대상 marker 진단 결과(inferred_machine, likely_machine, missing_markers) 반환
- `GET /api/roms/download/<token>`
- `GET /api/saves` (로그인 필요)
- `POST /api/saves/upsert` (로그인 필요)
- `POST /api/saves/upload` (로그인 필요, multipart `state_file`)
- `POST /api/highscores` (`game_id`, `score`, `session_id`, `duration_ms` 필요)
- `GET /api/leaderboard?game_id=<id>&limit=<n>`

## 다음 단계

- Emscripten 빌드 산출물(`.wasm`, JS glue) 실제 연동
- ROM 접근 정책(서명 URL/권한검사) 적용
- 세이브 blob 저장소(S3/MinIO 등)와 서버 검증
- 하이스코어 조작 방지(서명/서버 검증/재현 검증) 강화
