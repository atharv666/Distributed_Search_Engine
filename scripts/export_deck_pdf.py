"""Export the presentation (ppt/index.html) to a PDF with one page per slide.

Each slide is photographed at 1920x1080 with headless Edge and the pictures are assembled into a PDF,
so the PDF looks exactly like the slides on screen.   Usage:  python scripts/export_deck_pdf.py
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "ppt"
OUTPUT = DECK / "Distributed_Search_FA1_FA2.pdf"
EDGE = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)


def slide_count() -> int:
    """15 original slides + every slide pushed in fa2_slides.js + the rewritten conclusion."""
    return 15 + len(re.findall(r"slidesHtml\.push\(", (DECK / "fa2_slides.js").read_text(encoding="utf-8"))) + 1


def main() -> None:
    total = slide_count()
    pictures = []
    with tempfile.TemporaryDirectory() as folder:
        for number in range(1, total + 1):
            target = Path(folder) / f"slide_{number:02d}.png"
            subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1080",
                            "--virtual-time-budget=5000", f"--screenshot={target}",
                            f"file:///{(DECK / 'index.html').as_posix()}?pdf#{number}"], capture_output=True, timeout=120)
            jpeg = target.with_suffix(".jpg")
            Image.open(target).convert("RGB").save(jpeg, quality=90)
            pictures.append(jpeg)
            print(f"slide {number}/{total}")
        document = pymupdf.open()
        for picture in pictures:
            page = document.new_page(width=1440, height=810)       # 16:9
            page.insert_image(page.rect, filename=str(picture))
        document.save(OUTPUT, deflate=True)
    print(f"wrote {OUTPUT} ({total} pages)")


if __name__ == "__main__":
    main()
