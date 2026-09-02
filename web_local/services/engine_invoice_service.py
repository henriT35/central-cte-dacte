# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

SERVICE_VERSION = "2.7.0 RC27.14 WEB/WINDOWS MVP13 R12.7"
RESULT_SCHEMA_VERSION = 3

# O leitor pypdf é distribuído em web_local/vendor para que o fluxo funcione
# mesmo quando o Python do computador não possui pacotes adicionais.
VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor"
if VENDOR_ROOT.is_dir() and str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def file_signature(paths: Iterable[Path]) -> str:
    parts: list[str] = []
    for path in sorted((Path(item).resolve() for item in paths), key=lambda item: str(item).lower()):
        try:
            stat = path.stat()
            parts.append(f"{path}|{stat.st_size}|{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{path}|ausente")
    return hashlib.sha256("\n".join(parts).encode("utf-8", errors="replace")).hexdigest()


def money_br(value: Any) -> str:
    try:
        return "R$ " + f"{float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _financial_action(status: str) -> str:
    normalized = " ".join(str(status or "").upper().split())
    if normalized == "OK PAGAR":
        return "Liberar pagamento"
    if normalized.startswith("PAGAR PARCIAL"):
        return "Pagar itens liberados e reapresentar pendências"
    if normalized.startswith("PENDENTE INTEGRAL / PAGAMENTO FUTURO"):
        return "Aguardar comprovantes e reapresentar"
    if normalized.startswith("RETIDO INTEGRAL / PROBLEMA INTERNO"):
        return "Conferir antes de autorizar pagamento"
    if normalized.startswith("REVISAR PARSER"):
        return "Corrigir leitura da fatura e processar novamente"
    return "Conferir decisão detalhada"


class OfficialInvoiceEngineService:
    """Executa o fluxo modular oficial de faturas sem abrir a interface antiga.

    A classe apenas orquestra leitor PDF, parser, vínculo com Base SSW e motor
    de decisão já existentes no RC26.6. Nenhuma decisão financeira é criada na
    camada web.
    """

    def __init__(self, project_root: Path, upload_root: Path, state_root: Path):
        self.project_root = Path(project_root).resolve()
        self.upload_root = Path(upload_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.results_path = self.state_root / "invoice_processing_results.json"
        self.last_run_path = self.state_root / "invoice_processing_last_run.json"
        self.self_test_path = self.state_root / "invoice_engine_contract_self_test.json"
        self._lock = threading.RLock()
        self._services: Any | None = None
        self._build_read_model: Any | None = None
        self._result_cache: dict[str, Any] | None = None
        self._result_cache_mtime_ns = -1

    @property
    def engine_root(self) -> Path:
        return self.project_root / "engine"

    @property
    def service_file(self) -> Path:
        return self.engine_root / "central_cte_modular" / "ui" / "invoices" / "services.py"

    def resolve_base_source(self, *, raise_on_missing: bool = True) -> Path | None:
        uploaded = self.upload_root / "bases"
        if uploaded.is_dir() and any(uploaded.glob("*.sswweb")):
            return uploaded
        project_source = self.project_root / "bases"
        if project_source.is_dir() and any(project_source.glob("*.sswweb")):
            return project_source
        if raise_on_missing:
            raise FileNotFoundError("Nenhum arquivo .sswweb foi encontrado para processar as faturas.")
        return None

    @staticmethod
    def _base_files(source: Path | None) -> list[Path]:
        if source is None:
            return []
        if source.is_file():
            return [source]
        return sorted(source.glob("*.sswweb"))

    @staticmethod
    def _pdf_backends() -> list[str]:
        result: list[str] = []
        if importlib.util.find_spec("pypdf") is not None:
            result.append("pypdf")
        if importlib.util.find_spec("fitz") is not None:
            result.append("pymupdf")
        return result

    def readiness(self) -> dict[str, Any]:
        base_source = self.resolve_base_source(raise_on_missing=False)
        backends = self._pdf_backends()
        ready = self.service_file.is_file() and base_source is not None and bool(backends)
        stored = self._results()
        return {
            "connected": bool(ready),
            "service_version": SERVICE_VERSION,
            "service_file": str(self.service_file),
            "base_source": str(base_source) if base_source else "",
            "pdf_backends": backends,
            "status": (
                "Serviço de faturas oficial disponível sem dependência da interface antiga."
                if ready
                else "Serviço de faturas aguardando módulos, Base SSW Web ou leitor de PDF."
            ),
            "last_run": read_json(self.last_run_path, {}),
            "self_test": read_json(self.self_test_path, {}),
            "stored_result_updated_at": str(stored.get("updated_at") or "") if isinstance(stored, Mapping) else "",
        }

    def _load_services(self) -> tuple[Any, Any]:
        with self._lock:
            if self._services is not None and self._build_read_model is not None:
                return self._services, self._build_read_model
            if not self.service_file.is_file():
                raise FileNotFoundError(f"Serviço modular de faturas ausente: {self.service_file}")
            engine_path = str(self.engine_root)
            if engine_path not in sys.path:
                sys.path.insert(0, engine_path)
            services_module = importlib.import_module("central_cte_modular.ui.invoices.services")
            read_model_module = importlib.import_module("central_cte_modular.ui.invoices.read_model")
            service_type = getattr(services_module, "InvoicePageServices", None)
            build_read_model = getattr(read_model_module, "build_invoice_read_model", None)
            if service_type is None or not callable(build_read_model):
                raise RuntimeError("O motor modular não publicou os serviços oficiais de faturas.")
            self._services = service_type()
            self._build_read_model = build_read_model
            return self._services, self._build_read_model

    def _contract_self_test(self) -> dict[str, Any]:
        cached = read_json(self.self_test_path, {})
        if isinstance(cached, Mapping) and cached.get("passed") and cached.get("service_version") == SERVICE_VERSION:
            return dict(cached)

        engine_path = str(self.engine_root)
        if engine_path not in sys.path:
            sys.path.insert(0, engine_path)
        from central_cte_modular.invoices.decision_engine import InvoiceDecisionEngine
        from central_cte_modular.invoices.input_models import InvoiceBaseLink, InvoiceInputDocument, InvoiceInputItem, InvoiceInputSnapshot

        def item(cte: str, nf: str, value: float, sequence: int) -> InvoiceInputItem:
            return InvoiceInputItem(
                invoice_number="0000001-0",
                invoice_key="1",
                partner="PARCEIRO TESTE CONTRATO",
                cte_number=cte,
                cte_key=cte,
                nf_number=nf,
                nf_key=nf,
                billed_value=value,
                layout="CT-e/RPS/NFS-e",
                source_file="contrato.pdf",
                source_document_hash="contrato",
                sequence=sequence,
            )

        first = item("10001", "50001", 100.0, 1)
        second = item("10002", "50002", 50.0, 2)
        document = InvoiceInputDocument(
            invoice_number="0000001-0",
            invoice_key="1",
            partner="PARCEIRO TESTE CONTRATO",
            source_file="contrato.pdf",
            document_hash="contrato",
            text_hash="contrato",
            parser_source="self_test",
            layout="CT-e/RPS/NFS-e",
            items=(first, second),
        )
        links = (
            InvoiceBaseLink(
                invoice_number=first.invoice_number,
                cte_number=first.cte_number,
                nf_number=first.nf_number,
                billed_value=first.billed_value,
                status="VINCULADO",
                mode="SELF_TEST",
                confidence="ALTA",
                base_nf=first.nf_number,
                base_cte=first.cte_number,
                base_value=first.billed_value,
                proof_status="S",
                document_type="NORMAL",
            ),
            InvoiceBaseLink(
                invoice_number=second.invoice_number,
                cte_number=second.cte_number,
                nf_number=second.nf_number,
                billed_value=second.billed_value,
                status="VINCULADO",
                mode="SELF_TEST",
                confidence="ALTA",
                base_nf=second.nf_number,
                base_cte=second.cte_number,
                base_value=second.billed_value,
                proof_status="N",
                document_type="NORMAL",
            ),
        )
        snapshot = InvoiceInputSnapshot(
            document_count=1,
            unique_document_count=1,
            duplicate_document_count=0,
            invoice_count=1,
            item_count=2,
            empty_nf_count=0,
            parser_error_count=0,
            documents=(document,),
            links=links,
            input_fingerprint="self-test",
        )
        result = InvoiceDecisionEngine().decide(snapshot)
        codes = Counter(decision.decision_code for decision in result.decisions)
        passed = (
            result.invoice_count == 1
            and result.item_count == 2
            and abs(result.total_value - 150.0) <= 0.001
            and abs(result.payable_value - 100.0) <= 0.001
            and abs(result.blocked_value - 50.0) <= 0.001
            and codes.get("OK") == 1
            and codes.get("SEM_COMPROVANTE") == 1
        )
        payload = {
            "passed": bool(passed),
            "service_version": SERVICE_VERSION,
            "checked_at": now_iso(),
            "invoice_count": result.invoice_count,
            "item_count": result.item_count,
            "total_value": result.total_value,
            "payable_value": result.payable_value,
            "blocked_value": result.blocked_value,
            "decision_codes": dict(codes),
        }
        write_json_atomic(self.self_test_path, payload)
        if not passed:
            raise RuntimeError("A trava de contrato do motor de faturas falhou.")
        return payload

    @staticmethod
    def _new_file_record(path: Path, position: int) -> dict[str, Any]:
        stat = path.stat()
        received_at = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
        return {
            "id": hashlib.sha256(str(path).encode("utf-8", errors="replace")).hexdigest()[:20],
            "position": int(position),
            "file": path.name,
            "path": str(path),
            "sha256": "",
            "text_sha256": "",
            "engine_document_hash": "",
            "size_bytes": int(stat.st_size),
            "status": "received",
            "stage": "intake",
            "code": "RECEIVED",
            "reason": "Arquivo recebido e aguardando processamento.",
            "duplicate_of": "",
            "duplicate_basis": "",
            "financial_disposition": "Aguardando decisão do motor.",
            "text_backend": "",
            "invoice_numbers": [],
            "invoice_keys": [],
            "partners": [],
            "parser_sources": [],
            "warnings": [],
            "attempts": 1,
            "received_at": received_at,
            "processed_at": "",
        }

    @staticmethod
    def _record_keys(value: str | Path) -> set[str]:
        raw = str(value or "").strip()
        if not raw:
            return set()
        keys = {raw.replace("\\", "/").lower(), Path(raw).name.lower()}
        try:
            keys.add(str(Path(raw).resolve()).replace("\\", "/").lower())
        except Exception:
            pass
        return {key for key in keys if key}

    def _persist_terminal_file_result(
        self,
        *,
        paths: list[Path],
        base_source: Path,
        self_test: Mapping[str, Any],
        file_records: list[dict[str, Any]],
        read_failures: list[dict[str, Any]],
        backend_counts: Mapping[str, int],
        started: float,
        started_iso: str,
        error: str,
    ) -> None:
        base_files = self._base_files(base_source)
        rejected = [dict(item) for item in file_records if str(item.get("status")) == "rejected"]
        duplicates = [dict(item) for item in file_records if str(item.get("status")) == "duplicate"]
        summary = {
            "documents": 0,
            "uploaded_documents": len(paths),
            "readable_documents": sum(1 for item in file_records if item.get("text_backend")),
            "read_failures": len(read_failures),
            "processed_files": 0,
            "rejected_files": len(rejected),
            "duplicate_files": len(duplicates),
            "unprocessed_files": max(0, len(paths) - len(rejected) - len(duplicates)),
            "items": 0,
            "invoices": 0,
            "total_value": 0.0,
            "payable_value": 0.0,
            "pending_total": 0.0,
            "future_value": 0.0,
            "internal_problem_value": 0.0,
            "ok_invoice_count": 0,
            "partial_invoice_count": 0,
            "future_invoice_count": 0,
            "internal_problem_invoice_count": 0,
            "ok_item_count": 0,
            "problem_item_count": 0,
            "financial_partition_difference": 0.0,
            "input_fingerprint": "",
        }
        payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "service_version": SERVICE_VERSION,
            "updated_at": now_iso(),
            "input_signature": file_signature(paths),
            "base_signature": file_signature(base_files),
            "input_paths": [str(path) for path in paths],
            "base_source": str(base_source),
            "base_info": {},
            "self_test": dict(self_test),
            "read_failures": read_failures,
            "file_records": file_records,
            "rejected_files": rejected,
            "duplicate_files": duplicates,
            "pdf_backends": dict(backend_counts),
            "summary": summary,
            "decision_codes": {},
            "statuses": {},
            "report_records": [],
            "invoices": [],
            "details": [],
            "error": str(error or ""),
        }
        write_json_atomic(self.results_path, payload)
        self._result_cache = payload
        self._result_cache_mtime_ns = self.results_path.stat().st_mtime_ns
        last_run = {
            "status": "falhou",
            "started_at": started_iso,
            "finished_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            **summary,
            "error": str(error or ""),
            "read_failures_detail": read_failures,
            "rejected_files_detail": rejected,
            "duplicate_files_detail": duplicates,
            "file_records": file_records,
            "pdf_backends": dict(backend_counts),
            "base_source": str(base_source),
            "base_file_count": len(base_files),
            "self_test": dict(self_test),
        }
        write_json_atomic(self.last_run_path, last_run)

    def process(
        self,
        pdf_paths: Iterable[Path],
        progress: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        started_iso = now_iso()
        paths = sorted({Path(item).resolve() for item in pdf_paths if Path(item).is_file()}, key=lambda path: str(path).lower())
        if not paths:
            raise ValueError("Adicione pelo menos uma fatura PDF antes de processar.")

        services, build_read_model = self._load_services()
        base_source = self.resolve_base_source()
        assert base_source is not None
        self_test = self._contract_self_test()

        documents: list[dict[str, Any]] = []
        file_records: list[dict[str, Any]] = []
        read_failures: list[dict[str, Any]] = []
        backend_counts: Counter[str] = Counter()
        seen_hashes: dict[str, dict[str, Any]] = {}
        seen_engine_documents: dict[str, dict[str, Any]] = {}
        total = len(paths)

        for position, path in enumerate(paths, 1):
            record = self._new_file_record(path, position)
            file_records.append(record)
            if progress:
                progress(position - 1, total, path.name, "Identificando e extraindo texto do PDF")
            try:
                body = path.read_bytes()
                digest = hashlib.sha256(body).hexdigest()
                record["sha256"] = digest
                original = seen_hashes.get(digest)
                if original is not None:
                    record.update({
                        "status": "duplicate",
                        "stage": "deduplication",
                        "code": "DUPLICATE_FILE_SHA256",
                        "reason": (
                            f"Fatura rejeitada por duplicidade: o arquivo é idêntico a {original.get('file')}. "
                            "O original foi mantido e esta cópia não entrou no cálculo financeiro."
                        ),
                        "duplicate_of": str(original.get("file") or ""),
                        "duplicate_basis": "arquivo_sha256",
                        "financial_disposition": "Excluído do cálculo financeiro por duplicidade.",
                        "processed_at": now_iso(),
                    })
                    if progress:
                        progress(position, total, path.name, "PDF duplicado rejeitado do cálculo")
                    continue
                seen_hashes[digest] = record
                text, backend = services.read_pdf(path)
                normalized_text = str(text or "").replace("\xa0", " ")
                text_digest = hashlib.sha256(normalized_text.encode("utf-8", errors="replace")).hexdigest()
                parsed_preview = services.document_parser.parse({"texto": normalized_text, "path": str(path)})
                engine_document_hash = str(getattr(parsed_preview, "document_hash", "") or "")
                record.update({
                    "text_sha256": text_digest,
                    "engine_document_hash": engine_document_hash,
                    "text_backend": str(backend or ""),
                })
                original = seen_engine_documents.get(engine_document_hash) if engine_document_hash else None
                if original is not None:
                    record.update({
                        "status": "duplicate",
                        "stage": "deduplication",
                        "code": "DUPLICATE_ENGINE_DOCUMENT",
                        "reason": (
                            f"Fatura rejeitada por duplicidade: o conteúdo lido corresponde à mesma fatura de {original.get('file')}. "
                            "A engine manteve somente o documento original para impedir dupla contabilização."
                        ),
                        "duplicate_of": str(original.get("file") or ""),
                        "duplicate_basis": "documento_canonico_engine",
                        "financial_disposition": "Excluído do cálculo financeiro por duplicidade identificada pela engine.",
                        "processed_at": now_iso(),
                    })
                    if progress:
                        progress(position, total, path.name, "Duplicidade da fatura identificada pela engine")
                    continue
                if engine_document_hash:
                    seen_engine_documents[engine_document_hash] = record
                record.update({
                    "status": "processing",
                    "stage": "parser",
                    "code": "PDF_READ",
                    "reason": "PDF lido; aguardando identificação da fatura pelo motor.",
                })
                documents.append({
                    "path": str(path),
                    "arquivo": str(path),
                    "texto": normalized_text,
                    "text_backend": backend,
                    "document_hash": digest,
                })
                backend_counts[str(backend or "desconhecido")] += 1
                if progress:
                    progress(position, total, path.name, f"PDF lido por {backend}")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                record.update({
                    "status": "rejected",
                    "stage": "pdf_read",
                    "code": "PDF_READ_FAILED",
                    "reason": error,
                    "financial_disposition": "Excluído do cálculo porque o PDF não pôde ser lido.",
                    "processed_at": now_iso(),
                })
                read_failures.append({
                    "file": path.name,
                    "path": str(path),
                    "stage": "pdf_read",
                    "code": "PDF_READ_FAILED",
                    "error": error,
                })
                if progress:
                    progress(position, total, path.name, "Falha na leitura do PDF")

        if not documents:
            detail = "; ".join(str(item.get("error") or "") for item in read_failures[:3])
            error = "Nenhuma fatura pôde ser lida." + (f" {detail}" if detail else "")
            self._persist_terminal_file_result(
                paths=paths,
                base_source=base_source,
                self_test=self_test,
                file_records=file_records,
                read_failures=read_failures,
                backend_counts=backend_counts,
                started=started,
                started_iso=started_iso,
                error=error,
            )
            raise RuntimeError(error)

        try:
            result = services.process(documents, base_path=base_source)
            read_model = build_read_model(result.decision_snapshot, money=money_br)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            for record in file_records:
                if record.get("status") == "processing":
                    record.update({
                        "status": "rejected",
                        "stage": "engine",
                        "code": "ENGINE_PROCESSING_FAILED",
                        "reason": error,
                        "financial_disposition": "Excluído do cálculo por falha durante o processamento da engine.",
                        "processed_at": now_iso(),
                    })
            self._persist_terminal_file_result(
                paths=paths,
                base_source=base_source,
                self_test=self_test,
                file_records=file_records,
                read_failures=read_failures,
                backend_counts=backend_counts,
                started=started,
                started_iso=started_iso,
                error=error,
            )
            raise

        input_snapshot = result.input_snapshot
        decision_snapshot = result.decision_snapshot

        source_documents: dict[str, list[Any]] = defaultdict(list)
        for document in tuple(getattr(input_snapshot, "documents", ()) or ()):
            source_file = str(getattr(document, "source_file", "") or "")
            for key in self._record_keys(source_file):
                source_documents[key].append(document)

        for record in file_records:
            if record.get("status") != "processing":
                continue
            matches: list[Any] = []
            for key in self._record_keys(str(record.get("path") or record.get("file") or "")):
                if source_documents.get(key):
                    matches = source_documents[key]
                    break
            invoice_numbers = sorted({
                str(getattr(document, "invoice_number", "") or "").strip()
                for document in matches
                if str(getattr(document, "invoice_number", "") or "").strip()
            })
            invoice_keys = sorted({
                str(getattr(document, "invoice_key", "") or "").strip()
                for document in matches
                if str(getattr(document, "invoice_key", "") or "").strip()
            })
            if matches and (invoice_numbers or invoice_keys):
                record.update({
                    "status": "processed",
                    "stage": "completed",
                    "code": "PROCESSED",
                    "reason": "PDF processado e reconciliado pelo motor oficial RC26.6.",
                    "financial_disposition": "Documento aceito no cálculo financeiro oficial.",
                    "invoice_numbers": invoice_numbers,
                    "invoice_keys": invoice_keys,
                    "partners": sorted({
                        str(getattr(document, "partner", "") or "").strip()
                        for document in matches
                        if str(getattr(document, "partner", "") or "").strip()
                    }),
                    "parser_sources": sorted({
                        str(getattr(document, "parser_source", "") or "").strip()
                        for document in matches
                        if str(getattr(document, "parser_source", "") or "").strip()
                    }),
                    "warnings": sorted({
                        str(warning)
                        for document in matches
                        for warning in tuple(getattr(document, "warnings", ()) or ())
                        if str(warning).strip()
                    }),
                    "processed_at": now_iso(),
                })
            else:
                record.update({
                    "status": "rejected",
                    "stage": "parser",
                    "code": "INVOICE_NOT_IDENTIFIED",
                    "reason": "O PDF foi lido, mas o motor RC26.6 não identificou uma fatura válida.",
                    "financial_disposition": "Excluído do cálculo porque nenhuma fatura válida foi identificada.",
                    "processed_at": now_iso(),
                })

        records_by_invoice: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in read_model.records:
            key = str(record.get("Fatura") or record.get("Fatura chave") or "")
            records_by_invoice[key].append(dict(record))

        documents_by_invoice: dict[str, list[str]] = defaultdict(list)
        document_warnings: dict[str, list[str]] = defaultdict(list)
        parser_sources: dict[str, list[str]] = defaultdict(list)
        for document in tuple(getattr(input_snapshot, "documents", ()) or ()):
            key = str(getattr(document, "invoice_number", "") or getattr(document, "invoice_key", "") or "")
            source_file = str(getattr(document, "source_file", "") or "")
            if source_file and source_file not in documents_by_invoice[key]:
                documents_by_invoice[key].append(source_file)
            parser = str(getattr(document, "parser_source", "") or "")
            if parser and parser not in parser_sources[key]:
                parser_sources[key].append(parser)
            for warning in tuple(getattr(document, "warnings", ()) or ()):
                if str(warning) not in document_warnings[key]:
                    document_warnings[key].append(str(warning))

        invoice_rows: list[dict[str, Any]] = []
        all_details: list[dict[str, Any]] = []
        for summary in tuple(getattr(decision_snapshot, "invoices", ()) or ()):
            key = str(getattr(summary, "invoice_number", "") or getattr(summary, "invoice_key", "") or "")
            records = records_by_invoice.get(key, [])
            future_value = round(sum(float(item.get("Valor para pagamento futuro") or 0.0) for item in records), 2)
            internal_value = round(sum(float(item.get("Valor retido por problema interno") or 0.0) for item in records), 2)
            retained_value = round(future_value + internal_value, 2)
            details: list[dict[str, Any]] = []
            for item in records:
                detail = {
                    "invoice": key,
                    "partner": item.get("Parceiro") or "",
                    "cte": item.get("CT-e fatura") or item.get("CT-e") or "",
                    "nf": item.get("NF fatura") or item.get("NF") or "",
                    "billed_value": item.get("Valor fatura"),
                    "base_value": item.get("Valor base"),
                    "future_value": item.get("Valor para pagamento futuro"),
                    "internal_problem_value": item.get("Valor retido por problema interno"),
                    "payable_value": item.get("Valor a pagar"),
                    "status": item.get("Status final CT-e") or "",
                    "decision_code": item.get("Código decisão") or "",
                    "proof_status": item.get("Comprovante") or "",
                    "base_cte": item.get("CT-e base") or "",
                    "base_nf": item.get("NF base") or "",
                    "link_mode": item.get("Método de busca") or "",
                    "confidence": item.get("Confiança validação valor") or "",
                    "value_status": item.get("Conferência do valor") or item.get("Status valor") or "",
                    "reason": item.get("Motivo") or "",
                    "recommended_action": item.get("Ação recomendada") or "",
                    "decision_path": item.get("Caminho do status") or "",
                    "source_file": item.get("Arquivo fatura") or "",
                    "financial_counted": bool(item.get("Financeiro contabilizado", True)),
                    "warnings": item.get("Avisos auditoria") or "",
                }
                details.append(detail)
                all_details.append(detail)

            status = str(getattr(summary, "status", "") or "")
            source_files = documents_by_invoice.get(key, [])
            modified_values = []
            size_total = 0
            for source_file in source_files:
                try:
                    stat = Path(source_file).stat()
                    modified_values.append(stat.st_mtime)
                    size_total += stat.st_size
                except OSError:
                    continue
            invoice_rows.append({
                "invoice": str(getattr(summary, "invoice_number", "") or key),
                "invoice_key": str(getattr(summary, "invoice_key", "") or ""),
                "file": Path(source_files[0]).name if len(source_files) == 1 else f"{len(source_files)} PDFs" if source_files else "",
                "source_files": source_files,
                "partner": str(getattr(summary, "partner", "") or "Parceiro não identificado"),
                "item_count": int(getattr(summary, "item_count", 0) or 0),
                "counted_item_count": int(getattr(summary, "counted_item_count", 0) or 0),
                "ok_count": int(getattr(summary, "ok_count", 0) or 0) + int(getattr(summary, "complementary_count", 0) or 0),
                "pending_count": int(getattr(summary, "missing_proof_count", 0) or 0) + int(getattr(summary, "outside_base_count", 0) or 0) + int(getattr(summary, "review_count", 0) or 0),
                "missing_proof_count": int(getattr(summary, "missing_proof_count", 0) or 0),
                "outside_base_count": int(getattr(summary, "outside_base_count", 0) or 0),
                "review_count": int(getattr(summary, "review_count", 0) or 0),
                "ignored_nf_count": int(getattr(summary, "ignored_nf_count", 0) or 0),
                "total_value": round(float(getattr(summary, "total_value", 0.0) or 0.0), 2),
                "payable_value": round(float(getattr(summary, "payable_value", 0.0) or 0.0), 2),
                "retained_value": retained_value,
                "future_value": future_value,
                "internal_problem_value": internal_value,
                "payment_status": status,
                "financial_action": _financial_action(status),
                "parser_sources": parser_sources.get(key, []),
                "warnings": document_warnings.get(key, []),
                "details": details,
                "size_bytes": size_total,
                "modified_at": datetime.fromtimestamp(max(modified_values)).astimezone().isoformat(timespec="seconds") if modified_values else now_iso(),
            })

        invoice_rows.sort(key=lambda row: (str(row.get("invoice") or ""), str(row.get("partner") or "")))
        total_value = round(float(getattr(decision_snapshot, "total_value", 0.0) or 0.0), 2)
        payable_value = round(float(getattr(decision_snapshot, "payable_value", 0.0) or 0.0), 2)
        future_value = round(float(getattr(read_model, "future_value", 0.0) or 0.0), 2)
        internal_value = round(float(getattr(read_model, "internal_problem_value", 0.0) or 0.0), 2)
        pending_total = round(future_value + internal_value, 2)
        partition_difference = round(total_value - payable_value - pending_total, 2)
        if abs(partition_difference) > 0.01:
            raise RuntimeError(
                f"Partição financeira inconsistente: total {total_value:.2f}, pagar {payable_value:.2f}, pendente {pending_total:.2f}."
            )

        rejected_files = [dict(item) for item in file_records if item.get("status") == "rejected"]
        duplicate_files = [dict(item) for item in file_records if item.get("status") == "duplicate"]
        processed_files = [dict(item) for item in file_records if item.get("status") == "processed"]
        unresolved_files = [dict(item) for item in file_records if item.get("status") not in {"processed", "rejected", "duplicate"}]
        base_files = self._base_files(base_source)
        input_signature = file_signature(paths)
        base_signature = file_signature(base_files)
        payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "service_version": SERVICE_VERSION,
            "updated_at": now_iso(),
            "input_signature": input_signature,
            "base_signature": base_signature,
            "input_paths": [str(path) for path in paths],
            "base_source": str(base_source),
            "base_info": dict(result.base_info or {}),
            "self_test": self_test,
            "read_failures": read_failures,
            "file_records": file_records,
            "rejected_files": rejected_files,
            "duplicate_files": duplicate_files,
            "pdf_backends": dict(backend_counts),
            "summary": {
                "documents": int(result.documents),
                "uploaded_documents": len(paths),
                "readable_documents": len(documents),
                "read_failures": len(read_failures),
                "processed_files": len(processed_files),
                "rejected_files": len(rejected_files),
                "duplicate_files": len(duplicate_files),
                "unprocessed_files": len(unresolved_files),
                "items": int(result.items),
                "invoices": int(result.invoices),
                "total_value": total_value,
                "payable_value": payable_value,
                "pending_total": pending_total,
                "future_value": future_value,
                "internal_problem_value": internal_value,
                "ok_invoice_count": int(getattr(read_model, "ok_invoice_count", 0) or 0),
                "partial_invoice_count": int(getattr(read_model, "partial_invoice_count", 0) or 0),
                "future_invoice_count": int(getattr(read_model, "future_invoice_count", 0) or 0),
                "internal_problem_invoice_count": int(getattr(read_model, "internal_problem_invoice_count", 0) or 0),
                "ok_item_count": int(getattr(read_model, "ok_item_count", 0) or 0),
                "problem_item_count": int(getattr(read_model, "problem_item_count", 0) or 0),
                "financial_partition_difference": partition_difference,
                "input_fingerprint": str(getattr(decision_snapshot, "input_fingerprint", "") or ""),
            },
            "decision_codes": dict(Counter(str(item.get("decision_code") or "SEM_CODIGO") for item in all_details)),
            "statuses": dict(Counter(str(item.get("status") or "SEM_STATUS") for item in all_details)),
            "report_records": [dict(record) for record in read_model.records],
            "invoices": invoice_rows,
            "details": all_details,
        }
        write_json_atomic(self.results_path, payload)
        self._result_cache = payload
        self._result_cache_mtime_ns = self.results_path.stat().st_mtime_ns

        has_alerts = bool(rejected_files or duplicate_files or unresolved_files)
        summary = {
            "status": "concluido_com_alertas" if has_alerts else "concluido",
            "started_at": started_iso,
            "finished_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            **payload["summary"],
            "read_failures_detail": read_failures,
            "rejected_files_detail": rejected_files,
            "duplicate_files_detail": duplicate_files,
            "file_records": file_records,
            "pdf_backends": dict(backend_counts),
            "base_source": str(base_source),
            "base_file_count": len(base_files),
            "base_row_count": int((result.base_info or {}).get("row_count") or 0),
            "candidate_row_count": int((result.base_info or {}).get("candidate_row_count") or 0),
            "self_test": self_test,
        }
        write_json_atomic(self.last_run_path, summary)
        return summary

    def _results(self) -> dict[str, Any]:
        try:
            mtime = self.results_path.stat().st_mtime_ns
        except OSError:
            return {}
        if self._result_cache is None or self._result_cache_mtime_ns != mtime:
            self._result_cache = read_json(self.results_path, {})
            self._result_cache_mtime_ns = mtime
        return self._result_cache if isinstance(self._result_cache, dict) else {}

    def clear_results(self) -> dict[str, Any]:
        """Remove somente a fotografia do lote de faturas atual.

        A Base SSW, o contrato de decisão e os relatórios já exportados
        permanecem preservados.
        """
        removed: list[str] = []
        with self._lock:
            for path in (self.results_path, self.last_run_path):
                try:
                    path.unlink()
                    removed.append(path.name)
                except FileNotFoundError:
                    pass
            self._result_cache = None
            self._result_cache_mtime_ns = -1
        return {
            "cleared_at": now_iso(),
            "removed_state_files": removed,
            "results_cleared": True,
        }

    def _stored_payload_for_paths(self, pdf_paths: Iterable[Path]) -> dict[str, Any]:
        paths = sorted({Path(item).resolve() for item in pdf_paths if Path(item).is_file()}, key=lambda path: str(path).lower())
        if not paths:
            return {}
        data = self._results()
        if not isinstance(data, Mapping):
            return {}
        if str(data.get("input_signature") or "") != file_signature(paths):
            return {}
        base_source = self.resolve_base_source(raise_on_missing=False)
        base_files = self._base_files(base_source)
        if not base_files or str(data.get("base_signature") or "") != file_signature(base_files):
            return {}
        return dict(data)

    def stored_rows(self, pdf_paths: Iterable[Path]) -> list[dict[str, Any]]:
        data = self._stored_payload_for_paths(pdf_paths)
        rows = data.get("invoices") if data else None
        return [dict(item) for item in rows] if isinstance(rows, list) else []

    def stored_file_records(self, pdf_paths: Iterable[Path]) -> list[dict[str, Any]]:
        data = self._stored_payload_for_paths(pdf_paths)
        rows = data.get("file_records") if data else None
        return [dict(item) for item in rows] if isinstance(rows, list) else []

    def stored_rejected_files(self, pdf_paths: Iterable[Path]) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in self.stored_file_records(pdf_paths)
            if str(item.get("status") or "") in {"rejected", "duplicate", "received", "processing"}
        ]

    def stored_summary(self, pdf_paths: Iterable[Path]) -> dict[str, Any]:
        data = self._stored_payload_for_paths(pdf_paths)
        summary = data.get("summary") if data else None
        return dict(summary) if isinstance(summary, Mapping) else {}


__all__ = ["OfficialInvoiceEngineService", "SERVICE_VERSION", "file_signature"]
