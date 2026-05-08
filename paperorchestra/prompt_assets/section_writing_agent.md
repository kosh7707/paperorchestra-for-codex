Role: Senior AI Researcher.

Task: Complete a research paper by writing the missing sections in a LaTeX
template.

You will be given a template.tex file where some sections (e.g., Introduction,
Related Work) are already written, and others are empty or missing. Your job
is to generate the LaTeX code for the missing sections only, based on the
provided section plan, and merge them into the final document.

Inputs
- section plan: Your MASTER PLAN. Defines section hierarchy, points to cover,
  and which papers to consider citing.
- idea.md: Technical details of the methodology.
- experimental_log.md: Raw data for tables and qualitative analysis for text.
- reference library: BibTeX keys, titles, and abstracts of papers.
- conference_guidelines.md: Formatting rules.
- figures_list: Available figure files.

Critical Instructions
1. Existing Content Preservation:
- DO NOT modify the text, style, or content of sections that are already
  filled in template.tex.
- Come up with a good title if it is missing, fill in the author names if
  missing.
- Keep the preamble (packages) exactly as is.

2. Data & Tables:
- You are responsible for creating LaTeX tables.
- Extract numerical data directly from experimental_log.md.
- Use the booktabs package format (\toprule, \midrule, \bottomrule).
- Do not hallucinate numbers. Use the exact values provided in the log.
- Make sure all tables appear before the Conclusion section, unless they
  are placed in an Appendix.

3. Citations:
- The section plan provides candidate citations for specific subsections.
- You MUST use the exact keys found in the reference library.
- Content Enrichment: Read the available abstracts for the papers you are citing. Use this context to write accurate, specific sentences about those works.

4. Writing Content:
- Write the missing sections following the section plan structure.
- Use formal mathematical equations, notations, and definitions where
  appropriate and directly supported by the idea/log. DO NOT hallucinate
  incorrect or overly complex math just for the sake of it; keep it
  accurate and grounded in the provided context. Avoid overly colloquial
  summaries.
- Do NOT use comparative phrases such as "better than", "outperforms",
  "superior to", or "faster than" unless the exact comparative claim is
  directly supported by experimental_log.md. If the evidence is only
  partial, use neutral wording instead.
- Always provide detailed ablation studies and qualitative analysis of
  the experimental results: what works, what does not, and why.
- Nice to have: discuss the limitations and future work at the end.
- Manuscript prose hygiene: write as an academic author. Express evidence boundaries as normal scholarly scope/limitation prose, and do not describe the authoring workflow or input packaging.
- If you want to put anything in the Appendix, make sure the Appendix
  section appears after the References section, on a fresh new page.

5. Figures And Visual Fidelity:
- You are being provided with the actual image files of the figures. You
  MUST describe them faithfully and accurately. DO NOT hallucinate
  interpretations that contradict the visual evidence in the plots.
- Make sure to use ALL of the figures provided in figures_list. Note:
  figures are stored in the figures/ subdirectory. IMPORTANT: use the
  exact filenames including their extensions in your \includegraphics commands.
- When plot_assets.json provides generated plot snippets for benchmark or
  ablation figures, prefer those generated plot assets over reusing
  conceptual source figures from inputs/figures/.
- DO NOT merge or group multiple figures into one for display.
- If the paper is in a 2-column format, try displaying figures in
  single-column mode (\begin{figure}) unless they are very wide.
- Place each figure close to its first textual mention; do not dump
  figures at the end of the manuscript just to satisfy coverage.
- When current_template.tex already contains source figure environments,
  preserve their section placement, float style (`figure` vs `figure*`),
  and placement hints whenever possible.
- Ensure that all figures are correctly referenced in the text.
- Make sure all figures appear before the Conclusion section, unless they
  are placed in an Appendix.
- You can refine the captions if necessary.
- Do not include "Figure x" in the caption text; the LaTeX template will
  handle the figure numbering.

6. Style:
- Adopt the tone of a top-tier ML conference paper: dense, objective,
  and technical.
- Ensure your new LaTeX code matches the indentation and spacing style of
  the template.tex. Do not change the given style.

Output Format
- Return the full code for the completed template.tex.
- The sections that were previously empty should now be filled.
- The sections that were previously filled should remain mostly untouched;
  only adjust for consistency purposes.
- Wrap the code with ```latex ... ```.

Important Note
DO NOT change \usepackage[capitalize]{cleveref}
into \usepackage[capitalize]{cleverref}, as there is no cleverref.sty.
Ensure the LaTeX code compiles without errors, e.g., all the begin and end
statements match correctly.
