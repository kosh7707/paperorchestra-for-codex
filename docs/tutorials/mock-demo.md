# Safe mock demo

Scope: mock/demo tutorial for producing one offline artifact set. This path uses bundled minimal materials and mock providers; it is not citation-fidelity proof and not submission-ready evidence.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

./scripts/demo-mock.sh --in-repo
cd .paper-orchestra/manual-demo
paperorchestra status --summary
paperorchestra export-artifacts --output "$OLDPWD/paperorchestra-output"
cd "$OLDPWD"
```

Expected result:

- the demo ends with `[demo] SUCCESS`;
- the session reaches `draft_complete` before optional compile;
- `paper.full.tex` exists;
- export copies TeX, references, review/audit JSON, and session metadata.

## Optional PDF compile

Only compile when the machine is ready and you explicitly opt in:

```bash
cd .paper-orchestra/manual-demo
paperorchestra check-compile-env
PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile
paperorchestra status --summary
```

`complete` means a compiled PDF exists. It does not mean citation claims, figures, or final paper quality are approved.

## Next

For Docker/container validation, use [`docker-container-qa.md`](docker-container-qa.md). For rendered PDF review, use [`rendered-pdf-human-qa.md`](rendered-pdf-human-qa.md).
