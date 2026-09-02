from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .common import VERSION, _atomic_write_text, _unique_path, cte_output_basename
from .html_signer import STAMP_SIZE_LABELS, normalize_stamp_size, render_signed_batch_html, render_signed_html
from .models import SignatureProfile
from .profiles import SignatureProfileStore
from .pdf_converter import find_browser, html_text_to_pdf, validate_pdf_file

class PdfBatchExporter:
    def __init__(self, runtime_dir: Path, engine: Any, store: SignatureProfileStore):
        self.runtime_dir = Path(runtime_dir)
        self.engine = engine
        self.store = store

    def export(
        self,
        infos: list[dict[str, Any]],
        profile: SignatureProfile,
        date_text: str,
        output_root: Optional[Path] = None,
        individuals: bool = True,
        batch: bool = True,
        position: Optional[str] = None,
        stamp_size: str = "official",
        source_description: str = "marcados",
    ) -> dict[str, Any]:
        if not infos:
            raise RuntimeError("Nenhum CT-e foi selecionado.")
        if not individuals and not batch:
            raise RuntimeError("Selecione PDF separado, lote único ou ambos.")
        if not profile.ready or not Path(profile.processed_file).exists():
            raise RuntimeError("O perfil ainda não possui uma assinatura digitalizada e tratada.")
        browser = find_browser()
        if browser is None:
            raise RuntimeError("Microsoft Edge ou Google Chrome não foi localizado para a conversão em PDF.")

        stamp_size = normalize_stamp_size(stamp_size or profile.stamp_size)
        timestamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        root = Path(output_root) if output_root else self.runtime_dir / "saida_pdf" / timestamp
        individuals_dir = root / "individuais"
        batch_dir = root / "lote"
        logs_dir = root
        root.mkdir(parents=True, exist_ok=True)
        generated: list[Path] = []
        failures: list[dict[str, str]] = []
        used: set[str] = set()

        if individuals:
            individuals_dir.mkdir(parents=True, exist_ok=True)
            for info in infos:
                basename = cte_output_basename(info, used)
                target = _unique_path(individuals_dir / f"{basename}.pdf")
                try:
                    document = render_signed_html(self.engine, info, profile, date_text, position, stamp_size)
                    html_text_to_pdf(document, target, browser=browser)
                    validate_pdf_file(target)
                    generated.append(target)
                except Exception as exc:
                    failures.append({"cte": str(info.get("numero") or ""), "arquivo": str(target), "erro": str(exc)})

        batch_path = None
        if batch:
            batch_dir.mkdir(parents=True, exist_ok=True)
            batch_path = _unique_path(batch_dir / f"Lote CT-e {datetime.now():%Y-%m-%d} {len(infos)} documentos.pdf")
            try:
                document = render_signed_batch_html(self.engine, infos, profile, date_text, position, stamp_size)
                html_text_to_pdf(document, batch_path, browser=browser)
                validate_pdf_file(batch_path)
                generated.append(batch_path)
            except Exception as exc:
                failures.append({"cte": "LOTE", "arquivo": str(batch_path), "erro": str(exc)})
                batch_path = None

        manifest = {
            "version": VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "selection_source": source_description,
            "requested": len(infos),
            "individuals_requested": individuals,
            "batch_requested": batch,
            "profile": asdict(profile),
            "date": date_text,
            "position": position or profile.position,
            "stamp_size": stamp_size,
            "stamp_size_label": STAMP_SIZE_LABELS.get(stamp_size, "Oficial - 85 x 32 mm"),
            "browser": str(browser),
            "generated": [str(path) for path in generated],
            "failures": failures,
            "xml_originals_modified": False,
        }
        manifest_path = logs_dir / "manifestacao_geracao.json"
        _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        txt_path = logs_dir / "manifestacao_geracao.txt"
        lines = [
            f"Central CT-e / DACTE - Assinatura e PDF {VERSION}",
            f"Data: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Origem da seleção: {source_description}",
            f"CT-es solicitados: {len(infos)}",
            f"Arquivos gerados: {len(generated)}",
            f"Falhas: {len(failures)}",
            f"Perfil: {profile.name} ({profile.id})",
            f"Responsável: {profile.person_name}",
            f"Data impressa: {date_text}",
            f"Tamanho do carimbo: {STAMP_SIZE_LABELS.get(stamp_size, 'Oficial - 85 x 32 mm')}",
            f"XML fiscal original alterado: NÃO",
            "",
            "ARQUIVOS GERADOS:",
            *[str(path) for path in generated],
        ]
        if failures:
            lines.extend(["", "FALHAS:"])
            lines.extend(f"CT-e {item['cte']}: {item['erro']}" for item in failures)
        _atomic_write_text(txt_path, "\n".join(lines))

        profile.stamp_size = stamp_size
        profile.last_used_at = datetime.now().isoformat(timespec="seconds")
        self.store.upsert(profile)
        return {
            "root": root,
            "generated": generated,
            "failures": failures,
            "batch": batch_path,
            "manifest": manifest_path,
        }
