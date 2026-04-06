## Bunyeok

Python SSR 기반의 아주 작은 PDF 번역 데모입니다.

- 화면: FastAPI + Jinja2 템플릿 렌더링
- 서버 작업: FastAPI BackgroundTasks
- 번역 체인: LangChain + OpenAI
- 입력: PDF 업로드
- 출력: 번역된 Markdown 다운로드
- 진행도: 작업 상태 polling

## 실행 방법

```bash
cp .env.example .env
uv sync
uv run uvicorn bunyeok.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 열면 됩니다.

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
- `bunyeok/translator.py`: PDF 파싱 + LangChain 번역 체인
- `templates/index.html`: SSR 화면 템플릿
- `static/styles.css`: 스타일

## 참고

현재 작업 저장소는 인메모리 방식이라 서버 재시작 시 작업 상태가 사라집니다. 실제 운영용이면 Redis나 DB 기반 큐로 바꾸는 편이 좋습니다.

## 검증

```bash
uv run python -m compileall bunyeok
```
