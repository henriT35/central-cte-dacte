# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
import re
import threading
import time
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - tratado pela prontidão da função
    PdfReader = None

SERVICE_VERSION = "2.7.0 RC27.14 WEB/WINDOWS MVP13 R12.13.9"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_SIGNATURE_PDF_BYTES = 30 * 1024 * 1024
MAX_PDF_IMAGE_RESPONSE_BYTES = 24 * 1024 * 1024
ALLOWED_POSITIONS = {
    "official-stamp",
    "custom",
    "reference-docs",
    "signature-field-legacy",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(value: Any, fallback: str = "assinatura") -> str:
    name = Path(str(value or fallback).replace("\\", "/")).name.strip().replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9À-ÿ._()\- ]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or fallback)[:160]


def decode_data_url(value: Any, maximum: int = MAX_IMAGE_BYTES) -> tuple[str, bytes]:
    text = str(value or "")
    match = re.fullmatch(r"data:([^;,]+);base64,(.+)", text, flags=re.I | re.S)
    if not match:
        raise ValueError("A imagem enviada não está em um formato Base64 válido.")
    mime = match.group(1).strip().lower()
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("A imagem enviada possui Base64 inválido.") from exc
    if not payload:
        raise ValueError("A imagem enviada está vazia.")
    if len(payload) > maximum:
        raise ValueError(f"A imagem ultrapassa o limite de {maximum // (1024 * 1024)} MB.")
    return mime, payload


def png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError("A imagem tratada não é um PNG válido.")
    width = int.from_bytes(payload[16:20], "big")
    height = int.from_bytes(payload[20:24], "big")
    if width < 20 or height < 10:
        raise ValueError("A assinatura tratada ficou pequena demais.")
    if width > 8000 or height > 8000 or width * height > 30_000_000:
        raise ValueError("A assinatura tratada possui dimensões excessivas.")
    return width, height


def original_extension(mime: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    aliases = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
    }
    resolved = aliases.get(mime, suffix)
    if resolved not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}:
        raise ValueError("Formato original não permitido. Use PNG, JPG, WEBP, BMP ou PDF.")
    return ".jpg" if resolved == ".jpeg" else resolved


def _image_mime(payload: bytes, name: str = "") -> str:
    suffix = Path(str(name or "")).suffix.lower()
    if payload.startswith(b"\x89PNG\r\n\x1a\n") or suffix == ".png":
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff") or suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if payload.startswith(b"BM") or suffix == ".bmp":
        return "image/bmp"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _jpeg_dimensions(payload: bytes) -> tuple[int, int]:
    if not payload.startswith(b"\xff\xd8"):
        return 0, 0
    index = 2
    while index + 9 < len(payload):
        if payload[index] != 0xFF:
            index += 1
            continue
        marker = payload[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(payload):
            break
        length = int.from_bytes(payload[index:index + 2], "big")
        if length < 2 or index + length > len(payload):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and length >= 7:
            height = int.from_bytes(payload[index + 3:index + 5], "big")
            width = int.from_bytes(payload[index + 5:index + 7], "big")
            return width, height
        index += length
    return 0, 0


def _basic_image_dimensions(mime: str, payload: bytes) -> tuple[int, int]:
    try:
        if mime == "image/png" and len(payload) >= 24:
            return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")
        if mime == "image/jpeg":
            return _jpeg_dimensions(payload)
        if mime == "image/bmp" and len(payload) >= 26:
            return abs(int.from_bytes(payload[18:22], "little", signed=True)), abs(int.from_bytes(payload[22:26], "little", signed=True))
        if mime == "image/webp" and len(payload) >= 30:
            kind = payload[12:16]
            if kind == b"VP8X":
                width = 1 + int.from_bytes(payload[24:27], "little")
                height = 1 + int.from_bytes(payload[27:30], "little")
                return width, height
    except Exception:
        pass
    return 0, 0


class OfficialSignatureService:
    """Perfis e assinatura visual sobre o HTML/PDF oficial do RC26.6.

    A assinatura é uma representação visual. O XML autorizado não é alterado e
    este serviço não cria assinatura digital com certificado ICP-Brasil.
    """

    def __init__(self, project_root: Path, data_root: Path, state_root: Path, xml_service: Any, dacte_service: Any):
        self.project_root = Path(project_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.xml_service = xml_service
        self.dacte_service = dacte_service
        self.last_run_path = self.state_root / "signature_last_run.json"
        self._store: Any | None = None
        self._lock = threading.RLock()

    def _plugin(self) -> Any:
        return self.dacte_service._load_plugin()

    def _profile_store(self) -> Any:
        with self._lock:
            if self._store is None:
                plugin = self._plugin()
                self._store = plugin.SignatureProfileStore(self.data_root)
            return self._store

    @staticmethod
    def _clamp(value: Any, minimum: float, maximum: float, fallback: float) -> float:
        try:
            number = float(value)
            if number != number:
                return fallback
            return max(minimum, min(maximum, number))
        except Exception:
            return fallback

    def _serialize_profile(self, profile: Any) -> dict[str, Any]:
        data = asdict(profile)
        processed = Path(str(data.get("processed_file") or ""))
        original = Path(str(data.get("original_file") or ""))
        data["ready"] = bool(processed.is_file() and processed.stat().st_size > 20)
        data["processed_exists"] = processed.is_file()
        data["original_exists"] = original.is_file()
        data["processed_sha256"] = file_sha256(processed) if processed.is_file() else ""
        data["processed_size_bytes"] = processed.stat().st_size if processed.is_file() else 0
        return data

    def list_profiles(self) -> list[dict[str, Any]]:
        profiles = [self._serialize_profile(profile) for profile in self._profile_store().load()]
        profiles.sort(key=lambda item: (str(item.get("last_used_at") or ""), str(item.get("updated_at") or "")), reverse=True)
        return profiles

    def readiness(self) -> dict[str, Any]:
        error = ""
        connected = False
        image_backend = "Navegador (Canvas)"
        try:
            plugin = self._plugin()
            required = (
                "SignatureProfileStore",
                "SignatureProfile",
                "registration_sheet_html",
                "render_signed_html",
                "render_signed_batch_html",
            )
            missing = [name for name in required if not hasattr(plugin, name)]
            if missing:
                raise RuntimeError("Motor de assinatura sem: " + ", ".join(missing))
            self._profile_store()
            dacte = self.dacte_service.readiness()
            if not dacte.get("connected"):
                raise RuntimeError(dacte.get("status") or "Serviço DACTE indisponível.")
            connected = True
        except Exception as exc:
            error = str(exc)
        return {
            "connected": connected,
            "service_version": SERVICE_VERSION,
            "status": (
                "Perfis, tratamento no navegador, posicionamento e DACTE assinado disponíveis."
                if connected
                else f"Serviço de assinatura indisponível: {error or 'dependência ausente.'}"
            ),
            "profiles": self.list_profiles() if connected else [],
            "profile_count": len(self.list_profiles()) if connected else 0,
            "image_backend": image_backend,
            "visual_signature_only": True,
            "certificate_signature": False,
            "last_run": self._read_last_run(),
        }

    def _read_last_run(self) -> dict[str, Any]:
        try:
            if self.last_run_path.is_file():
                return json.loads(self.last_run_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _write_last_run(self, payload: Mapping[str, Any]) -> None:
        self.last_run_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.last_run_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.last_run_path)

    def create_profile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        person_name = str(payload.get("person_name") or "").strip()
        if not name or not person_name:
            raise ValueError("Informe o nome do perfil e o responsável.")
        position = str(payload.get("position") or "official-stamp").strip().lower()
        if position not in ALLOWED_POSITIONS:
            position = "official-stamp"
        profile = self._profile_store().create_profile(
            name=name[:80],
            person_name=person_name[:120],
            role=str(payload.get("role") or "").strip()[:120],
            title=str(payload.get("title") or "REDESPACHO").strip()[:60] or "REDESPACHO",
            position=position,
        )
        return self._serialize_profile(profile)

    def update_profile(self, profile_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        store = self._profile_store()
        profile = store.get(str(profile_id or "").strip())
        if profile is None:
            raise ValueError("Perfil de assinatura não encontrado.")
        for field, limit in (("name", 80), ("person_name", 120), ("role", 120), ("title", 60)):
            if field in payload:
                value = str(payload.get(field) or "").strip()[:limit]
                if field in {"name", "person_name"} and not value:
                    raise ValueError("Nome do perfil e responsável não podem ficar vazios.")
                setattr(profile, field, value)
        if "active" in payload:
            profile.active = bool(payload.get("active"))
        if "threshold" in payload:
            profile.threshold = int(self._clamp(payload.get("threshold"), 205, 252, 242))
        if "position" in payload:
            position = str(payload.get("position") or "official-stamp").strip().lower()
            if position not in ALLOWED_POSITIONS:
                raise ValueError("Posição de assinatura inválida.")
            profile.position = position
        plugin = self._plugin()
        profile.custom_x_mm = self._clamp(payload.get("custom_x_mm", profile.custom_x_mm), -15, 195, plugin.STAMP_OFFICIAL_X_MM)
        profile.custom_y_mm = self._clamp(payload.get("custom_y_mm", profile.custom_y_mm), -15, 285, plugin.STAMP_OFFICIAL_Y_MM)
        profile.custom_width_mm = self._clamp(payload.get("custom_width_mm", profile.custom_width_mm), plugin.STAMP_MIN_WIDTH_MM, plugin.STAMP_MAX_WIDTH_MM, plugin.STAMP_STANDARD_WIDTH_MM)
        profile.custom_height_mm = round(profile.custom_width_mm / plugin.STAMP_STANDARD_ASPECT, 3)
        profile.custom_rotation_deg = self._clamp(payload.get("custom_rotation_deg", profile.custom_rotation_deg), -30, 30, 0)
        profile.signature_scale_percent = self._clamp(
            payload.get("signature_scale_percent", profile.signature_scale_percent),
            plugin.SIGNATURE_SCALE_MIN_PERCENT,
            plugin.SIGNATURE_SCALE_MAX_PERCENT,
            100,
        )
        profile.signature_offset_x_mm = self._clamp(
            payload.get("signature_offset_x_mm", profile.signature_offset_x_mm),
            -plugin.SIGNATURE_OFFSET_LIMIT_MM,
            plugin.SIGNATURE_OFFSET_LIMIT_MM,
            0,
        )
        profile.signature_offset_y_mm = self._clamp(
            payload.get("signature_offset_y_mm", profile.signature_offset_y_mm),
            -plugin.SIGNATURE_OFFSET_LIMIT_MM,
            plugin.SIGNATURE_OFFSET_LIMIT_MM,
            0,
        )
        if any(key in payload for key in ("custom_x_mm", "custom_y_mm", "custom_width_mm", "custom_rotation_deg")):
            profile.position = "custom"
            profile.stamp_size = "custom"
        store.upsert(profile)
        return self._serialize_profile(profile)

    def delete_profile(self, profile_id: str) -> bool:
        if not self._profile_store().delete(str(profile_id or "").strip()):
            raise ValueError("Perfil de assinatura não encontrado.")
        return True

    def _automatic_registration_signature(self, payload: bytes, original_name: str) -> tuple[dict[str, Any] | None, str]:
        """Lê automaticamente a assinatura feita dentro da folha de cadastro.

        O recorte automático só é aceito quando o motor localiza o quadro padrão
        da folha gerada pelo Central CT-e. PDFs genéricos continuam disponíveis
        no fluxo manual, evitando importar cabeçalhos, textos ou a página inteira.
        """
        try:
            from engine.central_cte_modular.signing.image_processing import process_signature_image
        except Exception as exc:
            return None, f"motor de leitura automática indisponível ({exc})"

        with tempfile.TemporaryDirectory(prefix="central_cte_signature_auto_") as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / safe_filename(original_name, "folha_assinada.pdf")
            if source.suffix.lower() != ".pdf":
                source = source.with_suffix(".pdf")
            target = temporary / "assinatura_automatica.png"
            source.write_bytes(payload)
            try:
                metadata = process_signature_image(source, target, threshold=242)
            except Exception as exc:
                detail = str(exc).strip() or type(exc).__name__
                return None, detail

            detection = str(metadata.get("detection") or "")
            if "quadro" not in detection.lower() or "não localizado" in detection.lower():
                return None, "o quadro padrão da folha de cadastro não foi reconhecido"
            if not target.is_file() or target.stat().st_size < 32:
                return None, "a leitura automática não produziu uma imagem válida"
            data = target.read_bytes()
            width, height = png_dimensions(data)
            digest = hashlib.sha256(data).hexdigest()
            return {
                "id": digest[:20],
                "page": 1,
                "name": "assinatura_detectada_automaticamente.png",
                "mime": "image/png",
                "width": width,
                "height": height,
                "size_bytes": len(data),
                "sha256": digest,
                "source": "registration_sheet_auto",
                "detection": detection,
                "backend": str(metadata.get("backend") or "Pillow"),
                "threshold": int(metadata.get("threshold") or 242),
                "processed_data_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
            }, ""

    def _rasterize_pdf_pages(self, payload: bytes, page_count: int, maximum_pages: int = 10) -> tuple[list[dict[str, Any]], str, list[str]]:
        """Rasteriza páginas para permitir recorte de PDFs vetoriais ou escaneados.

        A ordem de preferência é PyMuPDF, pdftoppm e, no Windows, a API
        nativa Windows.Data.Pdf por PowerShell. Nenhum conteúdo é enviado para
        serviços externos.
        """
        warnings: list[str] = []
        rendered: list[dict[str, Any]] = []
        page_limit = max(1, min(int(page_count or 1), int(maximum_pages or 10), 10))
        with tempfile.TemporaryDirectory(prefix="central_cte_pdf_signature_") as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "assinatura.pdf"
            output = temporary / "pages"
            output.mkdir(parents=True, exist_ok=True)
            source.write_bytes(payload)
            backend = ""

            try:
                import fitz  # type: ignore

                document = fitz.open(stream=payload, filetype="pdf")
                matrix = fitz.Matrix(2.0, 2.0)
                for index in range(min(page_limit, document.page_count)):
                    page = document.load_page(index)
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    target = output / f"pagina_{index + 1:02d}.png"
                    pixmap.save(str(target))
                document.close()
                backend = "PyMuPDF"
            except Exception as exc:
                warnings.append(f"PyMuPDF indisponível: {exc}")

            if not list(output.glob("*.png")):
                pdftoppm = shutil.which("pdftoppm")
                if pdftoppm:
                    try:
                        completed = subprocess.run(
                            [pdftoppm, "-png", "-r", "150", "-f", "1", "-l", str(page_limit), str(source), str(output / "pagina")],
                            capture_output=True,
                            text=True,
                            timeout=120,
                            errors="replace",
                        )
                        if completed.returncode != 0:
                            raise RuntimeError((completed.stderr or completed.stdout or "pdftoppm falhou").strip())
                        backend = "Poppler/pdftoppm"
                    except Exception as exc:
                        warnings.append(f"Poppler indisponível: {exc}")

            if not list(output.glob("*.png")) and os.name == "nt":
                script = self.project_root / "web_local" / "tools" / "render_pdf_pages_windows.ps1"
                powershell = shutil.which("powershell.exe") or shutil.which("powershell")
                if script.is_file() and powershell:
                    try:
                        completed = subprocess.run(
                            [
                                powershell,
                                "-NoLogo",
                                "-NoProfile",
                                "-ExecutionPolicy",
                                "Bypass",
                                "-File",
                                str(script),
                                "-PdfPath",
                                str(source),
                                "-OutputDirectory",
                                str(output),
                                "-MaximumPages",
                                str(page_limit),
                                "-DestinationWidth",
                                "1800",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=180,
                            errors="replace",
                        )
                        if completed.returncode != 0:
                            raise RuntimeError((completed.stderr or completed.stdout or "Windows.Data.Pdf falhou").strip())
                        backend = "Windows.Data.Pdf"
                    except Exception as exc:
                        warnings.append(f"Renderizador nativo do Windows indisponível: {exc}")

            for index, image_path in enumerate(sorted(output.glob("*.png")), start=1):
                try:
                    data = image_path.read_bytes()
                    if not data or len(data) > MAX_IMAGE_BYTES:
                        continue
                    width, height = png_dimensions(data)
                    rendered.append({
                        "id": hashlib.sha256(data).hexdigest()[:20],
                        "page": index,
                        "name": f"pagina_{index:02d}_completa.png",
                        "mime": "image/png",
                        "width": width,
                        "height": height,
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "source": "rendered_page",
                        "data_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
                    })
                except Exception as exc:
                    warnings.append(f"Página {index}: falha ao preparar imagem ({exc}).")
            return rendered, backend, warnings

    def extract_pdf_images(self, payload: bytes, original_name: str = "assinatura.pdf") -> dict[str, Any]:
        """Extrai imagens incorporadas de um PDF para tratamento no navegador.

        O método não executa JavaScript do PDF e não modifica o documento. Ele
        atende principalmente PDFs de scanner e folhas assinadas digitalizadas.
        PDFs puramente vetoriais, sem imagem incorporada, são recusados com uma
        orientação clara para exportação em PNG/JPG.
        """
        if PdfReader is None:
            raise RuntimeError("O leitor PDF não está disponível neste ambiente.")
        if not payload or len(payload) > MAX_SIGNATURE_PDF_BYTES:
            raise ValueError(f"O PDF deve ter até {MAX_SIGNATURE_PDF_BYTES // (1024 * 1024)} MB.")
        if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-8192:]:
            raise ValueError("O arquivo não possui uma estrutura PDF válida ou está incompleto.")
        try:
            reader = PdfReader(BytesIO(payload), strict=False)
        except Exception as exc:
            raise ValueError(f"Não foi possível ler o PDF: {exc}") from exc
        if getattr(reader, "is_encrypted", False):
            try:
                unlocked = bool(reader.decrypt(""))
            except Exception:
                unlocked = False
            if not unlocked:
                raise ValueError("O PDF está protegido por senha. Remova a proteção antes de importar.")
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("O PDF não possui páginas.")

        automatic_signature, automatic_detail = self._automatic_registration_signature(payload, original_name)
        if automatic_signature is not None:
            return {
                "original_name": safe_filename(original_name, "assinatura.pdf"),
                "original_mime": "application/pdf",
                "pages": page_count,
                "pages_scanned": 1,
                "candidates": [],
                "warnings": [],
                "pdf_size_bytes": len(payload),
                "pdf_sha256": hashlib.sha256(payload).hexdigest(),
                "raster_backend": automatic_signature.get("backend") or "",
                "full_page_candidates": 0,
                "automatic_signature": automatic_signature,
                "automatic_read": True,
            }

        candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        if automatic_detail and "Nenhum traço de assinatura" not in automatic_detail:
            warnings.append(f"Leitura automática: {automatic_detail}.")
        seen: set[str] = set()
        response_bytes = 0
        for page_number, page in enumerate(reader.pages[:10], start=1):
            try:
                images = list(page.images)
            except Exception as exc:
                warnings.append(f"Página {page_number}: imagens não puderam ser extraídas ({exc}).")
                continue
            for position, image_file in enumerate(images, start=1):
                try:
                    data = bytes(image_file.data)
                except Exception:
                    continue
                if not data or len(data) > MAX_IMAGE_BYTES:
                    continue
                digest = hashlib.sha256(data).hexdigest()
                if digest in seen:
                    continue
                mime = _image_mime(data, getattr(image_file, "name", ""))
                if not mime:
                    continue
                width = height = 0
                try:
                    image_object = getattr(image_file, "image", None)
                    if image_object is not None:
                        width, height = (int(value) for value in image_object.size)
                except Exception:
                    width = height = 0
                if width <= 0 or height <= 0:
                    width, height = _basic_image_dimensions(mime, data)
                encoded_size = ((len(data) + 2) // 3) * 4
                if response_bytes + encoded_size > MAX_PDF_IMAGE_RESPONSE_BYTES:
                    warnings.append("Outras imagens foram omitidas para respeitar o limite de resposta.")
                    break
                response_bytes += encoded_size
                seen.add(digest)
                name = safe_filename(getattr(image_file, "name", "") or f"pagina_{page_number}_imagem_{position}")
                area = max(width * height, len(data))
                candidates.append({
                    "id": digest[:20],
                    "page": page_number,
                    "name": name,
                    "mime": mime,
                    "width": width,
                    "height": height,
                    "size_bytes": len(data),
                    "sha256": digest,
                    "score": area,
                    "data_url": f"data:{mime};base64," + base64.b64encode(data).decode("ascii"),
                })
            if response_bytes >= MAX_PDF_IMAGE_RESPONSE_BYTES:
                break

        candidates.sort(key=lambda item: (int(item.get("score") or 0), int(item.get("size_bytes") or 0)), reverse=True)
        candidates = candidates[:8]
        raster_backend = ""
        if not candidates:
            rasterized, raster_backend, raster_warnings = self._rasterize_pdf_pages(payload, page_count, maximum_pages=10)
            warnings.extend(raster_warnings)
            candidates = rasterized[:8]
        if not candidates:
            detail = warnings[-1] if warnings else "Nenhum renderizador de páginas está disponível."
            raise ValueError(
                "O PDF não contém imagem incorporada e não pôde ser rasterizado automaticamente. "
                "No Windows 10/11, confirme que o PowerShell e Windows.Data.Pdf estão disponíveis. "
                f"Detalhe: {detail}"
            )
        for item in candidates:
            item.pop("score", None)
        return {
            "original_name": safe_filename(original_name, "assinatura.pdf"),
            "original_mime": "application/pdf",
            "pages": page_count,
            "pages_scanned": min(page_count, 10),
            "candidates": candidates,
            "warnings": warnings[:8],
            "pdf_size_bytes": len(payload),
            "pdf_sha256": hashlib.sha256(payload).hexdigest(),
            "raster_backend": raster_backend,
            "full_page_candidates": sum(1 for item in candidates if item.get("source") == "rendered_page"),
            "automatic_signature": None,
            "automatic_read": False,
        }

    def import_browser_processed(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        profile_id = str(payload.get("profile_id") or "").strip()
        store = self._profile_store()
        profile = store.get(profile_id)
        if profile is None:
            raise ValueError("Perfil de assinatura não encontrado.")
        original_mime, original_bytes = decode_data_url(payload.get("original_data_url"), MAX_SIGNATURE_PDF_BYTES)
        if original_mime != "application/pdf" and len(original_bytes) > MAX_IMAGE_BYTES:
            raise ValueError(f"A imagem original ultrapassa o limite de {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
        processed_mime, processed_bytes = decode_data_url(payload.get("processed_data_url"))
        if processed_mime != "image/png":
            raise ValueError("A imagem tratada deve ser enviada em PNG.")
        width, height = png_dimensions(processed_bytes)
        original_name = safe_filename(payload.get("original_name"), "assinatura")
        suffix = original_extension(original_mime, original_name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_target = store.originals / f"{profile.id}_{stamp}{suffix}"
        processed_target = store.processed / f"{profile.id}_assinatura.png"
        original_target.parent.mkdir(parents=True, exist_ok=True)
        processed_target.parent.mkdir(parents=True, exist_ok=True)
        original_target.write_bytes(original_bytes)
        temporary = processed_target.with_suffix(".png.tmp")
        temporary.write_bytes(processed_bytes)
        temporary.replace(processed_target)
        profile.original_file = str(original_target)
        profile.processed_file = str(processed_target)
        profile.original_sha256 = hashlib.sha256(original_bytes).hexdigest()
        profile.threshold = int(self._clamp(payload.get("threshold"), 205, 252, profile.threshold or 242))
        store.upsert(profile)
        return {
            "profile": self._serialize_profile(profile),
            "processing": {
                "backend": "Canvas do navegador",
                "width": width,
                "height": height,
                "threshold": profile.threshold,
                "original_size_bytes": len(original_bytes),
                "processed_size_bytes": len(processed_bytes),
                "processed_sha256": hashlib.sha256(processed_bytes).hexdigest(),
            },
        }

    def registration_sheet(self, profile_id: str) -> dict[str, Any]:
        profile = self._profile_store().get(str(profile_id or "").strip())
        if profile is None:
            raise ValueError("Perfil de assinatura não encontrado.")
        plugin = self._plugin()
        html = plugin.registration_sheet_html(profile)
        store = self._profile_store()
        target = store.sheets / f"{profile.id}_folha_cadastro.pdf"
        backend = self.dacte_service._html_to_pdf(html, target)
        contract = self.dacte_service._pdf_contract(target, minimum_pages=1)
        return {"path": str(target), "name": target.name, "renderer": backend, **contract}

    def _profile_ready(self, profile_id: str) -> Any:
        profile = self._profile_store().get(str(profile_id or "").strip())
        if profile is None:
            raise ValueError("Perfil de assinatura não encontrado.")
        processed = Path(str(profile.processed_file or ""))
        if not profile.active:
            raise ValueError("O perfil de assinatura está desativado.")
        if not profile.ready or not processed.is_file():
            raise ValueError("Importe e trate a assinatura antes de gerar o PDF assinado.")
        if self.data_root not in processed.resolve().parents:
            raise ValueError("A imagem de assinatura está fora da área local autorizada.")
        return profile

    @staticmethod
    def _date_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return datetime.now().strftime("%d/%m/%Y")
        if len(text) > 24:
            raise ValueError("A data do carimbo é longa demais.")
        return text

    def _signed_html(self, infos: list[dict[str, Any]], profile: Any, date_text: str) -> str:
        plugin = self._plugin()
        engine = self.xml_service._load_engine()
        if len(infos) == 1:
            return plugin.render_signed_html(engine, infos[0], profile, date_text, profile.position, profile.stamp_size)
        return plugin.render_signed_batch_html(engine, infos, profile, date_text, profile.position, profile.stamp_size)

    def preview(self, selected_path: str | Path, available_paths: Iterable[Path], profile_id: str, date_text: Any = "", *, include_compact: bool = True) -> dict[str, Any]:
        started = time.monotonic()
        with self._lock:
            paths = self.dacte_service._allowed_selection([selected_path], available_paths)
            infos = self.dacte_service._official_infos(paths, include_compact=include_compact)
            profile = self._profile_ready(profile_id)
            date_value = self._date_text(date_text)
            profile_state = json.dumps(asdict(profile), sort_keys=True, ensure_ascii=False, default=str)
            complementary_state = json.dumps(
                [str(info.get("informacao_complementar_impressao") or "") for info in infos],
                sort_keys=True, ensure_ascii=False, default=str,
            )
            identity = hashlib.sha256(
                (str(paths[0]) + "|" + file_sha256(paths[0]) + "|" + profile_state + "|" + date_value + "|" + complementary_state + "|compact=" + str(bool(include_compact))).encode("utf-8")
            ).hexdigest()[:24]
            target = self.dacte_service.preview_root / f"preview_assinado_{identity}.pdf"
            cached = target.is_file() and target.stat().st_size > 800
            backend = "cache local"
            if not cached:
                html = self._signed_html(infos, profile, date_value)
                backend = self.dacte_service._html_to_pdf(html, target)
            contract = self.dacte_service._pdf_contract(target, minimum_pages=1)
            profile.last_used_at = now_iso()
            self._profile_store().upsert(profile)
            result = {
                "status": "concluido",
                "operation": "signed-preview",
                "generated_at": now_iso(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "cached": cached,
                "path": str(target),
                "name": target.name,
                "cte": str(infos[0].get("numero") or ""),
                "profile_id": profile.id,
                "profile_name": profile.name,
                "date_text": date_value,
                "renderer": backend,
                "visual_signature_only": True,
                "include_compact": bool(include_compact),
                **contract,
            }
            self._write_last_run(result)
            return result

    def generate_batch(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        profile_id: str,
        date_text: Any = "",
        progress: Callable[[float, int, int, str, str], None] | None = None,
        include_compact: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        paths = self.dacte_service._allowed_selection(selected_paths, available_paths)
        total = len(paths)
        if progress:
            progress(5.0, 0, total, "", f"Validando {total} CT-e(s) selecionado(s).")
        infos = self.dacte_service._official_infos(paths, include_compact=include_compact)
        if progress:
            progress(22.0, total, total, "", f"Dados oficiais de {total} CT-e(s) preparados.")
        profile = self._profile_ready(profile_id)
        date_value = self._date_text(date_text)
        target = self.dacte_service._timestamped_target("lote_dactes_ASSINADOS_RC26_6_WEB", ".pdf")
        if progress:
            progress(35.0, total, total, "", "Montando o lote assinado em HTML oficial.")
        html = self._signed_html(infos, profile, date_value)
        if progress:
            progress(48.0, total, total, "", "Convertendo o lote assinado para PDF. Esta etapa pode levar alguns minutos.")
        backend = self.dacte_service._html_to_pdf(html, target)
        if progress:
            progress(90.0, total, total, target.name, "Conferindo páginas, tamanho e integridade do PDF.")
        contract = self.dacte_service._pdf_contract(target, minimum_pages=len(infos))
        profile.last_used_at = now_iso()
        self._profile_store().upsert(profile)
        result = {
            "status": "concluido",
            "operation": "signed-batch",
            "generated_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "path": str(target),
            "name": target.name,
            "documents": len(infos),
            "ctes": [str(info.get("numero") or "") for info in infos],
            "profile_id": profile.id,
            "profile_name": profile.name,
            "date_text": date_value,
            "renderer": backend,
            "visual_signature_only": True,
            "include_compact": bool(include_compact),
            **contract,
        }
        self._write_last_run(result)
        if progress:
            progress(100.0, total, total, target.name, "Lote assinado concluído e pronto para download.")
        return result

    def generate_individuals(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        profile_id: str,
        date_text: Any = "",
        progress: Callable[[float, int, int, str, str], None] | None = None,
        include_compact: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        paths = self.dacte_service._allowed_selection(selected_paths, available_paths)
        total = len(paths)
        if progress:
            progress(4.0, 0, total, "", f"Validando {total} CT-e(s) selecionado(s).")
        infos = self.dacte_service._official_infos(paths, include_compact=include_compact)
        if progress:
            progress(10.0, 0, total, "", "Dados oficiais carregados. Iniciando os PDFs individuais.")
        profile = self._profile_ready(profile_id)
        date_value = self._date_text(date_text)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        directory = self.dacte_service.individual_root / f"dactes_assinados_{stamp}"
        directory.mkdir(parents=True, exist_ok=False)
        files: list[dict[str, Any]] = []
        used: set[str] = set()
        backends: set[str] = set()
        for position, info in enumerate(infos, start=1):
            number = str(info.get("numero") or "SEM NUMERO")
            partner = str(info.get("emitente") or info.get("parceiro") or "PARCEIRO")
            if progress:
                percent = 10.0 + ((position - 1) / max(1, total)) * 78.0
                progress(percent, position - 1, total, f"CT-e {number}", f"Gerando PDF assinado {position} de {total}.")
            base = safe_filename(f"CT-e {number} {partner}", "DACTE ASSINADO")[:110]
            candidate = base
            counter = 2
            while candidate.casefold() in used:
                candidate = f"{base} {counter}"
                counter += 1
            used.add(candidate.casefold())
            target = directory / f"{candidate}.pdf"
            html = self._signed_html([info], profile, date_value)
            backend = self.dacte_service._html_to_pdf(html, target)
            backends.add(backend)
            contract = self.dacte_service._pdf_contract(target, minimum_pages=1)
            files.append({"path": str(target), "name": target.name, "cte": str(info.get("numero") or ""), **contract})
            if progress:
                percent = 10.0 + (position / max(1, total)) * 78.0
                progress(percent, position, total, f"CT-e {number}", f"PDF assinado {position} de {total} concluído.")
        zip_target = self.dacte_service._timestamped_target("dactes_ASSINADOS_individuais_RC26_6_WEB", ".zip")
        if progress:
            progress(91.0, total, total, zip_target.name, "Compactando os PDFs assinados em arquivo ZIP.")
        with zipfile.ZipFile(zip_target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in files:
                archive.write(item["path"], item["name"])
        with zipfile.ZipFile(zip_target, "r") as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"O pacote de DACTEs assinados contém arquivo corrompido: {bad}")
        if progress:
            progress(97.0, total, total, zip_target.name, "Validando o pacote ZIP e calculando o SHA-256.")
        profile.last_used_at = now_iso()
        self._profile_store().upsert(profile)
        result = {
            "status": "concluido",
            "operation": "signed-individuals",
            "generated_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "path": str(zip_target),
            "name": zip_target.name,
            "documents": len(files),
            "files": files,
            "profile_id": profile.id,
            "profile_name": profile.name,
            "date_text": date_value,
            "renderer": ", ".join(sorted(backends)),
            "size_bytes": zip_target.stat().st_size,
            "sha256": file_sha256(zip_target),
            "visual_signature_only": True,
            "include_compact": bool(include_compact),
        }
        self._write_last_run(result)
        if progress:
            progress(100.0, total, total, zip_target.name, "Arquivos assinados concluídos e prontos para download.")
        return result

    def generate(
        self,
        selected_paths: Iterable[str | Path],
        available_paths: Iterable[Path],
        profile_id: str,
        date_text: Any = "",
        mode: str = "batch",
        progress: Callable[[float, int, int, str, str], None] | None = None,
        include_compact: bool = True,
    ) -> dict[str, Any]:
        normalized = str(mode or "batch").strip().lower()
        with self._lock:
            if normalized == "batch":
                return self.generate_batch(selected_paths, available_paths, profile_id, date_text, progress=progress, include_compact=include_compact)
            if normalized in {"individuals", "individuais", "zip"}:
                return self.generate_individuals(selected_paths, available_paths, profile_id, date_text, progress=progress, include_compact=include_compact)
            raise ValueError("Modo de assinatura inválido. Use batch ou individuals.")


__all__ = ["OfficialSignatureService", "SERVICE_VERSION", "decode_data_url", "png_dimensions"]
