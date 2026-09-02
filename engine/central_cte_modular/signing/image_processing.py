from __future__ import annotations

import base64
import importlib
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None
    ImageEnhance = None
    ImageFont = None
    ImageOps = None

from .common import _data_uri, _sha256_file

def _qt_core_gui():
    """Carrega o backend gráfico já empacotado com o Central CT-e."""
    core = importlib.import_module("PySide6.QtCore")
    gui = importlib.import_module("PySide6.QtGui")
    return core, gui

def _qt_enum(owner, container_name: str, value_name: str):
    container = getattr(owner, container_name, None)
    if container is not None and hasattr(container, value_name):
        return getattr(container, value_name)
    if hasattr(owner, value_name):
        return getattr(owner, value_name)
    raise AttributeError(f"Enum Qt não encontrado: {container_name}.{value_name}")

def image_backend_status() -> tuple[str, str]:
    """Retorna o backend disponível sem exigir instalação manual de pacotes."""
    if Image is not None:
        return "Pillow", "Tratamento avançado disponível"
    try:
        _qt_core_gui()
        return "Qt", "Modo compatível interno disponível (Pillow não é necessária)"
    except Exception:
        return "Indisponível", "Os componentes gráficos do programa não foram localizados"

def _qimage_memory(image):
    pointer = image.bits()
    try:
        pointer.setsize(image.sizeInBytes())
    except Exception:
        pass
    return memoryview(pointer).cast("B")

def _qt_image_png_bytes(image) -> bytes:
    core, _ = _qt_core_gui()
    array = core.QByteArray()
    buffer = core.QBuffer(array)
    mode = getattr(getattr(core.QIODevice, "OpenModeFlag", core.QIODevice), "WriteOnly")
    if not buffer.open(mode):
        raise RuntimeError("Não foi possível criar a imagem temporária da assinatura.")
    if not image.save(buffer, "PNG"):
        raise RuntimeError("O backend Qt não conseguiu salvar a assinatura em PNG.")
    buffer.close()
    return bytes(array)

def _qt_load_qimage(path: Path, max_side: int = 2600):
    """Lê imagem ou a primeira página de PDF usando os plugins do Qt do EXE."""
    core, gui = _qt_core_gui()
    reader = gui.QImageReader(str(path))
    try:
        reader.setAutoTransform(True)
    except Exception:
        pass
    if not reader.canRead():
        message = reader.errorString() or "formato não reconhecido pelo Qt"
        raise RuntimeError(f"Não foi possível ler o arquivo pelo modo compatível: {message}")
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > 0:
        scale = min(1.0, max_side / max(size.width(), size.height()))
        # PDF costuma informar o tamanho em pontos. Amplia a primeira página para
        # manter os traços da caneta nítidos durante o recorte.
        if path.suffix.lower() == ".pdf" and max(size.width(), size.height()) < 1800:
            scale = min(max_side / max(size.width(), size.height()), 2.8)
        if abs(scale - 1.0) > 0.01:
            reader.setScaledSize(core.QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale))))
    image = reader.read()
    if image.isNull():
        raise RuntimeError(reader.errorString() or "O Qt retornou uma imagem vazia.")
    rgba_format = _qt_enum(gui.QImage, "Format", "Format_RGBA8888")
    return image.convertToFormat(rgba_format)

def _signature_data_uri(path: Path, compact: bool = False) -> str:
    """Normaliza a proporção da assinatura para evitar cortes entre renderizadores."""
    target = (680, 100) if compact else (680, 220)
    if Image is not None:
        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail(target, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", target, (255, 255, 255, 0))
            x = (target[0] - image.width) // 2
            y = (target[1] - image.height) // 2
            canvas.alpha_composite(image, (x, y))
            stream = io.BytesIO()
            canvas.save(stream, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
    try:
        core, gui = _qt_core_gui()
        source = _qt_load_qimage(path, max_side=max(target))
        aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
        smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
        scaled = source.scaled(target[0], target[1], aspect, smooth)
        canvas_format = _qt_enum(gui.QImage, "Format", "Format_ARGB32_Premultiplied")
        canvas = gui.QImage(target[0], target[1], canvas_format)
        canvas.fill(getattr(getattr(core.Qt, "GlobalColor", core.Qt), "transparent"))
        painter = gui.QPainter(canvas)
        painter.setRenderHint(gui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage((target[0] - scaled.width()) // 2, (target[1] - scaled.height()) // 2, scaled)
        painter.end()
        return "data:image/png;base64," + base64.b64encode(_qt_image_png_bytes(canvas)).decode("ascii")
    except Exception:
        return _data_uri(path)

def _signature_stamp_data_uri(path: Path, title: str, date_text: str, person_name: str = "") -> str:
    """Monta o carimbo oficial 85 x 32 mm com assinatura grande sobre a linha.

    O bloco é produzido como uma imagem única para impedir que Edge/Chrome,
    Qt ou a impressora alterem separadamente título, data, linha e assinatura.
    """
    safe_title = str(title or "REDESPACHO").upper()[:34]
    safe_date = str(date_text or "")[:20]
    width, height = 1000, 376

    if Image is None or ImageDraw is None:
        try:
            core, gui = _qt_core_gui()
            canvas_format = _qt_enum(gui.QImage, "Format", "Format_ARGB32_Premultiplied")
            canvas = gui.QImage(width, height, canvas_format)
            canvas.fill(getattr(getattr(core.Qt, "GlobalColor", core.Qt), "transparent"))
            painter = gui.QPainter(canvas)
            painter.setRenderHint(gui.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(gui.QPainter.RenderHint.SmoothPixmapTransform, True)
            black = gui.QColor(18, 18, 18)

            border_pen = gui.QPen(black)
            border_pen.setWidth(5)
            painter.setPen(border_pen)
            painter.drawRect(7, 7, width - 14, height - 14)

            align = (
                getattr(getattr(core.Qt, "AlignmentFlag", core.Qt), "AlignHCenter")
                | getattr(getattr(core.Qt, "AlignmentFlag", core.Qt), "AlignVCenter")
            )
            title_font = gui.QFont("Arial", 66)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.drawText(core.QRect(30, 24, width - 60, 82), align, safe_title)

            if safe_date:
                date_font = gui.QFont("Arial", 38)
                date_font.setBold(True)
                painter.setFont(date_font)
                painter.drawText(core.QRect(30, 96, width - 60, 58), align, safe_date)

            label_font = gui.QFont("Arial", 42)
            label_font.setBold(True)
            painter.setFont(label_font)
            painter.drawText(core.QRect(34, 267, 150, 70), align, "Ass:")

            line_pen = gui.QPen(black)
            line_pen.setWidth(4)
            painter.setPen(line_pen)
            painter.drawLine(160, 313, 955, 313)

            signature = _qt_load_qimage(path, max_side=1800)
            aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
            smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
            signature = signature.scaled(790, 220, aspect, smooth)
            x = 165 + max(0, (790 - signature.width()) // 2)
            # A assinatura toca/sobrepõe a linha, como num carimbo real.
            y = 128 + max(0, (204 - signature.height()) // 2)
            painter.drawImage(x, y, signature)
            painter.end()
            return "data:image/png;base64," + base64.b64encode(_qt_image_png_bytes(canvas)).decode("ascii")
        except Exception:
            return _signature_data_uri(path, compact=False)

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)

    def load_font(size: int, bold: bool = False):
        candidates = []
        if os.name == "nt":
            windir = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts"
            candidates.extend([
                windir / ("arialbd.ttf" if bold else "arial.ttf"),
                windir / "calibrib.ttf",
                windir / "calibri.ttf",
            ])
        candidates.extend([
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ])
        if ImageFont is not None:
            for candidate in candidates:
                try:
                    if candidate.exists():
                        return ImageFont.truetype(str(candidate), size=size)
                except Exception:
                    pass
            try:
                return ImageFont.load_default(size=size)
            except TypeError:
                return ImageFont.load_default()
        return None

    title_font = load_font(88, bold=True)
    date_font = load_font(48, bold=True)
    label_font = load_font(52, bold=True)

    draw.rectangle((7, 7, width - 8, height - 8), outline=(18, 18, 18, 255), width=5)
    title_bbox = draw.textbbox((0, 0), safe_title, font=title_font) if hasattr(draw, "textbbox") else (0, 0, len(safe_title) * 44, 88)
    draw.text(((width - (title_bbox[2] - title_bbox[0])) // 2, 18), safe_title, fill=(18, 18, 18, 255), font=title_font)

    if safe_date:
        date_bbox = draw.textbbox((0, 0), safe_date, font=date_font) if hasattr(draw, "textbbox") else (0, 0, len(safe_date) * 24, 48)
        draw.text(((width - (date_bbox[2] - date_bbox[0])) // 2, 100), safe_date, fill=(18, 18, 18, 255), font=date_font)

    draw.text((34, 267), "Ass:", fill=(18, 18, 18, 255), font=label_font)
    draw.line((160, 313, 955, 313), fill=(18, 18, 18, 255), width=4)

    with Image.open(path) as source:
        signature = source.convert("RGBA")
        signature.thumbnail((790, 220), Image.Resampling.LANCZOS)
        x = 165 + max(0, (790 - signature.width) // 2)
        y = 128 + max(0, (204 - signature.height) // 2)
        canvas.alpha_composite(signature, (x, y))

    stream = io.BytesIO()
    canvas.save(stream, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")

def _load_image(path: Path):
    suffix = path.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}:
        raise RuntimeError("Formato não suportado. Use PDF, JPG, JPEG ou PNG.")
    if Image is not None:
        if suffix != ".pdf":
            with Image.open(path) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
        return render_pdf_first_page(path)
    # O EXE já possui PySide6 e o plugin qpdf. Este caminho elimina a
    # necessidade de instalar Pillow na máquina do usuário.
    return _qt_load_qimage(path)

def render_pdf_first_page(path: Path):
    from .pdf_converter import _no_window_flags, find_browser
    errors: list[str] = []
    if Image is not None:
        try:
            pdfium = importlib.import_module("pypdfium2")
            document = pdfium.PdfDocument(str(path))
            page = document[0]
            bitmap = page.render(scale=2.4)
            image = bitmap.to_pil().convert("RGB")
            page.close()
            document.close()
            return image
        except Exception as exc:
            errors.append(f"PDFium: {exc}")

        try:
            fitz = importlib.import_module("fitz")
            document = fitz.open(str(path))
            page = document.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            document.close()
            return image
        except Exception as exc:
            errors.append(f"PyMuPDF: {exc}")

        try:
            pdftoppm = shutil.which("pdftoppm")
            if pdftoppm:
                with tempfile.TemporaryDirectory(prefix="cte_pdf_poppler_") as tmp:
                    prefix = Path(tmp) / "pagina"
                    command = [
                        pdftoppm, "-singlefile", "-png", "-r", "180",
                        "-f", "1", "-l", "1", str(path), str(prefix),
                    ]
                    process = subprocess.run(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=90, creationflags=_no_window_flags(),
                    )
                    output = prefix.with_suffix(".png")
                    if process.returncode == 0 and output.is_file():
                        with Image.open(output) as image:
                            return image.convert("RGB")
                    detail = (process.stderr or process.stdout or b"pdftoppm falhou").decode("utf-8", errors="replace").strip()
                    errors.append(f"Poppler/pdftoppm: {detail or 'não gerou a página'}")
            else:
                errors.append("Poppler/pdftoppm: executável não encontrado")
        except Exception as exc:
            errors.append(f"Poppler/pdftoppm: {exc}")

    try:
        qimage = _qt_load_qimage(path)
        if Image is None:
            return qimage
        return Image.open(io.BytesIO(_qt_image_png_bytes(qimage))).convert("RGB")
    except Exception as exc:
        errors.append(f"Qt/qpdf: {exc}")

    if Image is not None:
        try:
            browser = find_browser()
            if browser:
                with tempfile.TemporaryDirectory(prefix="cte_pdf_page_") as tmp:
                    output = Path(tmp) / "pagina.png"
                    user_data = Path(tmp) / "perfil"
                    command = [
                        str(browser), "--headless=new", "--disable-gpu", "--disable-extensions",
                        "--hide-scrollbars", f"--user-data-dir={user_data}",
                        "--window-size=1654,2339", f"--screenshot={output}", path.resolve().as_uri(),
                    ]
                    if os.name != "nt":
                        command.insert(1, "--no-sandbox")
                    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, creationflags=_no_window_flags())
                    if process.returncode == 0 and output.exists():
                        with Image.open(output) as image:
                            return image.convert("RGB")
                    errors.append("Edge/Chrome não gerou a imagem da primeira página")
        except Exception as exc:
            errors.append(f"Edge/Chrome: {exc}")

    raise RuntimeError("Não foi possível ler a primeira página do PDF. " + " | ".join(errors[-3:]))

def _clusters(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    groups: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value <= previous + 3:
            previous = value
            continue
        groups.append((start, previous))
        start = previous = value
    groups.append((start, previous))
    return groups

def _dark_mask_counts(image, threshold: int = 105):
    if Image is not None and hasattr(image, "convert"):
        gray = ImageOps.grayscale(image)
        width, height = gray.size
        pixels = gray.load()
        row_counts = [0] * height
        col_counts = [0] * width
        for y in range(height):
            count = 0
            for x in range(width):
                if pixels[x, y] < threshold:
                    count += 1
                    col_counts[x] += 1
            row_counts[y] = count
        return row_counts, col_counts
    _, gui = _qt_core_gui()
    gray_format = _qt_enum(gui.QImage, "Format", "Format_Grayscale8")
    gray = image.convertToFormat(gray_format)
    width, height = gray.width(), gray.height()
    data = _qimage_memory(gray)
    stride = gray.bytesPerLine()
    row_counts = [0] * height
    col_counts = [0] * width
    for y in range(height):
        base = y * stride
        count = 0
        for x in range(width):
            if data[base + x] < threshold:
                count += 1
                col_counts[x] += 1
        row_counts[y] = count
    return row_counts, col_counts

def _image_dimensions(image) -> tuple[int, int]:
    """Retorna largura e altura para Pillow ou QImage sem depender do backend."""
    if Image is not None and hasattr(image, "size") and not hasattr(image, "isNull"):
        return int(image.size[0]), int(image.size[1])
    return int(image.width()), int(image.height())

def _template_registration_box(image) -> Optional[tuple[int, int, int, int]]:
    """Fallback geométrico para a folha A4 gerada pelo próprio programa.

    A folha possui posição fixa do quadro. Este caminho é usado quando uma
    digitalização suaviza/clareia as linhas a ponto de o detector não enxergá-las.
    O recorte corresponde à área interna do quadro, sem cabeçalho, código ou rodapé.
    """
    width, height = _image_dimensions(image)
    if width < 500 or height < 700:
        return None
    ratio = width / max(1, height)
    # A4 retrato, incluindo pequenas variações de scanner e margens.
    if not (0.62 <= ratio <= 0.80):
        return None
    left = int(round(width * 0.165))
    right = int(round(width * 0.835))
    top = int(round(height * 0.335))
    bottom = int(round(height * 0.515))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom

def _detect_registration_box_details(image) -> tuple[Optional[tuple[int, int, int, int]], str]:
    """Localiza o quadro por linhas e retorna também o método utilizado."""
    use_pillow = Image is not None and hasattr(image, "copy") and not hasattr(image, "isNull")
    max_side = 1800
    scale = 1.0
    if use_pillow:
        work = image.copy().convert("RGB")
        if max(work.size) > max_side:
            scale = max_side / max(work.size)
            work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        width, height = work.size
    else:
        core, _ = _qt_core_gui()
        work = image.copy()
        width, height = work.width(), work.height()
        if max(width, height) > max_side:
            scale = max_side / max(width, height)
            aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
            smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
            work = work.scaled(max_side, max_side, aspect, smooth)
            width, height = work.width(), work.height()

    # Digitalizações e o plugin PDF do Qt podem suavizar linhas pretas. Testa
    # limiares progressivos, em vez de depender apenas de preto quase puro.
    all_candidates: list[tuple[float, int, int, int, int]] = []
    for threshold in (105, 135, 165, 195, 220):
        row_counts, col_counts = _dark_mask_counts(work, threshold=threshold)
        row_min = int(width * 0.34)
        col_min = int(height * 0.055)
        strong_rows = [index for index, value in enumerate(row_counts) if value >= row_min]
        strong_cols = [index for index, value in enumerate(col_counts) if value >= col_min]
        if len(strong_rows) < 2 or len(strong_cols) < 2:
            continue
        row_groups = _clusters(strong_rows)
        col_groups = _clusters(strong_cols)
        for top_group in row_groups:
            for bottom_group in row_groups:
                top = int(sum(top_group) / 2)
                bottom = int(sum(bottom_group) / 2)
                box_h = bottom - top
                if box_h < height * 0.10 or box_h > height * 0.34:
                    continue
                for left_group in col_groups:
                    for right_group in col_groups:
                        left = int(sum(left_group) / 2)
                        right = int(sum(right_group) / 2)
                        box_w = right - left
                        if box_w < width * 0.48 or box_w > width * 0.92:
                            continue
                        ratio = box_w / max(1, box_h)
                        if ratio < 1.8 or ratio > 5.4:
                            continue
                        width_ratio = box_w / max(1, width)
                        height_ratio = box_h / max(1, height)
                        center_y = ((top + bottom) / 2) / max(1, height)
                        center_x = ((left + right) / 2) / max(1, width)
                        # Geometria esperada do quadro: ~72% da largura, ~20%
                        # da altura e centralizado horizontalmente na metade superior.
                        penalty = (
                            abs(width_ratio - 0.72) * 5200
                            + abs(height_ratio - 0.20) * 6800
                            + abs(center_y - 0.425) * 4200
                            + abs(center_x - 0.50) * 1800
                            + threshold * 0.08
                        )
                        # O tamanho absoluto não pode dominar a escolha, pois
                        # blocos de instrução acima do quadro podem formar um
                        # retângulo maior. Prioriza a geometria conhecida da folha.
                        score = -penalty
                        all_candidates.append((score, left, top, right, bottom))
        if all_candidates and threshold <= 165:
            # Em geral o primeiro conjunto confiável já representa as linhas reais.
            break

    if all_candidates:
        _, left, top, right, bottom = max(all_candidates)
        pad_x = max(8, int((right - left) * 0.055))
        pad_y = max(8, int((bottom - top) * 0.13))
        left, right = left + pad_x, right - pad_x
        top, bottom = top + pad_y, bottom - pad_y
        if right > left and bottom > top:
            inverse = 1.0 / scale
            box = tuple(int(round(value * inverse)) for value in (left, top, right, bottom))
            return box, "quadro da folha localizado automaticamente"

    template = _template_registration_box(image)
    if template:
        return template, "quadro localizado pela posição padrão da folha de cadastro"
    return None, ""

def detect_registration_box(image) -> Optional[tuple[int, int, int, int]]:
    """API pública: retorna somente o retângulo localizado."""
    return _detect_registration_box_details(image)[0]

def _crop_to_nonwhite(image, threshold: int = 248, padding: int = 18):
    if Image is not None and not hasattr(image, "isNull"):
        gray = ImageOps.grayscale(image)
        mask = gray.point(lambda p: 255 if p < threshold else 0)
        bbox = mask.getbbox()
        if not bbox:
            return image.copy()
        left, top, right, bottom = bbox
        return image.crop((max(0, left - padding), max(0, top - padding), min(image.width, right + padding), min(image.height, bottom + padding)))
    core, gui = _qt_core_gui()
    gray_format = _qt_enum(gui.QImage, "Format", "Format_Grayscale8")
    gray = image.convertToFormat(gray_format)
    data = _qimage_memory(gray)
    stride = gray.bytesPerLine()
    left, top, right, bottom = gray.width(), gray.height(), -1, -1
    for y in range(gray.height()):
        base = y * stride
        for x in range(gray.width()):
            if data[base + x] < threshold:
                left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    if right < left or bottom < top:
        return image.copy()
    rect = core.QRect(max(0, left - padding), max(0, top - padding), min(image.width() - max(0, left - padding), right - left + 1 + padding * 2), min(image.height() - max(0, top - padding), bottom - top + 1 + padding * 2))
    return image.copy(rect)

def _clear_edge_frame_pillow(rgba) -> None:
    """Remove restos das linhas-guia do formulário sem tocar no miolo."""
    pixels = rgba.load()
    width, height = rgba.size
    edge_x = max(4, int(width * 0.14))
    edge_y = max(4, int(height * 0.16))
    strong_cols = []
    for x in list(range(edge_x)) + list(range(max(edge_x, width - edge_x), width)):
        if sum(1 for y in range(height) if pixels[x, y][3] > 30) >= height * 0.42:
            strong_cols.append(x)
    strong_rows = []
    for y in list(range(edge_y)) + list(range(max(edge_y, height - edge_y), height)):
        if sum(1 for x in range(width) if pixels[x, y][3] > 30) >= width * 0.42:
            strong_rows.append(y)
    for x in strong_cols:
        for xx in range(max(0, x - 3), min(width, x + 4)):
            for y in range(height):
                red, green, blue, _ = pixels[xx, y]
                pixels[xx, y] = (red, green, blue, 0)
    for y in strong_rows:
        for yy in range(max(0, y - 3), min(height, y + 4)):
            for x in range(width):
                red, green, blue, _ = pixels[x, yy]
                pixels[x, yy] = (red, green, blue, 0)
    # As marcas grossas do formulário ficam encostadas às bordas. A folha
    # orienta o usuário a não assinar nessa margem, então ela pode ser limpa
    # integralmente sem reduzir o traço útil.
    strip_x = max(3, int(width * 0.045))
    strip_y = max(3, int(height * 0.055))
    for y in range(height):
        for x in list(range(strip_x)) + list(range(max(strip_x, width - strip_x), width)):
            red, green, blue, _ = pixels[x, y]
            pixels[x, y] = (red, green, blue, 0)
    for y in list(range(strip_y)) + list(range(max(strip_y, height - strip_y), height)):
        for x in range(width):
            red, green, blue, _ = pixels[x, y]
            pixels[x, y] = (red, green, blue, 0)

def _clear_edge_frame_qt(rgba, data, stride: int) -> None:
    width, height = rgba.width(), rgba.height()
    edge_x = max(4, int(width * 0.14))
    edge_y = max(4, int(height * 0.16))
    strong_cols = []
    for x in list(range(edge_x)) + list(range(max(edge_x, width - edge_x), width)):
        count = 0
        for y in range(height):
            if data[y * stride + x * 4 + 3] > 30:
                count += 1
        if count >= height * 0.42:
            strong_cols.append(x)
    strong_rows = []
    for y in list(range(edge_y)) + list(range(max(edge_y, height - edge_y), height)):
        base = y * stride
        count = sum(1 for x in range(width) if data[base + x * 4 + 3] > 30)
        if count >= width * 0.42:
            strong_rows.append(y)
    for x in strong_cols:
        for xx in range(max(0, x - 3), min(width, x + 4)):
            for y in range(height):
                data[y * stride + xx * 4 + 3] = 0
    for y in strong_rows:
        for yy in range(max(0, y - 3), min(height, y + 4)):
            base = yy * stride
            for x in range(width):
                data[base + x * 4 + 3] = 0
    strip_x = max(3, int(width * 0.045))
    strip_y = max(3, int(height * 0.055))
    for y in range(height):
        base = y * stride
        for x in list(range(strip_x)) + list(range(max(strip_x, width - strip_x), width)):
            data[base + x * 4 + 3] = 0
    for y in list(range(strip_y)) + list(range(max(strip_y, height - strip_y), height)):
        base = y * stride
        for x in range(width):
            data[base + x * 4 + 3] = 0

def _process_signature_qt(source: Path, output: Path, threshold: int) -> dict[str, Any]:
    core, gui = _qt_core_gui()
    image = _qt_load_qimage(source)
    box, detection = _detect_registration_box_details(image)
    if box:
        left, top, right, bottom = box
        cropped = image.copy(core.QRect(left, top, max(1, right - left), max(1, bottom - top)))
        detection = f"{detection} (modo Qt)"
    else:
        cropped = _crop_to_nonwhite(image, threshold=250, padding=max(12, int(min(image.width(), image.height()) * 0.01)))
        detection = "quadro não localizado; utilizada a área com conteúdo (modo Qt)"
    if max(cropped.width(), cropped.height()) > 1800:
        aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
        smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
        cropped = cropped.scaled(1800, 1800, aspect, smooth)
    rgba_format = _qt_enum(gui.QImage, "Format", "Format_RGBA8888")
    rgba = cropped.convertToFormat(rgba_format)
    data = _qimage_memory(rgba)
    stride = rgba.bytesPerLine()
    threshold = max(205, min(252, int(threshold)))
    softness = max(6, 255 - threshold)
    left, top, right, bottom = rgba.width(), rgba.height(), -1, -1
    for y in range(rgba.height()):
        base = y * stride
        for x in range(rgba.width()):
            offset = base + x * 4
            red, green, blue = int(data[offset]), int(data[offset + 1]), int(data[offset + 2])
            # Contraste leve equivalente ao backend Pillow.
            red = max(0, min(255, int((red - 128) * 1.12 + 128)))
            green = max(0, min(255, int((green - 128) * 1.12 + 128)))
            blue = max(0, min(255, int((blue - 128) * 1.12 + 128)))
            light, minimum = max(red, green, blue), min(red, green, blue)
            if light >= threshold and minimum >= threshold - 10:
                alpha = 0
            else:
                luminance = int(0.2126 * red + 0.7152 * green + 0.0722 * blue)
                alpha = max(0, min(255, int((255 - luminance) * (255 / max(1, softness)))))
                if light - minimum > 18:
                    alpha = max(alpha, 170)
                alpha = max(alpha, 38 if luminance < 225 else 0)
            data[offset], data[offset + 1], data[offset + 2], data[offset + 3] = red, green, blue, alpha
            if alpha > 0:
                left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    _clear_edge_frame_qt(rgba, data, stride)
    left, top, right, bottom = rgba.width(), rgba.height(), -1, -1
    for y in range(rgba.height()):
        base = y * stride
        for x in range(rgba.width()):
            if data[base + x * 4 + 3] > 0:
                left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    if right < left or bottom < top:
        raise RuntimeError("Nenhum traço de assinatura foi encontrado após a remoção do fundo.")
    pad = max(8, int(min(rgba.width(), rgba.height()) * 0.025))
    crop_left, crop_top = max(0, left - pad), max(0, top - pad)
    final = rgba.copy(core.QRect(crop_left, crop_top, min(rgba.width() - crop_left, right - left + 1 + pad * 2), min(rgba.height() - crop_top, bottom - top + 1 + pad * 2)))
    output.parent.mkdir(parents=True, exist_ok=True)
    if not final.save(str(output), "PNG"):
        raise RuntimeError("O modo compatível Qt não conseguiu salvar a assinatura tratada.")
    return {
        "source": str(source), "output": str(output), "width": final.width(), "height": final.height(),
        "threshold": threshold, "detection": detection, "backend": "Qt",
        "source_sha256": _sha256_file(source), "output_sha256": _sha256_file(output),
    }

def process_signature_image(source: Path, output: Path, threshold: int = 242) -> dict[str, Any]:
    """Recorta o quadro e transforma o fundo claro em transparência."""
    if Image is None:
        return _process_signature_qt(Path(source), Path(output), threshold)
    image = _load_image(Path(source))
    box, detection = _detect_registration_box_details(image)
    if box:
        cropped = image.crop(box)
    else:
        cropped = _crop_to_nonwhite(image, threshold=250, padding=max(12, int(min(image.size) * 0.01)))
        detection = "quadro não localizado; utilizada a área com conteúdo"
    cropped = ImageOps.exif_transpose(cropped).convert("RGB")
    cropped = ImageEnhance.Contrast(cropped).enhance(1.12)
    if max(cropped.size) > 1800:
        cropped.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    rgba = cropped.convert("RGBA")
    pixels = rgba.load()
    threshold = max(205, min(252, int(threshold)))
    softness = max(6, 255 - threshold)
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, _ = pixels[x, y]
            light, minimum = max(red, green, blue), min(red, green, blue)
            if light >= threshold and minimum >= threshold - 10:
                alpha = 0
            else:
                luminance = int(0.2126 * red + 0.7152 * green + 0.0722 * blue)
                alpha = max(0, min(255, int((255 - luminance) * (255 / max(1, softness)))))
                if light - minimum > 18:
                    alpha = max(alpha, 170)
                alpha = max(alpha, 38 if luminance < 225 else 0)
            pixels[x, y] = (red, green, blue, alpha)
    _clear_edge_frame_pillow(rgba)
    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        raise RuntimeError("Nenhum traço de assinatura foi encontrado após a remoção do fundo.")
    left, top, right, bottom = bbox
    pad = max(8, int(min(rgba.size) * 0.025))
    rgba = rgba.crop((max(0, left - pad), max(0, top - pad), min(rgba.width, right + pad), min(rgba.height, bottom + pad)))
    output.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(output, "PNG", optimize=True)
    return {
        "source": str(source), "output": str(output), "width": rgba.width, "height": rgba.height,
        "threshold": threshold, "detection": detection, "backend": "Pillow",
        "source_sha256": _sha256_file(Path(source)), "output_sha256": _sha256_file(output),
    }

