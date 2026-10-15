# Presentation Deck

Open `index.html` in a browser. It is a 43-slide, self-contained HTML/CSS/JavaScript presentation for the distributed-search-engine project (FA–1 and FA–2). `Distributed_Search_FA1_FA2.pdf` is the same deck as a PDF, one page per slide.

Navigation: Left/Right arrows, Space, Page Up/Down, Home/End, or the on-screen buttons. Slide URLs include a hash (`index.html#25`), so any slide can be opened directly.

## Contents

| Slides | Topic |
|---|---|
| 1–15 | FA–1: Unit 1 and 2 (search engine, partitioning, indexing, TF-IDF, gRPC, demo) |
| 16–19 | FA–2 problem and design: what broke, before / after architecture, Bully election |
| 20–22 | Election in our system, epochs, beacon (heartbeat) protocol |
| 23–25 | Causal ordering and vector clocks, advantages |
| 26–27 | Complete architecture and the add-a-document sequence |
| 28–31 | Unit 4: replication and consistency, proposed AWS deployment (EC2 + S3), syllabus mapping for Units 3 and 4 |
| 32–40 | The running system: search page, admin console, lifecycle, concurrency, vector timeline and trace, failover |
| 41–43 | Demo script and conclusion |

## Files

* `index.html`, `app.js`, `story.js`, `style.css`: the original deck. `app.js` now loads the files below after `story.js`.
* `fa2_slides.js`: the new slides and the rewritten conclusion. `fa2_diagrams.js`: the inline SVG diagrams. `fa2.css`: their styles.
* `capture_data.js`: the exact vectors and IDs shown in the screenshots (generated).
* `img/`: screenshots of the real interface (generated) and the cloud logos (see `img/CREDITS.txt`).

## Regenerating the screenshots and the PDF

The screenshots come from a disposable cluster (own ports, a copy of the data), so the real `data/` folder is untouched. Both scripts need Microsoft Edge and Pillow; the PDF script also needs PyMuPDF.

```powershell
python scripts/capture_deck_images.py     # ppt/img/*.png and ppt/capture_data.js
python scripts/export_deck_pdf.py         # ppt/Distributed_Search_FA1_FA2.pdf
```

The deck uses CSS-built and inline-SVG diagrams, so it runs without internet access. The AWS and S3 logos are local files.
