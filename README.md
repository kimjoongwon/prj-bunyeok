## Bunyeok

Python SSR 기반의 아주 작은 PDF 번역 데모입니다.

- 화면: FastAPI + Jinja2 템플릿 렌더링
- 서버 작업: FastAPI BackgroundTasks
- 번역 체인: LangChain + OpenAI
- 인증 방식: 화면에 입력한 OpenAI API Key로 요청
- 입력: PDF 업로드
- 출력: 페이지별 Markdown 파일 저장 + 통합 Markdown 다운로드
- 진행도: 작업 상태 polling

## 실행 방법

```bash
cp .env.example .env
uv sync
uv run uvicorn bunyeok.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 열면 됩니다.

## 키 사용 방식

기본 동작은 화면에 입력한 OpenAI API Key로 해당 번역 요청을 보내는 방식입니다. 키는 서버 메모리나 파일에 저장하지 않고, 요청 처리 시에만 사용합니다.

서버에 `OPENAI_API_KEY`가 설정되어 있으면 화면에서 키를 비웠을 때 그 값을 fallback으로 사용할 수 있습니다.

## 환경 변수

```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

LLM 호출 없이 화면과 진행도를 먼저 확인하고 싶다면 아래처럼 mock 모드도 사용할 수 있습니다.

```bash
MOCK_TRANSLATION=true
```

## 파일 구성

- `bunyeok/main.py`: FastAPI 앱, SSR 화면, API 엔드포인트
- `bunyeok/job_store.py`: 데모용 인메모리 작업 저장소
- `bunyeok/translator.py`: PDF 페이지 단위 파싱 + 페이지별 LangChain 번역 + 파일 저장
- `templates/index.html`: SSR 화면 템플릿
- `static/styles.css`: 스타일

## 저장 결과

번역이 완료되면 프로젝트 루트의 `outputs/` 아래에 작업별 폴더가 생성됩니다.

- `page-001.md`, `page-002.md` ...: 페이지별 번역 결과
- `index.md`: 전체 페이지를 합친 통합본

## 참고

현재 작업 저장소는 인메모리 방식이라 서버 재시작 시 작업 상태가 사라집니다. 실제 운영용이면 Redis나 DB 기반 큐로 바꾸는 편이 좋습니다.

## 검증

```bash
uv run python -m compileall bunyeok
```
