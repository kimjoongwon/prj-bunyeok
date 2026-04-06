from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

from bunyeok.job_store import job_store, utcnow_iso

TRANSLATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a professional document translator. "
            "Translate the provided PDF excerpt into natural markdown in the requested target language. "
            "Preserve headings, lists, tables, code blocks, links, and numeric values when possible. "
            "Do not add commentary or explanations. Return markdown only.",
        ),
        (
            "human",
            "Target language: {target_language}\n\n"
            "Translate the following PDF excerpt into polished markdown:\n{content}",
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


def page_label(metadata: dict[str, object], index: int) -> str:
    page = metadata.get("page")

    if isinstance(page, int):
        return f"Page {page + 1}"

    return f"Chunk {index}"


def render_mock_translation(content: str, target_language: str) -> str:
    return "\n".join(
        [
            f"> Mock translation output for {target_language}",
            "",
            content,
        ]
    )


def run_translation_job(job_id: str, filename: str, file_bytes: bytes, target_language: str) -> None:
    temp_path: Path | None = None

    try:
        job_store.update(
            job_id,
            status="extracting",
            progress=5,
            message="PDF에서 텍스트를 추출하고 있습니다.",
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_path = Path(temp_file.name)

        pages = [page for page in PyPDFLoader(str(temp_path)).load() if page.page_content.strip()]

        if not pages:
            raise RuntimeError("PDF에서 번역할 텍스트를 찾지 못했습니다.")

        splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=180)
        chunks = splitter.split_documents(pages)

        if not chunks:
            raise RuntimeError("PDF 내용을 번역 가능한 청크로 나누지 못했습니다.")

        mock_mode = os.getenv("MOCK_TRANSLATION", "false").lower() == "true"

        if not mock_mode and not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY가 없어 번역을 실행할 수 없습니다.")

        chain = None

        if not mock_mode:
            chain = (
                TRANSLATION_PROMPT
                | ChatOpenAI(
                    model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    temperature=0.2,
                )
                | StrOutputParser()
            )

        job_store.update(
            job_id,
            status="translating",
            progress=12,
            message=f"{len(chunks)}개 청크를 순서대로 번역하고 있습니다.",
            source_page_count=len(pages),
            chunk_count=len(chunks),
        )

        translated_sections: list[str] = []

        for index, chunk in enumerate(chunks, start=1):
            translated_chunk = (
                render_mock_translation(chunk.page_content, target_language)
                if mock_mode
                else chain.invoke(
                    {
                        "target_language": target_language,
                        "content": chunk.page_content,
                    }
                )
            )

            if mock_mode:
                time.sleep(0.25)

            translated_sections.append(
                "\n".join(
                    [
                        f"## {page_label(chunk.metadata, index)}",
                        "",
                        translated_chunk.strip(),
                    ]
                )
            )

            job_store.update(
                job_id,
                progress=12 + round((index / len(chunks)) * 83),
                message=f"{index}/{len(chunks)} 청크 번역을 완료했습니다.",
            )

        translated_markdown = "\n".join(
            [
                f"# {filename} 번역본",
                "",
                f"- Target language: {target_language}",
                f"- Source pages: {len(pages)}",
                f"- Chunks: {len(chunks)}",
                f"- Generated at: {utcnow_iso()}",
                "",
                *translated_sections,
            ]
        )

        job_store.update(
            job_id,
            status="completed",
            progress=100,
            message="번역이 완료되었습니다. 마크다운 파일을 내려받을 수 있습니다.",
            completed_at=utcnow_iso(),
            translated_markdown=translated_markdown,
            download_filename=f"{normalize_stem(filename)}.{sanitize_language(target_language)}.md",
        )
    except Exception as error:  # noqa: BLE001
        job_store.fail(job_id, error)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
