from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

def _no_window_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

def find_browser() -> Optional[Path]:
    names = ["msedge", "msedge.exe", "chrome", "chrome.exe", "google-chrome", "chromium", "chromium.exe"]
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    env = os.environ
    candidates = [
        Path(env.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(env.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(env.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(env.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(env.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.exists():
            return candidate
    return None



def _wait_for_pdf_output(output_path: Path, timeout_seconds: float = 12.0, minimum_size: int = 800) -> bool:
    """Aguarda o Edge/Chrome terminar de gravar o PDF.

    Em algumas versões do Edge o processo headless retorna código 0 antes de o
    arquivo ficar visível no disco. A RC6 verificava imediatamente e caía na
    prévia genérica mesmo quando a impressão ainda estava sendo finalizada.
    """
    output_path = Path(output_path)
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    stable_size = -1
    stable_hits = 0
    while time.monotonic() < deadline:
        try:
            if output_path.exists():
                size = output_path.stat().st_size
                if size >= int(minimum_size):
                    with output_path.open("rb") as stream:
                        valid_header = stream.read(5) == b"%PDF-"
                    if valid_header:
                        if size == stable_size:
                            stable_hits += 1
                        else:
                            stable_size = size
                            stable_hits = 0
                        if stable_hits >= 2:
                            return True
        except (OSError, PermissionError):
            pass
        time.sleep(0.15)
    try:
        return output_path.exists() and output_path.stat().st_size >= int(minimum_size) and output_path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False

def html_file_to_pdf(html_path: Path, output_path: Path, browser: Optional[Path] = None, timeout: int = 100) -> Path:
    browser = Path(browser) if browser else find_browser()
    if browser is None:
        raise RuntimeError("Microsoft Edge ou Google Chrome não foi localizado. Instale/ative um deles para gerar PDF confiável.")
    html_path = Path(html_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    profiles_root = Path(tempfile.gettempdir()) / "cte_browser_profiles"
    profiles_root.mkdir(parents=True, exist_ok=True)
    profile_dir = profiles_root / f"profile_{uuid.uuid4().hex}"
    profile_dir.mkdir(parents=True, exist_ok=True)

    process = None
    stderr = ""
    try:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=2200",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={output_path}",
            html_path.as_uri(),
        ]
        if os.name != "nt":
            command.insert(1, "--no-sandbox")
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=_no_window_flags(),
        )
        first_ready = _wait_for_pdf_output(output_path, timeout_seconds=8.0)
        if (process.returncode != 0 or not first_ready) and "--headless=new" in command:
            fallback_command = ["--headless" if item == "--headless=new" else item for item in command]
            process = subprocess.run(
                fallback_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                creationflags=_no_window_flags(),
            )
            _wait_for_pdf_output(output_path, timeout_seconds=12.0)
        stderr = process.stderr.decode("utf-8", errors="replace")[-1800:] if process else ""
    finally:
        for _ in range(10):
            try:
                shutil.rmtree(profile_dir, ignore_errors=False)
                break
            except Exception:
                time.sleep(0.25)
        shutil.rmtree(profile_dir, ignore_errors=True)

    pdf_ready = _wait_for_pdf_output(output_path, timeout_seconds=4.0)
    if process is None or process.returncode != 0 or not pdf_ready:
        raise RuntimeError(f"O navegador não conseguiu gerar o PDF (código {getattr(process, 'returncode', 'desconhecido')}).\n{stderr}")
    with output_path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise RuntimeError("O arquivo produzido não possui uma assinatura PDF válida.")
    return output_path

def html_text_to_pdf(document_html: str, output_path: Path, browser: Optional[Path] = None) -> Path:
    with tempfile.TemporaryDirectory(prefix="cte_html_pdf_") as tmp:
        html_path = Path(tmp) / "documento.html"
        html_path.write_text(document_html, encoding="utf-8")
        return html_file_to_pdf(html_path, output_path, browser=browser)

def validate_pdf_file(path: Path, minimum_size: int = 800) -> dict[str, object]:
    candidate = Path(path)
    if not candidate.exists():
        raise RuntimeError(f"PDF não encontrado: {candidate}")
    size = candidate.stat().st_size
    if size < int(minimum_size):
        raise RuntimeError(f"PDF incompleto: {size} bytes")
    with candidate.open("rb") as stream:
        header = stream.read(5)
    if header != b"%PDF-":
        raise RuntimeError("O arquivo não possui cabeçalho PDF válido.")
    data = candidate.read_bytes()
    pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    return {"path": str(candidate), "size": size, "header": "%PDF-", "pages_detected": max(0, pages)}
