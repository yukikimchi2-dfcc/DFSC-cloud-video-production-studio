"""Environment audit: what exists, what works, what is blocked. Re-run any time with `studio audit`."""
from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from .config import REPO_ROOT

# status vocabulary used in SETUP_AUDIT.md
EXISTS, REUSE, UPGRADE, RECONFIGURE, MISSING, NO_ACCESS = (
    "已存在", "可以继续使用", "需要升级", "需要重新配置", "尚未安装", "无法访问")

HOSTS = {
    "github.com": "https://github.com",
    "pypi.org": "https://pypi.org/simple/",
    "www.googleapis.com (Drive API)": "https://www.googleapis.com/drive/v3/about",
    "drive.google.com": "https://drive.google.com",
    "huggingface.co (Whisper weights)": "https://huggingface.co",
    "api.runpod.io": "https://api.runpod.io/graphql",
    "app.notion.com": "https://app.notion.com",
    "www.facebook.com": "https://www.facebook.com",
}


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def _http(url: str) -> str:
    try:
        p = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-m", "12", "-w", "%{http_code}", url],
                           capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"unreachable ({e})"
    code = p.stdout.strip()
    if code.isdigit() and code != "000":
        return f"reachable (HTTP {code})"
    if "CONNECT tunnel failed, response 403" in p.stderr:
        return "blocked by network policy"
    return f"unreachable ({p.stderr.strip()[-80:]})"


def _pkg(name: str) -> str | None:
    try:
        mod = importlib.import_module(name)
        return getattr(mod, "__version__", "installed")
    except Exception:  # noqa: BLE001
        return None


def run_audit(check_network: bool = True) -> dict:
    a: dict = {"platform": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
               "cpus": os.cpu_count()}
    try:
        mem_kb = int(next(l for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal")).split()[1])
        a["memory_gb"] = round(mem_kb / 1e6, 1)
    except (OSError, StopIteration):
        a["memory_gb"] = None
    a["cloud_session"] = {
        "claude_code_remote": bool(os.environ.get("CLAUDE_CODE_REMOTE") or os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")),
        "codespaces": bool(os.environ.get("CODESPACES")),
        "ci": bool(os.environ.get("CI")),
        "container": Path("/.dockerenv").exists() or Path("/run/.containerenv").exists(),
        "persistent": False,  # Claude Code cloud containers are ephemeral; git + Drive are the persistence layer
    }
    tools = {}
    for tool, args in {"ffmpeg": ["-version"], "ffprobe": ["-version"], "docker": ["--version"], "git": ["--version"],
                       "node": ["--version"], "gcloud": ["--version"], "nvidia-smi": ["-L"]}.items():
        path = shutil.which(tool)
        tools[tool] = {"path": path, "version": _run([tool, *args])[1].splitlines()[0] if path else None}
    a["tools"] = tools
    a["gpu"] = tools["nvidia-smi"]["version"] or "none (CPU only)"
    a["python_packages"] = {n: _pkg(m) for n, m in {
        "numpy": "numpy", "opencv": "cv2", "pillow": "PIL", "scipy": "scipy", "pyyaml": "yaml",
        "pymupdf": "pymupdf", "faster-whisper": "faster_whisper", "pyloudnorm": "pyloudnorm",
        "soundfile": "soundfile", "google-api-python-client": "googleapiclient", "pytest": "pytest"}.items()}
    fonts = _run(["fc-list", ":lang=zh-tw", "family"])[1]
    a["fonts"] = {"cjk_traditional": "Noto Sans CJK TC" in fonts,
                  "emoji": Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf").exists(),
                  "apple_emoji": False}
    code, remote = _run(["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"])
    a["github"] = {"remote": remote if code == 0 else None,
                   "branch": _run(["git", "-C", str(REPO_ROOT), "branch", "--show-current"])[1]}
    a["credentials"] = {
        "google_drive": bool(os.environ.get("STUDIO_DRIVE_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                             or os.environ.get("STUDIO_DRIVE_TOKEN")),
        "gcloud_account": "credentialed" if "No credentialed" not in _run(["gcloud", "auth", "list"])[1] else None,
        "runpod_api_key": bool(os.environ.get("RUNPOD_API_KEY")),
        "anthropic_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "whisper_local_model": bool(os.environ.get("STUDIO_WHISPER_MODEL_DIR")),
    }
    if check_network:
        a["network"] = {name: _http(url) for name, url in HOSTS.items()}
    return a


def main() -> None:  # pragma: no cover
    print(json.dumps(run_audit(), ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
