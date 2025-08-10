# KOSPI 공시·뉴스 와처 — Starter Kit

이 저장소는 GPTs의 Custom Action과 연동되는 **미니 백엔드(FastAPI)** 예제입니다.
- `/updates`: DART(코스피)와 네이버 뉴스 검색을 조회해 정규화하여 반환
- GPTs 에디터에서 `openapi.yaml`을 Import하면 바로 액션으로 연결할 수 있습니다.

## 빠른 시작

### 1) 환경변수 준비
```bash
cp .env.example .env
# .env 열어서 API_KEY, DART_API_KEY, NAVER_CLIENT_ID/SECRET 입력
```

### 2) 로컬 실행
```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

헬스체크: `GET http://localhost:8000/healthz` → `{"ok": true}`

### 3) Docker 실행
```bash
docker build -t kospi-bot:latest .
docker run -p 8000:8000 --env-file .env kospi-bot:latest
```

### 4) 테스트
```bash
curl -H "X-API-Key: <API_KEY>"   "http://localhost:8000/updates?limit=20&since=2025-08-10T05:00:00Z&market=KOSPI"
```

## GPTs와 연동

1. `openapi.yaml`의 `servers.url`을 실제 배포 URL로 바꾼 뒤, GPTs 에디터 **Configure → Custom Actions → Import**에 붙입니다.
2. 인증: **API Key(Header)**, 헤더 이름 `X-API-Key`, 값은 `.env`의 `API_KEY`.
3. **Instructions**: `gpts_instructions_ko.txt` 파일 내용을 **Configure → Instructions**에 복붙합니다.
4. **Prompt Starters**(예시):
   - 지금 코스피 전체 업데이트 요약(최근 1시간)
   - 삼성전자(005930), SK하이닉스(000660)만 보여줘
   - 유증/CB/IR 관련 공시만
   - 뉴스는 제외하고 공시만
   - 상위 10건만

## 주의사항
- 이 코드는 학습용 최소 예시입니다. 운영 환경에서는 다음을 보강하세요.
  - 페이지네이션/재시도/백오프, DART 오류 코드 처리
  - 뉴스 회사명→심볼 매핑 사전
  - Redis/DB 기반 중복제거 및 레이트리밋
  - 로깅/모니터링
