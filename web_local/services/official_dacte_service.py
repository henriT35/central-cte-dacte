# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - validado pela readiness
    PdfReader = None

SERVICE_VERSION = "2.7.0 RC27.14 WEB/WINDOWS MVP13 R12.13.9"
COMPLEMENTARY_INFO_KEY = "informacao_complementar_impressao"
COMPLEMENTARY_INFO_META_KEY = "informacao_complementar_impressao_meta"
MAX_COMPLEMENTARY_CHARS = 600


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_component(value: Any, fallback: str = "DACTE", limit: int = 90) -> str:
    text = str(value or "").strip()
    allowed = []
    for character in text:
        if character.isalnum() or character in " ._-()":
            allowed.append(character)
        else:
            allowed.append(" ")
    normalized = " ".join("".join(allowed).split()).strip(" ._")
    return (normalized or fallback)[:limit].rstrip(" ._") or fallback


class OfficialDacteService:
    """Gera o DACTE oficial a partir da fotografia publicada pelo RC26.6.

    A classe não interpreta XML nem recalcula valores. Ela exige o resultado
    oficial persistido pelo serviço XML e apenas reaproveita `render_document`
    e o conversor HTML -> PDF já usados pelo aplicativo original.
    """

    def __init__(self, project_root: Path, output_root: Path, state_root: Path, xml_service: Any):
        self.project_root = Path(project_root).resolve()
        self.output_root = Path(output_root).resolve() / "dacte"
        self.preview_root = self.output_root / "previews"
        self.individual_root = self.output_root / "individuais"
        self.state_root = Path(state_root).resolve()
        self.xml_service = xml_service
        self.last_run_path = self.state_root / "dacte_last_run.json"
        self.complementary_path = self.state_root / "complementary_information.json"
        self._plugin: Any | None = None
        self._lock = threading.RLock()

    @property
    def plugin_file(self) -> Path:
        return self.project_root / "engine" / "assinatura_pdf_engine_2_6_65_18.py"

    def _load_plugin(self) -> Any:
        with self._lock:
            if self._plugin is not None:
                return self._plugin
            if not self.plugin_file.is_file():
                raise FileNotFoundError(f"Motor de PDF ausente: {self.plugin_file}")
            engine_dir = str(self.plugin_file.parent)
            if engine_dir not in sys.path:
                sys.path.insert(0, engine_dir)
            module_name = "central_cte_assinatura_pdf_web_mvp5"
            spec = importlib.util.spec_from_file_location(module_name, str(self.plugin_file))
            if spec is None or spec.loader is None:
                raise RuntimeError("Não foi possível carregar o motor oficial de DACTE/PDF.")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            required = ("_resolve_render_document", "html_text_to_pdf", "find_browser")
            missing = [name for name in required if not callable(getattr(module, name, None))]
            if missing:
                raise RuntimeError("O motor de PDF não publicou: " + ", ".join(missing))
            self._plugin = module
            return module

    @staticmethod
    def _weasyprint_available() -> bool:
        try:
            import weasyprint  # noqa: F401
            return True
        except Exception:
            return False

    def readiness(self) -> dict[str, Any]:
        browser = ""
        error = ""
        connected = False
        backends: list[str] = []
        try:
            plugin = self._load_plugin()
            engine = self.xml_service._load_engine()
            plugin._resolve_render_document(engine)
            browser_path = plugin.find_browser()
            browser = str(browser_path or "")
            if browser_path:
                backends.append("Edge/Chrome")
            if self._weasyprint_available():
                backends.append("WeasyPrint")
            connected = bool(backends) and PdfReader is not None
            if not backends:
                error = "Nenhum conversor HTML para PDF foi localizado."
            elif PdfReader is None:
                error = "O leitor de verificação PDF não está disponível."
        except Exception as exc:
            error = str(exc)
        return {
            "connected": connected,
            "service_version": SERVICE_VERSION,
            "status": (
                "Renderer oficial do DACTE disponível sem abrir a interface antiga."
                if connected
                else f"Serviço DACTE indisponível: {error or 'dependência ausente.'}"
            ),
            "browser": browser,
            "conversion_backends": backends,
            "output_root": str(self.output_root),
            "last_run": read_json(self.last_run_path, {}),
            "signature_editor_connected": False,
        }

    @staticmethod
    def _clean_complementary_information(value: Any, *, limit: bool = False) -> str:
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        text = "\n".join(lines).strip()
        return text[:MAX_COMPLEMENTARY_CHARS] if limit else text

    @staticmethod
    def _info_identities(info: Mapping[str, Any] | None, path: Path | None = None) -> list[str]:
        data = dict(info or {})
        identities: list[str] = []

        def add(value: str) -> None:
            if value and value not in identities:
                identities.append(value)

        key = "".join(character for character in str(data.get("chave") or data.get("chave_acesso") or data.get("key") or "") if character.isdigit())
        if len(key) == 44:
            add(f"chave:{key}")

        emit = data.get("emit") if isinstance(data.get("emit"), Mapping) else {}
        cnpj = "".join(character for character in str(
            data.get("emitente_cnpj") or data.get("cnpj_emitente") or emit.get("CNPJ") or emit.get("cnpj") or ""
        ) if character.isdigit())
        number = str(data.get("numero") or data.get("nCT") or data.get("cte") or "").strip()
        series = str(data.get("serie") or data.get("serie_cte") or "").strip()
        if number or series or cnpj:
            add(f"cte:{cnpj}:{series}:{number}")

        source = Path(path).resolve() if path is not None else None
        if source is None:
            raw = str(data.get("arquivo") or data.get("path") or "").strip()
            source = Path(raw).resolve() if raw else None
        if source is not None:
            add(f"arquivo:{source.name.lower()}")
            add(f"caminho:{str(source).lower()}")
        return identities

    def _complementary_store(self) -> dict[str, Any]:
        raw = read_json(self.complementary_path, {})
        if not isinstance(raw, dict):
            raw = {}
        raw.setdefault("version", 1)
        raw.setdefault("items", {})
        if not isinstance(raw.get("items"), dict):
            raw["items"] = {}
        return raw

    def _save_complementary_store(self, store: Mapping[str, Any]) -> None:
        payload = dict(store or {})
        payload["version"] = 1
        payload["updated_at"] = now_iso()
        payload.setdefault("items", {})
        write_json_atomic(self.complementary_path, payload)

    def _stored_complementary(self, info: Mapping[str, Any] | None, path: Path | None = None) -> str:
        items = self._complementary_store().get("items") or {}
        for identity in self._info_identities(info, path):
            item = items.get(identity) if isinstance(items, Mapping) else None
            if isinstance(item, Mapping):
                text = self._clean_complementary_information(item.get("text") or item.get("texto"))
                if text:
                    return text
        return ""

    def complementary_information(self, path: str | Path) -> str:
        resolved = Path(path).resolve()
        stored = self.xml_service.stored_row(resolved)
        info = dict(stored.get("engine_info") or {}) if isinstance(stored, Mapping) else {}
        return self._stored_complementary(info, resolved)

    def apply_complementary_information(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        text: Any,
    ) -> dict[str, Any]:
        paths = self._allowed_selection(selected_paths, available_paths)
        value = self._clean_complementary_information(text)
        if not value:
            raise ValueError("Digite a informação complementar antes de aplicar.")
        if len(value) > MAX_COMPLEMENTARY_CHARS:
            raise ValueError(f"O texto ultrapassa o limite de {MAX_COMPLEMENTARY_CHARS} caracteres.")
        store = self._complementary_store()
        items = store.setdefault("items", {})
        updated_at = now_iso()
        identities_written: set[str] = set()
        ctes: list[str] = []
        for path in paths:
            stored = self.xml_service.stored_row(path)
            info = dict(stored.get("engine_info") or {}) if isinstance(stored, Mapping) else {}
            identities = self._info_identities(info, path)
            if not identities:
                continue
            number = str(info.get("numero") or info.get("nCT") or "").strip()
            if number and number not in ctes:
                ctes.append(number)
            item = {
                "text": value,
                "updated_at": updated_at,
                "source_path": str(path),
                "file": path.name,
                "cte": number,
                "xml_fiscal_modified": False,
            }
            for identity in identities:
                items[identity] = dict(item)
                identities_written.add(identity)
        if not identities_written:
            raise ValueError("Nenhum CT-e válido foi localizado para receber a informação complementar.")
        self._save_complementary_store(store)
        return {
            "updated_at": updated_at,
            "documents": len(paths),
            "identities": len(identities_written),
            "ctes": ctes,
            "text": value,
            "max_chars": MAX_COMPLEMENTARY_CHARS,
            "xml_fiscal_modified": False,
        }

    def remove_complementary_information(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path] | None = None,
    ) -> dict[str, Any]:
        paths = (
            self._allowed_selection(selected_paths, available_paths)
            if available_paths is not None
            else [Path(item).resolve() for item in selected_paths]
        )
        store = self._complementary_store()
        items = store.setdefault("items", {})
        removed = 0
        for path in paths:
            stored = self.xml_service.stored_row(path)
            info = dict(stored.get("engine_info") or {}) if isinstance(stored, Mapping) else {}
            for identity in self._info_identities(info, path):
                if identity in items:
                    items.pop(identity, None)
                    removed += 1
        if removed:
            self._save_complementary_store(store)
        return {
            "removed_identities": removed,
            "documents": len(paths),
            "removed_at": now_iso(),
            "xml_fiscal_modified": False,
        }

    @staticmethod
    def _allowed_selection(selected_paths: Iterable[str | Path], available_paths: Iterable[Path]) -> list[Path]:
        allowed = {str(Path(path).resolve()): Path(path).resolve() for path in available_paths}
        selected: list[Path] = []
        seen: set[str] = set()
        for raw in selected_paths:
            resolved = str(Path(raw).resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            path = allowed.get(resolved)
            if path is None:
                raise ValueError("Um dos XMLs selecionados não pertence à biblioteca local autorizada.")
            if path.suffix.lower() != ".xml" or not path.is_file():
                raise ValueError(f"XML selecionado inválido: {path.name}")
            selected.append(path)
        if not selected:
            raise ValueError("Selecione pelo menos um CT-e processado.")
        return selected


    def _hydrate_manual_validation(
        self,
        stored: Mapping[str, Any],
        info: Mapping[str, Any],
        path: Path,
        validation: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Reanexa a baixa manual à fotografia usada no DACTE/PDF.

        R12.13.9: a fotografia persistida da linha é a fonte final da decisão
        operacional. Algumas linhas antigas ficaram com a decisão espalhada
        entre ``validation``, ``manual_decision`` e os campos resumidos da
        linha. Antes de assinar ou converter, consolidamos essas três fontes e
        marcamos explicitamente que a baixa manual foi aplicada. Assim o
        guarda do bloco compacto pode continuar auditando a diferença
        automática sem bloquear um CT-e que já foi aprovado manualmente.
        """
        result = dict(validation or {})

        # 1) Procura a decisão em todas as fontes conhecidas.
        decision = stored.get("manual_decision")
        if not isinstance(decision, Mapping) or not str(decision.get("decision") or "").strip():
            embedded = result.get("manual_decision")
            decision = dict(embedded) if isinstance(embedded, Mapping) else None
        if not isinstance(decision, Mapping) or not str(decision.get("decision") or "").strip():
            resolver = getattr(self.xml_service, "_decision_for", None)
            if callable(resolver):
                try:
                    _key, canonical = resolver(info, path)
                    if isinstance(canonical, Mapping):
                        decision = dict(canonical)
                except Exception:
                    decision = None

        row_status = str(stored.get("status") or "").strip()
        result_status = str(result.get("status") or "").strip()
        final_status = row_status or result_status
        final_status_upper = final_status.upper()
        review_upper = str(result.get("revisao_manual") or "").strip().upper()
        row_reason = str(
            stored.get("manual_reason")
            or result.get("observacao_manual")
            or ((decision or {}).get("reason") if isinstance(decision, Mapping) else "")
            or ""
        ).strip()
        row_date = str(
            stored.get("manual_decided_at")
            or result.get("revisao_data")
            or ((decision or {}).get("decided_at") if isinstance(decision, Mapping) else "")
            or ""
        ).strip()

        # 2) Compatibilidade com fotografias antigas: se a própria linha já
        #    está marcada como OK MANUAL/OK EXTRA AUTORIZADO, sintetiza a
        #    decisão mesmo quando o JSON canônico antigo não pôde ser achado.
        manual_final_approved = bool(
            final_status_upper.startswith("OK MANUAL")
            or final_status_upper.startswith("OK EXTRA AUTORIZADO")
            or review_upper == "APROVADO"
        )
        if manual_final_approved and (
            not isinstance(decision, Mapping)
            or str(decision.get("decision") or "").strip().lower() != "approved"
        ):
            previous = dict(decision) if isinstance(decision, Mapping) else {}
            previous.update({
                "decision": "approved",
                "reason": row_reason,
                "decided_at": row_date,
                "actor_id": str(previous.get("actor_id") or ""),
                "actor_name": str(previous.get("actor_name") or "Usuário autorizado"),
                "source": str(previous.get("source") or "fotografia_persistida"),
            })
            decision = previous

        # 3) Reaplica pela mesma função oficial usada na tela, quando possível.
        if isinstance(decision, Mapping) and str(decision.get("decision") or "").strip():
            applier = getattr(self.xml_service, "_apply_manual_decision", None)
            if callable(applier):
                try:
                    result = dict(applier(result, decision))
                except Exception:
                    result["manual_decision"] = dict(decision)
            else:
                result["manual_decision"] = dict(decision)

        # 4) Os campos resumidos da linha não podem se perder no PDF.
        if row_reason:
            result["observacao_manual"] = row_reason
            result["controle_dacte_justificativa"] = row_reason
        if row_date:
            result["revisao_data"] = row_date
            result["controle_dacte_data_manual"] = row_date

        actor = ""
        if isinstance(decision, Mapping):
            actor = str(decision.get("actor_name") or decision.get("actor_id") or "").strip()
        if actor:
            result["controle_dacte_responsavel_manual"] = actor

        # 5) Se a linha persistida já tem um desfecho manual aprovado, esse é
        #    o status final operacional. O resultado automático continua
        #    preservado nos campos automatic_* / engine_* para auditoria.
        status_after = str(result.get("status") or "").strip().upper()
        if manual_final_approved or status_after.startswith("OK MANUAL") or status_after.startswith("OK EXTRA AUTORIZADO"):
            if final_status_upper.startswith("OK EXTRA AUTORIZADO") or status_after.startswith("OK EXTRA AUTORIZADO"):
                result["status"] = "OK EXTRA AUTORIZADO"
            else:
                result["status"] = "OK MANUAL"
            result["revisao_manual"] = "APROVADO"
            result["baixa_manual_aplicada"] = True
            result["status_final_persistido"] = str(result.get("status") or final_status or "OK MANUAL")
            if isinstance(decision, Mapping):
                result["manual_decision"] = dict(decision)

        return result

    def _prepare_manual_compact_for_render(
        self,
        info: Mapping[str, Any],
        validation: Mapping[str, Any],
        *,
        include_compact: bool,
    ) -> dict[str, Any]:
        """Constrói o bloco manual antes do HTML/assinatura.

        O motor também possui um guarda final, mas preparar a fotografia aqui
        evita que o caminho de assinatura reentre no renderizador com um bloco
        antigo/incompleto.
        """
        result = dict(validation or {})
        if not include_compact:
            return result
        status = str(result.get("status") or "").strip().upper()
        approved = bool(
            result.get("baixa_manual_aplicada")
            or status.startswith("OK MANUAL")
            or status.startswith("OK EXTRA AUTORIZADO")
            or str(result.get("revisao_manual") or "").strip().upper() == "APROVADO"
            or (
                isinstance(result.get("manual_decision"), Mapping)
                and str((result.get("manual_decision") or {}).get("decision") or "").strip().lower() == "approved"
            )
        )
        if not approved:
            return result
        try:
            from engine.central_cte_modular.commercial.compact_render_guard import FinalCompactRenderGuard

            candidate = dict(info or {})
            candidate["validacao"] = result
            prepared, _audit = FinalCompactRenderGuard().prepare_info(candidate)
            final_validation = prepared.get("validacao")
            if isinstance(final_validation, Mapping):
                result = dict(final_validation)
        except Exception:
            # Não mascara a baixa manual se o enriquecimento visual falhar.
            result["baixa_manual_aplicada"] = True
        return result

    def _official_infos(self, selected_paths: Iterable[Path], *, include_compact: bool = True) -> list[dict[str, Any]]:
        infos: list[dict[str, Any]] = []
        stale: list[str] = []
        invalid: list[str] = []
        for path in selected_paths:
            stored = self.xml_service.stored_row(path)
            if not isinstance(stored, Mapping):
                stale.append(path.name)
                continue
            info = dict(stored.get("engine_info") or {})
            validation = dict(stored.get("validation") or {})
            validation = self._hydrate_manual_validation(stored, info, path, validation)
            validation = self._prepare_manual_compact_for_render(
                info, validation, include_compact=include_compact
            )
            has_official_validation = bool(validation)
            if not include_compact:
                for key in (
                    "controle_dacte_compacto",
                    "controle_dacte_regra",
                    "controle_dacte_linha1",
                    "controle_dacte_linha2",
                    "controle_dacte_status",
                ):
                    validation.pop(key, None)
            document_type = str(info.get("tipo") or "").strip().upper()
            if document_type != "CT-E":
                invalid.append(path.name)
                continue
            if not info or not has_official_validation:
                stale.append(path.name)
                continue
            info["validacao"] = validation
            info["path"] = str(path)
            info["arquivo"] = str(path)
            complementary = self._stored_complementary(info, path)
            if complementary:
                info[COMPLEMENTARY_INFO_KEY] = complementary
                info[COMPLEMENTARY_INFO_META_KEY] = {
                    "updated_at": now_iso(),
                    "source": "Central CT-e / DACTE Web",
                    "xml_fiscal_modified": False,
                }
            infos.append(info)
        if stale:
            names = ", ".join(stale[:4]) + ("…" if len(stale) > 4 else "")
            raise ValueError(
                "Há XMLs sem fotografia oficial válida. Processe novamente antes de gerar o DACTE: " + names
            )
        if invalid:
            names = ", ".join(invalid[:4]) + ("…" if len(invalid) > 4 else "")
            raise ValueError("A seleção contém documentos que não são CT-e: " + names)
        return infos

    def _render_html(self, infos: list[dict[str, Any]]) -> str:
        engine = self.xml_service._load_engine()
        plugin = self._load_plugin()
        renderer = plugin._resolve_render_document(engine)
        html = renderer([dict(info) for info in infos], with_button=False)
        if not isinstance(html, str) or "<html" not in html.lower() or "dacte" not in html.lower():
            raise RuntimeError("O renderizador oficial não devolveu um documento DACTE válido.")
        return html

    @staticmethod
    def _pdf_contract(path: Path, minimum_pages: int = 1) -> dict[str, Any]:
        if not path.is_file() or path.stat().st_size < 800:
            raise RuntimeError("O arquivo PDF não foi produzido ou está vazio.")
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise RuntimeError("O arquivo produzido não possui assinatura PDF válida.")
        if PdfReader is None:
            raise RuntimeError("O leitor de verificação PDF não está disponível.")
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        if pages < minimum_pages:
            raise RuntimeError(
                f"O DACTE gerado possui {pages} página(s), abaixo do mínimo esperado de {minimum_pages}."
            )
        return {
            "pages": pages,
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }

    def _browser(self) -> Path | None:
        browser = self._load_plugin().find_browser()
        return Path(browser) if browser is not None else None

    def _html_to_pdf(self, document_html: str, target: Path) -> str:
        """Converte o HTML oficial em PDF sem tocar nos dados do documento.

        No Windows, prioriza Edge/Chrome, igual ao aplicativo original. O
        navegador grava primeiro num caminho curto em ``%TEMP%`` e o serviço
        promove o arquivo validado para a pasta oficial. Isso evita o erro 0x3
        do Chromium quando o projeto foi extraído em uma árvore muito longa.
        Em Linux/VPS, usa WeasyPrint quando disponível e mantém o navegador
        como contingência.
        """
        target = Path(target).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []

        if os.name != "nt" and self._weasyprint_available():
            try:
                from weasyprint import HTML
                HTML(string=document_html, base_url=str(self.project_root)).write_pdf(str(target))
                return "HTML oficial RC26.6 -> WeasyPrint"
            except Exception as exc:
                errors.append(f"WeasyPrint: {exc}")

        browser = self._browser()
        if browser is not None:
            staging: Path | None = None
            browser_target = target
            if os.name == "nt":
                staging_root = Path(tempfile.gettempdir()) / "central_cte_pdf"
                staging_root.mkdir(parents=True, exist_ok=True)
                staging = staging_root / f"dacte_{uuid.uuid4().hex}.pdf"
                browser_target = staging
            try:
                self._load_plugin().html_text_to_pdf(document_html, browser_target, browser=browser)
                if staging is not None:
                    if target.exists():
                        target.unlink()
                    try:
                        with staging.open("rb") as source, target.open("wb") as destination:
                            shutil.copyfileobj(source, destination, length=1024 * 1024)
                    except OSError as exc:
                        raise RuntimeError(
                            "O navegador gerou o PDF, mas o Windows não conseguiu copiá-lo para a pasta oficial. "
                            "Extraia o projeto em um caminho curto, como C:\\CentralCTe. "
                            f"Detalhe: {exc}"
                        ) from exc
                    if not target.is_file() or target.stat().st_size < 800:
                        raise RuntimeError("A cópia do PDF temporário para a saída oficial ficou incompleta.")
                    with target.open("rb") as stream:
                        if stream.read(5) != b"%PDF-":
                            raise RuntimeError("A cópia final não possui assinatura PDF válida.")
                return f"HTML oficial RC26.6 -> {browser.name} (saída temporária segura)" if staging is not None else f"HTML oficial RC26.6 -> {browser.name}"
            except Exception as exc:
                errors.append(f"Edge/Chrome: {exc}")
            finally:
                if staging is not None:
                    try:
                        staging.unlink(missing_ok=True)
                    except OSError:
                        pass

        if os.name == "nt" and self._weasyprint_available():
            try:
                from weasyprint import HTML
                HTML(string=document_html, base_url=str(self.project_root)).write_pdf(str(target))
                return "HTML oficial RC26.6 -> WeasyPrint (contingência)"
            except Exception as exc:
                errors.append(f"WeasyPrint: {exc}")

        raise RuntimeError("Nenhum backend conseguiu converter o HTML oficial em PDF. " + " | ".join(errors[-2:]))

    def preview(self, selected_path: str | Path, available_paths: Iterable[Path], *, include_compact: bool = True) -> dict[str, Any]:
        started = time.monotonic()
        paths = self._allowed_selection([selected_path], available_paths)
        infos = self._official_infos(paths, include_compact=include_compact)
        info = infos[0]
        identity = hashlib.sha256(
            (str(paths[0]) + "|" + file_sha256(paths[0]) + "|" + json.dumps({
                "validation": info.get("validacao") or {},
                "complementary": info.get(COMPLEMENTARY_INFO_KEY) or "",
                "include_compact": bool(include_compact),
            }, sort_keys=True, default=str)).encode("utf-8")
        ).hexdigest()[:24]
        self.preview_root.mkdir(parents=True, exist_ok=True)
        target = self.preview_root / f"preview_dacte_{identity}.pdf"
        cached = target.is_file() and target.stat().st_size > 800
        if not cached:
            html = self._render_html(infos)
            backend = self._html_to_pdf(html, target)
        contract = self._pdf_contract(target, minimum_pages=1)
        result = {
            "status": "concluido",
            "operation": "preview",
            "generated_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "cached": cached,
            "path": str(target),
            "name": target.name,
            "cte": str(info.get("numero") or ""),
            "partner": str(info.get("emitente") or ""),
            "renderer": backend,
            "include_compact": bool(include_compact),
            **contract,
        }
        write_json_atomic(self.last_run_path, result)
        return result

    def _timestamped_target(self, prefix: str, suffix: str) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.output_root / f"{prefix}_{stamp}{suffix}"
        counter = 2
        while target.exists():
            target = self.output_root / f"{prefix}_{stamp}_{counter}{suffix}"
            counter += 1
        return target

    def generate_batch(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        *,
        progress: Callable[[float, int, int, str, str], None] | None = None,
        include_compact: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        paths = self._allowed_selection(selected_paths, available_paths)
        total = len(paths)
        if progress:
            progress(5.0, 0, total, "", f"Validando {total} CT-e(s) selecionado(s).")
        infos = self._official_infos(paths, include_compact=include_compact)
        if progress:
            progress(22.0, total, total, "", f"Dados oficiais de {total} CT-e(s) preparados.")
        target = self._timestamped_target("lote_dactes_RC26_6_WEB", ".pdf")
        if progress:
            progress(35.0, total, total, target.name, "Montando o lote oficial em HTML.")
        html = self._render_html(infos)
        if progress:
            progress(48.0, total, total, target.name, "Convertendo o lote oficial para PDF. Esta etapa pode levar alguns minutos.")
        backend = self._html_to_pdf(html, target)
        if progress:
            progress(90.0, total, total, target.name, "Conferindo páginas, tamanho e integridade do PDF.")
        contract = self._pdf_contract(target, minimum_pages=len(infos))
        result = {
            "status": "concluido",
            "operation": "batch",
            "generated_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "path": str(target),
            "name": target.name,
            "documents": len(infos),
            "ctes": [str(info.get("numero") or "") for info in infos],
            "renderer": backend,
            "include_compact": bool(include_compact),
            **contract,
        }
        write_json_atomic(self.last_run_path, result)
        if progress:
            progress(100.0, total, total, target.name, "Lote oficial concluído e pronto para download.")
        return result

    def generate_individuals(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        *,
        progress: Callable[[float, int, int, str, str], None] | None = None,
        include_compact: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        paths = self._allowed_selection(selected_paths, available_paths)
        total = len(paths)
        if progress:
            progress(4.0, 0, total, "", f"Validando {total} CT-e(s) selecionado(s).")
        infos = self._official_infos(paths, include_compact=include_compact)
        if progress:
            progress(10.0, 0, total, "", "Dados oficiais carregados. Iniciando os PDFs individuais.")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        directory = self.individual_root / f"dactes_{stamp}"
        directory.mkdir(parents=True, exist_ok=False)
        used: set[str] = set()
        files: list[dict[str, Any]] = []
        backends: set[str] = set()
        try:
            for position, info in enumerate(infos, start=1):
                number = safe_component(info.get("numero"), "SEM NUMERO", 28)
                partner = safe_component(info.get("emitente") or info.get("parceiro"), "PARCEIRO", 70)
                if progress:
                    percent = 10.0 + ((position - 1) / max(1, total)) * 78.0
                    progress(percent, position - 1, total, f"CT-e {number}", f"Gerando PDF oficial {position} de {total}.")
                base = f"CT-e {number} {partner}"
                candidate = base
                counter = 2
                while candidate.casefold() in used:
                    candidate = f"{base} {counter}"
                    counter += 1
                used.add(candidate.casefold())
                target = directory / f"{candidate}.pdf"
                html = self._render_html([info])
                backend = self._html_to_pdf(html, target)
                backends.add(backend)
                contract = self._pdf_contract(target, minimum_pages=1)
                files.append({
                    "name": target.name,
                    "path": str(target),
                    "cte": str(info.get("numero") or ""),
                    **contract,
                })
                if progress:
                    percent = 10.0 + (position / max(1, total)) * 78.0
                    progress(percent, position, total, f"CT-e {number}", f"PDF oficial {position} de {total} concluído.")

            zip_target = self._timestamped_target("dactes_individuais_RC26_6_WEB", ".zip")
            if progress:
                progress(91.0, total, total, zip_target.name, "Compactando os PDFs oficiais em arquivo ZIP.")
            with zipfile.ZipFile(zip_target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for item in files:
                    archive.write(item["path"], item["name"])
            with zipfile.ZipFile(zip_target, "r") as archive:
                bad = archive.testzip()
                if bad:
                    raise RuntimeError(f"O pacote ZIP contém um PDF corrompido: {bad}")
            if progress:
                progress(97.0, total, total, zip_target.name, "Validando o pacote ZIP e calculando o SHA-256.")
            result = {
                "status": "concluido",
                "operation": "individuals",
                "generated_at": now_iso(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "path": str(zip_target),
                "name": zip_target.name,
                "documents": len(files),
                "files": files,
                "size_bytes": zip_target.stat().st_size,
                "sha256": file_sha256(zip_target),
                "renderer": ", ".join(sorted(backends)),
                "include_compact": bool(include_compact),
            }
            write_json_atomic(self.last_run_path, result)
            if progress:
                progress(100.0, total, total, zip_target.name, "Arquivos oficiais concluídos e prontos para download.")
            return result
        except Exception:
            raise

    def generate(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        *,
        mode: str = "batch",
        progress: Callable[[float, int, int, str, str], None] | None = None,
        include_compact: bool = True,
    ) -> dict[str, Any]:
        normalized = str(mode or "batch").strip().lower()
        with self._lock:
            if normalized == "batch":
                return self.generate_batch(selected_paths, available_paths, progress=progress, include_compact=include_compact)
            if normalized in {"individuals", "individuais", "zip"}:
                return self.generate_individuals(selected_paths, available_paths, progress=progress, include_compact=include_compact)
            raise ValueError("Modo DACTE inválido. Use batch ou individuals.")


__all__ = ["OfficialDacteService", "SERVICE_VERSION"]
