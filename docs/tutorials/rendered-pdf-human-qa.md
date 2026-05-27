# Rendered PDF human QA

Scope: human-only rendered-PDF QA tutorial for acting as the operator who inspects compiled pages. This checklist covers layout/readability evidence. It does not authorize new scientific claims, citation approval, or author/domain judgment.

## Preconditions

- A compiled `paper.full.pdf` exists.
- You know which session/run produced it.
- The review is grounded in rendered pages, not only JSON or TeX.
- `pdfinfo`, `pdftotext`, and `pdftoppm` are installed; on many Linux systems they come from `poppler-utils`.

## Extract inspectable evidence

```bash
PDF=/absolute/path/to/paper.full.pdf
OUT=/tmp/paperorchestra-rendered-pdf-qa
rm -rf "$OUT" && mkdir -p "$OUT/pages"

pdfinfo "$PDF" | tee "$OUT/pdfinfo.txt"
pdftotext "$PDF" "$OUT/paper.full.txt"
pdftoppm -png -r 160 "$PDF" "$OUT/pages/page"
sha256sum "$PDF" "$OUT"/pages/*.png "$OUT/paper.full.txt" > "$OUT/sha256sums.txt"
```

Open every page image. Check at least:

- title/top matter;
- section order and readability;
- figure bodies, table bodies, captions, and references to them;
- wide tables crossing page margins, overflow, clipping, unreadable text, excessive whitespace, and page breaks;
- prompt/meta leakage in rendered text;
- whether generated placeholder figures are still being treated as final figures.

## Required hash-bound attestation

Write a review artifact even when there are no findings. Include `compiled_pdf_sha256`, `reviewed_page_count`, `page_image_sha256`, and a statement such as:

```json
{
  "schema_version": "manual-human-rendered-pdf-qa/1",
  "reviewer_role": "human_or_codex_as_human_qa_operator",
  "compiled_pdf_sha256": "...",
  "reviewed_page_count": 2,
  "page_image_sha256": {"page-1.png": "..."},
  "attestation": "I inspected every rendered PDF page before writing this QA result.",
  "findings": []
}
```

If you find an issue, cite `source_artifact_role=compiled_pdf` and a concrete page/locator. If no layout-only issue exists, a `rendered_pdf_no_issues` attestation is valid only after all pages were inspected.

In short: author/domain judgments remain blockers. Do not approve unsupported claims, scientific meaning, bibliography correctness, title suitability, citation density, or final figure adequacy merely because the PDF layout is readable.
