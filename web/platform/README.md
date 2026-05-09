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

## 로컬 ROM으로 확인하기 (개발용)

1. `web/platform/roms/` 폴더를 만들고 ROM 파일(`.zip`, `.7z`, `.chd`, `.rom`)을 넣습니다.
2. 서버 실행 후 메인 페이지에서 **로컬 ROM 동기화** 버튼을 누릅니다.
3. 목록에 나타난 게임에서 **실행 준비 확인** 버튼을 누르면:
    - ROM 파일 접근 가능 여부
    - WASM 번들(`/static/wasm/mame.js`) 존재 여부
    를 로그에서 확인할 수 있습니다.
4. **실행** 버튼을 누르면:
   - ROM 파일을 브라우저 메모리 FS(`/roms`)로 로드
   - `mame.js` 코어 스크립트를 동적으로 로드
   - 캔버스에서 코어 초기화를 시작

> 참고: MVP 실행 흐름은 연결되었지만, 코어/ROM 조합별 옵션 튜닝(머신명, BIOS, 추가 아규먼트 등)은 개별 게임에 맞춰 추가 조정이 필요합니다.

## API 개요

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/games`
- `GET /api/saves` (로그인 필요)
- `POST /api/saves/upsert` (로그인 필요)
- `POST /api/highscores`
- `GET /api/leaderboard?game_id=<id>&limit=<n>`

## 다음 단계

- Emscripten 빌드 산출물(`.wasm`, JS glue) 실제 연동
- ROM 접근 정책(서명 URL/권한검사) 적용
- 세이브 blob 저장소(S3/MinIO 등)와 서버 검증
- 하이스코어 조작 방지(서명/서버 검증/재현 검증) 강화
