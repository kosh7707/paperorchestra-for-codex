from __future__ import annotations

import shutil
from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session_paths import project_root


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _snapshot_file(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination)


def snapshot_inputs(
    cwd: str | Path | None,
    run_dir: Path,
    inputs: InputBundle,
    *,
    allow_outside_workspace: bool,
) -> InputBundle:
    root = project_root(cwd)
    inputs_dir = run_dir / "inputs"
    idea_source = Path(inputs.idea_path).resolve()
    experimental_source = Path(inputs.experimental_log_path).resolve()
    template_source = Path(inputs.template_path).resolve()
    guidelines_source = Path(inputs.guidelines_path).resolve()
    figures_source = Path(inputs.figures_dir).resolve() if inputs.figures_dir else None

    sources = [idea_source, experimental_source, template_source, guidelines_source]
    if figures_source:
        sources.append(figures_source)
    if not allow_outside_workspace:
        outside = [str(path) for path in sources if not _is_within(path, root)]
        if outside:
            raise ValueError(
                "Refusing to initialize session from paths outside the workspace without --allow-outside-workspace: "
                + ", ".join(outside)
            )

    snapped_figures = None
    if figures_source:
        snapped_figures_dir = inputs_dir / "figures"
        if snapped_figures_dir.exists():
            shutil.rmtree(snapped_figures_dir)
        shutil.copytree(figures_source, snapped_figures_dir)
        snapped_figures = str(snapped_figures_dir)

    return InputBundle(
        idea_path=_snapshot_file(idea_source, inputs_dir / "idea.md"),
        experimental_log_path=_snapshot_file(experimental_source, inputs_dir / "experimental_log.md"),
        template_path=_snapshot_file(template_source, inputs_dir / "template.tex"),
        guidelines_path=_snapshot_file(guidelines_source, inputs_dir / "conference_guidelines.md"),
        figures_dir=snapped_figures,
        cutoff_date=inputs.cutoff_date,
        venue=inputs.venue,
        page_limit=inputs.page_limit,
    )
