from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from bunyeok.job_store import job_store, utcnow_iso

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"

TRANSLATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a professional document translator. "
            "Translate the provided PDF page into natural markdown in the requested target language. "
            "Preserve headings, lists, tables, code blocks, links, and numeric values when possible. "
            "Do not add commentary or explanations. Return markdown only.",
        ),
        (
            "human",
            "Target language: {target_language}\n\n"
            "Translate the following PDF page into polished markdown:\n{content}",
        ),
    ]
)


def normalize_stem(filename: str) -> str:
    stem = filename.removesuffix(".pdf").strip().lower()
    sanitized = "".join(char if char.isalnum() or char in "-_" else "-" for char in stem)
    return "-".join(part for part in sanitized.split("-") if part) or "translated-document"


def sanitize_language(language: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in "-_" else "-" for char in language.strip().lower())
    return "-".join(part for part in sanitized.split("-") if part) or "translated"


def resolve_page_number(metadata: dict[str, object], index: int) -> int:
    page = metadata.get("page")

    if isinstance(page, int):
        return page + 1

    return index


def render_mock_translation(content: str, target_language: str) -> str:
    return "\n".join(
        [
            f"> Mock translation output for {target_language}",
            "",
            content,
        ]
    )


def job_output_dir(filename: str, job_id: str, target_language: str) -> Path:
    folder_name = f"{normalize_stem(filename)}-{sanitize_language(target_language)}-{job_id[:8]}"
    return OUTPUTS_DIR / folder_name


def relative_to_project(path: Path) -> str:
    return path.relative_to(BASE_DIR).as_posix()


def render_page_markdown(
    filename: str,
    target_language: str,
    page_number: int,
    body: str,
) -> str:
    return "\n".join(
        [
            f"# {filename} - Page {page_number}",
            "",
            f"- Target language: {target_language}",
            f"- Source page: {page_number}",
            f"- Generated at: {utcnow_iso()}",
            "",
            body.strip(),
            "",
        ]
    )


def render_empty_page_markdown(
    filename: str,
    target_language: str,
    page_number: int,
) -> str:
    return "\n".join(
        [
            f"# {filename} - Page {page_number}",
            "",
            f"- Target language: {target_language}",
            f"- Source page: {page_number}",
            f"- Generated at: {utcnow_iso()}",
            "",
            "_No extractable text was found on this page._",
            "",
        ]
    )


def run_translation_job(
    job_id: str,
    filename: str,
    file_bytes: bytes,
    target_language: str,
    openai_api_key: str | None = None,
) -> None:
    temp_path: Path | None = None
    output_dir: Path | None = None

    try:
        job_store.update(
            job_id,
            status="extracting",
            progress=5,
            message="PDF에서 페이지별 텍스트를 추출하고 있습니다.",
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_path = Path(temp_file.name)

        pages = PyPDFLoader(str(temp_path)).load()

        if not pages:
            raise RuntimeError("PDF에서 번역할 텍스트를 찾지 못했습니다.")

        mock_mode = os.getenv("MOCK_TRANSLATION", "false").lower() == "true"
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

        if not mock_mode and not api_key:
            raise RuntimeError("OpenAI API 키가 없어 번역을 실행할 수 없습니다.")

        chain = None

        if not mock_mode:
            chain = (
                TRANSLATION_PROMPT
                | ChatOpenAI(
                    api_key=api_key,
                    model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    temperature=0.2,
                )
                | StrOutputParser()
            )

        output_dir = job_output_dir(filename, job_id, target_language)
        output_dir.mkdir(parents=True, exist_ok=True)

        job_store.update(
            job_id,
            status="translating",
            progress=12,
            message=f"{len(pages)}개 페이지를 순서대로 번역하고 폴더에 저장하고 있습니다.",
            source_page_count=len(pages),
            saved_page_count=0,
            output_dir=relative_to_project(output_dir),
            page_files=[],
        )

        translated_sections: list[str] = []
        page_files: list[str] = []

        for index, page in enumerate(pages, start=1):
            current_page_number = resolve_page_number(page.metadata, index)
            page_text = page.page_content.strip()

            if page_text:
                translated_text = (
                    render_mock_translation(page_text, target_language)
                    if mock_mode
                    else chain.invoke(
                        {
                            "target_language": target_language,
                            "content": page_text,
                        }
                    )
                )

                if mock_mode:
                    time.sleep(0.25)

                page_markdown = render_page_markdown(
                    filename=filename,
                    target_language=target_language,
                    page_number=current_page_number,
                    body=translated_text,
                )
            else:
                page_markdown = render_empty_page_markdown(
                    filename=filename,
                    target_language=target_language,
                    page_number=current_page_number,
                )

            page_file = output_dir / f"page-{current_page_number:03d}.md"
            page_file.write_text(page_markdown, encoding="utf-8")
            page_files.append(relative_to_project(page_file))
            translated_sections.append(page_markdown.strip())

            job_store.update(
                job_id,
                progress=12 + round((index / len(pages)) * 83),
                message=f"{index}/{len(pages)} 페이지 번역 및 저장을 완료했습니다.",
                saved_page_count=index,
                page_files=page_files.copy(),
            )

        translated_markdown = "\n\n".join(
            [
                "\n".join(
                    [
                        f"# {filename} 번역본",
                        "",
                        f"- Target language: {target_language}",
                        f"- Source pages: {len(pages)}",
                        f"- Output directory: {relative_to_project(output_dir)}",
                        f"- Generated at: {utcnow_iso()}",
                    ]
                ),
                *translated_sections,
            ]
        )

        index_file = output_dir / "index.md"
        index_file.write_text(translated_markdown, encoding="utf-8")

        job_store.update(
            job_id,
            status="completed",
            progress=100,
            message="페이지 단위 번역이 완료되었습니다. 폴더에 페이지별 Markdown 파일이 저장되었습니다.",
            completed_at=utcnow_iso(),
            translated_markdown=translated_markdown,
            download_filename=f"{normalize_stem(filename)}.{sanitize_language(target_language)}.md",
            saved_page_count=len(pages),
            page_files=page_files + [relative_to_project(index_file)],
        )
    except Exception as error:  # noqa: BLE001
        job_store.fail(job_id, error)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
