"""Offline OCR for image-only PDF pages, including rotated scans."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile


def tesseract_path() -> str:
    configured = os.environ.get("TESSERACT_CMD")
    candidates = [configured, shutil.which("tesseract")]
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            candidates.extend([str(Path(base) / "Tesseract-OCR" / "tesseract.exe"),
                               str(Path(base) / "Programs" / "Tesseract-OCR" / "tesseract.exe")])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise ValueError("Для сканов установите Tesseract OCR (инструкция в README.md). "
                     "Затем перезапустите программу. Украинский языковой пакет включён в архив.")


def recognize_pages(path: Path, page_indexes: list[int], progress=None) -> dict[int, str]:
    import pypdfium2 as pdfium

    executable = tesseract_path()
    tessdata = Path(__file__).parent / "tessdata"
    if not all((tessdata / name).is_file() for name in ("ukr.traineddata", "osd.traineddata")):
        raise ValueError("Не найдены языковые пакеты OCR. Распакуйте архив целиком, включая папку tessdata.")
    result = {}
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    environment = dict(os.environ, OMP_THREAD_LIMIT="2")
    with pdfium.PdfDocument(str(path)) as pdf, tempfile.TemporaryDirectory(prefix="protocol_ocr_") as temp:
        for pos, index in enumerate(page_indexes, 1):
            if progress:
                progress(f"OCR: страница {pos} из {len(page_indexes)} — {path.name}")
            page = pdf[index]
            try:
                # 300 dpi. Rendering respects the PDF page's own rotation metadata.
                bitmap = page.render(scale=300 / 72)
                try:
                    image = bitmap.to_pil()
                    # Orientation detection precedes spread splitting. Do not guess
                    # the rotation when OSD cannot establish it; psm 1 handles that case.
                    image_path = Path(temp) / "page.png"
                    image.save(image_path)
                    orientation = subprocess.run(
                        [executable, str(image_path), "stdout", "--tessdata-dir", str(tessdata),
                         "-l", "osd", "--psm", "0"], capture_output=True, timeout=60,
                        env=environment, **kwargs,
                    )
                    rotation = re.search(rb"Rotate:\s*(\d+)", orientation.stdout)
                    if rotation:
                        rotated = image.rotate(-int(rotation[1]), expand=True)
                        image.close()
                        image = rotated
                    crops = [image]
                    if rotation and image.width > image.height * 1.3:
                        # Two-page scans have a clean, vertical gutter. A wide table
                        # without a gutter must remain intact.
                        gray = image.convert("L")
                        band = gray.crop((int(image.width * .49), int(image.height * .08),
                                          int(image.width * .51), int(image.height * .92)))
                        histogram = band.histogram()
                        white_fraction = sum(histogram[235:]) / max(sum(histogram), 1)
                        band.close()
                        gray.close()
                        if white_fraction > .985:
                            crops = [image.crop((0, 0, image.width // 2, image.height)),
                                     image.crop((image.width // 2, 0, image.width, image.height))]
                    texts = []
                    for crop in crops:
                        gray = crop.convert("L")
                        hist = gray.histogram()
                        gray.close()
                        if sum(hist[:190]) / max(sum(hist), 1) < .002:
                            if crop is not image:
                                crop.close()
                            continue
                        crop.save(image_path)
                        process = subprocess.run(
                            [executable, str(image_path), "stdout", "--tessdata-dir", str(tessdata),
                             "-l", "ukr", "--psm", "3" if rotation else "1"],
                            capture_output=True, timeout=180, env=environment, **kwargs,
                        )
                        if crop is not image:
                            crop.close()
                        if process.returncode:
                            error = process.stderr.decode("utf-8", errors="replace")[-1000:]
                            raise ValueError(f"OCR страницы {index + 1} завершился ошибкой: {error}")
                        texts.append(process.stdout.decode("utf-8", errors="replace").strip())
                    image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
            text = "\n".join(texts).strip()
            if len(text) < 30:
                raise ValueError(f"OCR не прочитал страницу {index + 1}. Проверьте качество скана.")
            result[index] = text
    return result
