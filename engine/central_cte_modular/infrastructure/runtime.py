from __future__ import annotations

import os
import shutil
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeEnvironment:
    """Paths and desktop operations compatible with the legacy engine."""

    engine_file: Path

    @classmethod
    def from_engine_file(cls, engine_file: Path) -> "RuntimeEnvironment":
        return cls(Path(engine_file).resolve())

    def resource_path(self, relative_path: Any) -> Path:
        relative = Path(str(relative_path))
        candidates: list[Path] = []
        try:
            candidates.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if getattr(sys, "frozen", False):
                candidates.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
        engine_dir = self.engine_file.parent
        candidates.extend((engine_dir, engine_dir.parent))
        seen: set[str] = set()
        for base_path in candidates:
            key = str(base_path)
            if key in seen:
                continue
            seen.add(key)
            candidate = base_path / relative
            if candidate.exists():
                return candidate
        return (candidates[0] if candidates else engine_dir) / relative

    def runtime_dir(self) -> Path:
        try:
            if getattr(sys, "frozen", False):
                return Path(sys.executable).resolve().parent
        except Exception:
            pass
        engine_dir = self.engine_file.parent
        # Na distribuição em código-fonte, o motor fica em <app>/engine,
        # enquanto bases, tabelas, relatórios e cache pertencem à raiz <app>.
        if engine_dir.name.casefold() == "engine":
            return engine_dir.parent
        return engine_dir

    @staticmethod
    def open_path(path: Any) -> None:
        target = Path(path)
        try:
            if os.name == "nt":
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                webbrowser.open(target.resolve().as_uri())
        except Exception:
            webbrowser.open(str(target))

    def ensure_work_folders(self) -> dict[str, Path]:
        base = self.runtime_dir()
        folders = {
            "raiz": base,
            "bases": base / "bases",
            "tabelas": base / "tabelas",
            "xmls": base / "xmls",
            "relatorios": base / "relatorios",
            "logs": base / "logs",
            "sessoes": base / "sessoes",
            "cache": base / "cache",
            "saida_html": base / "saida_html",
        }
        for key, folder in folders.items():
            if key != "raiz":
                folder.mkdir(parents=True, exist_ok=True)
        source = self.resource_path("modelos/cadastro_tabelas_parceiros_v1.xlsx")
        destination = folders["tabelas"] / "cadastro_tabelas_parceiros.xlsx"
        if source.exists() and not destination.exists():
            try:
                shutil.copy2(source, destination)
            except Exception:
                pass
        return folders
