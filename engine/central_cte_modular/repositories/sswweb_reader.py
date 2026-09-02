from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterator, Sequence

from ..infrastructure.normalization import normalize_header


class SswWebBaseReader:
    """Leitor streaming dos relatórios CSV exportados pelo SSW.

    Os arquivos usam a extensão ``.sswweb``, codificação Windows-1252,
    separador ``;`` e uma primeira coluna de controle:

    * ``0``: metadados do relatório;
    * ``1``: cabeçalho;
    * ``2``: registro de dados;
    * ``9``: fim do arquivo.

    Uma pasta pode conter vários períodos. O leitor valida que todos usam o
    mesmo cabeçalho e produz uma única sequência lógica de linhas.
    """

    SUFFIX = ".sswweb"
    ENCODING = "cp1252"

    @classmethod
    def source_files(cls, source: str | Path | Sequence[str | Path]) -> list[Path]:
        if isinstance(source, (list, tuple, set)):
            files = [Path(item).resolve() for item in source]
        else:
            path = Path(source).resolve()
            if path.is_dir():
                files = sorted(
                    (item for item in path.iterdir() if item.is_file() and item.suffix.lower() == cls.SUFFIX),
                    key=lambda item: item.name.lower(),
                )
            else:
                files = [path]

        missing = [str(path) for path in files if not path.is_file()]
        if missing:
            raise FileNotFoundError("Arquivo(s) SSW não encontrado(s): " + ", ".join(missing))
        invalid = [str(path) for path in files if path.suffix.lower() != cls.SUFFIX]
        if invalid:
            raise ValueError("Fonte SSW inválida: " + ", ".join(invalid))
        if not files:
            raise ValueError("Nenhum arquivo .sswweb foi encontrado na pasta selecionada.")
        return files

    @staticmethod
    def _trim_trailing_empty(row: list[str]) -> list[str]:
        while row and not str(row[-1] or "").strip():
            row.pop()
        return row

    @staticmethod
    def _header_key(header: list[Any]) -> tuple[str, ...]:
        return tuple(normalize_header(value) for value in header)

    def _iter_file(self, path: Path) -> Iterator[tuple[str, list[str], int]]:
        try:
            stream = path.open("r", encoding=self.ENCODING, newline="")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Não foi possível ler {path.name} como Windows-1252.") from exc

        with stream:
            reader = csv.reader(stream, delimiter=";", quotechar='"')
            for line_number, row in enumerate(reader, start=1):
                if not row:
                    continue
                marker = str(row[0] or "").replace("\ufeff", "").strip()
                yield marker, list(row[1:]), line_number

    def iter_sheet(self, source: str | Path | Sequence[str | Path]) -> Iterator[list[Any]]:
        expected_header: list[str] | None = None
        expected_key: tuple[str, ...] | None = None

        for path in self.source_files(source):
            file_header: list[str] | None = None
            data_seen = False

            for marker, payload, line_number in self._iter_file(path):
                if marker == "0":
                    continue
                if marker == "1":
                    candidate = self._trim_trailing_empty(payload)
                    if not candidate:
                        raise ValueError(f"Cabeçalho vazio em {path.name}, linha {line_number}.")
                    key = self._header_key(candidate)
                    if expected_header is None:
                        expected_header = candidate
                        expected_key = key
                        yield list(expected_header)
                    elif key != expected_key:
                        first_difference = next(
                            (
                                index
                                for index, (left, right) in enumerate(zip(expected_key or (), key), start=1)
                                if left != right
                            ),
                            min(len(expected_key or ()), len(key)) + 1,
                        )
                        raise ValueError(
                            f"O cabeçalho de {path.name} difere dos demais na coluna {first_difference}."
                        )
                    file_header = candidate
                    continue
                if marker == "2":
                    if file_header is None:
                        raise ValueError(
                            f"Registro de dados antes do cabeçalho em {path.name}, linha {line_number}."
                        )
                    data_seen = True
                    width = len(file_header)
                    row = list(payload)
                    while len(row) > width and not str(row[-1] or "").strip():
                        row.pop()
                    if len(row) > width:
                        raise ValueError(
                            f"Linha {line_number} de {path.name} possui {len(row)} campos; esperado: {width}."
                        )
                    if len(row) < width:
                        row.extend([""] * (width - len(row)))
                    yield row
                    continue
                if marker == "9":
                    break
                if marker:
                    raise ValueError(
                        f"Marcador SSW desconhecido '{marker}' em {path.name}, linha {line_number}."
                    )

            if file_header is None:
                raise ValueError(f"Cabeçalho SSW não encontrado em {path.name}.")
            if not data_seen:
                raise ValueError(f"Nenhum registro de dados foi encontrado em {path.name}.")

    def read_sheet(self, source: str | Path | Sequence[str | Path]) -> list[list[Any]]:
        return list(self.iter_sheet(source))

    def read_sheet_sample(
        self,
        source: str | Path | Sequence[str | Path],
        max_data_rows: int = 500,
    ) -> list[list[Any]]:
        limit = max(1, int(max_data_rows)) + 1
        rows: list[list[Any]] = []
        for row in self.iter_sheet(source):
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows
