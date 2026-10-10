"""OCR the selected scanned UPSC PDF into a plain-text file."""

from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_FOLDER / "data"
OUTPUT_FILE = DATA_FOLDER / "extracted_text.txt"
PDF_NAME = "QP-CSM-26-010926-GENERAL STUDIES PAPER - I.pdf"
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DPI = 225


def main() -> None:
    pdf_path = DATA_FOLDER / PDF_NAME
    if not pdf_path.is_file():
        raise SystemExit(f"Input PDF was not found: {pdf_path}")
    if not TESSERACT_EXE.is_file():
        raise SystemExit(f"Tesseract executable was not found: {TESSERACT_EXE}")

    # Configure the executable directly so Tesseract does not need to be on PATH.
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
    extracted_pages = []

    try:
        with pymupdf.open(pdf_path) as document:
            total_pages = len(document)
            if total_pages == 0:
                raise ValueError("The PDF contains no pages.")

            scale = DPI / 72
            matrix = pymupdf.Matrix(scale, scale)
            for page_number, page in enumerate(document, start=1):
                print(f"OCR page {page_number}/{total_pages}...", flush=True)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                page_text = pytesseract.image_to_string(image, lang="eng")
                extracted_pages.append(f"--- PAGE {page_number} ---\n{page_text.strip()}")
    except Exception as error:
        raise SystemExit(f"OCR failed for {pdf_path.name}: {error}") from error

    combined_text = "\n\n".join(extracted_pages) + "\n"
    try:
        OUTPUT_FILE.write_text(combined_text, encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"Could not write OCR output to {OUTPUT_FILE}: {error}") from error

    print(f"\nPDF: {pdf_path.name}")
    print(f"Pages processed: {len(extracted_pages)}")
    print(f"Extracted characters: {len(combined_text)}")
    print(f"Saved text to: {OUTPUT_FILE}")
    print("\nPreview (first 1500 characters):\n")
    print(combined_text[:1500])


if __name__ == "__main__":
    main()
