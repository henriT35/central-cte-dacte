from __future__ import annotations

"""Serviços diretos da página CT-e.

A camada recebe dicionários simples e funções já publicadas pelo runtime. Ela
não altera classes em tempo de execução, não procura páginas em ``sys.modules``
e não abre workers de polling.
"""

import importlib.util
import re
import sys
import types
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .helpers import CTeHelperService

SERVICES_VERSION = "2.7.0"


class CTePageServices:
    version = SERVICES_VERSION

    def __init__(self, helper_service: CTeHelperService | None = None) -> None:
        self.helpers = helper_service or CTeHelperService()

    @staticmethod
    def _norm(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return " ".join(text.upper().split())

    def is_cte(self, info: Mapping[str, Any] | None) -> bool:
        return self.helpers.is_cte(info)

    def selected_or_visible(self, view: Any) -> tuple[list[dict[str, Any]], str]:
        return self.helpers.selected_or_visible(view)

    def status_group(self, status: Any) -> str:
        return self.helpers.status_group(status)

    def report_bucket(self, status: Any) -> str:
        return self.helpers.report_bucket(status)

    def matches_page_status_filter(self, status: Any, selected_filter: Any) -> bool:
        return self.helpers.matches_page_status_filter(status, selected_filter)

    @staticmethod
    def clean_output_component(value: Any, fallback: str = "ARQUIVO") -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", text)
        text = re.sub(r"[^A-Za-z0-9. ()-]+", " ", text)
        text = re.sub(r"[\s._-]+", " ", text).strip(" .")
        return text or fallback

    def partner_name(self, info: Mapping[str, Any]) -> str:
        result = info.get("validacao") or info.get("validation") or {}
        emit = info.get("emit") or {}
        for value in (
            result.get("partner_name"),
            result.get("nome_parceiro"),
            result.get("partner_id"),
            info.get("parceiro"),
            info.get("partner_name"),
            info.get("emitente"),
            emit.get("nome"),
            emit.get("fant"),
        ):
            if str(value or "").strip():
                return self.clean_output_component(value, "PARCEIRO NAO IDENTIFICADO")
        return "PARCEIRO NAO IDENTIFICADO"

    def output_name(
        self,
        info: Mapping[str, Any],
        used: set[str],
        extension: str,
    ) -> str:
        number = self.clean_output_component(info.get("numero"), "SEM NUMERO")
        partner = self.partner_name(info)
        base = f"CT-e {number} {partner}".strip()
        candidate = base
        serial = 2
        while candidate.casefold() in used:
            candidate = f"{base} ({serial})"
            serial += 1
        used.add(candidate.casefold())
        return candidate + extension

    def write_individual_htmls(
        self,
        infos: Sequence[Mapping[str, Any]],
        output_dir: str | Path,
        render_document: Callable[..., str],
    ) -> list[Path]:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()
        generated: list[Path] = []
        for info in infos:
            name = self.output_name(info, used, ".html")
            target = target_dir / name
            if target.exists():
                stem = target.stem
                serial = 2
                while target.exists():
                    target = target_dir / f"{stem} ({serial}).html"
                    serial += 1
            html = render_document([dict(info)], with_button=True)
            target.write_text(str(html), encoding="utf-8")
            generated.append(target)
        return generated

    @staticmethod
    def write_batch_html(
        infos: Sequence[Mapping[str, Any]],
        output_path: str | Path,
        render_document: Callable[..., str],
    ) -> Path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        html = render_document([dict(info) for info in infos], with_button=True)
        target.write_text(str(html), encoding="utf-8")
        return target

    @staticmethod
    def apply_complementary_information(
        infos: Sequence[dict[str, Any]],
        text: Any,
        *,
        cleaner: Callable[..., str],
        applier: Callable[[Sequence[dict[str, Any]], str], int],
        max_chars: int,
    ) -> int:
        cleaned = str(cleaner(text, limit=False) or "")
        if not cleaned:
            raise ValueError("Digite a informação complementar.")
        if len(cleaned) > int(max_chars):
            raise ValueError(
                f"O texto ultrapassa o limite de {int(max_chars)} caracteres."
            )
        return int(applier(list(infos), cleaned) or 0)

    def exact_status_values(self, infos: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
        values = {
            str((info.get("validacao") or {}).get("status") or "NÃO PROCESSADO").strip()
            for info in infos
            if isinstance(info, Mapping)
        }
        values.discard("")
        return ("TODOS", *sorted(values, key=self._norm))

    def has_ignored_nfs(self, info: Mapping[str, Any]) -> bool:
        return self.helpers.has_ignored_nfs(info)

    def matches_advanced_filters(
        self,
        info: Mapping[str, Any],
        *,
        exact_status: Any = "TODOS",
        manual_review: Any = "TODOS",
        observation: Any = "TODOS",
        ignored_nfs: Any = "TODOS",
    ) -> bool:
        result = info.get("validacao") or {}
        raw_status = str(result.get("status") or "NÃO PROCESSADO").strip()
        exact = self._norm(exact_status)
        if exact not in {"", "TODOS"} and self._norm(raw_status) != exact:
            return False

        review = self._norm(manual_review)
        reviewed = self._norm(info.get("revisao_manual")) == "REVISADO"
        if review == "REVISADO" and not reviewed:
            return False
        if review == "NAO REVISADO" and reviewed:
            return False

        observation_mode = self._norm(observation)
        has_observation = bool(str(info.get("observacao_manual") or "").strip())
        if observation_mode == "COM OBSERVACAO" and not has_observation:
            return False
        if observation_mode == "SEM OBSERVACAO" and has_observation:
            return False

        ignored_mode = self._norm(ignored_nfs)
        has_ignored = self.has_ignored_nfs(info)
        if ignored_mode == "COM NFS IGNORADAS" and not has_ignored:
            return False
        if ignored_mode == "SEM NFS IGNORADAS" and has_ignored:
            return False
        return True

    @staticmethod
    def _load_signature_plugin(engine_dir: Path) -> types.ModuleType:
        name = "central_cte_assinatura_pdf_2_6_65_18"
        existing = sys.modules.get(name)
        if isinstance(existing, types.ModuleType):
            return existing
        path = engine_dir / "assinatura_pdf_engine_2_6_65_18.py"
        if not path.exists():
            raise FileNotFoundError(f"Motor de assinatura e PDF não encontrado: {path}")
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Não foi possível criar o carregador de assinatura e PDF.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def open_signature_manager(
        self,
        *,
        runtime_dir: str | Path,
        engine_dir: str | Path,
        render_document: Callable[..., str],
        infos_provider: Callable[[], tuple[list[dict[str, Any]], str]],
    ) -> Any:
        plugin = self._load_signature_plugin(Path(engine_dir))
        dialog_class = getattr(plugin, "SignatureManagerDialog", None)
        if not isinstance(dialog_class, type):
            raise RuntimeError("A interface de assinatura e PDF não foi publicada pelo motor.")
        try:
            widgets = __import__("PySide6.QtWidgets", fromlist=["QApplication"])
        except Exception as exc:
            raise RuntimeError(
                "O editor de Assinaturas e PDF requer o executável oficial com PySide6; "
                "ele não é executado no modo Tk de contingência."
            ) from exc
        application = widgets.QApplication.instance()
        if application is None:
            application = widgets.QApplication([])
        engine_bridge = types.SimpleNamespace(render_document=render_document)
        dialog = dialog_class(
            None,
            Path(runtime_dir),
            engine_bridge,
            infos_provider,
        )
        return dialog.exec()


__all__ = ["SERVICES_VERSION", "CTePageServices"]
