from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

CONTEXT_PACKAGE = "wg_lux_mcp.context"


def _read(name: str) -> str:
    packaged = files(CONTEXT_PACKAGE).joinpath(name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")

    project_root = Path(__file__).resolve().parents[3]
    source_path = project_root / ("AGENT.md" if name == "AGENT.md" else f"context/{name}")
    return source_path.read_text(encoding="utf-8")


def _sections(name: str) -> list[dict[str, object]]:
    text = _read(name)
    lines = text.splitlines()
    headings = [index for index, line in enumerate(lines) if line.startswith("## ")]
    sections: list[dict[str, object]] = []
    for position, start in enumerate(headings):
        end = headings[position + 1] if position + 1 < len(headings) else len(lines)
        title = lines[start][3:].strip()
        body = "\n".join(lines[start + 1 : end]).strip()
        sections.append(
            {
                "title": title,
                "content": body,
                "source": {"path": f"context/{name}", "lines": [start + 1, end]},
            }
        )
    return sections


def get_agent_guidance() -> dict[str, object]:
    text = _read("AGENT.md")
    return {"guidance": text, "source": {"path": "AGENT.md", "lines": [1, len(text.splitlines())]}}


def search_project_context(query: str, max_results: int = 10) -> dict[str, object]:
    if not 1 <= max_results <= 30:
        raise ValueError("max_results must be between 1 and 30")
    terms = list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_-]{1,}", query.lower())))
    if not terms:
        raise ValueError("query must contain at least one searchable term")
    hits: list[dict[str, object]] = []
    for name in ("architecture.md", "decisions.md", "current-work.md", "references.md"):
        for section in _sections(name):
            haystack = f"{section['title']}\n{section['content']}".lower()
            score = sum(term in haystack for term in terms)
            if score:
                content = str(section["content"])
                hits.append(
                    {
                        "summary": content.split("\n\n", 1)[0][:500],
                        "title": section["title"],
                        "score": score,
                        "sources": [section["source"]],
                    }
                )

    def sort_key(hit: dict[str, object]) -> tuple[int, str]:
        score = hit.get("score")
        return (-(score if isinstance(score, int) else 0), str(hit.get("title", "")))

    hits.sort(key=sort_key)
    return {"query": query, "matches": hits[:max_results], "truncated": len(hits) > max_results}


def get_current_work() -> dict[str, object]:
    text = _read("current-work.md")
    goal_match = re.search(r"^Goal:\s*(.+)$", text, flags=re.MULTILINE)
    result: dict[str, object] = {"goal": goal_match.group(1) if goal_match else None}
    for section in _sections("current-work.md"):
        key = str(section["title"]).lower().replace(" ", "_")
        items = [line[2:] for line in str(section["content"]).splitlines() if line.startswith("- ")]
        result[key] = items
    result["blockers"] = result.get("open", [])
    result["source"] = {"path": "context/current-work.md", "lines": [1, len(text.splitlines())]}
    return result


def get_decision(decision_id: str) -> dict[str, object]:
    expected = decision_id.strip().upper()
    if not re.fullmatch(r"ADR-[0-9]{4}", expected):
        raise ValueError("decision_id must use the form ADR-0001")
    for section in _sections("decisions.md"):
        title = str(section["title"])
        if title.upper().startswith(f"{expected}:"):
            status = re.search(r"^Status:\s*(.+)$", str(section["content"]), re.MULTILINE)
            summary = re.search(
                r"^Summary:\s*(.+(?:\n(?!\n|[A-Z][a-z]+:).+)*)",
                str(section["content"]),
                re.MULTILINE,
            )
            return {
                "id": expected,
                "title": title.split(":", 1)[1].strip(),
                "status": status.group(1).strip() if status else None,
                "summary": " ".join(summary.group(1).splitlines()) if summary else None,
                "content": section["content"],
                "source": section["source"],
            }
    raise ValueError(f"Unknown decision {expected}")


def list_references() -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for section in _sections("references.md"):
        content = str(section["content"])
        title = str(section["title"])
        source = re.search(r"^Source:\s*(\S+)", content, re.MULTILINE)
        published = re.search(r"^Published:\s*(\S+)", content, re.MULTILINE)
        topics = re.search(r"^Topics:\s*(.+)$", content, re.MULTILINE)
        references.append(
            {
                "id": title.split(":", 1)[0],
                "title": title.split(":", 1)[1].strip() if ":" in title else title,
                "url": source.group(1) if source else None,
                "published": published.group(1) if published else None,
                "topics": [item.strip() for item in topics.group(1).split(",")] if topics else [],
                "source": section["source"],
            }
        )
    return references
