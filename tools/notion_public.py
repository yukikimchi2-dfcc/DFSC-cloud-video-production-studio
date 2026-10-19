#!/usr/bin/env python3
"""Export a *public* Notion page (shared to the web) to Markdown, without an API token.

Uses the same endpoint the Notion web client uses for public pages (www.notion.so/api/v3).
Private pages still need a Notion connector or an integration token (NOTION_TOKEN).

Usage:
  python tools/notion_public.py PAGE_URL_OR_ID OUT.md [--subpages]
app.notion.com links work too: only the 32-hex page id is used, fetched via www.notion.so.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

API = "https://www.notion.so/api/v3"


def page_id(s: str) -> str:
    m = re.search(r"([0-9a-f]{32})", s.replace("-", ""))
    if not m:
        raise ValueError(f"no Notion page id in {s!r}")
    h = m.group(1)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _value(rec: dict) -> dict:
    v = rec.get("value", {})
    return v.get("value", v)  # newer responses nest value twice


def load_page(pid: str) -> dict[str, dict]:
    blocks: dict[str, dict] = {}
    cursor = {"stack": []}
    for chunk in range(50):
        r = requests.post(f"{API}/loadPageChunk", timeout=60, json={
            "pageId": pid, "limit": 100, "cursor": cursor, "chunkNumber": chunk, "verticalColumns": False})
        r.raise_for_status()
        data = r.json()
        for bid, rec in data.get("recordMap", {}).get("block", {}).items():
            blocks[bid] = _value(rec)
        cursor = data.get("cursor", {})
        if not cursor.get("stack"):
            break
    return blocks


def schema_names(pid: str, blocks: dict) -> dict[str, str]:
    """Property-id -> name for a database row page (needs the parent collection schema)."""
    page = blocks.get(pid, {})
    if page.get("parent_table") != "collection":
        return {}
    r = requests.post(f"{API}/syncRecordValues", timeout=60, json={
        "requests": [{"pointer": {"table": "collection", "id": page["parent_id"]}, "version": -1}]})
    if r.status_code != 200:
        return {}
    coll = r.json().get("recordMap", {}).get("collection", {}).get(page["parent_id"], {})
    schema = _value(coll).get("schema", {})
    return {k: v.get("name", k) for k, v in schema.items()}


def rich(text) -> str:
    if not text:
        return ""
    out = []
    for seg in text:
        s = seg[0]
        for fmt in (seg[1] if len(seg) > 1 else []):
            if fmt[0] == "a":
                s = f"[{s}]({fmt[1]})"
            elif fmt[0] == "b":
                s = f"**{s}**"
        out.append(s)
    return "".join(out)


PREFIX = {"header": "# ", "sub_header": "## ", "sub_sub_header": "### ", "bulleted_list": "- ",
          "numbered_list": "1. ", "to_do": "- [ ] ", "quote": "> ", "callout": "> 💡 "}


def render(bid: str, blocks: dict, depth: int = 0, max_depth: int = 6, root: bool = True) -> list[str]:
    b = blocks.get(bid)
    if not b or depth > max_depth:
        return []
    t = b.get("type")
    title = rich(b.get("properties", {}).get("title"))
    lines = []
    if t in ("page", "collection_view_page") and not root:
        kind = "数据库" if t == "collection_view_page" else "子页面"
        lines.append(f"- 📄 **{title}**（{kind}，id {bid}）")
        return lines
    if t == "collection_view":
        return [f"- 🗃️ 内嵌数据库视图（collection {b.get('collection_id')}）"]
    if t in ("image", "video", "file", "pdf", "bookmark", "embed"):
        src = b.get("format", {}).get("display_source") or rich(b.get("properties", {}).get("source"))
        lines.append(f"[{t}] {title or ''} {src or ''}".strip())
    elif t == "code":
        lines += ["```", title, "```"]
    elif t == "divider":
        lines.append("---")
    elif t != "page" and title:
        lines.append(PREFIX.get(t, "") + title)
    for child in b.get("content", []):
        sub = render(child, blocks, depth + (1 if t not in ("page", "column_list", "column") else 0), max_depth,
                     root=False)
        indent = "  " if t in PREFIX and t not in ("header", "sub_header", "sub_sub_header") else ""
        lines += [indent + s for s in sub]
    return lines


def child_pages(url: str) -> list[tuple[str, str]]:
    pid = page_id(url)
    blocks = load_page(pid)
    return [(c, rich(blocks[c].get("properties", {}).get("title"))) for c in blocks.get(pid, {}).get("content", [])
            if blocks.get(c, {}).get("type") == "page"]


def export(url: str) -> str:
    pid = page_id(url)
    blocks = load_page(pid)
    if pid not in blocks:
        raise RuntimeError("page not returned — it is probably not public (Share → Publish to web)")
    page = blocks[pid]
    names = schema_names(pid, blocks)
    md = [f"# {rich(page.get('properties', {}).get('title')) or 'Untitled'}", "",
          f"> 来源：https://www.notion.so/{pid.replace('-', '')}（公开页面导出）", ""]
    props = {k: v for k, v in page.get("properties", {}).items() if k != "title"}
    if props:
        md += ["| 属性 | 内容 |", "|---|---|"]
        md += [f"| {names.get(k, k)} | {rich(v).replace('|', '/')} |" for k, v in props.items()]
        md.append("")
    md += render(pid, blocks)
    return "\n".join(md) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page")
    ap.add_argument("out")
    ap.add_argument("--subpages", action="store_true", help="also export direct child pages next to OUT")
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = export(a.page)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text)} chars)")
    if a.subpages:
        for cid, title in child_pages(a.page):
            sub = out.with_name(f"{out.stem}__{re.sub(r'[^0-9A-Za-z一-鿿]+', '_', title).strip('_')[:40]}.md")
            body = export(cid)
            sub.write_text(body, encoding="utf-8")
            print(f"wrote {sub} ({len(body)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
