"""Result builder: shapes step outputs by task type. Every payload also carries plain `sections` as a fallback."""
import json
import re

CODE_RE = re.compile(r"```([A-Za-z0-9_+\-]*)[ \t]*([^\n`]*)\n(.*?)```", re.S)
EXT = {"python": "py", "javascript": "js", "typescript": "ts", "html": "html", "css": "css", "bash": "sh", "sql": "sql", "json": "json"}
KIND = {"research": "research", "code": "code", "analysis": "analysis", "document": "document", "image": "image", "strategy": "document", "project": "project"}
GEN = {"reasoning", "writing", "long_context_documents", "code_generation"}


def split_blocks(text: str) -> tuple[str, list[dict], dict | None]:
    files, chart, n = [], None, 0

    def take(m):
        nonlocal chart, n
        lang, name, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        if lang == "json":
            try:
                j = json.loads(body)
                if isinstance(j, dict) and isinstance(j.get("labels"), list) and isinstance(j.get("values"), list):
                    chart = {"title": str(j.get("title", "")), "labels": [str(x) for x in j["labels"]],
                             "values": [float(x) for x in j["values"]][:len(j["labels"])]}
                    return ""
            except (ValueError, TypeError):
                pass
        n += 1
        ok = name and " " not in name and "." in name
        files.append({"path": name if ok else f"file{n}.{EXT.get(lang, 'txt')}", "language": lang or "text", "content": body.rstrip("\n")})
        return m.group(0)

    stripped = CODE_RE.sub(take, text)
    return stripped.strip(), files, chart


def build_result(task, subs) -> dict:
    outs = [(s, s.output or {}) for s in sorted(subs, key=lambda x: x.position) if s.capability != "validation" and s.output]
    sections, files, sources, images, chart, simulated = [], [], [], [], None, False
    for s, o in outs:
        text, f, c = split_blocks(o.get("text", ""))
        chart = chart or c
        if s.capability == "code_generation":
            files += f
        d = o.get("data") or {}
        for src in d.get("sources", []):
            if src.get("url") and all(src["url"] != x["url"] for x in sources):
                sources.append(src)
        images += d.get("images", [])
        simulated = simulated or bool(o.get("simulated"))
        sections.append({"label": o.get("label", s.capability), "capability": s.capability, "text": text})
    val = next((s.output.get("validation") for s in subs if s.capability == "validation" and s.output), None)
    if val is None:
        val = {"passed": None, "issues": [], "note": "This result was not independently checked."}
    gen = [x for x in sections if x["capability"] in GEN and x["text"]]
    main = gen[-1]["text"] if gen else (sections[-1]["text"] if sections else "")
    kind = KIND.get((task.plan or {}).get("task_type", ""), "document")
    p = {"kind": kind, "title": (task.plan or {}).get("title", task.objective[:70]), "simulated": simulated, "validation": val,
         "sections": sections, "markdown": main}
    if kind in ("research", "project"):
        p.update(sources=sources, findings=main)
    if kind in ("code", "project"):
        p["files"] = files
    if kind in ("analysis", "project"):
        p.update(chart=chart, insights=main)
    if kind in ("image", "project") or images:
        p["images"] = images
    return p
