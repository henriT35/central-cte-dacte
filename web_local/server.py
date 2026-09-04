# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import csv
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import socket
import sys
import threading
import time
import webbrowser
import zipfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

APP_VERSION = "RC27.14 WEB/WINDOWS MVP13 R12.13.10"
ENGINE_VERSION = "RC26.6"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
SESSION_COOKIE_NAME = "central_cte_session"

WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
VENDOR_ROOT = WEB_ROOT / "vendor"
for import_root in (VENDOR_ROOT, WEB_ROOT):
    if import_root.is_dir() and str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from security import AuthManager, AuthenticatedUser
from developer_tools import DeveloperTools
from services import OfficialDacteService, OfficialInvoiceEngineService, OfficialReportService, OfficialSignatureService, OfficialXmlEngineService, SswPostgresService

STATIC_ROOT = WEB_ROOT / "static"
GLOBAL_DATA_ROOT = Path(os.environ.get("CENTRAL_CTE_DATA_ROOT") or (WEB_ROOT / "data")).expanduser().resolve()
SECURITY_ROOT = GLOBAL_DATA_ROOT / "security"
WORKSPACES_ROOT = GLOBAL_DATA_ROOT / "workspaces"
BACKUP_ROOT = GLOBAL_DATA_ROOT / "backups"
GLOBAL_QA_ROOT = GLOBAL_DATA_ROOT / "qa"
GLOBAL_QA_PATH = GLOBAL_QA_ROOT / "qa_notes.json"
GLOBAL_QA_ATTACHMENT_ROOT = GLOBAL_QA_ROOT / "attachments"
MAX_QA_ATTACHMENT_BYTES = 6 * 1024 * 1024
GLOBAL_PARTNER_TABLE_ROOT = GLOBAL_DATA_ROOT / "partner_tables"
PUBLIC_DOMAIN = str(os.environ.get("CENTRAL_CTE_PUBLIC_DOMAIN") or "centraldacte.testeprojetosricky.com.br").strip().lower()
PUBLIC_URL = str(os.environ.get("CENTRAL_CTE_PUBLIC_URL") or (f"https://{PUBLIC_DOMAIN}" if PUBLIC_DOMAIN else "")).strip().rstrip("/")
MAX_BACKUP_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_BACKUP_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
MAX_BACKUP_FILES = 20_000

UPLOAD_EXTENSIONS = {
    "xml": {".xml"},
    "faturas": {".pdf"},
    "bases": {".sswweb"},
    "tabelas": {".xlsx"},
}
UPLOAD_LIMITS = {
    "xml": 20 * 1024 * 1024,
    "faturas": 100 * 1024 * 1024,
    "bases": 200 * 1024 * 1024,
    "tabelas": 30 * 1024 * 1024,
}

for directory in (
    STATIC_ROOT,
    GLOBAL_DATA_ROOT,
    SECURITY_ROOT,
    WORKSPACES_ROOT,
    BACKUP_ROOT,
    GLOBAL_QA_ROOT,
    GLOBAL_QA_ATTACHMENT_ROOT,
    GLOBAL_PARTNER_TABLE_ROOT,
):
    directory.mkdir(parents=True, exist_ok=True)

AUTH = AuthManager(SECURITY_ROOT)
DEVELOPER_TOOLS = DeveloperTools(PROJECT_ROOT, SECURITY_ROOT)
SSW_POSTGRES = SswPostgresService(GLOBAL_DATA_ROOT)


class WorkspaceContext:
    def __init__(
        self,
        *,
        user_id: str,
        root: Path,
        upload_root: Path,
        output_root: Path,
        state_root: Path,
        upload_categories: dict[str, Path],
        qa_path: Path,
        settings_path: Path,
        xml_service: OfficialXmlEngineService,
        invoice_service: OfficialInvoiceEngineService,
        report_service: OfficialReportService,
        dacte_service: OfficialDacteService,
        signature_service: OfficialSignatureService,
    ) -> None:
        self.user_id = user_id
        self.root = root
        self.upload_root = upload_root
        self.output_root = output_root
        self.state_root = state_root
        self.upload_categories = upload_categories
        self.qa_path = qa_path
        self.settings_path = settings_path
        self.xml_service = xml_service
        self.invoice_service = invoice_service
        self.report_service = report_service
        self.dacte_service = dacte_service
        self.signature_service = signature_service


WORKSPACE_LOCK = threading.RLock()
WORKSPACE_CACHE: dict[str, WorkspaceContext] = {}


def get_workspace(user_id: str = "local-default") -> WorkspaceContext:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(user_id or "local-default"))[:80] or "local-default"
    with WORKSPACE_LOCK:
        cached = WORKSPACE_CACHE.get(safe_id)
        if cached is not None:
            return cached
        root = (WORKSPACES_ROOT / safe_id).resolve()
        upload_root = root / "uploads"
        output_root = root / "outputs"
        state_root = root / "state"
        categories = {
            "xml": upload_root / "xml",
            "faturas": upload_root / "faturas",
            "bases": upload_root / "bases",
            "tabelas": upload_root / "tabelas",
        }
        for directory in (root, upload_root, output_root, state_root, *categories.values()):
            directory.mkdir(parents=True, exist_ok=True)
        xml_service = OfficialXmlEngineService(
            PROJECT_ROOT,
            upload_root,
            state_root,
            GLOBAL_PARTNER_TABLE_ROOT,
        )
        invoice_service = OfficialInvoiceEngineService(PROJECT_ROOT, upload_root, state_root)
        report_service = OfficialReportService(
            PROJECT_ROOT, upload_root, output_root, state_root, xml_service, invoice_service,
        )
        dacte_service = OfficialDacteService(PROJECT_ROOT, output_root, state_root, xml_service)
        signature_service = OfficialSignatureService(
            PROJECT_ROOT, root, state_root, xml_service, dacte_service,
        )
        context = WorkspaceContext(
            user_id=safe_id,
            root=root,
            upload_root=upload_root,
            output_root=output_root,
            state_root=state_root,
            upload_categories=categories,
            qa_path=GLOBAL_QA_PATH,
            settings_path=state_root / "settings.json",
            xml_service=xml_service,
            invoice_service=invoice_service,
            report_service=report_service,
            dacte_service=dacte_service,
            signature_service=signature_service,
        )
        # R12.13.6: mantém o consolidado comercial sincronizado com os arquivos
        # individuais de parceiros antes de qualquer workspace entrar em uso.
        # Isso elimina falsos "PARCEIRO SEM CADASTRO" quando um XLSX individual
        # existe, mas o cadastro_tabelas_parceiros_compilada.xlsx está defasado.
        DEVELOPER_TOOLS.ensure_partner_files(context)
        WORKSPACE_CACHE[safe_id] = context
        return context


# Contexto compatível com os testes de unidade e com o modo sem autenticação.
DEFAULT_WORKSPACE = get_workspace("local-default")
DATA_ROOT = DEFAULT_WORKSPACE.root
UPLOAD_ROOT = DEFAULT_WORKSPACE.upload_root
OUTPUT_ROOT = DEFAULT_WORKSPACE.output_root
STATE_ROOT = DEFAULT_WORKSPACE.state_root
UPLOAD_CATEGORIES = DEFAULT_WORKSPACE.upload_categories
QA_PATH = DEFAULT_WORKSPACE.qa_path
SETTINGS_PATH = DEFAULT_WORKSPACE.settings_path
XML_ENGINE_SERVICE = DEFAULT_WORKSPACE.xml_service
INVOICE_ENGINE_SERVICE = DEFAULT_WORKSPACE.invoice_service
REPORT_SERVICE = DEFAULT_WORKSPACE.report_service
DACTE_SERVICE = DEFAULT_WORKSPACE.dacte_service
SIGNATURE_SERVICE = DEFAULT_WORKSPACE.signature_service

JOB_LOCK = threading.RLock()
JOBS: dict[str, dict[str, Any]] = {}
ACTIVE_JOB_IDS: dict[str, dict[str, str]] = {"xml": {}, "invoices": {}, "dacte": {}, "signature": {}}
RECOVERED_WORKSPACES: set[str] = set()
ENGINE_EXECUTION_LOCK = threading.Lock()
ENGINE_STATE_LOCK = threading.RLock()
ENGINE_STATE: dict[str, Any] = {
    "active": False,
    "operation": "",
    "workspace_id": "",
    "job_id": "",
    "started_at": "",
    "waiting": 0,
}
SYSTEM_PROBE_LOCK = threading.RLock()
SYSTEM_PROBE_CACHE: dict[str, Any] = {"checked_at": 0.0, "data": {}}

DEFAULT_SETTINGS = {
    "theme": "claro",
    "density": "confortavel",
    "sidebar": "padrao",
    "start_page": "dashboard",
}

PROCESS_STARTED_AT = time.time()
METRICS_LOCK = threading.RLock()
METRICS: dict[str, Any] = {
    "requests_total": 0,
    "responses_by_status": {},
    "bytes_uploaded_total": 0,
    "login_success_total": 0,
    "login_failure_total": 0,
}


def metric_increment(name: str, amount: int = 1) -> None:
    with METRICS_LOCK:
        METRICS[name] = int(METRICS.get(name) or 0) + int(amount)


def metric_status(code: int) -> None:
    with METRICS_LOCK:
        statuses = METRICS.setdefault("responses_by_status", {})
        key = str(int(code))
        statuses[key] = int(statuses.get(key) or 0) + 1


def production_readiness() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for name, directory in {
        "data": GLOBAL_DATA_ROOT,
        "security": SECURITY_ROOT,
        "workspaces": WORKSPACES_ROOT,
        "backups": BACKUP_ROOT,
    }.items():
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / f".health_{uuid.uuid4().hex}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            checks[name] = {"ok": True, "path": str(directory)}
        except Exception as exc:
            checks[name] = {"ok": False, "path": str(directory), "error": str(exc)}
    try:
        usage = shutil.disk_usage(GLOBAL_DATA_ROOT)
        free_mb = round(usage.free / (1024 * 1024), 1)
        checks["disk"] = {"ok": usage.free >= 512 * 1024 * 1024, "free_mb": free_mb}
    except Exception as exc:
        checks["disk"] = {"ok": False, "error": str(exc)}
    engine_file = PROJECT_ROOT / "engine" / "central_cte_engine_1_1_36.py"
    checks["engine"] = {"ok": engine_file.is_file(), "path": str(engine_file)}
    ready = all(bool(item.get("ok")) for item in checks.values())
    return {
        "ready": ready,
        "version": APP_VERSION,
        "engine": ENGINE_VERSION,
        "uptime_seconds": int(max(0, time.time() - PROCESS_STARTED_AT)),
        "checks": checks,
    }


def prometheus_metrics() -> str:
    with METRICS_LOCK:
        snapshot = json.loads(json.dumps(METRICS))
    lines = [
        "# HELP central_cte_uptime_seconds Tempo de atividade do processo.",
        "# TYPE central_cte_uptime_seconds gauge",
        f"central_cte_uptime_seconds {int(max(0, time.time() - PROCESS_STARTED_AT))}",
        "# HELP central_cte_requests_total Requisições HTTP recebidas.",
        "# TYPE central_cte_requests_total counter",
        f"central_cte_requests_total {int(snapshot.get('requests_total') or 0)}",
        "# HELP central_cte_upload_bytes_total Bytes aceitos em uploads.",
        "# TYPE central_cte_upload_bytes_total counter",
        f"central_cte_upload_bytes_total {int(snapshot.get('bytes_uploaded_total') or 0)}",
        "# HELP central_cte_login_total Tentativas de login por resultado.",
        "# TYPE central_cte_login_total counter",
        f'central_cte_login_total{{resultado="sucesso"}} {int(snapshot.get("login_success_total") or 0)}',
        f'central_cte_login_total{{resultado="falha"}} {int(snapshot.get("login_failure_total") or 0)}',
        "# HELP central_cte_http_responses_total Respostas HTTP por código.",
        "# TYPE central_cte_http_responses_total counter",
    ]
    for code, count in sorted((snapshot.get("responses_by_status") or {}).items()):
        lines.append(f'central_cte_http_responses_total{{status="{code}"}} {int(count)}')
    with JOB_LOCK:
        active = sum(1 for job in JOBS.values() if job.get("state") in {"queued", "running"})
    lines.extend([
        "# HELP central_cte_active_jobs Processamentos em fila ou execução.",
        "# TYPE central_cte_active_jobs gauge",
        f"central_cte_active_jobs {active}",
        "",
    ])
    return "\n".join(lines)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


QA_MIGRATION_LOCK = threading.RLock()
QA_MIGRATION_DONE = False


def migrate_workspace_qa_notes() -> dict[str, Any]:
    """Consolida cadernos antigos sem ressuscitar ocorrências já apagadas."""
    global QA_MIGRATION_DONE
    with QA_MIGRATION_LOCK:
        if QA_MIGRATION_DONE:
            notes = read_json(GLOBAL_QA_PATH, [])
            return {"migrated": 0, "total": len(notes) if isinstance(notes, list) else 0}

        # IDs presentes em arquivos de limpeza/arquivo são tombstones. Isso
        # impede que qa_notes.json legado republique registros já removidos.
        tombstoned_ids: set[str] = set()
        last_clear = read_json(GLOBAL_QA_ROOT / "last_clear.json", {})
        if isinstance(last_clear, dict):
            tombstoned_ids.update(str(value) for value in last_clear.get("deleted_ids", []) if value)
        archive_root = GLOBAL_QA_ROOT / "archive"
        if archive_root.is_dir():
            for archive_path in archive_root.glob("qa_*.json"):
                archived_rows = read_json(archive_path, [])
                if isinstance(archived_rows, list):
                    tombstoned_ids.update(
                        str(item.get("id")) for item in archived_rows
                        if isinstance(item, dict) and item.get("id")
                    )

        existing = read_json(GLOBAL_QA_PATH, [])
        merged: dict[str, dict[str, Any]] = {}
        if isinstance(existing, list):
            for item in existing:
                if isinstance(item, dict) and item.get("id") and str(item.get("id")) not in tombstoned_ids:
                    merged[str(item["id"])] = item

        migrated = 0
        for path in WORKSPACES_ROOT.glob("*/state/qa_notes.json"):
            rows = read_json(path, [])
            if not isinstance(rows, list):
                continue
            for item in rows:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                key = str(item["id"])
                if key in tombstoned_ids:
                    continue
                current = merged.get(key)
                current_stamp = str((current or {}).get("updated_at") or (current or {}).get("created_at") or "")
                item_stamp = str(item.get("updated_at") or item.get("created_at") or "")
                if current is None or item_stamp >= current_stamp:
                    merged[key] = item
                migrated += 1
            if rows:
                archived = path.with_name("qa_notes_migrated_mvp13.json")
                if not archived.exists():
                    shutil.copy2(path, archived)
                # Após consolidar, a fonte antiga deve ficar vazia. Deixá-la
                # intacta fazia ocorrências apagadas voltarem no reinício.
                write_json_atomic(path, [])

        ordered = sorted(
            merged.values(),
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        write_json_atomic(GLOBAL_QA_PATH, ordered)
        write_json_atomic(
            GLOBAL_QA_ROOT / "migration_mvp13.json",
            {"migrated_rows": migrated, "tombstoned": len(tombstoned_ids), "total": len(ordered), "at": now_iso()},
        )
        QA_MIGRATION_DONE = True
        return {"migrated": migrated, "total": len(ordered)}


migrate_workspace_qa_notes()


def _workspace_jobs_path(context: WorkspaceContext) -> Path:
    return context.state_root / "jobs_journal.json"


def _job_is_terminal(state: Any) -> bool:
    return str(state or "").lower() in {"completed", "failed", "discarded", "interrupted"}


def _persist_workspace_jobs(context: WorkspaceContext) -> None:
    with JOB_LOCK:
        items = [dict(job) for job in JOBS.values() if str(job.get("workspace_id")) == context.user_id]
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    write_json_atomic(_workspace_jobs_path(context), {"version": 1, "updated_at": now_iso(), "jobs": items[:80]})


def ensure_job_recovery(context: WorkspaceContext) -> None:
    with JOB_LOCK:
        if context.user_id in RECOVERED_WORKSPACES:
            return
        RECOVERED_WORKSPACES.add(context.user_id)
        payload = read_json(_workspace_jobs_path(context), {})
        rows = payload.get("jobs") if isinstance(payload, dict) else []
        changed = False
        for raw in rows if isinstance(rows, list) else []:
            if not isinstance(raw, dict):
                continue
            job = dict(raw)
            job_id = str(job.get("id") or "").strip()
            if not job_id:
                continue
            state = str(job.get("state") or "").lower()
            if state in {"queued", "running"}:
                job.update({
                    "state": "interrupted",
                    "recoverable": True,
                    "message": "A execução foi interrompida pelo encerramento ou reinício do servidor.",
                    "error": "Processamento interrompido antes da conclusão.",
                    "finished_at": now_iso(),
                    "updated_at": now_iso(),
                })
                changed = True
            JOBS[job_id] = job
        if changed:
            write_json_atomic(_workspace_jobs_path(context), {"version": 1, "updated_at": now_iso(), "jobs": [dict(job) for job in JOBS.values() if str(job.get("workspace_id")) == context.user_id]})


def recoverable_jobs(context: WorkspaceContext) -> list[dict[str, Any]]:
    ensure_job_recovery(context)
    with JOB_LOCK:
        jobs = [
            dict(job)
            for job in JOBS.values()
            if str(job.get("workspace_id")) == context.user_id
            and (bool(job.get("recoverable")) or str(job.get("state")) in {"interrupted", "failed"})
            and str(job.get("state")) != "discarded"
        ]
    jobs.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return jobs[:20]


@contextlib.contextmanager
def engine_execution(operation: str, context: WorkspaceContext, job_id: str = ""):
    with ENGINE_STATE_LOCK:
        ENGINE_STATE["waiting"] = int(ENGINE_STATE.get("waiting") or 0) + 1
    acquired = ENGINE_EXECUTION_LOCK.acquire(timeout=15 * 60)
    with ENGINE_STATE_LOCK:
        ENGINE_STATE["waiting"] = max(0, int(ENGINE_STATE.get("waiting") or 1) - 1)
    if not acquired:
        raise RuntimeError("O motor oficial permaneceu ocupado por mais de 15 minutos.")
    try:
        with ENGINE_STATE_LOCK:
            ENGINE_STATE.update({
                "active": True,
                "operation": operation,
                "workspace_id": context.user_id,
                "job_id": job_id,
                "started_at": now_iso(),
            })
        yield
    finally:
        with ENGINE_STATE_LOCK:
            waiting = int(ENGINE_STATE.get("waiting") or 0)
            ENGINE_STATE.clear()
            ENGINE_STATE.update({"active": False, "operation": "", "workspace_id": "", "job_id": "", "started_at": "", "waiting": waiting})
        ENGINE_EXECUTION_LOCK.release()


def engine_state_snapshot() -> dict[str, Any]:
    with ENGINE_STATE_LOCK:
        return dict(ENGINE_STATE)


def _process_memory_bytes() -> int | None:
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        else:
            import resource
            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return value if sys.platform == "darwin" else value * 1024
    except Exception:
        return None
    return None


def _cloudflared_status() -> dict[str, Any]:
    result = {"installed": False, "running": False, "detail": "Não verificado"}
    try:
        if os.name == "nt":
            completed = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, timeout=5, errors="replace")
            output = (completed.stdout or "") + (completed.stderr or "")
            result["installed"] = completed.returncode == 0
            result["running"] = "RUNNING" in output.upper()
            result["detail"] = "Serviço Windows em execução" if result["running"] else ("Serviço instalado, mas parado" if result["installed"] else "Serviço cloudflared não localizado")
        else:
            binary = shutil.which("cloudflared")
            result["installed"] = bool(binary)
            result["detail"] = "Binário localizado" if binary else "Binário não localizado neste ambiente"
    except Exception as exc:
        result["detail"] = str(exc)
    return result


def _public_domain_probe(force: bool = False) -> dict[str, Any]:
    now = time.time()
    with SYSTEM_PROBE_LOCK:
        cached = dict(SYSTEM_PROBE_CACHE.get("data") or {})
        if not force and cached and now - float(SYSTEM_PROBE_CACHE.get("checked_at") or 0) < 45:
            return cached
    result: dict[str, Any] = {"domain": PUBLIC_DOMAIN, "url": PUBLIC_URL, "dns": False, "online": False, "status": 0, "latency_ms": None, "error": ""}
    if not PUBLIC_DOMAIN or not PUBLIC_URL:
        result["error"] = "Domínio público não configurado."
    else:
        try:
            socket.getaddrinfo(PUBLIC_DOMAIN, 443, type=socket.SOCK_STREAM)
            result["dns"] = True
        except Exception as exc:
            result["error"] = f"DNS: {exc}"
        started = time.perf_counter()
        try:
            request = Request(PUBLIC_URL + "/api/ready", headers={"User-Agent": "CentralCTe-Monitor/1.0"})
            with urlopen(request, timeout=7) as response:
                result["status"] = int(getattr(response, "status", 0) or 0)
                result["online"] = result["status"] == 200
                response.read(2048)
        except Exception as exc:
            if not result["error"]:
                result["error"] = str(exc)
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    with SYSTEM_PROBE_LOCK:
        SYSTEM_PROBE_CACHE["checked_at"] = now
        SYSTEM_PROBE_CACHE["data"] = dict(result)
    return result


def _recent_audit_errors(limit: int = 5) -> list[dict[str, Any]]:
    path = AUTH.audit_path
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
    except Exception:
        return []
    errors: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except Exception:
            continue
        if str(item.get("outcome") or "").lower() == "failure" or str(item.get("action") or "").endswith(".error"):
            errors.append({
                "at": item.get("at") or item.get("created_at") or "",
                "action": item.get("action") or "",
                "user": (item.get("user") or {}).get("username") if isinstance(item.get("user"), dict) else "",
                "error": ((item.get("metadata") or {}).get("error") if isinstance(item.get("metadata"), dict) else "") or "Falha registrada",
            })
            if len(errors) >= limit:
                break
    return errors


def safe_filename(value: str) -> str:
    name = Path(unquote(value or "arquivo").replace("\\", "/")).name.strip().replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9À-ÿ._()\- ]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:180] or "arquivo"


def validate_upload_filename(category: str, filename: str) -> str:
    safe = safe_filename(filename)
    allowed = UPLOAD_EXTENSIONS.get(category, set())
    suffix = Path(safe).suffix.lower()
    if suffix not in allowed:
        expected = ", ".join(sorted(allowed)) or "formato autorizado"
        raise ValueError(f"Formato não permitido para {category}. Use: {expected}.")
    return safe


def unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    if not destination.exists():
        return destination
    stem, suffix = destination.stem, destination.suffix
    for index in range(2, 10_000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Não foi possível gerar um nome de arquivo livre.")

def xml_document_identity(body: bytes) -> str:
    """Retorna a chave fiscal do CT-e/NF-e quando disponível, sem alterar o XML."""
    try:
        root = ET.fromstring(body)
    except Exception:
        return ""
    for element in root.iter():
        name = local_name(element.tag)
        if name in {"infCte", "infNFe"}:
            raw = str(element.attrib.get("Id") or "").strip()
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 44:
                return digits[-44:]
        if name in {"chCTe", "chNFe"}:
            digits = re.sub(r"\D", "", str(element.text or ""))
            if len(digits) >= 44:
                return digits[-44:]
    return ""


def find_duplicate_xml(directory: Path, body: bytes, digest: str | None = None) -> dict[str, str] | None:
    """Detecta conteúdo idêntico ou a mesma chave fiscal dentro do workspace do usuário."""
    digest = digest or hashlib.sha256(body).hexdigest()
    identity = xml_document_identity(body)
    for path in sorted(directory.glob("*.xml")):
        if not path.is_file():
            continue
        try:
            existing = path.read_bytes()
        except OSError:
            continue
        existing_digest = hashlib.sha256(existing).hexdigest()
        if existing_digest == digest:
            return {"file": path.name, "sha256": existing_digest, "identity": xml_document_identity(existing), "match": "sha256"}
        if identity:
            existing_identity = xml_document_identity(existing)
            if existing_identity and existing_identity == identity:
                return {"file": path.name, "sha256": existing_digest, "identity": existing_identity, "match": "fiscal_identity"}
    return None


def save_qa_attachment(payload: Any, note_id: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data_url = str(payload.get("data_url") or "").strip()
    if not data_url:
        return None
    match = re.match(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\r\n]+)$", data_url, re.I)
    if not match:
        raise ValueError("O anexo do relato deve ser uma imagem PNG, JPG ou WEBP válida.")
    mime = match.group(1).lower()
    try:
        body = base64.b64decode(match.group(2), validate=True)
    except Exception as exc:
        raise ValueError("A imagem anexada está corrompida ou incompleta.") from exc
    if not body:
        raise ValueError("A imagem anexada está vazia.")
    if len(body) > MAX_QA_ATTACHMENT_BYTES:
        raise ValueError("A imagem do relato ultrapassa o limite de 6 MB.")
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime]
    valid = (
        mime == "image/png" and body.startswith(b"\x89PNG\r\n\x1a\n")
    ) or (
        mime == "image/jpeg" and body.startswith(b"\xff\xd8\xff")
    ) or (
        mime == "image/webp" and len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP"
    )
    if not valid:
        raise ValueError("A assinatura interna do arquivo não corresponde ao formato da imagem.")
    attachment_id = f"ATT-{uuid.uuid4().hex[:16]}"
    target = GLOBAL_QA_ATTACHMENT_ROOT / f"{attachment_id}{suffix}"
    target.write_bytes(body)
    original_name = safe_filename(str(payload.get("name") or f"evidencia{suffix}"))
    return {
        "id": attachment_id,
        "name": original_name,
        "mime": mime,
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "url": f"/api/qa/attachment?id={attachment_id}",
        "note_id": note_id,
    }


def qa_attachment_path(attachment_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "", str(attachment_id or ""))[:80]
    if not safe_id.startswith("ATT-"):
        raise ValueError("Identificador de anexo inválido.")
    matches = sorted(GLOBAL_QA_ATTACHMENT_ROOT.glob(f"{safe_id}.*"))
    if len(matches) != 1 or not matches[0].is_file():
        raise FileNotFoundError("Anexo do relato não localizado.")
    target = matches[0].resolve()
    if GLOBAL_QA_ATTACHMENT_ROOT.resolve() not in target.parents:
        raise PermissionError("O anexo solicitado está fora da pasta autorizada.")
    return target


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def first(root: ET.Element | None, name: str) -> ET.Element | None:
    if root is None:
        return None
    for element in root.iter():
        if local_name(element.tag) == name:
            return element
    return None


def all_of(root: ET.Element | None, name: str) -> list[ET.Element]:
    if root is None:
        return []
    return [element for element in root.iter() if local_name(element.tag) == name]


def child(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    for element in list(parent):
        if local_name(element.tag) == name:
            return element
    return None


def text(parent: ET.Element | None, name: str | None = None, default: str = "") -> str:
    element = child(parent, name) if name else parent
    if element is not None and element.text:
        return element.text.strip()
    return default


def digits(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def money_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("R$", "").replace(" ", "").replace(",", "."))
    except Exception:
        return None


def percentage_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number * 100.0 if 0 < abs(number) <= 1 else number
    text = str(value).strip().replace(" ", "").replace(",", ".")
    has_percent = text.endswith("%")
    if has_percent:
        text = text[:-1]
    try:
        number = float(text)
    except Exception:
        return None
    if not has_percent and 0 < abs(number) <= 1:
        number *= 100.0
    return number


def cte_number_from_root(root: ET.Element) -> str:
    return text(first(root, "ide"), "nCT")


def nfe_number_from_key(key: str) -> str:
    raw = digits(key)
    return str(int(raw[25:34])) if len(raw) >= 34 and raw[25:34].isdigit() else ""


def person_name(root: ET.Element, tag: str) -> str:
    return text(first(root, tag), "xNome")


def parse_xml_document(path: Path) -> dict[str, Any]:
    base = {
        "file": path.name,
        "path": str(path),
        "source": "web_upload" if WORKSPACES_ROOT in path.resolve().parents else "project",
        "cte": "",
        "series": "",
        "partner": "Não localizado",
        "recipient": "Não localizado",
        "nf": "Não localizado",
        "city": "Não localizado",
        "proof": "Não localizado",
        "document_type": "Não calculado",
        "charge_type": "Não calculado",
        "xml_value": None,
        "expected_value": None,
        "difference": None,
        "status": "Aguardando motor",
        "diagnosis": "Documento lido pela camada web. A validação comercial oficial ainda não foi executada.",
        "compact_calculation": "Aguardando serviço independente do motor RC26.6.",
        "error": "",
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
    }
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        base.update({"document_type": "XML inválido", "status": "Erro de leitura", "error": str(exc), "diagnosis": str(exc)})
        return base

    inf_cte = first(root, "infCte")
    if inf_cte is not None:
        ide = first(root, "ide")
        emit = first(root, "emit")
        dest = first(root, "dest")
        vprest = first(root, "vPrest")
        docs: list[str] = []
        for inf_nfe in all_of(root, "infNFe"):
            key = text(inf_nfe, "chave")
            number = nfe_number_from_key(key)
            if number and number not in docs:
                docs.append(number)
        for inf_nf in all_of(root, "infNF"):
            number = text(inf_nf, "nDoc")
            if number and number not in docs:
                docs.append(number)
        tp_cte = text(ide, "tpCTe")
        tp_map = {"0": "NORMAL", "1": "COMPLEMENTO", "2": "ANULAÇÃO", "3": "SUBSTITUIÇÃO"}
        city = " / ".join(part for part in (text(ide, "xMunFim"), text(ide, "UFFim")) if part)
        key = str((inf_cte.attrib or {}).get("Id", ""))
        base.update({
            "cte": cte_number_from_root(root),
            "series": text(ide, "serie"),
            "partner": text(emit, "xNome") or "Não localizado",
            "recipient": text(dest, "xNome") or "Não localizado",
            "nf": ", ".join(docs) if docs else "Não localizado",
            "city": city or "Não localizado",
            "proof": ", ".join(docs) if docs else "Não localizado",
            "document_type": tp_map.get(tp_cte, tp_cte or "CT-e"),
            "charge_type": tp_map.get(tp_cte, tp_cte or "Não calculado"),
            "xml_value": money_number(text(vprest, "vTPrest")),
            "key": key.removeprefix("CTe"),
            "issue_date": text(ide, "dhEmi"),
            "origin": " / ".join(part for part in (text(ide, "xMunIni"), text(ide, "UFIni")) if part),
            "destination": city,
            "sender": person_name(root, "rem") or "Não localizado",
            "product": text(first(root, "infCarga"), "proPred"),
            "status": "Aguardando motor",
        })
        return base

    inf_nfe = first(root, "infNFe")
    if inf_nfe is not None:
        ide = first(root, "ide")
        total = first(root, "ICMSTot")
        base.update({
            "cte": text(ide, "nNF"),
            "series": text(ide, "serie"),
            "partner": person_name(root, "emit") or "Não localizado",
            "recipient": person_name(root, "dest") or "Não localizado",
            "nf": text(ide, "nNF") or "Não localizado",
            "proof": text(ide, "nNF") or "Não localizado",
            "document_type": "NF-e",
            "charge_type": "Documento fiscal",
            "xml_value": money_number(text(total, "vNF")),
            "status": "Documento auxiliar",
        })
        return base

    base.update({"document_type": "XML", "status": "Formato não reconhecido"})
    return base


def iter_unique_files(paths: Iterable[Path], suffixes: set[str]) -> Iterable[Path]:
    seen: set[str] = set()
    for base in paths:
        if not base.exists():
            continue
        files = [base] if base.is_file() else base.rglob("*")
        for path in files:
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                key = str(path.resolve()).lower()
            except Exception:
                key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            yield path


def xml_file_paths(context: WorkspaceContext | None = None) -> list[Path]:
    context = context or DEFAULT_WORKSPACE
    paths = [PROJECT_ROOT / "xmls", context.upload_categories["xml"]]
    return list(iter_unique_files(paths, {".xml"}))


def invoice_file_paths(context: WorkspaceContext | None = None) -> list[Path]:
    context = context or DEFAULT_WORKSPACE
    paths = [PROJECT_ROOT / "faturas", context.upload_categories["faturas"]]
    return list(iter_unique_files(paths, {".pdf"}))


def scan_xmls(context: WorkspaceContext | None = None) -> list[dict[str, Any]]:
    context = context or DEFAULT_WORKSPACE
    rows: list[dict[str, Any]] = []
    for path in xml_file_paths(context):
        row = parse_xml_document(path)
        official = context.xml_service.stored_row(path)
        if official:
            # O resultado oficial substitui somente os campos de apresentação.
            # Nenhum cálculo é executado durante a leitura do bootstrap.
            row.update(official)
        complementary = context.dacte_service.complementary_information(path)
        row["complementary_information"] = complementary
        row["has_complementary_information"] = bool(complementary)
        rows.append(row)
    rows.sort(key=lambda row: (row.get("modified_at", ""), row.get("file", "")), reverse=True)
    return rows


def _job_snapshot(job_id: str, context: WorkspaceContext | None = None) -> dict[str, Any] | None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not isinstance(job, dict):
            return None
        if context is not None and str(job.get("workspace_id")) != context.user_id:
            return None
        return dict(job)


def active_xml_job(context: WorkspaceContext | None = None) -> dict[str, Any] | None:
    context = context or DEFAULT_WORKSPACE
    with JOB_LOCK:
        job_id = ACTIVE_JOB_IDS["xml"].get(context.user_id)
        if not job_id:
            return None
        job = JOBS.get(job_id)
        if not isinstance(job, dict) or job.get("state") in {"completed", "failed"}:
            return None
        return dict(job)


def active_invoice_job(context: WorkspaceContext | None = None) -> dict[str, Any] | None:
    context = context or DEFAULT_WORKSPACE
    with JOB_LOCK:
        job_id = ACTIVE_JOB_IDS["invoices"].get(context.user_id)
        if not job_id:
            return None
        job = JOBS.get(job_id)
        if not isinstance(job, dict) or job.get("state") in {"completed", "failed"}:
            return None
        return dict(job)


def active_dacte_job(context: WorkspaceContext | None = None) -> dict[str, Any] | None:
    context = context or DEFAULT_WORKSPACE
    with JOB_LOCK:
        job_id = ACTIVE_JOB_IDS["dacte"].get(context.user_id)
        if not job_id:
            return None
        job = JOBS.get(job_id)
        if not isinstance(job, dict) or _job_is_terminal(job.get("state")):
            return None
        return dict(job)


def active_signature_job(context: WorkspaceContext | None = None) -> dict[str, Any] | None:
    context = context or DEFAULT_WORKSPACE
    with JOB_LOCK:
        job_id = ACTIVE_JOB_IDS["signature"].get(context.user_id)
        if not job_id:
            return None
        job = JOBS.get(job_id)
        if not isinstance(job, dict) or job.get("state") in {"completed", "failed", "discarded", "interrupted"}:
            return None
        return dict(job)


def _update_job(job_id: str, **values: Any) -> None:
    workspace_id = ""
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if isinstance(job, dict):
            job.update(values)
            job["updated_at"] = now_iso()
            workspace_id = str(job.get("workspace_id") or "")
    if workspace_id:
        _persist_workspace_jobs(get_workspace(workspace_id))


def _run_xml_job(job_id: str, context: WorkspaceContext, paths: list[Path]) -> None:
    def progress(processed: int, total: int, filename: str, message: str) -> None:
        _update_job(
            job_id,
            state="running",
            processed=processed,
            total=total,
            current_file=filename,
            message=message,
            percent=round((processed / total) * 100, 1) if total else 0.0,
        )

    try:
        _update_job(job_id, state="queued", message="Sincronizando tabelas de parceiros antes da validação.")
        DEVELOPER_TOOLS.ensure_partner_files(context)
        _update_job(job_id, state="queued", message="Aguardando acesso exclusivo ao motor RC26.6.")
        with engine_execution("Validação XML", context, job_id):
            _update_job(job_id, state="running", message="Carregando o motor RC26.6 e as fontes oficiais.")
            summary = context.xml_service.process(paths, progress=progress)
        _update_job(
            job_id,
            state="completed",
            processed=len(paths),
            total=len(paths),
            percent=100.0,
            current_file="",
            message="Validação oficial concluída.",
            result=summary,
            finished_at=now_iso(),
        )
    except Exception as exc:
        _update_job(
            job_id,
            state="failed",
            message="A validação oficial foi interrompida.",
            error=str(exc),
            finished_at=now_iso(),
        )
    finally:
        with JOB_LOCK:
            if ACTIVE_JOB_IDS["xml"].get(context.user_id) == job_id:
                ACTIVE_JOB_IDS["xml"].pop(context.user_id, None)


def start_xml_job(context: WorkspaceContext | None = None) -> dict[str, Any]:
    context = context or DEFAULT_WORKSPACE
    paths = xml_file_paths(context)
    if not paths:
        raise ValueError("Adicione pelo menos um XML antes de processar.")
    with JOB_LOCK:
        active_id = ACTIVE_JOB_IDS["xml"].get(context.user_id)
        if active_id:
            existing = JOBS.get(active_id)
            if isinstance(existing, dict) and existing.get("state") not in {"completed", "failed"}:
                return dict(existing)
        job_id = f"XML-{uuid.uuid4().hex[:12]}"
        job = {
            "id": job_id,
            "kind": "xml",
            "workspace_id": context.user_id,
            "state": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "total": len(paths),
            "percent": 0.0,
            "current_file": "",
            "message": "Validação adicionada à fila local.",
            "error": "",
        }
        JOBS[job_id] = job
        ACTIVE_JOB_IDS["xml"][context.user_id] = job_id
    _persist_workspace_jobs(context)
    thread = threading.Thread(target=_run_xml_job, args=(job_id, context, paths), name=f"central-cte-{job_id}", daemon=True)
    thread.start()
    return dict(job)


def _run_invoice_job(job_id: str, context: WorkspaceContext, paths: list[Path]) -> None:
    def progress(processed: int, total: int, filename: str, message: str) -> None:
        _update_job(
            job_id,
            state="running",
            processed=processed,
            total=total,
            current_file=filename,
            message=message,
            percent=round((processed / total) * 100, 1) if total else 0.0,
        )

    try:
        _update_job(job_id, state="queued", message="Aguardando acesso exclusivo ao motor RC26.6.")
        with engine_execution("Processamento de faturas", context, job_id):
            _update_job(job_id, state="running", message="Carregando leitor PDF, Base SSW e motor de decisão RC26.6.")
            summary = context.invoice_service.process(paths, progress=progress)
        rejected = int(summary.get("rejected_files") or 0)
        duplicates = int(summary.get("duplicate_files") or 0)
        alerts = rejected + duplicates + int(summary.get("unprocessed_files") or 0)
        message = (
            f"Processamento concluído com {alerts} alerta(s): "
            f"{rejected} rejeitado(s) e {duplicates} duplicado(s)."
            if alerts
            else "Processamento oficial de faturas concluído sem rejeições."
        )
        _update_job(
            job_id,
            state="completed",
            processed=len(paths),
            total=len(paths),
            percent=100.0,
            current_file="",
            message=message,
            result=summary,
            finished_at=now_iso(),
        )
    except Exception as exc:
        _update_job(
            job_id,
            state="failed",
            message="O processamento oficial de faturas foi interrompido.",
            error=str(exc),
            finished_at=now_iso(),
        )
    finally:
        with JOB_LOCK:
            if ACTIVE_JOB_IDS["invoices"].get(context.user_id) == job_id:
                ACTIVE_JOB_IDS["invoices"].pop(context.user_id, None)


def start_invoice_job(context: WorkspaceContext | None = None) -> dict[str, Any]:
    context = context or DEFAULT_WORKSPACE
    paths = invoice_file_paths(context)
    if not paths:
        raise ValueError("Adicione pelo menos uma fatura PDF antes de processar.")
    with JOB_LOCK:
        active_id = ACTIVE_JOB_IDS["invoices"].get(context.user_id)
        if active_id:
            existing = JOBS.get(active_id)
            if isinstance(existing, dict) and existing.get("state") not in {"completed", "failed"}:
                return dict(existing)
        job_id = f"FAT-{uuid.uuid4().hex[:12]}"
        job = {
            "id": job_id,
            "kind": "invoices",
            "workspace_id": context.user_id,
            "state": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "total": len(paths),
            "percent": 0.0,
            "current_file": "",
            "message": "Processamento de faturas adicionado à fila local.",
            "error": "",
        }
        JOBS[job_id] = job
        ACTIVE_JOB_IDS["invoices"][context.user_id] = job_id
    _persist_workspace_jobs(context)
    thread = threading.Thread(target=_run_invoice_job, args=(job_id, context, paths), name=f"central-cte-{job_id}", daemon=True)
    thread.start()
    return dict(job)


def _run_dacte_job(
    job_id: str,
    context: WorkspaceContext,
    selected_paths: list[str],
    mode: str,
    include_compact: bool,
) -> None:
    def progress(percent: float, processed: int, total: int, current_file: str, message: str) -> None:
        _update_job(
            job_id,
            state="running",
            processed=max(0, int(processed or 0)),
            total=max(0, int(total or len(selected_paths))),
            percent=max(0.0, min(100.0, round(float(percent or 0.0), 1))),
            current_file=str(current_file or ""),
            message=str(message or "Gerando DACTEs oficiais."),
        )

    try:
        _update_job(job_id, state="queued", message="Aguardando acesso exclusivo ao motor RC26.6.")
        with engine_execution("Geração DACTE", context, job_id):
            _update_job(job_id, state="running", message="Preparando os documentos oficiais.")
            result = context.dacte_service.generate(
                selected_paths,
                xml_file_paths(context),
                mode=mode,
                progress=progress,
                include_compact=include_compact,
            )
        total = int(result.get("documents") or len(selected_paths))
        _update_job(
            job_id,
            state="completed",
            processed=total,
            total=total,
            percent=100.0,
            current_file=str(result.get("name") or ""),
            message="Geração oficial concluída.",
            result=result,
            finished_at=now_iso(),
        )
    except Exception as exc:
        _update_job(
            job_id,
            state="failed",
            message="A geração dos DACTEs oficiais foi interrompida.",
            error=str(exc),
            finished_at=now_iso(),
        )
    finally:
        with JOB_LOCK:
            if ACTIVE_JOB_IDS["dacte"].get(context.user_id) == job_id:
                ACTIVE_JOB_IDS["dacte"].pop(context.user_id, None)


def start_dacte_job(
    context: WorkspaceContext,
    selected_paths: list[str],
    *,
    mode: str = "batch",
    include_compact: bool = True,
) -> dict[str, Any]:
    paths = [str(value or "").strip() for value in selected_paths if str(value or "").strip()]
    if not paths:
        raise ValueError("Selecione pelo menos um CT-e já processado.")
    normalized_mode = str(mode or "batch").strip().lower()
    if normalized_mode not in {"batch", "individuals", "individuais", "zip"}:
        raise ValueError("Modo DACTE inválido. Use batch ou individuals.")
    normalized_mode = "individuals" if normalized_mode in {"individuals", "individuais", "zip"} else "batch"
    with JOB_LOCK:
        active_id = ACTIVE_JOB_IDS["dacte"].get(context.user_id)
        if active_id:
            existing = JOBS.get(active_id)
            if isinstance(existing, dict) and not _job_is_terminal(existing.get("state")):
                return dict(existing)
        job_id = f"DACTE-{uuid.uuid4().hex[:12]}"
        job = {
            "id": job_id,
            "kind": "dacte",
            "mode": normalized_mode,
            "workspace_id": context.user_id,
            "state": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "total": len(paths),
            "percent": 0.0,
            "current_file": "",
            "message": "Geração oficial adicionada à fila local.",
            "error": "",
            "request": {
                "paths": paths,
                "mode": normalized_mode,
                "include_compact": bool(include_compact),
            },
        }
        JOBS[job_id] = job
        ACTIVE_JOB_IDS["dacte"][context.user_id] = job_id
    _persist_workspace_jobs(context)
    thread = threading.Thread(
        target=_run_dacte_job,
        args=(job_id, context, paths, normalized_mode, bool(include_compact)),
        name=f"central-cte-{job_id}",
        daemon=True,
    )
    thread.start()
    return dict(job)


def _run_signature_job(
    job_id: str,
    context: WorkspaceContext,
    selected_paths: list[str],
    profile_id: str,
    date_text: str,
    mode: str,
    include_compact: bool,
) -> None:
    def progress(percent: float, processed: int, total: int, current_file: str, message: str) -> None:
        _update_job(
            job_id,
            state="running",
            processed=max(0, int(processed or 0)),
            total=max(0, int(total or len(selected_paths))),
            percent=max(0.0, min(100.0, round(float(percent or 0.0), 1))),
            current_file=str(current_file or ""),
            message=str(message or "Gerando DACTEs assinados."),
        )

    try:
        _update_job(job_id, state="queued", message="Aguardando acesso exclusivo ao motor RC26.6.")
        with engine_execution("Geração DACTE assinado", context, job_id):
            _update_job(job_id, state="running", message="Preparando os documentos e o perfil de assinatura.")
            result = context.signature_service.generate(
                selected_paths,
                xml_file_paths(context),
                profile_id,
                date_text,
                mode=mode,
                progress=progress,
                include_compact=include_compact,
            )
        total = int(result.get("documents") or len(selected_paths))
        _update_job(
            job_id,
            state="completed",
            processed=total,
            total=total,
            percent=100.0,
            current_file=str(result.get("name") or ""),
            message="Geração assinada concluída.",
            result=result,
            finished_at=now_iso(),
        )
    except Exception as exc:
        _update_job(
            job_id,
            state="failed",
            message="A geração dos DACTEs assinados foi interrompida.",
            error=str(exc),
            finished_at=now_iso(),
        )
    finally:
        with JOB_LOCK:
            if ACTIVE_JOB_IDS["signature"].get(context.user_id) == job_id:
                ACTIVE_JOB_IDS["signature"].pop(context.user_id, None)


def start_signature_job(
    context: WorkspaceContext,
    selected_paths: list[str],
    profile_id: str,
    date_text: str = "",
    mode: str = "batch",
    include_compact: bool = True,
) -> dict[str, Any]:
    paths = [str(value or "").strip() for value in selected_paths if str(value or "").strip()]
    if not paths:
        raise ValueError("Selecione pelo menos um CT-e já processado.")
    normalized_mode = str(mode or "batch").strip().lower()
    if normalized_mode not in {"batch", "individuals", "individuais", "zip"}:
        raise ValueError("Modo de assinatura inválido. Use batch ou individuals.")
    normalized_mode = "individuals" if normalized_mode in {"individuals", "individuais", "zip"} else "batch"
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise ValueError("Selecione um perfil de assinatura.")
    with JOB_LOCK:
        active_id = ACTIVE_JOB_IDS["signature"].get(context.user_id)
        if active_id:
            existing = JOBS.get(active_id)
            if isinstance(existing, dict) and not _job_is_terminal(existing.get("state")):
                return dict(existing)
        job_id = f"ASS-{uuid.uuid4().hex[:12]}"
        job = {
            "id": job_id,
            "kind": "signature",
            "mode": normalized_mode,
            "workspace_id": context.user_id,
            "state": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "total": len(paths),
            "percent": 0.0,
            "current_file": "",
            "message": "Geração assinada adicionada à fila local.",
            "error": "",
            "request": {
                "paths": paths,
                "profile_id": profile_id,
                "date_text": str(date_text or ""),
                "mode": normalized_mode,
                "include_compact": bool(include_compact),
            },
        }
        JOBS[job_id] = job
        ACTIVE_JOB_IDS["signature"][context.user_id] = job_id
    _persist_workspace_jobs(context)
    thread = threading.Thread(
        target=_run_signature_job,
        args=(job_id, context, paths, profile_id, str(date_text or ""), normalized_mode, bool(include_compact)),
        name=f"central-cte-{job_id}",
        daemon=True,
    )
    thread.start()
    return dict(job)


def scan_invoices(context: WorkspaceContext | None = None) -> list[dict[str, Any]]:
    context = context or DEFAULT_WORKSPACE
    paths = invoice_file_paths(context)
    official_rows = context.invoice_service.stored_rows(paths)
    official_files = context.invoice_service.stored_file_records(paths)
    if official_rows or official_files:
        return official_rows

    rows: list[dict[str, Any]] = []
    for path in paths:
        stat = path.stat()
        rows.append({
            "invoice": path.stem,
            "file": path.name,
            "path": str(path),
            "source_files": [str(path)],
            "partner": "Aguardando leitura",
            "item_count": None,
            "ok_count": None,
            "pending_count": None,
            "total_value": None,
            "payable_value": None,
            "retained_value": None,
            "future_value": None,
            "internal_problem_value": None,
            "payment_status": "Aguardando motor",
            "financial_action": "Não calculado",
            "details": [],
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        })
    rows.sort(key=lambda row: row["modified_at"], reverse=True)
    return rows


def scan_invoice_files(context: WorkspaceContext | None = None) -> list[dict[str, Any]]:
    """Retorna a reconciliação arquivo a arquivo do lote de faturas atual."""
    context = context or DEFAULT_WORKSPACE
    paths = invoice_file_paths(context)
    stored = context.invoice_service.stored_file_records(paths)
    if stored:
        order = {"rejected": 0, "duplicate": 1, "processing": 2, "received": 3, "processed": 4}
        stored.sort(key=lambda item: (order.get(str(item.get("status") or ""), 9), int(item.get("position") or 0), str(item.get("file") or "").lower()))
        return stored

    rows: list[dict[str, Any]] = []
    for position, path in enumerate(paths, 1):
        stat = path.stat()
        rows.append({
            "id": hashlib.sha256(str(path).encode("utf-8", errors="replace")).hexdigest()[:20],
            "position": position,
            "file": path.name,
            "path": str(path),
            "sha256": "",
            "size_bytes": stat.st_size,
            "status": "received",
            "stage": "intake",
            "code": "RECEIVED",
            "reason": "Arquivo recebido e aguardando processamento.",
            "duplicate_of": "",
            "text_backend": "",
            "invoice_numbers": [],
            "invoice_keys": [],
            "partners": [],
            "parser_sources": [],
            "warnings": [],
            "attempts": 0,
            "received_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "processed_at": "",
        })
    return rows


def clear_xml_workspace(context: WorkspaceContext | None = None) -> dict[str, Any]:
    """Limpa o lote XML do workspace sem apagar bases ou relatórios exportados."""
    context = context or DEFAULT_WORKSPACE
    active = active_xml_job(context)
    if active is not None:
        raise RuntimeError("Aguarde o processamento XML atual terminar antes de limpar a lista.")

    deleted_files: list[str] = []
    xml_root = context.upload_categories["xml"].resolve()
    deleted_xml_paths = [path.resolve() for path in xml_root.rglob("*.xml") if path.is_file()]
    if deleted_xml_paths:
        context.dacte_service.remove_complementary_information(deleted_xml_paths)
    for path in sorted(xml_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            try:
                deleted_files.append(path.name)
                path.unlink()
            except FileNotFoundError:
                pass
        elif path.is_dir() and path != xml_root:
            try:
                path.rmdir()
            except OSError:
                pass
    xml_root.mkdir(parents=True, exist_ok=True)

    state_result = context.xml_service.clear_results()
    preview_root = context.dacte_service.preview_root
    if preview_root.exists():
        shutil.rmtree(preview_root, ignore_errors=True)
    preview_root.mkdir(parents=True, exist_ok=True)
    for state_file in (context.dacte_service.last_run_path, context.signature_service.last_run_path):
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass

    with JOB_LOCK:
        ACTIVE_JOB_IDS["xml"].pop(context.user_id, None)

    return {
        "cleared_at": now_iso(),
        "deleted_xml_count": len(deleted_files),
        "deleted_files": deleted_files[:200],
        "reports_preserved": True,
        "bases_preserved": True,
        "state": state_result,
    }


def clear_invoice_workspace(context: WorkspaceContext | None = None) -> dict[str, Any]:
    """Limpa o lote de faturas sem apagar bases ou relatórios exportados."""
    context = context or DEFAULT_WORKSPACE
    active = active_invoice_job(context)
    if active is not None:
        raise RuntimeError("Aguarde o processamento de faturas atual terminar antes de limpar a lista.")

    deleted_files: list[str] = []
    invoice_root = context.upload_categories["faturas"].resolve()
    for path in sorted(invoice_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            try:
                deleted_files.append(path.name)
                path.unlink()
            except FileNotFoundError:
                pass
        elif path.is_dir() and path != invoice_root:
            try:
                path.rmdir()
            except OSError:
                pass
    invoice_root.mkdir(parents=True, exist_ok=True)

    state_result = context.invoice_service.clear_results()
    with JOB_LOCK:
        ACTIVE_JOB_IDS["invoices"].pop(context.user_id, None)

    return {
        "cleared_at": now_iso(),
        "deleted_invoice_count": len(deleted_files),
        "deleted_files": deleted_files[:200],
        "reports_preserved": True,
        "bases_preserved": True,
        "state": state_result,
    }


def xlsx_col_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", str(reference or "").upper())
    if not match:
        return 0
    value = 0
    for char in match.group(1):
        value = value * 26 + (ord(char) - 64)
    return max(value - 1, 0)


def xlsx_records(path: Path, wanted_sheets: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    output: dict[str, list[dict[str, Any]]] = {name: [] for name in wanted_sheets}
    with zipfile.ZipFile(path, "r") as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{{{main_ns}}}si"):
                shared.append("".join(node.text or "" for node in si.iter(f"{{{main_ns}}}t")))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib.get("Id", ""): rel.attrib.get("Target", "") for rel in relationships.findall(f"{{{pkg_rel_ns}}}Relationship")}
        sheet_paths: dict[str, str] = {}
        sheets = workbook.find(f"{{{main_ns}}}sheets")
        if sheets is not None:
            for sheet in sheets.findall(f"{{{main_ns}}}sheet"):
                target = rel_map.get(sheet.attrib.get(f"{{{rel_ns}}}id", ""), "")
                if target.startswith("/"):
                    target = target.lstrip("/")
                elif not target.startswith("xl/"):
                    target = "xl/" + target.lstrip("./")
                sheet_paths[sheet.attrib.get("name", "")] = target
        for sheet_name in wanted_sheets:
            target = sheet_paths.get(sheet_name)
            if not target or target not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(target))
            matrix: list[list[Any]] = []
            for row in root.iter(f"{{{main_ns}}}row"):
                values: dict[int, Any] = {}
                maximum = -1
                for cell in row.findall(f"{{{main_ns}}}c"):
                    index = xlsx_col_index(cell.attrib.get("r", ""))
                    maximum = max(maximum, index)
                    cell_type = cell.attrib.get("t", "")
                    value_node = cell.find(f"{{{main_ns}}}v")
                    raw = value_node.text if value_node is not None else None
                    if cell_type == "inlineStr":
                        value: Any = "".join(node.text or "" for node in cell.iter(f"{{{main_ns}}}t"))
                    elif cell_type == "s" and raw is not None:
                        try:
                            value = shared[int(raw)]
                        except Exception:
                            value = raw
                    elif raw is None:
                        value = None
                    else:
                        try:
                            number = float(raw)
                            value = int(number) if number.is_integer() else number
                        except Exception:
                            value = raw
                    values[index] = value
                if maximum >= 0:
                    matrix.append([values.get(index) for index in range(maximum + 1)])
            if not matrix:
                continue
            headers = [str(value or "").strip() for value in matrix[0]]
            output[sheet_name] = [
                {headers[index]: value for index, value in enumerate(values) if index < len(headers) and headers[index]}
                for values in matrix[1:]
                if any(value not in (None, "") for value in values)
            ]
    return output


def partner_table_path(context: WorkspaceContext | None = None) -> Path | None:
    context = context or DEFAULT_WORKSPACE
    try:
        return context.xml_service.resolve_table_source(raise_on_missing=False)
    except Exception:
        return None


def partner_review_pending(value: Any) -> bool:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")
    if not normalized or normalized == "NAO_LOCALIZADO":
        return False
    approved = {"OK", "REVISAR_OK", "REVISADO_OK", "REVISADO", "VALIDADO", "CONFERIDO", "ALIAS_OK"}
    if normalized in approved or normalized.endswith("_OK"):
        return False
    return any(token in normalized for token in ("PEND", "REVIS", "ALERT", "ATENC", "MANUAL", "ERRO", "FALHA", "INCOMPLET"))


def scan_partners(context: WorkspaceContext | None = None) -> dict[str, Any]:
    context = context or DEFAULT_WORKSPACE
    path = partner_table_path(context)
    if path is None:
        return {"path": None, "error": "Tabela oficial não localizada.", "partners": [], "rules": []}
    try:
        records = xlsx_records(path, ("PARCEIROS", "REGRAS_PERCENTUAL", "REGIOES"))
    except Exception as exc:
        return {"path": str(path), "error": str(exc), "partners": [], "rules": []}
    partners: list[dict[str, Any]] = []
    for record in records.get("PARCEIROS", []):
        partner_id = str(record.get("Parceiro ID") or "").strip()
        if not partner_id:
            continue
        partners.append({
            "partner_id": partner_id,
            "name": str(record.get("Nome Parceiro") or partner_id).strip(),
            "alias": str(record.get("Nome no XML / Alias principal") or "Não localizado").strip(),
            "base_city": str(record.get("Origem base") or "Não localizado").strip(),
            "base_uf": str(record.get("UF base") or "Não localizado").strip(),
            "table_type": str(record.get("Tipo tabela principal") or "Não localizado").strip(),
            "status": str(record.get("Status") or "Não localizado").strip(),
            "source_pdf": str(record.get("Fonte PDF") or "Não localizado").strip(),
            "observation": str(record.get("Observação") or "").strip(),
        })
    rules: list[dict[str, Any]] = []
    seen_rule_keys: set[tuple[str, str]] = set()

    def append_partner_rule(record: Mapping[str, Any], *, region_sheet: bool = False) -> None:
        partner_id = str(record.get("Parceiro ID") or "").strip()
        rule_id = str(record.get("Regra ID") or record.get("Região ID") or "").strip()
        if not partner_id or not rule_id:
            return
        key = (partner_id.upper(), rule_id.upper())
        if key in seen_rule_keys:
            return
        seen_rule_keys.add(key)
        if region_sheet:
            origin = "Não localizado"
            destination = " / ".join(
                str(record.get(field) or "").strip()
                for field in ("Cidade", "UF")
                if str(record.get(field) or "").strip()
            ) or "Não localizado"
            region = str(record.get("Região/Base") or "Não localizado").strip()
            percentage = percentage_number(record.get("Percentual Default"))
            minimum = money_number(record.get("Frete Mínimo Default"))
            calculation_base = str(record.get("Base Cálculo") or "Não calculado").strip()
            toll = str(record.get("Valor Pedágio") or record.get("Pedágio Ativo") or "Não localizado").strip()
            gris = str(record.get("Percentual GRIS") or record.get("GRIS Ativo") or "Não localizado").strip()
            deadline = str(record.get("Prazo Default") or "Não localizado").strip()
            review_status = str(record.get("Status Revisão") or "Não localizado").strip()
            observation = str(record.get("Observação Conferência") or record.get("Observação Controle") or "").strip()
        else:
            origin = " / ".join(str(record.get(field) or "").strip() for field in ("Origem Cidade", "Origem UF") if str(record.get(field) or "").strip()) or "Não localizado"
            destination = " / ".join(str(record.get(field) or "").strip() for field in ("Destino Cidade", "Destino UF") if str(record.get(field) or "").strip()) or "Não localizado"
            region = str(record.get("Região / Base") or "Não localizado").strip()
            percentage = percentage_number(record.get("Percentual"))
            minimum = money_number(record.get("Frete Mínimo"))
            calculation_base = str(record.get("Base Cálculo") or "Não calculado").strip()
            toll = str(record.get("Pedágio") or record.get("Valor Pedágio") or "Não localizado").strip()
            gris = str(record.get("GRIS Ativo") or record.get("Percentual GRIS") or "Não localizado").strip()
            deadline = str(record.get("Prazo") or "Não localizado").strip()
            review_status = str(record.get("Status Revisão") or "Não localizado").strip()
            observation = str(record.get("Observação") or "").strip()
        rules.append({
            "rule_id": rule_id,
            "partner_id": partner_id,
            "origin": origin,
            "destination": destination,
            "region": region,
            "percentage": percentage,
            "minimum": minimum,
            "calculation_base": calculation_base,
            "toll": toll,
            "gris": gris,
            "deadline": deadline,
            "review_status": review_status,
            "needs_review": partner_review_pending(review_status),
            "observation": observation,
            "source_sheet": "REGIOES" if region_sheet else "REGRAS_PERCENTUAL",
        })

    for record in records.get("REGRAS_PERCENTUAL", []):
        append_partner_rule(record)
    for record in records.get("REGIOES", []):
        append_partner_rule(record, region_sheet=True)
    partners.sort(key=lambda item: (item["name"].upper(), item["partner_id"].upper()))
    rules.sort(key=lambda item: (item["partner_id"].upper(), item["rule_id"].upper()))
    return {"path": str(path), "error": "", "partners": partners, "rules": rules}


def scan_reports(context: WorkspaceContext | None = None, *, include_technical: bool = False) -> list[dict[str, Any]]:
    """Lista somente entregáveis operacionais para perfis comuns.

    Usuários comuns recebem exclusivamente relatórios XML, relatórios de
    faturas e PDFs/ZIPs de DACTE gerados no próprio workspace. O Desenvolvedor
    também pode consultar arquivos técnicos, históricos globais e logs.
    """
    context = context or DEFAULT_WORKSPACE
    workspace_reports = (context.output_root / "relatorios").resolve()
    workspace_dacte = (context.output_root / "dacte").resolve()
    preview_root = (workspace_dacte / "previews").resolve()

    global_reports = (PROJECT_ROOT / "relatorios").resolve()
    directories = [workspace_reports, workspace_dacte, global_reports]
    allowed = {".xlsx", ".xls", ".csv", ".pdf", ".zip"}
    technical_roots: list[Path] = []
    if include_technical:
        directories.extend([
            (PROJECT_ROOT / "saida_html").resolve(),
            (PROJECT_ROOT / "logs").resolve(),
            context.state_root.resolve(),
        ])
        allowed.update({".html", ".htm", ".txt", ".json", ".log"})
        technical_roots = [
            (PROJECT_ROOT / "logs").resolve(),
            context.state_root.resolve(),
            (PROJECT_ROOT / "saida_html").resolve(),
        ]

    rows: list[dict[str, Any]] = []
    for path in iter_unique_files(directories, allowed):
        resolved = path.resolve()
        if preview_root == resolved or preview_root in resolved.parents:
            continue
        is_workspace_report = resolved == workspace_reports or workspace_reports in resolved.parents
        is_workspace_dacte = resolved == workspace_dacte or workspace_dacte in resolved.parents
        is_global_report = resolved == global_reports or global_reports in resolved.parents
        is_technical = any(resolved == root or root in resolved.parents for root in technical_roots) or path.suffix.lower() in {".json", ".txt", ".log", ".html", ".htm"}
        if not include_technical and not (is_workspace_report or is_workspace_dacte or is_global_report):
            continue
        if is_technical and not include_technical:
            continue

        lower = path.name.lower()
        if is_workspace_dacte:
            module = "DACTE / PDF"
        elif "fatur" in lower or "invoice" in lower:
            module = "Faturas"
        elif "xml" in lower or "valid" in lower:
            module = "Validação XML"
        elif is_technical:
            module = "Técnico / Logs"
        elif is_workspace_report or is_global_report:
            module = "Relatórios operacionais"
        elif include_technical:
            module = "Operacional"
        else:
            continue

        stat = path.stat()
        rows.append({
            "name": path.name,
            "module": module,
            "format": path.suffix.lstrip(".").upper(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "size_bytes": stat.st_size,
            "path": str(path),
            "technical": is_technical,
        })
    rows.sort(key=lambda row: row["modified_at"], reverse=True)
    return rows[:500]


def base_files(context: WorkspaceContext | None = None) -> list[dict[str, Any]]:
    context = context or DEFAULT_WORKSPACE
    rows: list[dict[str, Any]] = []
    for path in iter_unique_files([PROJECT_ROOT / "bases", context.upload_categories["bases"]], {".sswweb", ".csv", ".xlsx", ".xls"}):
        stat = path.stat()
        rows.append({"name": path.name, "path": str(path), "size_bytes": stat.st_size, "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")})
    rows.sort(key=lambda item: item["modified_at"], reverse=True)
    return rows


def build_bootstrap(context: WorkspaceContext | None = None, user: AuthenticatedUser | None = None) -> dict[str, Any]:
    context = context or DEFAULT_WORKSPACE
    capabilities = DEVELOPER_TOOLS.capabilities(user)
    # A fonte comercial é global: sincronize para todos os perfis, não apenas
    # quando um Desenvolvedor abre a administração das tabelas.
    DEVELOPER_TOOLS.ensure_partner_files(context)
    xmls = scan_xmls(context)
    invoices = scan_invoices(context)
    invoice_files = scan_invoice_files(context)
    partner_data = scan_partners(context)
    reports = scan_reports(context, include_technical=capabilities.get("can_view_technical_reports", False))
    settings = {**DEFAULT_SETTINGS, **read_json(context.settings_path, {})}
    qa = read_json(context.qa_path, []) if capabilities.get("can_view_qa", False) else []
    xml_engine_state = context.xml_service.readiness()
    invoice_engine_state = context.invoice_service.readiness()
    report_engine_state = context.report_service.readiness()
    dacte_engine_state = context.dacte_service.readiness()
    signature_engine_state = context.signature_service.readiness()
    engine_state = {
        **xml_engine_state,
        "connected": bool(xml_engine_state.get("connected")) and bool(invoice_engine_state.get("connected")),
        "ui_is_passive": True,
        "xml_service_connected": bool(xml_engine_state.get("connected")),
        "invoice_service_connected": bool(invoice_engine_state.get("connected")),
        "invoice_status": invoice_engine_state.get("status") or "",
        "invoice_service_version": invoice_engine_state.get("service_version") or "",
        "invoice_base_source": invoice_engine_state.get("base_source") or "",
        "invoice_pdf_backends": invoice_engine_state.get("pdf_backends") or [],
        "invoice_last_run": invoice_engine_state.get("last_run") or {},
        "invoice_self_test": invoice_engine_state.get("self_test") or {},
        "report_service_connected": bool(report_engine_state.get("connected")),
        "report_status": report_engine_state.get("status") or "",
        "report_service_version": report_engine_state.get("service_version") or "",
        "report_output_root": report_engine_state.get("output_root") or "",
        "report_last_run": report_engine_state.get("last_run") or {},
        "dacte_service_connected": bool(dacte_engine_state.get("connected")),
        "dacte_status": dacte_engine_state.get("status") or "",
        "dacte_service_version": dacte_engine_state.get("service_version") or "",
        "dacte_browser": dacte_engine_state.get("browser") or "",
        "dacte_conversion_backends": dacte_engine_state.get("conversion_backends") or [],
        "dacte_output_root": dacte_engine_state.get("output_root") or "",
        "dacte_last_run": dacte_engine_state.get("last_run") or {},
        "signature_editor_connected": bool(signature_engine_state.get("connected")),
        "signature_status": signature_engine_state.get("status") or "",
        "signature_service_version": signature_engine_state.get("service_version") or "",
        "signature_image_backend": signature_engine_state.get("image_backend") or "",
        "signature_profile_count": int(signature_engine_state.get("profile_count") or 0),
        "signature_last_run": signature_engine_state.get("last_run") or {},
        "visual_signature_only": bool(signature_engine_state.get("visual_signature_only", True)),
    }
    user_security = AUTH.user_security_state(user.id) if user is not None else {}
    return {
        "app": {
            "version": APP_VERSION,
            "engine_version": ENGINE_VERSION,
            "mode": "web-local",
            "server_time": now_iso(),
            "project_root": str(PROJECT_ROOT),
            "host_security": "Autenticação obrigatória; acesso local por padrão",
            "workspace_id": context.user_id,
        },
        "auth": {
            "authenticated": user is not None,
            "user": user.as_public_dict() if user else None,
            "csrf": "",
            "must_change_password": bool(user_security.get("must_change_password", False)),
            "password_changed_at": str(user_security.get("password_changed_at") or ""),
        },
        "engine": engine_state,
        "processing": {
            "xml": active_xml_job(context),
            "last_xml": xml_engine_state.get("last_run") or {},
            "invoices": active_invoice_job(context),
            "last_invoices": invoice_engine_state.get("last_run") or {},
            "dacte": active_dacte_job(context),
            "last_dacte": dacte_engine_state.get("last_run") or {},
            "signature": active_signature_job(context),
            "last_signature": signature_engine_state.get("last_run") or {},
        },
        "xmls": xmls,
        "invoices": invoices,
        "invoice_files": invoice_files,
        "partners": partner_data["partners"],
        "partner_rules": partner_data["rules"],
        "partner_table": {"path": partner_data["path"], "error": partner_data["error"]},
        "reports": reports,
        "signatures": signature_engine_state.get("profiles") or [],
        "bases": base_files(context),
        "settings": settings,
        "qa": qa,
        "capabilities": capabilities,
        "developer_features": DEVELOPER_TOOLS.load_features() if capabilities.get("can_manage_features") else {},
        "base_management": DEVELOPER_TOOLS.base_overview(context) if capabilities.get("can_import_base") else {},
        "partner_files": DEVELOPER_TOOLS.partner_files_overview(context) if capabilities.get("can_manage_partner_tables") else [],
        "postgres_integration": SSW_POSTGRES.public_status() if capabilities.get("can_manage_database_integration") else {},
    }


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


def validate_upload_content(category: str, body: bytes) -> None:
    if not body:
        raise ValueError("O arquivo enviado está vazio.")
    if category == "xml":
        try:
            root = ET.fromstring(body)
        except Exception as exc:
            raise ValueError(f"O conteúdo não é um XML válido: {exc}") from exc
        if not local_name(root.tag):
            raise ValueError("O XML não possui elemento raiz válido.")
        return
    if category == "faturas":
        if not body.startswith(b"%PDF-"):
            raise ValueError("O conteúdo enviado não possui cabeçalho de PDF válido.")
        if b"%%EOF" not in body[-8192:]:
            raise ValueError("O PDF parece incompleto ou corrompido.")
        return
    if category == "tabelas":
        try:
            from io import BytesIO
            with zipfile.ZipFile(BytesIO(body), "r") as archive:
                if archive.testzip() is not None:
                    raise ValueError("A planilha XLSX contém uma entrada corrompida.")
                names = set(archive.namelist())
                required = {"[Content_Types].xml", "xl/workbook.xml"}
                if not required.issubset(names):
                    raise ValueError("O arquivo não possui a estrutura mínima de uma planilha XLSX.")
        except zipfile.BadZipFile as exc:
            raise ValueError("O conteúdo enviado não é uma planilha XLSX válida.") from exc
        return
    if category == "bases":
        prefix = body[:4096]
        if prefix.startswith((b"MZ", b"PK\x03\x04", b"%PDF-")) or b"\x00" in prefix:
            raise ValueError("O conteúdo não corresponde ao formato textual .sswweb esperado.")
        sample = prefix.decode("latin-1", errors="ignore").strip().lower()
        if sample.startswith("<!doctype html") or sample.startswith("<html"):
            raise ValueError("Uma página HTML não pode ser usada como Base SSW Web.")
        if len(sample) < 20:
            raise ValueError("A Base SSW Web parece vazia ou incompleta.")
        return
    raise ValueError("Categoria de upload inválida.")


def workspace_health(
    context: WorkspaceContext,
    *,
    include_admin: bool = False,
    include_infrastructure: bool = False,
) -> dict[str, Any]:
    disk = shutil.disk_usage(context.root)
    checks: dict[str, Any] = {}
    for name, directory in {
        "workspace": context.root,
        "uploads": context.upload_root,
        "outputs": context.output_root,
        "state": context.state_root,
    }.items():
        probe = directory / ".write_test"
        writable = False
        error = ""
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            writable = True
        except Exception as exc:
            error = str(exc)
        checks[name] = {"path": str(directory), "writable": writable, "error": error}
    return {
        "status": "ok" if all(item["writable"] for item in checks.values()) else "attention",
        "server_time": now_iso(),
        "workspace_id": context.user_id,
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "free_percent": round((disk.free / disk.total) * 100, 2) if disk.total else 0,
        },
        "directories": checks,
        "services": {
            "xml": context.xml_service.readiness(),
            "invoices": context.invoice_service.readiness(),
            "reports": context.report_service.readiness(),
            "dacte": context.dacte_service.readiness(),
            "signatures": context.signature_service.readiness(),
        },
        "process": {
            "uptime_seconds": int(max(0, time.time() - PROCESS_STARTED_AT)),
            "memory_bytes": _process_memory_bytes(),
            "engine": engine_state_snapshot(),
        },
        "cloudflare": _cloudflared_status() if include_infrastructure else {},
        "public_domain": _public_domain_probe() if include_infrastructure else {},
        "backups": list_workspace_backups(context, AuthenticatedUser(context.user_id, "workspace", "Workspace", "admin"), limit=5) if include_admin else [],
        "recoverable_jobs": recoverable_jobs(context),
        "recent_errors": _recent_audit_errors(5) if include_admin else [],
    }


def create_workspace_backup(context: WorkspaceContext, user: AuthenticatedUser) -> dict[str, Any]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = safe_filename(f"central_cte_backup_{user.username}_{timestamp}.zip")
    target = unique_destination(BACKUP_ROOT, filename)
    entries: list[dict[str, Any]] = []
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(context.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(context.root)
            archive.write(path, f"workspace/{str(relative).replace(os.sep, '/')}")
            entries.append({
                "path": str(relative).replace(os.sep, "/"),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        manifest = {
            "project": "Central CT-e / DACTE",
            "version": APP_VERSION,
            "engine": ENGINE_VERSION,
            "created_at": now_iso(),
            "created_by": user.as_public_dict(),
            "workspace_id": context.user_id,
            "file_count": len(entries),
            "files": entries,
        }
        archive.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    with zipfile.ZipFile(target, "r") as archive:
        corrupt = archive.testzip()
        if corrupt:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"O backup ficou corrompido na entrada {corrupt}.")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "name": target.name,
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "sha256": digest,
        "files": len(entries),
        "created_at": now_iso(),
    }


def list_workspace_backups(context: WorkspaceContext, user: AuthenticatedUser, limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(BACKUP_ROOT.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            with zipfile.ZipFile(path, "r") as archive:
                manifest = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
            if str(manifest.get("workspace_id") or "") != context.user_id:
                continue
            rows.append({
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "created_at": manifest.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                "files": int(manifest.get("file_count") or 0),
                "version": manifest.get("version") or "",
                "created_by": (manifest.get("created_by") or {}).get("username") if isinstance(manifest.get("created_by"), dict) else "",
            })
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows


def restore_workspace_backup(context: WorkspaceContext, user: AuthenticatedUser, payload: bytes, original_name: str) -> dict[str, Any]:
    if not payload or len(payload) > MAX_BACKUP_UPLOAD_BYTES:
        raise ValueError(f"O backup deve ter até {MAX_BACKUP_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError("O arquivo enviado não é um ZIP de backup válido.")

    staging_root = Path(tempfile.mkdtemp(prefix="central_cte_restore_", dir=str(BACKUP_ROOT)))
    extracted_workspace = staging_root / "workspace"
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = archive.namelist()
            if "backup_manifest.json" not in names:
                raise ValueError("O ZIP não contém backup_manifest.json.")
            manifest = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
            if str(manifest.get("project") or "") != "Central CT-e / DACTE":
                raise ValueError("O arquivo não pertence ao Central CT-e / DACTE.")
            members = [item for item in archive.infolist() if not item.is_dir() and item.filename.startswith("workspace/")]
            if not members:
                raise ValueError("O backup não contém arquivos de workspace.")
            if len(members) > MAX_BACKUP_FILES:
                raise ValueError("O backup contém arquivos demais para uma restauração segura.")
            total = sum(max(0, int(item.file_size)) for item in members)
            if total > MAX_BACKUP_EXTRACTED_BYTES:
                raise ValueError("O conteúdo descompactado ultrapassa o limite de 2 GB.")
            expected = {
                str(item.get("path") or ""): item
                for item in (manifest.get("files") or [])
                if isinstance(item, dict) and item.get("path")
            }
            for member in members:
                relative_name = member.filename[len("workspace/"):]
                relative = Path(relative_name)
                if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                    raise ValueError("O backup contém um caminho inseguro.")
                target = (extracted_workspace / relative).resolve()
                if extracted_workspace.resolve() not in target.parents:
                    raise ValueError("O backup tentou gravar fora do workspace.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                record = expected.get(relative_name.replace("\\", "/"))
                if record:
                    if int(record.get("size_bytes") or target.stat().st_size) != target.stat().st_size:
                        raise ValueError(f"Tamanho divergente no arquivo {relative_name}.")
                    digest = str(record.get("sha256") or "").lower()
                    if digest and hashlib.sha256(target.read_bytes()).hexdigest().lower() != digest:
                        raise ValueError(f"Hash divergente no arquivo {relative_name}.")

        emergency = create_workspace_backup(context, user)
        previous_root = BACKUP_ROOT / f"workspace_pre_restore_{context.user_id}_{uuid.uuid4().hex[:10]}"
        with WORKSPACE_LOCK:
            WORKSPACE_CACHE.pop(context.user_id, None)
            RECOVERED_WORKSPACES.discard(context.user_id)
            try:
                context.root.rename(previous_root)
                extracted_workspace.rename(context.root)
            except Exception:
                if context.root.exists():
                    shutil.rmtree(context.root, ignore_errors=True)
                if previous_root.exists():
                    previous_root.rename(context.root)
                raise
        shutil.rmtree(previous_root, ignore_errors=True)
        restored = get_workspace(context.user_id)
        ensure_job_recovery(restored)
        receipt = {
            "restored_at": now_iso(),
            "source_name": safe_filename(original_name or "backup.zip"),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "source_version": manifest.get("version") or "",
            "files": len(members),
            "emergency_backup": emergency,
        }
        write_json_atomic(restored.state_root / "restore_last_run.json", receipt)
        return receipt
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


class LocalWebHandler(BaseHTTPRequestHandler):
    server_version = "CentralCTeLocal/2.0"

    def setup(self) -> None:
        super().setup()
        self.request_id = uuid.uuid4().hex[:16]
        self.session_token = ""
        self.session = None
        self.user = None
        self.workspace = DEFAULT_WORKSPACE

    def _prepare_request_context(self) -> None:
        self.session_token = self._read_session_cookie()
        self.session = AUTH.get_session(self.session_token)
        self.user = self.session.get("user") if isinstance(self.session, dict) else None
        self.workspace = get_workspace(self.user.id) if isinstance(self.user, AuthenticatedUser) else DEFAULT_WORKSPACE
        ensure_job_recovery(self.workspace)

    def _read_session_cookie(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
            morsel = cookie.get(SESSION_COOKIE_NAME)
            return morsel.value if morsel else ""
        except Exception:
            return ""

    @property
    def remote_key(self) -> str:
        direct = str(self.client_address[0] if self.client_address else "unknown")
        if os.environ.get("CENTRAL_CTE_TRUST_PROXY", "").strip() != "1":
            return direct
        forwarded = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        if not forwarded:
            return direct
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            return direct

    def _host_allowed(self) -> bool:
        configured = os.environ.get("CENTRAL_CTE_ALLOWED_HOSTS", "").strip()
        if not configured:
            return True
        host = self.headers.get("Host", "").split(":", 1)[0].strip().lower()
        allowed = {item.strip().lower() for item in configured.split(",") if item.strip()}
        for pattern in allowed:
            if pattern == "*":
                return True
            if pattern.startswith("*."):
                suffix = pattern[1:]
                if host.endswith(suffix) and host != suffix[1:]:
                    return True
            elif host == pattern:
                return True
        return False

    def send_response(self, code: int, message: str | None = None) -> None:
        metric_increment("requests_total")
        metric_status(code)
        super().send_response(code, message)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[%s] [%s] %s\n" % (self.log_date_time_string(), self.request_id, fmt % args))

    def _security_headers(self, *, static: bool = False) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'")
        self.send_header("X-Request-ID", self.request_id)
        if not static:
            self.send_header("Cache-Control", "no-store")

    def _set_session_cookie(self, token: str, *, clear: bool = False) -> None:
        value = "" if clear else token
        max_age = 0 if clear else 8 * 60 * 60
        secure = os.environ.get("CENTRAL_CTE_HTTPS", "").strip() == "1"
        cookie = f"{SESSION_COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        if secure:
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def send_json(self, payload: Any, status: int = 200, *, session_cookie: str | None = None, clear_cookie: bool = False) -> None:
        data = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        if session_cookie is not None or clear_cookie:
            self._set_session_cookie(session_cookie or "", clear=clear_cookie)
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, payload: str, status: int = 200, *, content_type: str = "text/plain; charset=utf-8") -> None:
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, message: str, status: int = 400, **extra: Any) -> None:
        self.send_json({"ok": False, "error": message, "request_id": self.request_id, **extra}, status)

    def read_body(self, maximum: int = MAX_UPLOAD_BYTES) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length inválido.") from exc
        if length < 0 or length > maximum:
            raise ValueError(f"Conteúdo acima do limite de {maximum // (1024 * 1024)} MB.")
        return self.rfile.read(length)

    def _auth_payload(self) -> dict[str, Any]:
        security_state = AUTH.user_security_state(self.user.id) if isinstance(self.user, AuthenticatedUser) else {}
        return {
            "setup_required": AUTH.setup_required(),
            "authenticated": isinstance(self.user, AuthenticatedUser),
            "user": self.user.as_public_dict() if isinstance(self.user, AuthenticatedUser) else None,
            "csrf": str(self.session.get("csrf") or "") if isinstance(self.session, dict) else "",
            "session_expires_at": float(self.session.get("expires_at") or 0) if isinstance(self.session, dict) else 0,
            "must_change_password": bool(security_state.get("must_change_password", False)),
            "password_changed_at": str(security_state.get("password_changed_at") or ""),
            "capabilities": DEVELOPER_TOOLS.capabilities(self.user),
        }

    def require_auth(self, roles: set[str] | None = None) -> bool:
        if not isinstance(self.user, AuthenticatedUser) or not isinstance(self.session, dict):
            self.send_error_json("Autenticação necessária.", 401, code="AUTH_REQUIRED")
            return False
        if roles and self.user.role not in roles:
            self.send_error_json("Seu perfil não possui permissão para esta operação.", 403, code="FORBIDDEN")
            return False
        return True

    def require_capability(self, capability: str) -> bool:
        if not self.require_auth():
            return False
        if not DEVELOPER_TOOLS.capabilities(self.user).get(capability, False):
            self.send_error_json("Seu perfil não possui permissão para esta operação.", 403, code="FORBIDDEN")
            return False
        return True

    def require_csrf(self) -> bool:
        if not isinstance(self.session, dict) or not AUTH.verify_csrf(self.session, self.headers.get("X-CSRF-Token", "")):
            self.send_error_json("Token de segurança inválido. Atualize a página e tente novamente.", 403, code="CSRF_INVALID")
            return False
        return True

    def audit(self, action: str, outcome: str = "success", **metadata: Any) -> None:
        AUTH.audit(
            action,
            user=self.user if isinstance(self.user, AuthenticatedUser) else None,
            outcome=outcome,
            remote=self.remote_key,
            request_id=self.request_id,
            metadata=metadata,
        )

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_allowed():
            return self.send_error_json("Host não autorizado.", 421, code="HOST_NOT_ALLOWED")
        self._prepare_request_context()
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/ready":
            readiness = production_readiness()
            return self.send_json({
                "ok": readiness["ready"],
                "version": readiness["version"],
                "engine": readiness["engine"],
                "uptime_seconds": readiness["uptime_seconds"],
            }, 200 if readiness["ready"] else 503)
        if path == "/api/metrics":
            expected = os.environ.get("CENTRAL_CTE_METRICS_TOKEN", "").strip()
            supplied = self.headers.get("X-Metrics-Token", "").strip()
            if expected and not hmac.compare_digest(supplied, expected):
                return self.send_error_json("Métricas não autorizadas.", 403)
            return self.send_text(prometheus_metrics(), content_type="text/plain; version=0.0.4; charset=utf-8")
        if path == "/api/health":
            return self.send_json({
                "ok": True,
                "version": APP_VERSION,
                "engine": ENGINE_VERSION,
                "time": now_iso(),
                "setup_required": AUTH.setup_required(),
            })
        if path == "/api/auth/status":
            return self.send_json({"ok": True, "data": self._auth_payload()})
        if not path.startswith("/api/"):
            return self.serve_static(path)
        if not self.require_auth():
            return
        if AUTH.requires_password_change(self.user.id) and path != "/api/auth/status":
            return self.send_error_json(
                "Sua senha precisa ser alterada antes de continuar.",
                403,
                code="PASSWORD_CHANGE_REQUIRED",
            )
        context = self.workspace
        if path == "/api/bootstrap":
            payload = build_bootstrap(context, self.user)
            payload["auth"]["csrf"] = str(self.session.get("csrf") or "")
            return self.send_json({"ok": True, "data": payload})
        if path == "/api/xmls":
            return self.send_json({"ok": True, "data": scan_xmls(context)})
        if path == "/api/invoices":
            return self.send_json({"ok": True, "data": scan_invoices(context)})
        if path == "/api/partners":
            return self.send_json({"ok": True, "data": scan_partners(context)})
        if path == "/api/reports":
            caps = DEVELOPER_TOOLS.capabilities(self.user)
            return self.send_json({"ok": True, "data": scan_reports(context, include_technical=caps.get("can_view_technical_reports", False))})
        if path == "/api/reports/status":
            return self.send_json({"ok": True, "data": context.report_service.readiness()})
        if path == "/api/dacte/status":
            return self.send_json({"ok": True, "data": context.dacte_service.readiness()})
        if path in {"/api/signatures/status", "/api/signatures/profiles"}:
            return self.send_json({"ok": True, "data": context.signature_service.readiness()})
        if path == "/api/qa/attachment":
            if not self.require_capability("can_view_qa"):
                return
            attachment_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                return self.serve_file(qa_attachment_path(attachment_id), download=False)
            except FileNotFoundError:
                return self.send_error_json("Anexo do relato não localizado.", 404)
        if path == "/api/developer/qa/export":
            if not self.require_capability("can_view_qa"):
                return
            try:
                return self.serve_file(DEVELOPER_TOOLS.export_qa_bundle(context), download=True)
            except Exception as exc:
                return self.send_error_json(f"Não foi possível exportar o caderno com imagens: {exc}", 500)
        if path == "/api/qa":
            if not self.require_capability("can_view_qa"):
                return
            return self.send_json({"ok": True, "data": read_json(context.qa_path, [])})
        if path == "/api/settings":
            return self.send_json({"ok": True, "data": {**DEFAULT_SETTINGS, **read_json(context.settings_path, {})}})
        if path == "/api/system/health":
            force = parse_qs(parsed.query).get("force", [""])[0] == "1"
            if force:
                _public_domain_probe(force=True)
            caps = DEVELOPER_TOOLS.capabilities(self.user)
            return self.send_json({
                "ok": True,
                "data": workspace_health(
                    context,
                    include_admin=caps.get("can_view_audit", False),
                    include_infrastructure=caps.get("can_view_infrastructure", False),
                ),
            })
        if path == "/api/jobs/recovery":
            return self.send_json({"ok": True, "data": recoverable_jobs(context)})
        if path == "/api/admin/backups":
            if not self.require_capability("can_manage_backups"):
                return
            return self.send_json({"ok": True, "data": list_workspace_backups(context, self.user)})
        if path == "/api/admin/users":
            if not self.require_capability("can_manage_users"):
                return
            return self.send_json({"ok": True, "data": AUTH.list_users(actor=self.user)})
        if path == "/api/admin/audit":
            if not self.require_capability("can_view_audit"):
                return
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["200"])[0] or 200)
            return self.send_json({"ok": True, "data": AUTH.recent_audit(actor=self.user, limit=limit)})
        if path == "/api/developer/features":
            if not self.require_capability("can_manage_features"):
                return
            return self.send_json({"ok": True, "data": DEVELOPER_TOOLS.load_features()})
        if path == "/api/base/status":
            if not self.require_capability("can_import_base"):
                return
            return self.send_json({"ok": True, "data": DEVELOPER_TOOLS.base_overview(context)})
        if path == "/api/developer/postgres/status":
            if not self.require_capability("can_manage_database_integration"):
                return
            return self.send_json({"ok": True, "data": SSW_POSTGRES.public_status()})
        if path == "/api/developer/postgres/bridge-script":
            if not self.require_capability("can_manage_database_integration"):
                return
            return self.serve_file(WEB_ROOT / "tools" / "SSW_POSTGRES_BRIDGE.ps1", download=True)
        if path == "/api/developer/partners/files":
            if not self.require_capability("can_manage_partner_tables"):
                return
            return self.send_json({"ok": True, "data": DEVELOPER_TOOLS.partner_files_overview(context)})
        if path == "/api/developer/partners/model":
            if not self.require_capability("can_manage_partner_tables"):
                return
            return self.serve_file(DEVELOPER_TOOLS.export_partner_registration_template(context), download=True)
        if path == "/api/developer/partners/template":
            if not self.require_capability("can_manage_partner_tables"):
                return
            return self.serve_file(DEVELOPER_TOOLS.export_partner_files_zip(context), download=True)
        if path == "/api/developer/partners/file":
            if not self.require_capability("can_manage_partner_tables"):
                return
            partner_id = parse_qs(parsed.query).get("partner_id", [""])[0]
            return self.serve_file(DEVELOPER_TOOLS.partner_file(context, partner_id), download=True)
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            job = _job_snapshot(job_id, context)
            if not job:
                return self.send_error_json("Processamento não encontrado.", 404)
            return self.send_json({"ok": True, "data": job})
        if path == "/api/process/xml/status":
            return self.send_json({"ok": True, "data": active_xml_job(context) or read_json(context.xml_service.last_run_path, {})})
        if path == "/api/process/invoices/status":
            return self.send_json({"ok": True, "data": active_invoice_job(context) or read_json(context.invoice_service.last_run_path, {})})
        if path == "/api/process/dacte/status":
            return self.send_json({"ok": True, "data": active_dacte_job(context) or read_json(context.dacte_service.last_run_path, {})})
        if path == "/api/process/signatures/status":
            return self.send_json({"ok": True, "data": active_signature_job(context) or read_json(context.signature_service.last_run_path, {})})
        if path.startswith("/api/file"):
            query = parse_qs(parsed.query)
            raw = query.get("path", [""])[0]
            try:
                target = Path(raw).resolve()
                caps = DEVELOPER_TOOLS.capabilities(self.user)
                allowed_roots = [
                    context.output_root.resolve(),
                    (context.root / "sessoes" / "assinaturas").resolve(),
                    (PROJECT_ROOT / "relatorios").resolve(),
                ]
                if caps.get("can_view_technical_reports"):
                    allowed_roots.extend([
                        context.state_root.resolve(),
                        (PROJECT_ROOT / "saida_html").resolve(),
                        (PROJECT_ROOT / "logs").resolve(),
                    ])
                if caps.get("can_manage_backups"):
                    allowed_roots.append(BACKUP_ROOT.resolve())
                if not any(target == root or root in target.parents for root in allowed_roots) or not target.is_file():
                    raise ValueError("Arquivo não autorizado.")
                inline = query.get("inline", [""])[0].strip().lower() in {"1", "true", "yes"}
                return self.serve_file(target, download=not inline)
            except Exception as exc:
                return self.send_error_json(str(exc), 404)
        return self.send_error_json("Rota não encontrada.", 404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_allowed():
            return self.send_error_json("Host não autorizado.", 421, code="HOST_NOT_ALLOWED")
        self._prepare_request_context()
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/auth/setup":
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                user = AUTH.setup_developer(payload.get("username"), payload.get("display_name"), payload.get("password"))
                metric_increment("login_success_total")
                token, session = AUTH.create_session(user)
                self.user, self.session, self.session_token = user, session, token
                self.workspace = get_workspace(user.id)
                return self.send_json({"ok": True, "data": self._auth_payload()}, 201, session_cookie=token)

            if parsed.path == "/api/integrations/ssw-postgres/publish":
                authorization = str(self.headers.get("Authorization") or "").strip()
                token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
                if not SSW_POSTGRES.verify_bridge_token(token):
                    return self.send_error_json("Token da ponte PostgreSQL inválido.", 401, code="BRIDGE_TOKEN_INVALID")
                body = self.read_body(64 * 1024 * 1024)
                payload = SSW_POSTGRES.decode_bridge_payload(body, self.headers.get("Content-Encoding", ""))
                result = SSW_POSTGRES.publish_snapshot(payload)
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/auth/login":
                allowed, retry_after = AUTH.can_attempt_login(self.remote_key)
                if not allowed:
                    return self.send_error_json("Muitas tentativas. Aguarde antes de tentar novamente.", 429, code="LOGIN_RATE_LIMIT", retry_after=retry_after)
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                user = AUTH.authenticate(payload.get("username"), payload.get("password"), remote_key=self.remote_key)
                if user is None:
                    metric_increment("login_failure_total")
                    return self.send_error_json("Usuário ou senha inválidos.", 401, code="LOGIN_INVALID")
                metric_increment("login_success_total")
                token, session = AUTH.create_session(user)
                self.user, self.session, self.session_token = user, session, token
                self.workspace = get_workspace(user.id)
                return self.send_json({"ok": True, "data": self._auth_payload()}, session_cookie=token)

            if not self.require_auth():
                return
            if not self.require_csrf():
                return

            if parsed.path == "/api/auth/logout":
                AUTH.destroy_session(self.session_token, remote=self.remote_key)
                self.session = None
                self.user = None
                return self.send_json({"ok": True, "data": {"authenticated": False}}, clear_cookie=True)

            if parsed.path == "/api/auth/password/change":
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                user = AUTH.change_own_password(
                    self.user.id,
                    payload.get("current_password"),
                    payload.get("new_password"),
                    actor=self.user,
                )
                token, session = AUTH.create_session(user)
                self.user, self.session, self.session_token = user, session, token
                self.workspace = get_workspace(user.id)
                return self.send_json({"ok": True, "data": self._auth_payload()}, session_cookie=token)

            if AUTH.requires_password_change(self.user.id):
                return self.send_error_json(
                    "Sua senha precisa ser alterada antes de continuar.",
                    403,
                    code="PASSWORD_CHANGE_REQUIRED",
                )

            context = self.workspace
            if parsed.path == "/api/developer/postgres/bridge-token/rotate":
                if not self.require_capability("can_manage_database_integration"):
                    return
                token = SSW_POSTGRES.rotate_bridge_token()
                self.audit("developer.postgres.bridge_token.rotate")
                return self.send_json({"ok": True, "data": {"token": token, "shown_once": True, "status": SSW_POSTGRES.public_status()}})

            if parsed.path == "/api/developer/postgres/test":
                if not self.require_capability("can_manage_database_integration"):
                    return
                result = SSW_POSTGRES.test_direct()
                self.audit("developer.postgres.test", ok=bool(result.get("ok")))
                return self.send_json({"ok": bool(result.get("ok")), "data": result, "error": result.get("error") or ""}, 200 if result.get("ok") else 422)

            if parsed.path == "/api/developer/postgres/sync-direct":
                if not self.require_capability("can_manage_database_integration"):
                    return
                payload = json.loads(self.read_body(128 * 1024).decode("utf-8") or "{}")
                result = SSW_POSTGRES.sync_direct(max_rows=int(payload.get("max_rows") or 300000))
                self.audit("developer.postgres.sync_direct", row_count=result.get("row_count"), source=result.get("source"))
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/developer/postgres/compare":
                if not self.require_capability("can_manage_database_integration"):
                    return
                base_source = context.xml_service.resolve_base_source()
                engine = context.xml_service._load_engine()
                base_data = engine.load_rodovitor_base_cached(base_source, force=False)
                base_rows = list(base_data.get("rows") or []) if isinstance(base_data, dict) else []
                result = SSW_POSTGRES.compare_with_base_rows(base_rows)
                self.audit("developer.postgres.compare", matched=result.get("matched"), freight_equal=result.get("freight_equal"), freight_different=result.get("freight_different"))
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/admin/users":
                if not self.require_capability("can_manage_users"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                created = AUTH.create_user(
                    payload.get("username"),
                    payload.get("display_name"),
                    payload.get("role"),
                    payload.get("password"),
                    actor=self.user,
                    must_change_password=bool(payload.get("must_change_password", False)),
                )
                get_workspace(created.id)
                return self.send_json({"ok": True, "data": created.as_public_dict()}, 201)

            if parsed.path == "/api/admin/users/password":
                if not self.require_capability("can_manage_users"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                user_id = str(payload.get("user_id") or "")
                must_change = bool(payload.get("must_change_password", True))
                if bool(payload.get("generate_temporary", False)):
                    result = AUTH.create_temporary_password(
                        user_id,
                        actor=self.user,
                        must_change_password=must_change,
                    )
                    return self.send_json({"ok": True, "data": result})
                updated = AUTH.reset_password(
                    user_id,
                    payload.get("password"),
                    actor=self.user,
                    must_change_password=must_change,
                )
                return self.send_json({
                    "ok": True,
                    "data": {
                        "user": updated.as_public_dict(),
                        "must_change_password": must_change,
                        "sessions_revoked": True,
                    },
                })

            if parsed.path == "/api/developer/users/sessions/revoke":
                if not self.require_capability("can_edit_users"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                result = AUTH.revoke_sessions_managed(str(payload.get("user_id") or ""), actor=self.user)
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/developer/users/update":
                if not self.require_capability("can_edit_users"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                updated = AUTH.update_user(
                    str(payload.get("user_id") or ""),
                    username=payload.get("username"),
                    display_name=payload.get("display_name"),
                    role=payload.get("role"),
                    active=payload.get("active", True),
                    actor=self.user,
                )
                return self.send_json({"ok": True, "data": updated.as_public_dict()})

            if parsed.path == "/api/developer/users/delete":
                if not self.require_capability("can_edit_users"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                result = AUTH.delete_user(str(payload.get("user_id") or ""), actor=self.user)
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/admin/backup":
                if not self.require_capability("can_manage_backups"):
                    return
                result = create_workspace_backup(context, self.user)
                self.audit("admin.backup.create", path=result["path"], files=result["files"], sha256=result["sha256"])
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/admin/backup/restore":
                if not self.require_capability("can_manage_backups"):
                    return
                filename = safe_filename(self.headers.get("X-Filename", "backup.zip"))
                body = self.read_body(MAX_BACKUP_UPLOAD_BYTES)
                result = restore_workspace_backup(context, self.user, body, filename)
                self.audit("admin.backup.restore", source=filename, files=result.get("files"), sha256=result.get("source_sha256"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/developer/features":
                if not self.require_capability("can_manage_features"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                flags = DEVELOPER_TOOLS.save_features(payload)
                self.audit("developer.features.save", flags=flags)
                return self.send_json({"ok": True, "data": flags})

            if parsed.path == "/api/developer/qa/clear":
                if not self.require_capability("can_clear_qa"):
                    return
                result = DEVELOPER_TOOLS.clear_qa(context)
                self.audit("developer.qa.clear", deleted=result.get("deleted"), archive_path=result.get("archive_path"))
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/base/stage":
                if not self.require_capability("can_import_base"):
                    return
                result = DEVELOPER_TOOLS.stage_base_file(
                    context,
                    self.headers.get("X-Batch-ID", ""),
                    self.headers.get("X-Filename", "base.sswweb"),
                    self.read_body(220 * 1024 * 1024),
                )
                self.audit("base.stage", batch_id=result.get("batch_id"), filename=(result.get("file") or {}).get("name"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/base/commit":
                if not self.require_capability("can_import_base"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                result = DEVELOPER_TOOLS.commit_base_batch(context, payload.get("batch_id"), payload.get("expected_count"))
                self.audit("base.replace", file_count=result.get("active_file_count"), validated_rows=result.get("validated_rows"), previous_backup=result.get("previous_backup"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path in {"/api/developer/partners/replace", "/api/developer/partners/import"}:
                if not self.require_capability("can_manage_partner_tables"):
                    return
                filename = self.headers.get("X-Filename", "parceiro.xlsx")
                result = DEVELOPER_TOOLS.import_partner_file(
                    context,
                    self.read_body(40 * 1024 * 1024),
                    filename,
                )
                self.audit(
                    "developer.partner_file.import",
                    partner_id=result.get("partner_id"),
                    rules=result.get("rules"),
                    sha256=result.get("sha256"),
                )
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/developer/partners/delete":
                if not self.require_capability("can_manage_partner_tables"):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                result = DEVELOPER_TOOLS.delete_partner_file(context, payload.get("partner_id"))
                self.audit(
                    "developer.partner_file.delete",
                    partner_id=result.get("partner_id"),
                    backup=result.get("backup"),
                )
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/jobs/retry":
                if not self.require_auth({"admin", "operador"}):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                job_id = str(payload.get("job_id") or "").strip()
                job = _job_snapshot(job_id, context)
                if not job:
                    raise KeyError("Execução não encontrada.")
                if str(job.get("state")) not in {"failed", "interrupted"}:
                    raise ValueError("Somente execuções falhas ou interrompidas podem ser repetidas.")
                kind = str(job.get("kind") or "")
                if kind not in {"xml", "invoices", "dacte", "signature"}:
                    raise ValueError("Tipo de processamento não reconhecido.")
                _update_job(job_id, recoverable=False, recovery_action="retried", recovered_at=now_iso())
                if kind == "xml":
                    result = start_xml_job(context)
                elif kind == "invoices":
                    result = start_invoice_job(context)
                elif kind == "dacte":
                    request = job.get("request") if isinstance(job.get("request"), dict) else {}
                    result = start_dacte_job(
                        context,
                        list(request.get("paths") or []),
                        mode=str(request.get("mode") or job.get("mode") or "batch"),
                        include_compact=bool(request.get("include_compact", True)),
                    )
                else:
                    request = job.get("request") if isinstance(job.get("request"), dict) else {}
                    result = start_signature_job(
                        context,
                        list(request.get("paths") or []),
                        str(request.get("profile_id") or ""),
                        str(request.get("date_text") or ""),
                        mode=str(request.get("mode") or job.get("mode") or "batch"),
                        include_compact=bool(request.get("include_compact", True)),
                    )
                self.audit("job.recovery.retry", old_job_id=job_id, new_job_id=result.get("id"), kind=job.get("kind"))
                return self.send_json({"ok": True, "data": result}, 202)

            if parsed.path == "/api/jobs/discard":
                if not self.require_auth({"admin", "operador"}):
                    return
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                job_id = str(payload.get("job_id") or "").strip()
                job = _job_snapshot(job_id, context)
                if not job:
                    raise KeyError("Execução não encontrada.")
                _update_job(job_id, state="discarded", recoverable=False, recovery_action="discarded", finished_at=now_iso(), message="Registro de recuperação descartado pelo usuário.")
                self.audit("job.recovery.discard", job_id=job_id, kind=job.get("kind"))
                return self.send_json({"ok": True, "data": {"discarded": True}})

            if self.user.role == "consulta" and parsed.path != "/api/qa":
                return self.send_error_json("O perfil Consulta possui acesso somente para leitura.", 403, code="READ_ONLY_ROLE")

            if parsed.path == "/api/upload":
                category = self.headers.get("X-Category", "").strip().lower()
                if category not in context.upload_categories:
                    return self.send_error_json("Categoria de upload inválida.", 400)
                caps = DEVELOPER_TOOLS.capabilities(self.user)
                if category == "bases" and not caps.get("can_import_base"):
                    return self.send_error_json("Somente Administrador ou Desenvolvedor pode importar a Base SSW.", 403)
                if category == "tabelas" and not caps.get("can_manage_partner_tables"):
                    return self.send_error_json("Somente o perfil Desenvolvedor pode substituir tabelas de parceiros.", 403)
                filename = validate_upload_filename(category, self.headers.get("X-Filename", "arquivo"))
                limit = UPLOAD_LIMITS.get(category, MAX_UPLOAD_BYTES)
                body = self.read_body(limit)
                validate_upload_content(category, body)
                digest = hashlib.sha256(body).hexdigest()
                if category == "xml":
                    duplicate = find_duplicate_xml(context.upload_categories[category], body, digest)
                    if duplicate:
                        identity = str(duplicate.get("identity") or "")
                        cte_hint = f" Chave fiscal: {identity}." if identity else ""
                        message = (
                            f"O XML {filename} não foi importado porque duplica {duplicate.get('file') or 'um arquivo já existente no lote'}."
                            f"{cte_hint} O arquivo já existente foi mantido e a cópia foi bloqueada."
                        )
                        self.audit(
                            "upload.duplicate_blocked",
                            category=category,
                            filename=filename,
                            duplicate_of=duplicate.get("file"),
                            match=duplicate.get("match"),
                            sha256=digest,
                            identity=identity,
                        )
                        return self.send_error_json(
                            message,
                            409,
                            code="DUPLICATE_XML",
                            duplicate={
                                "file": duplicate.get("file"),
                                "match": duplicate.get("match"),
                                "identity": identity,
                                "sha256": duplicate.get("sha256"),
                            },
                        )
                destination = unique_destination(context.upload_categories[category], filename)
                destination.write_bytes(body)
                metric_increment("bytes_uploaded_total", len(body))
                self.audit("upload.create", category=category, filename=destination.name, size_bytes=len(body), sha256=digest)
                return self.send_json({"ok": True, "file": {"name": destination.name, "path": str(destination), "size_bytes": len(body), "sha256": digest}})

            if parsed.path == "/api/qa":
                if not self.require_capability("can_submit_qa"):
                    return
                payload = json.loads(self.read_body(10 * 1024 * 1024).decode("utf-8") or "{}")
                notes = read_json(context.qa_path, [])
                if not isinstance(notes, list):
                    notes = []
                note_id = str(payload.get("id") or f"QA-{int(time.time() * 1000)}")[:80]
                existing_index = next((index for index, item in enumerate(notes) if item.get("id") == note_id), None)
                previous = notes[existing_index] if existing_index is not None and isinstance(notes[existing_index], dict) else {}
                attachment = save_qa_attachment(payload.get("attachment"), note_id) or previous.get("attachment")
                note = {
                    "id": note_id,
                    "type": str(payload.get("type") or "bug"),
                    "page": str(payload.get("page") or "Geral"),
                    "title": str(payload.get("title") or "Sem título").strip()[:200],
                    "observed": str(payload.get("observed") or "").strip()[:8000],
                    "expected": str(payload.get("expected") or "").strip()[:8000],
                    "severity": str(payload.get("severity") or "média"),
                    "status": str(payload.get("status") or "aberto"),
                    "created_at": previous.get("created_at") or payload.get("created_at") or now_iso(),
                    "updated_at": now_iso(),
                    "created_by": previous.get("created_by") or self.user.as_public_dict(),
                }
                if attachment:
                    note["attachment"] = attachment
                if existing_index is None:
                    notes.insert(0, note)
                else:
                    notes[existing_index] = note
                write_json_atomic(context.qa_path, notes)
                self.audit("qa.save", note_id=note["id"], note_type=note["type"], attachment=bool(attachment))
                return self.send_json({"ok": True, "data": note})

            if parsed.path == "/api/settings":
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                allowed = {
                    "theme": {"claro", "escuro", "sistema"},
                    "density": {"compacta", "confortavel"},
                    "sidebar": {"padrao", "compacta"},
                    "start_page": {"dashboard", "xml", "invoices", "audit", "partners", "signature", "reports", "settings"},
                }
                current = {**DEFAULT_SETTINGS, **read_json(context.settings_path, {})}
                for key, values in allowed.items():
                    value = payload.get(key)
                    if value in values:
                        current[key] = value
                write_json_atomic(context.settings_path, current)
                return self.send_json({"ok": True, "data": current})

            if parsed.path == "/api/xml/clear":
                result = clear_xml_workspace(context)
                self.audit(
                    "xml.library.clear",
                    deleted_xml_count=result.get("deleted_xml_count"),
                    reports_preserved=True,
                )
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/invoices/clear":
                result = clear_invoice_workspace(context)
                self.audit(
                    "invoice.library.clear",
                    deleted_invoice_count=result.get("deleted_invoice_count"),
                    reports_preserved=True,
                )
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/xml/complementary":
                payload = json.loads(self.read_body(2 * 1024 * 1024).decode("utf-8") or "{}")
                selected_paths = payload.get("paths") or []
                if not isinstance(selected_paths, list):
                    raise ValueError("A seleção de CT-es é inválida.")
                # A informação complementar pertence ao documento de impressão.
                # O XML fiscal original nunca é aberto para escrita.
                allowed = {str(path.resolve()): path.resolve() for path in xml_file_paths(context)}
                selected: list[Path] = []
                for raw in selected_paths:
                    resolved = str(Path(str(raw)).resolve())
                    path = allowed.get(resolved)
                    if path is None:
                        raise ValueError("Um dos XMLs selecionados não pertence à biblioteca autorizada.")
                    parsed_row = parse_xml_document(path)
                    if not parsed_row.get("cte") or "NF-E" in str(parsed_row.get("document_type") or "").upper():
                        raise ValueError(f"O arquivo {path.name} não é um CT-e válido.")
                    selected.append(path)
                action = str(payload.get("action") or "apply").strip().lower()
                if action == "remove":
                    result = context.dacte_service.remove_complementary_information(selected, xml_file_paths(context))
                    self.audit("xml.complementary.remove", documents=result.get("documents"), identities=result.get("removed_identities"))
                else:
                    result = context.dacte_service.apply_complementary_information(
                        selected, xml_file_paths(context), payload.get("text") or "",
                    )
                    self.audit("xml.complementary.apply", documents=result.get("documents"), characters=len(result.get("text") or ""))
                # Evita manter uma prévia antiga após alteração do conteúdo impresso.
                if context.dacte_service.preview_root.exists():
                    shutil.rmtree(context.dacte_service.preview_root, ignore_errors=True)
                context.dacte_service.preview_root.mkdir(parents=True, exist_ok=True)
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/process/xml/manual-status":
                if not self.require_capability("can_override_xml_status"):
                    return
                payload = json.loads(self.read_body(512 * 1024).decode("utf-8") or "{}")
                raw_path = str(payload.get("path") or "").strip()
                allowed = {str(item.resolve()): item.resolve() for item in xml_file_paths(context)}
                selected = allowed.get(str(Path(raw_path).resolve())) if raw_path else None
                if selected is None:
                    raise ValueError("O XML selecionado não pertence à biblioteca autorizada.")
                result = context.xml_service.set_manual_decision(
                    selected,
                    str(payload.get("decision") or ""),
                    str(payload.get("reason") or ""),
                    actor_id=str(self.user.id),
                    actor_name=str(self.user.display_name or self.user.username),
                )
                self.audit(
                    "xml.manual_status",
                    cte=result.get("cte"),
                    decision=str(payload.get("decision") or ""),
                    decision_key=result.get("decision_key"),
                    reason=str(payload.get("reason") or "")[:500],
                    automatic_status=result.get("automatic_status"),
                    resulting_status=result.get("status"),
                )
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/process/xml":
                readiness = context.xml_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "XML_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço XML oficial não está pronto."}, 409)
                job = start_xml_job(context)
                self.audit("xml.process.start", job_id=job["id"], documents=job["total"])
                return self.send_json({"ok": True, "data": job}, 202)

            if parsed.path == "/api/process/invoices":
                readiness = context.invoice_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "INVOICE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de faturas oficial não está pronto."}, 409)
                job = start_invoice_job(context)
                self.audit("invoice.process.start", job_id=job["id"], documents=job["total"])
                return self.send_json({"ok": True, "data": job}, 202)

            if parsed.path == "/api/dacte/preview":
                readiness = context.dacte_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "DACTE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço oficial de DACTE não está pronto."}, 409)
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                with engine_execution("Prévia DACTE", context):
                    result = context.dacte_service.preview(
                        str(payload.get("path") or "").strip(),
                        xml_file_paths(context),
                        include_compact=bool(payload.get("include_compact", True)),
                    )
                self.audit("dacte.preview", cte=result.get("cte"), pages=result.get("pages"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/dacte/generate-job":
                readiness = context.dacte_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "DACTE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço oficial de DACTE não está pronto."}, 409)
                payload = json.loads(self.read_body(2 * 1024 * 1024).decode("utf-8") or "{}")
                selected_paths = payload.get("paths") or []
                if not isinstance(selected_paths, list):
                    raise ValueError("A seleção de CT-es é inválida.")
                result = start_dacte_job(
                    context,
                    [str(value or "") for value in selected_paths],
                    mode=str(payload.get("mode") or "batch"),
                    include_compact=bool(payload.get("include_compact", True)),
                )
                self.audit("dacte.generate.start", mode=payload.get("mode"), documents=len(selected_paths), job_id=result.get("id"), include_compact=bool(payload.get("include_compact", True)))
                return self.send_json({"ok": True, "data": result}, 202)

            if parsed.path == "/api/dacte/generate":
                readiness = context.dacte_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "DACTE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço oficial de DACTE não está pronto."}, 409)
                payload = json.loads(self.read_body(2 * 1024 * 1024).decode("utf-8") or "{}")
                selected_paths = payload.get("paths") or []
                if not isinstance(selected_paths, list):
                    raise ValueError("A seleção de CT-es é inválida.")
                with engine_execution("Geração DACTE", context):
                    result = context.dacte_service.generate(
                        selected_paths,
                        xml_file_paths(context),
                        mode=str(payload.get("mode") or "batch"),
                        include_compact=bool(payload.get("include_compact", True)),
                    )
                self.audit("dacte.generate", mode=payload.get("mode"), documents=result.get("documents"), path=result.get("path"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/signatures/profile":
                readiness = context.signature_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "SIGNATURE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de assinatura não está pronto."}, 409)
                payload = json.loads(self.read_body(512 * 1024).decode("utf-8") or "{}")
                profile_id = str(payload.get("id") or payload.get("profile_id") or "").strip()
                result = context.signature_service.update_profile(profile_id, payload) if profile_id else context.signature_service.create_profile(payload)
                self.audit("signature.profile.save", profile_id=result.get("id"), updated=bool(profile_id))
                return self.send_json({"ok": True, "data": result}, 200 if profile_id else 201)

            if parsed.path == "/api/signatures/profile/delete":
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                profile_id = str(payload.get("profile_id") or "")
                context.signature_service.delete_profile(profile_id)
                self.audit("signature.profile.delete", profile_id=profile_id)
                return self.send_json({"ok": True, "data": {"deleted": True}})

            if parsed.path == "/api/signatures/pdf-images":
                readiness = context.signature_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "SIGNATURE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de assinatura não está pronto."}, 409)
                filename = safe_filename(self.headers.get("X-Filename", "assinatura.pdf"))
                body = self.read_body(30 * 1024 * 1024)
                result = context.signature_service.extract_pdf_images(body, filename)
                self.audit(
                    "signature.pdf.read",
                    filename=filename,
                    pages=result.get("pages"),
                    candidates=len(result.get("candidates") or []),
                    sha256=result.get("pdf_sha256"),
                )
                return self.send_json({"ok": True, "data": result})

            if parsed.path == "/api/signatures/import":
                readiness = context.signature_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "SIGNATURE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de assinatura não está pronto."}, 409)
                payload = json.loads(self.read_body(60 * 1024 * 1024).decode("utf-8") or "{}")
                result = context.signature_service.import_browser_processed(payload)
                self.audit("signature.image.import", profile_id=(result.get("profile") or {}).get("id"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/signatures/registration-sheet":
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                with engine_execution("Folha de assinatura", context):
                    result = context.signature_service.registration_sheet(str(payload.get("profile_id") or ""))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/signatures/preview":
                readiness = context.signature_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "SIGNATURE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de assinatura não está pronto."}, 409)
                payload = json.loads(self.read_body(512 * 1024).decode("utf-8") or "{}")
                with engine_execution("Prévia DACTE assinado", context):
                    result = context.signature_service.preview(
                        str(payload.get("path") or ""),
                        xml_file_paths(context),
                        str(payload.get("profile_id") or ""),
                        payload.get("date_text") or "",
                        include_compact=bool(payload.get("include_compact", True)),
                    )
                self.audit("signature.preview", profile_id=payload.get("profile_id"), cte=result.get("cte"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/signatures/generate-job":
                readiness = context.signature_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "SIGNATURE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de assinatura não está pronto."}, 409)
                payload = json.loads(self.read_body(2 * 1024 * 1024).decode("utf-8") or "{}")
                selected_paths = payload.get("paths") or []
                if not isinstance(selected_paths, list):
                    raise ValueError("A seleção de CT-es é inválida.")
                result = start_signature_job(
                    context,
                    [str(value or "") for value in selected_paths],
                    str(payload.get("profile_id") or ""),
                    str(payload.get("date_text") or ""),
                    mode=str(payload.get("mode") or "batch"),
                    include_compact=bool(payload.get("include_compact", True)),
                )
                self.audit("signature.generate.start", profile_id=payload.get("profile_id"), mode=payload.get("mode"), documents=len(selected_paths), job_id=result.get("id"))
                return self.send_json({"ok": True, "data": result}, 202)

            if parsed.path == "/api/signatures/generate":
                readiness = context.signature_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "SIGNATURE_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço de assinatura não está pronto."}, 409)
                payload = json.loads(self.read_body(2 * 1024 * 1024).decode("utf-8") or "{}")
                selected_paths = payload.get("paths") or []
                if not isinstance(selected_paths, list):
                    raise ValueError("A seleção de CT-es é inválida.")
                with engine_execution("Geração DACTE assinado", context):
                    result = context.signature_service.generate(
                        selected_paths,
                        xml_file_paths(context),
                        str(payload.get("profile_id") or ""),
                        payload.get("date_text") or "",
                        mode=str(payload.get("mode") or "batch"),
                        include_compact=bool(payload.get("include_compact", True)),
                    )
                self.audit("signature.generate", profile_id=payload.get("profile_id"), mode=payload.get("mode"), documents=result.get("documents"), path=result.get("path"))
                return self.send_json({"ok": True, "data": result}, 201)

            if parsed.path == "/api/reports/generate":
                readiness = context.report_service.readiness()
                if not readiness.get("connected"):
                    return self.send_json({"ok": False, "code": "REPORT_ENGINE_NOT_READY", "error": readiness.get("status") or "O serviço oficial de relatórios não está pronto."}, 409)
                payload = json.loads(self.read_body(256 * 1024).decode("utf-8") or "{}")
                module = str(payload.get("module") or "").strip().lower()
                with engine_execution("Relatório XLSX", context):
                    result = context.report_service.generate(module, xml_paths=xml_file_paths(context), pdf_paths=invoice_file_paths(context), only_problem_invoices=bool(payload.get("only_problem_invoices", False)))
                self.audit("report.generate", module=module, path=result.get("path"), only_problem=bool(payload.get("only_problem_invoices", False)))
                return self.send_json({"ok": True, "data": result}, 201)

            return self.send_error_json("Rota não encontrada.", 404)
        except json.JSONDecodeError:
            self.audit("request.error", "failure", path=parsed.path, error="JSON inválido")
            return self.send_error_json("JSON inválido.", 400)
        except PermissionError as exc:
            self.audit("request.error", "failure", path=parsed.path, error=str(exc))
            return self.send_error_json(str(exc), 403)
        except KeyError as exc:
            return self.send_error_json(str(exc).strip("'"), 404)
        except ValueError as exc:
            self.audit("request.error", "failure", path=parsed.path, error=str(exc))
            return self.send_error_json(str(exc), 400)
        except Exception as exc:
            self.audit("request.error", "failure", path=parsed.path, error=str(exc))
            return self.send_error_json(f"Falha interna: {exc}", 500)

    def serve_static(self, requested_path: str) -> None:
        relative = unquote(requested_path.lstrip("/")) or "index.html"
        if relative.startswith("api/"):
            return self.send_error_json("Rota não encontrada.", 404)
        target = (STATIC_ROOT / relative).resolve()
        static = STATIC_ROOT.resolve()
        if static not in target.parents and target != static:
            return self.send_error(HTTPStatus.FORBIDDEN)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            if "." not in Path(relative).name:
                target = STATIC_ROOT / "index.html"
            else:
                return self.send_error(HTTPStatus.NOT_FOUND)
        self.serve_file(target)

    def serve_file(self, target: Path, download: bool = False) -> None:
        data = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"} else ""))
        self.send_header("Content-Length", str(len(data)))
        self._security_headers(static=True)
        self.send_header("Cache-Control", "no-cache" if target.suffix in {".html", ".js", ".css"} else "private, max-age=3600")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{safe_filename(target.name)}"')
        self.end_headers()
        self.wfile.write(data)


def pick_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise OSError("Nenhuma porta local disponível entre %s e %s." % (preferred, preferred + 29))


def main() -> int:
    parser = argparse.ArgumentParser(description="Central CT-e / DACTE — servidor web local")
    parser.add_argument("--host", default=os.environ.get("CENTRAL_CTE_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CENTRAL_CTE_PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--strict-port", action="store_true", default=os.environ.get("CENTRAL_CTE_STRICT_PORT", "").strip() == "1")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"} and os.environ.get("CENTRAL_CTE_ALLOW_REMOTE", "").strip() != "1":
        print("ERRO: acesso remoto está bloqueado por padrão.")
        print("Para uma futura VPS, use um proxy HTTPS e defina CENTRAL_CTE_ALLOW_REMOTE=1 conscientemente.")
        return 2
    ensure_job_recovery(DEFAULT_WORKSPACE)
    port = args.port if args.strict_port else pick_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), LocalWebHandler)
    server.daemon_threads = True
    url = f"http://{args.host}:{port}/"
    print("=" * 68)
    print(f"Central CT-e / DACTE {APP_VERSION}")
    print(f"Endereço local: {url}")
    print("Autenticação obrigatória, sessão HttpOnly e workspace separado por usuário.")
    print("Primeiro acesso: crie o Desenvolvedor inicial na tela exibida no navegador.")
    print("Pressione Ctrl+C para encerrar.")
    print("=" * 68)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url, new=2)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
