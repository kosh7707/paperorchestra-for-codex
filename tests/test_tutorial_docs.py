from __future__ import annotations

import json
import re
import shlex
import unittest
from pathlib import Path


TUTORIALS = {
    "docs/tutorials/index.md": ["Scope:", "README", "ENVIRONMENT.md", "not submission-ready"],
    "docs/tutorials/start.md": ["Scope:", "first-use", "paperorchestra first-use", "stale", "package_context"],
    "docs/tutorials/mock-demo.md": ["Scope:", "mock/demo", "./scripts/demo-mock.sh --in-repo", "not citation-fidelity proof"],
    "docs/tutorials/docker-container-qa.md": [
        "Scope:",
        "developer/container QA",
        "scripts/container-run.sh --privileged --with-codex-auth --docker-arg -v --docker-arg paperorchestra-qa-venv:/repo/.venv",
        "PAPERO_UPDATE_CONTAINER_AI_CLIS=0",
        "PEP 668",
        "export-artifacts",
    ],
    "docs/tutorials/rendered-pdf-human-qa.md": [
        "Scope:",
        "human-only rendered-PDF QA",
        "pdfinfo",
        "pdftotext",
        "pdftoppm",
        "compiled_pdf_sha256",
        "reviewed_page_count",
        "hash-bound attestation",
        "author/domain judgments remain blockers",
    ],
    "docs/tutorials/claim-safe-quality-loop.md": [
        "Scope:",
        "claim-safe QA",
        "quality-gate",
        "qa-loop-step",
        "complete` means",
        "pass_loop_verified",
        "not submission-ready",
    ],
}


PUBLIC_DOC_GLOBS = ["README.md", "ENVIRONMENT.md", "skills/paperorchestra/SKILL.md", "docs/**/*.md"]
PRIVATE_PATH_PATTERNS = ["/home/kosh", "/Users/", "C:\\Users"]
PRIVATE_DOMAIN_MARKERS = ["CCI_MATERIALS", "paperorchestra-for-codex-qa-evidence"]
FALSE_READY_PATTERNS = [
    re.compile(r"complete[` ]+(?:means|=|is)\s+(?:submission|camera|publication)-ready", re.IGNORECASE),
    re.compile(r"pass_loop_verified[` ]+(?:means|=|is)\s+(?:manuscript|submission|camera)-ready", re.IGNORECASE),
    re.compile(r"mock artifacts?\s+(?:prove|guarantee)\s+(?:claim|citation|submission)", re.IGNORECASE),
]


class TutorialDocsTests(unittest.TestCase):
    def _read(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def test_tutorial_file_contract_is_present(self) -> None:
        for path, phrases in TUTORIALS.items():
            with self.subTest(path=path):
                tutorial = Path(path)
                self.assertTrue(tutorial.exists(), f"missing {path}")
                text = tutorial.read_text(encoding="utf-8")
                for phrase in phrases:
                    self.assertIn(phrase, text)

    def test_readme_is_router_with_tutorial_map_not_full_runbook(self) -> None:
        text = self._read("README.md")
        self.assertLessEqual(len(text.splitlines()), 1450)
        self.assertIn("## Tutorials", text)
        for path in TUTORIALS:
            self.assertIn(path, text)
        # Detailed operator checklists should live in tutorials, not only README.
        self.assertIn("docs/tutorials/docker-container-qa.md", text)
        self.assertIn("docs/tutorials/rendered-pdf-human-qa.md", text)
        self.assertIn("docs/tutorials/claim-safe-quality-loop.md", text)
        self.assertIn("Keep these status meanings separate", text)
        self.assertIn("complete`: a compiled PDF exists", text)
        self.assertIn("does **not** mean the paper is claim-safe", text)

    def test_readme_copyable_model_command_is_valid_json(self) -> None:
        text = self._read("README.md")
        matches = re.findall(r"^export PAPERO_MODEL_CMD=(.+)$", text, re.MULTILINE)
        self.assertTrue(matches, "README must contain a copyable PAPERO_MODEL_CMD export")
        for assignment in matches:
            with self.subTest(assignment=assignment):
                value = shlex.split(assignment)[0]
                parsed = json.loads(value)
                self.assertIsInstance(parsed, list)
                self.assertIn("codex", parsed[0])

    def test_tutorials_are_generic_and_do_not_overclaim_readiness(self) -> None:
        offenders: list[str] = []
        for pattern in PUBLIC_DOC_GLOBS:
            for path in sorted(Path().glob(pattern)):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in PRIVATE_PATH_PATTERNS + PRIVATE_DOMAIN_MARKERS:
                    if token in text:
                        offenders.append(f"{path}:{token}")
                if str(path).startswith("docs/tutorials/") or path.name == "README.md":
                    for regex in FALSE_READY_PATTERNS:
                        if regex.search(text):
                            offenders.append(f"{path}:false-readiness:{regex.pattern}")
        self.assertEqual([], offenders)

    def test_docker_and_pdf_tutorials_define_dogfood_evidence(self) -> None:
        docker = self._read("docs/tutorials/docker-container-qa.md")
        pdf = self._read("docs/tutorials/rendered-pdf-human-qa.md")
        for phrase in [
            "fresh install",
            "mock demo",
            "export bundle",
            "PDF must exist",
            "do not claim the QA loop complete",
        ]:
            self.assertIn(phrase, docker)
        for phrase in [
            "pdfinfo",
            "pdftotext",
            "pdftoppm",
            "page image",
            "compiled_pdf_sha256",
            "page_image_sha256",
            "I inspected every rendered PDF page",
        ]:
            self.assertIn(phrase, pdf)


if __name__ == "__main__":
    unittest.main()
