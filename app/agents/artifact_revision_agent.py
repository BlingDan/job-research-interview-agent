from __future__ import annotations

import concurrent.futures
import json
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from textwrap import dedent
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import JobResearchLLM
from app.schemas.agent_pilot import ArtifactKind


PatchOperation = Literal["insert", "append", "replace"]
PatchLocation = Literal[
    "first_line",
    "last_line",
    "before_title",
    "section",
    "page",
    "canvas",
    "unknown",
]


class ArtifactRevisionPatch(BaseModel):
    target_artifact: ArtifactKind
    operation: PatchOperation = "insert"
    location: PatchLocation = "unknown"
    content: str = ""
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: str = ""
    page_number: int | None = None
    section_title: str | None = None
    raw_instruction: str = ""


def build_artifact_revision_patch(
    instruction: str,
    target_artifact: ArtifactKind,
    *,
    now: Callable[[], datetime] | None = None,
) -> ArtifactRevisionPatch:
    text = _strip_revision_prefix(instruction)
    operation = _operation(text)
    content = _content(text, now=now or datetime.now)

    if target_artifact == "doc":
        location, section_title = _doc_location(text)
        needs_clarification = location == "unknown" or _generic_section_rewrite(text)
        return ArtifactRevisionPatch(
            target_artifact=target_artifact,
            operation=operation,
            location=location,
            content=content,
            confidence=0.86 if not needs_clarification else 0.35,
            needs_clarification=needs_clarification,
            clarification_question="请说明要修改文档的第一行、最后一行、文末或具体章节。",
            section_title=section_title,
            raw_instruction=instruction,
        )

    if target_artifact == "slides":
        page_number = _page_number(text)
        return ArtifactRevisionPatch(
            target_artifact=target_artifact,
            operation=operation,
            location="page" if page_number else "unknown",
            content=content,
            confidence=0.82 if page_number else 0.68,
            page_number=page_number,
            raw_instruction=instruction,
        )

    return ArtifactRevisionPatch(
        target_artifact=target_artifact,
        operation=operation,
        location="canvas",
        content=content,
        confidence=0.78,
        raw_instruction=instruction,
    )


def apply_doc_patch(content: str, patch: ArtifactRevisionPatch) -> str:
    _raise_if_clarification_needed(patch)
    insert_text = patch.content.strip()
    if not insert_text:
        return content

    if patch.operation == "replace" and patch.section_title:
        return _replace_doc_section(content, patch.section_title, insert_text)

    if patch.location == "first_line":
        return f"{insert_text}\n{content.lstrip()}"
    if patch.location == "before_title":
        return _insert_before_title(content, insert_text)
    if patch.location == "section" and patch.section_title:
        return _append_to_doc_section(content, patch.section_title, insert_text)
    if patch.location in {"last_line", "unknown"}:
        return f"{content.rstrip()}\n{insert_text}\n"

    return content


def apply_slides_patch(
    slides: list[dict[str, str]], patch: ArtifactRevisionPatch
) -> list[dict[str, str]]:
    _raise_if_clarification_needed(patch)
    updated = deepcopy(slides)
    if not updated:
        return updated

    index = _slide_index(updated, patch)
    if index is None:
        raise ValueError("无法定位要修改的 PPT 页面，请指定页码。")

    content = patch.content.strip()
    if not content:
        return updated

    body = str(updated[index].get("body") or "")
    if patch.operation == "replace":
        updated[index]["body"] = content
    elif content not in body:
        separator = "\n" if "\n" in body else "；"
        updated[index]["body"] = f"{body.rstrip()}{separator}本次修改：{content}".strip("；")
    return updated


def apply_canvas_patch(mermaid: str, patch: ArtifactRevisionPatch) -> str:
    _raise_if_clarification_needed(patch)
    content = _sanitize_mermaid_label(patch.content or patch.raw_instruction)
    if not content:
        return mermaid
    if content in mermaid:
        return mermaid

    base = mermaid.rstrip()
    connector = "    Brief --> RevisionNote" if "Brief" in mermaid else ""
    note = f'    RevisionNote["{content}"]'
    if connector:
        return f"{base}\n{note}\n{connector}\n"
    return f"{base}\n{note}\n"


def _strip_revision_prefix(instruction: str) -> str:
    text = instruction.strip()
    return re.sub(r"^\s*修改\s*[:：]\s*", "", text)


def _operation(text: str) -> PatchOperation:
    if any(keyword in text for keyword in ("替换", "改成", "修改为")):
        return "replace"
    if any(keyword in text for keyword in ("追加", "补充")):
        return "append"
    return "insert"


def _content(text: str, *, now: Callable[[], datetime]) -> str:
    if any(keyword in text for keyword in ("当前日期和时间", "现在的时间", "当前时间", "现在时间", "当前日期")):
        return now().strftime("%Y-%m-%d %H:%M")

    for keyword in ("添加", "增加", "插入", "追加", "补充", "改成", "修改为", "替换为", "突出", "强化"):
        if keyword in text:
            candidate = text.rsplit(keyword, 1)[-1]
            return _clean_content(candidate)
    return _clean_content(text)


def _clean_content(value: str) -> str:
    text = value.strip(" ：:，,。；;")
    text = re.sub(r"^(文档|PPT|ppt|幻灯片|画板|白板|中|里|的)+", "", text).strip(" ：:，,。；;")
    return text


def _doc_location(text: str) -> tuple[PatchLocation, str | None]:
    if any(keyword in text for keyword in ("第一行", "首行", "开头", "文首", "顶部")):
        return "first_line", None
    if "标题前" in text:
        return "before_title", None
    if any(keyword in text for keyword in ("最后一行", "末尾", "文末", "最后")):
        return "last_line", None
    section = _section_title(text)
    if section:
        return "section", section
    return "unknown", None


def _generic_section_rewrite(text: str) -> bool:
    if not any(keyword in text for keyword in ("章节", "小节", "部分")):
        return False
    return not any(
        keyword in text
        for keyword in ("添加", "增加", "插入", "追加", "补充", "替换", "改成", "修改为")
    )


def _section_title(text: str) -> str | None:
    match = re.search(r"([A-Za-z0-9\u4e00-\u9fff /-]{2,24})(?:章节|小节|部分)", text)
    if match:
        return match.group(1).strip(" 的在把")
    match = re.search(r"(?:第\s*\d+\s*[章节])", text)
    if match:
        return match.group(0)
    return None


def _page_number(text: str) -> int | None:
    match = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*[页頁]", text)
    if not match:
        return None
    return _parse_number(match.group(1))


def _parse_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + digits.get(value[1:], 0)
    if "十" in value:
        head, _, tail = value.partition("十")
        return digits.get(head, 0) * 10 + digits.get(tail, 0)
    return digits.get(value)


def _replace_doc_section(content: str, section_title: str, replacement: str) -> str:
    lines = content.splitlines()
    start = _find_section_header(lines, section_title)
    if start is None:
        raise ValueError(f"无法定位文档章节：{section_title}")
    end = _next_section_header(lines, start + 1)
    new_lines = lines[: start + 1] + ["", replacement, ""] + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"


def _append_to_doc_section(content: str, section_title: str, addition: str) -> str:
    lines = content.splitlines()
    start = _find_section_header(lines, section_title)
    if start is None:
        raise ValueError(f"无法定位文档章节：{section_title}")
    end = _next_section_header(lines, start + 1)
    new_lines = lines[:end] + ["", addition] + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"


def _insert_before_title(content: str, addition: str) -> str:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            new_lines = lines[:index] + [addition] + lines[index:]
            return "\n".join(new_lines).rstrip() + "\n"
    return f"{addition}\n{content.lstrip()}"


def _find_section_header(lines: list[str], section_title: str) -> int | None:
    normalized = _normalize(section_title)
    for index, line in enumerate(lines):
        if line.startswith("#") and normalized in _normalize(line):
            return index
    return None


def _next_section_header(lines: list[str], start: int) -> int:
    for index in range(start, len(lines)):
        if lines[index].startswith("#"):
            return index
    return len(lines)


def _slide_index(slides: list[dict[str, str]], patch: ArtifactRevisionPatch) -> int | None:
    if patch.page_number is not None:
        index = patch.page_number - 1
        return index if 0 <= index < len(slides) else None

    content = patch.content
    for keyword in ("工程实现", "多端", "协同", "飞书", "Agent", "架构", "fallback"):
        if keyword in content:
            for index, slide in enumerate(slides):
                haystack = f"{slide.get('title', '')}\n{slide.get('body', '')}"
                if keyword in haystack:
                    return index
    return len(slides) - 1


def _sanitize_mermaid_label(value: str) -> str:
    text = value.strip().replace("\n", "<br/>")
    return text.replace('"', "'").replace("[", "(").replace("]", ")")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _raise_if_clarification_needed(patch: ArtifactRevisionPatch) -> None:
    if patch.needs_clarification:
        raise ValueError(patch.clarification_question or "修改指令需要进一步澄清。")


# ---------------------------------------------------------------------------
# LLM-powered full-content rewrite
# ---------------------------------------------------------------------------

_MAX_INPUT_CHARS = 60000

_REVISION_DOC_PROMPT = dedent("""\
你是飞书文档编辑 Agent。用户对一份 Markdown 文档提出了修改意见。
你的任务是返回修改后的完整 Markdown 文档。

规则：
1. 输出的 Markdown 结构与输入保持一致（标题层级、列表、代码块等）
2. 只修改用户指定的部分，其他内容逐字保留
3. 不要添加任何解释、注释或说明文字
4. 如果用户要求在特定位置插入内容，准确定位并插入
5. 如果用户要求改写某段，保持该段的原有结构框架，只替换内容

返回格式（严格 JSON，不要 Markdown 代码块包裹）：
{"content": "修改后的完整 Markdown 文档", "change_summary": "一句话简述做了什么修改"}""")

_REVISION_SLIDES_PROMPT = dedent("""\
你是飞书演示文稿编辑 Agent。用户对一份 JSON 格式的幻灯片文件提出了修改意见。
你的任务是返回修改后的完整 JSON 幻灯片数组。

输入和输出格式：
[{"title": "页面标题", "body": "页面正文"}, ...]

规则：
1. 保持页面数量不变，除非用户明确要求添加或删除页面
2. 保持每页的 title 不变，除非用户要求改标题
3. body 字段按用户指令修改
4. 输出的 JSON 必须是合法的 JSON 数组，每个元素必须有 title 和 body 字段
5. 不要添加其他字段，不要包装在 Markdown 代码块中
6. 不要添加解释文字

返回格式（严格 JSON）：
{"content": [{"title": "...", "body": "..."}, ...], "change_summary": "一句话简述做了什么修改"}""")

_REVISION_CANVAS_PROMPT = dedent("""\
你是飞书画板（Mermaid 架构图）编辑 Agent。用户对一份 Mermaid 流程图提出了修改意见。
你的任务是返回修改后的完整 Mermaid 代码。

规则：
1. 保持原有的 graph/flowchart 声明和整体布局
2. 按用户指令添加、删除或修改节点和连线
3. 节点标签使用双引号包裹
4. 输出的 Mermaid 代码必须是合法的 Mermaid 语法
5. 不要包装在代码块中，不要添加解释文字

返回格式（严格 JSON）：
{"content": "修改后的完整 Mermaid 代码", "change_summary": "一句话简述做了什么修改"}""")

_REVISION_PROMPTS: dict[ArtifactKind, str] = {
    "doc": _REVISION_DOC_PROMPT,
    "slides": _REVISION_SLIDES_PROMPT,
    "canvas": _REVISION_CANVAS_PROMPT,
}


def _revision_timeout() -> float:
    return float(getattr(get_settings(), "agent_pilot_router_timeout_seconds", 15.0))


def build_llm_revision_content(
    instruction: str,
    current_content: str,
    artifact_kind: ArtifactKind,
    *,
    max_input_chars: int = _MAX_INPUT_CHARS,
) -> tuple[str, str]:
    if len(current_content) > max_input_chars:
        raise ValueError(f"内容过长（{len(current_content)} 字符），请指定具体要修改的段落或页面。")

    system_prompt = _REVISION_PROMPTS.get(artifact_kind, _REVISION_DOC_PROMPT)
    user_message = f"当前内容：\n{current_content}\n\n修改指令：{instruction}"

    llm = JobResearchLLM(temperature=0.3, max_tokens=8192)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    raw = _call_llm_with_timeout(llm, messages)
    content_str, change_summary = _parse_revision_llm_response(raw)
    validated = _validate_rewritten_content(content_str, artifact_kind)
    return validated, change_summary


def _call_llm_with_timeout(llm: JobResearchLLM, messages: list[dict[str, str]]) -> str:
    timeout = _revision_timeout()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(llm.invoke, messages)
        return future.result(timeout=timeout)


def _parse_revision_llm_response(raw: str) -> tuple[str, str]:
    data = _extract_json_object(raw)
    content = data.get("content")
    if isinstance(content, (list, dict)):
        content = json.dumps(content, ensure_ascii=False, indent=2)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM 返回的内容为空。")
    change_summary = str(data.get("change_summary") or "") or "已根据指令重写内容。"
    return content.strip(), change_summary.strip()


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            data = json.loads(fenced.group(1).strip())
        else:
            obj_match = re.search(r"({.*})", text, re.DOTALL)
            if not obj_match:
                raise ValueError("Failed to extract JSON from LLM revision response.")
            data = json.loads(obj_match.group(1))
    if not isinstance(data, dict):
        raise ValueError("LLM revision response must be a JSON object.")
    return data


def _validate_rewritten_content(content: str, kind: ArtifactKind) -> str:
    if kind == "doc":
        return _validate_doc_content(content)
    if kind == "slides":
        return _validate_slides_content(content)
    return _validate_canvas_content(content)


def _validate_doc_content(content: str) -> str:
    if not re.search(r"^#+\s", content, re.MULTILINE):
        raise ValueError("重写后的文档缺少标题结构。")
    return content


def _validate_slides_content(content: str) -> str:
    try:
        slides = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"重写后的幻灯片不是合法 JSON：{exc}") from exc
    if not isinstance(slides, list):
        raise ValueError("重写后的幻灯片必须是 JSON 数组。")
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            raise ValueError(f"幻灯片第 {index + 1} 页不是对象。")
        if not ("title" in slide or "body" in slide):
            raise ValueError(f"幻灯片第 {index + 1} 页缺少 title 或 body 字段。")
    return json.dumps(slides, ensure_ascii=False, indent=2)


def _validate_canvas_content(content: str) -> str:
    trimmed = content.strip()
    if not (trimmed.startswith("graph") or trimmed.startswith("flowchart")):
        raise ValueError("重写后的画板内容不是合法的 Mermaid 代码（需要以 graph 或 flowchart 开头）。")
    return trimmed
