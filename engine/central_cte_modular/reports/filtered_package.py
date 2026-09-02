from __future__ import annotations

"""Exportação atômica de pacotes filtrados de CT-e.

A pasta final só aparece depois que XMLs, relatório, HTML e resumo foram
concluídos. Em caso de erro, o diretório temporário é removido para que o
operador nunca receba um pacote pela metade.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class FilteredPackageResult:
    root: Path
    copied: int
    missing: tuple[str, ...] = field(default_factory=tuple)
    counts: Mapping[str, int] = field(default_factory=dict)
    report_path: Path | None = None
    html_path: Path | None = None


def _unique_final_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10000):
        candidate = path.with_name(f"{path.name}_{index}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.name}_{datetime.now().strftime('%f')}")


def _unique_destination(directory: Path, name: str) -> Path:
    target = directory / name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(2, 10000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}_{datetime.now().strftime('%H%M%S%f')}{suffix}"


def create_filtered_validation_package(
    infos: Iterable[dict[str, Any]],
    *,
    parent_dir: str | Path,
    label: str,
    app_title: str,
    app_version: str,
    status_of: Callable[[dict[str, Any]], str],
    bucket_of: Callable[[str], str],
    sanitize_label: Callable[[str], str],
    report_writer: Callable[[Path, list[dict[str, Any]]], Any],
    render_document: Callable[..., str] | None = None,
    now: datetime | None = None,
) -> FilteredPackageResult:
    """Cria um pacote completo em diretório temporário e promove-o no sucesso."""

    items = list(infos or [])
    if not items:
        raise ValueError("O filtro atual não possui nenhum arquivo para empacotar.")

    parent = Path(parent_dir)
    parent.mkdir(parents=True, exist_ok=True)
    safe_label = str(label or "todos").strip() or "todos"
    moment = now or datetime.now()
    stamp = moment.strftime("%Y%m%d_%H%M%S")
    final_root = _unique_final_path(parent / f"pacote_{safe_label}_{stamp}")
    temp_root = Path(
        tempfile.mkdtemp(prefix=f".{final_root.name}_tmp_", dir=str(parent))
    )

    copied = 0
    missing: list[str] = []
    counts: dict[str, int] = {}
    report_path: Path | None = None
    html_path: Path | None = None

    try:
        for info in items:
            status = str(status_of(info) or "NÃO VALIDADO")
            bucket = str(bucket_of(status) or "OUTROS")
            status_label = str(sanitize_label(status) or "nao_validado")[:42]
            folder = temp_root / f"{bucket}_{status_label}"
            folder.mkdir(parents=True, exist_ok=True)

            raw_path = str(info.get("path") or "")
            source = Path(raw_path) if raw_path else None
            if source is not None and source.is_file():
                destination = _unique_destination(folder, source.name)
                shutil.copy2(source, destination)
                copied += 1
            else:
                missing.append(str(info.get("arquivo") or raw_path or "arquivo sem nome"))
            counts[status] = counts.get(status, 0) + 1

        report_path = temp_root / f"relatorio_{safe_label}.xlsx"
        report_writer(report_path, items)
        if not report_path.is_file() or report_path.stat().st_size <= 0:
            raise RuntimeError("O relatório do pacote não foi gravado corretamente.")

        cte_infos = [info for info in items if str(info.get("tipo") or "") == "CT-e"]
        if cte_infos and callable(render_document):
            html_path = temp_root / f"dacte_{safe_label}.html"
            html = render_document(cte_infos, with_button=True)
            html_path.write_text(str(html or ""), encoding="utf-8")
            if html_path.stat().st_size <= 0:
                raise RuntimeError("O HTML do pacote foi gerado vazio.")

        summary_lines = [
            f"{app_title} - {app_version}",
            "PACOTE DE CONFERÊNCIA",
            "=" * 72,
            f"Gerado em: {moment.strftime('%d/%m/%Y %H:%M:%S')}",
            f"Filtro usado: {safe_label}",
            f"Arquivos no filtro: {len(items)}",
            f"Arquivos copiados: {copied}",
            f"Relatório: {report_path.name}",
        ]
        if html_path is not None:
            summary_lines.append(f"DACTE HTML: {html_path.name}")
        summary_lines.extend(["", "STATUS", "-" * 72])
        for status, quantity in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            summary_lines.append(f"{status}: {quantity}")
        if missing:
            summary_lines.extend(["", "ARQUIVOS NÃO COPIADOS", "-" * 72])
            summary_lines.extend(missing[:80])
            if len(missing) > 80:
                summary_lines.append(f"... mais {len(missing) - 80} arquivo(s).")

        summary_path = temp_root / "RESUMO_DO_PACOTE.txt"
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        if summary_path.stat().st_size <= 0:
            raise RuntimeError("O resumo do pacote foi gerado vazio.")

        os.replace(temp_root, final_root)
        return FilteredPackageResult(
            root=final_root,
            copied=copied,
            missing=tuple(missing),
            counts=dict(counts),
            report_path=final_root / report_path.name,
            html_path=(final_root / html_path.name) if html_path is not None else None,
        )
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


__all__ = ["FilteredPackageResult", "create_filtered_validation_package"]
