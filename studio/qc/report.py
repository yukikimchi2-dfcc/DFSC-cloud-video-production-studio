"""QC report writers: Markdown (中文 + English) for reviewers, JSON for automation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .checks import FAIL, PASS, SKIP, WARN, QCReport

_ICON = {PASS: "✅", WARN: "⚠️", FAIL: "❌", SKIP: "⏭️"}


def to_markdown(report: QCReport) -> str:
    info = report.info
    verdict = "通過 PASSED" if report.passed else "未通過 FAILED"
    lines = [
        f"# 品質檢查報告 QC Report — {Path(report.path).name}",
        "",
        f"- 結果 Result: **{verdict}**",
        f"- 檔案 File: `{report.path}`",
        f"- 時間 Checked: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- 規格 Specs: {info.get('width')}x{info.get('height')} · {round(info.get('fps') or 0, 3)} fps · "
        f"{info.get('vcodec')}/{info.get('acodec')} · {round(info.get('duration') or 0, 2)} s · "
        f"{round((info.get('size_bytes') or 0) / 1e6, 2)} MB",
        "",
        "| 狀態 | 檢查項目 Check | 數值 Value | 標準 Expected | 說明 Notes |",
        "|---|---|---|---|---|",
    ]
    for c in report.checks:
        val = json.dumps(c.value, ensure_ascii=False) if not isinstance(c.value, str) else c.value
        exp = json.dumps(c.expected, ensure_ascii=False) if not isinstance(c.expected, str) else c.expected
        lines.append(f"| {_ICON.get(c.status, c.status)} {c.status} | {c.label_zh} {c.name} | {val if c.value is not None else ''} | "
                     f"{exp if c.expected is not None else ''} | {c.message} |")
    fails = [c for c in report.checks if c.status == FAIL]
    warns = [c for c in report.checks if c.status == WARN]
    lines += ["", "## 需要處理 Action items", ""]
    if not fails and not warns:
        lines.append("無。No action needed.")
    for c in fails:
        lines.append(f"- ❌ **{c.label_zh} {c.name}**: {c.message}")
    for c in warns:
        lines.append(f"- ⚠️ {c.label_zh} {c.name}: {c.message}（請人工確認 please confirm manually）")
    return "\n".join(lines) + "\n"


def write_report(report: QCReport, out_dir: str | Path, stem: str | None = None) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = stem or f"{Path(report.path).stem}_qc"
    md, js = out / f"{stem}.md", out / f"{stem}.json"
    md.write_text(to_markdown(report), encoding="utf-8")
    js.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return md, js
