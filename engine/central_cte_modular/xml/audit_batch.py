from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from .shadow_parser import ParserShadowComparator, ShadowComparison
from .shadow_report import ParserShadowReport

BATCH_VERSION = "2.6.66.5"


@dataclass(frozen=True)
class BatchAuditResult:
    version: str
    requested_inputs: int
    xml_files_found: int
    processed: int
    equal: int
    informative: int
    critical: int
    failed: int
    files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ParserBatchAudit:
    """Executa a mesma comparação sombra sobre arquivos ou pastas inteiras."""

    def __init__(self, comparator: ParserShadowComparator, reporter: ParserShadowReport) -> None:
        self.comparator = comparator
        self.reporter = reporter

    def run(self, inputs: Path | str | Iterable[Path | str], *, recursive: bool = True) -> dict[str, Any]:
        requested = self._coerce_inputs(inputs)
        files = self._collect_xml_files(requested, recursive=recursive)
        comparisons: list[ShadowComparison] = []
        failed = 0
        for path in files:
            try:
                comparisons.append(self.comparator.compare(path))
            except Exception:
                failed += 1
        self.reporter.rebuild_consolidated()
        result = BatchAuditResult(
            version=BATCH_VERSION,
            requested_inputs=len(requested),
            xml_files_found=len(files),
            processed=len(comparisons),
            equal=sum(1 for item in comparisons if item.status == "IGUAL"),
            informative=sum(1 for item in comparisons if item.status == "INFORMATIVA"),
            critical=sum(1 for item in comparisons if item.status == "CRÍTICA"),
            failed=failed,
            files=tuple(str(path) for path in files),
        )
        return result.to_dict()

    @staticmethod
    def _coerce_inputs(inputs: Path | str | Iterable[Path | str]) -> list[Path]:
        if isinstance(inputs, (str, Path)):
            return [Path(inputs)]
        return [Path(value) for value in inputs]

    @staticmethod
    def _collect_xml_files(inputs: Iterable[Path], *, recursive: bool) -> list[Path]:
        unique: dict[str, Path] = {}
        for raw in inputs:
            path = raw.expanduser()
            if path.is_file() and path.suffix.casefold() == ".xml":
                candidate = path.resolve()
                unique[str(candidate).casefold()] = candidate
                continue
            if not path.is_dir():
                continue
            iterator = path.rglob("*.xml") if recursive else path.glob("*.xml")
            for candidate in iterator:
                if candidate.is_file():
                    resolved = candidate.resolve()
                    unique[str(resolved).casefold()] = resolved
        return sorted(unique.values(), key=lambda item: str(item).casefold())
