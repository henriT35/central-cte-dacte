from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApplicationPaths:
    root: Path
    engine: Path
    internal: Path
    logs: Path
    cache: Path
    sessions: Path
    reports: Path
    invoices: Path
    bases: Path
    models: Path
    tables: Path
    xmls: Path
    html_output: Path
    assets: Path
    config: Path
    docs: Path

    @classmethod
    def from_engine_file(cls, engine_file: Path) -> "ApplicationPaths":
        file_path = Path(engine_file).resolve()
        engine_dir = file_path.parent
        if engine_dir.name.lower() == "engine" and engine_dir.parent.name.lower() == "_internal":
            root = engine_dir.parent.parent
        elif engine_dir.name.lower() == "engine":
            root = engine_dir.parent
        else:
            root = engine_dir
        return cls(
            root=root,
            engine=root / "engine",
            internal=root / "_internal",
            logs=root / "logs",
            cache=root / "cache",
            sessions=root / "sessoes",
            reports=root / "relatorios",
            invoices=root / "faturas",
            bases=root / "bases",
            models=root / "modelos",
            tables=root / "tabelas",
            xmls=root / "xmls",
            html_output=root / "saida_html",
            assets=root / "assets",
            config=root / "config",
            docs=root / "docs",
        )

    def ensure_runtime_directories(self) -> None:
        for path in (self.logs, self.cache, self.sessions, self.reports, self.invoices, self.tables, self.xmls, self.html_output):
            path.mkdir(parents=True, exist_ok=True)
