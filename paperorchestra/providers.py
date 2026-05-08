from __future__ import annotations

import html
import json
import math
import os
import random
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from .domains import get_domain
from .transport_retry import is_retryable_transport_text


class ProviderError(RuntimeError):
    pass


class TransientProviderError(ProviderError):
    """Provider failure that may succeed after waiting or replaying the same prompt."""


def _env_float(name: str, default: float, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value) or value < minimum:
        return default
    if maximum is not None:
        return min(value, maximum)
    return value


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < minimum:
        return default
    if maximum is not None:
        return min(value, maximum)
    return value


def is_retryable_provider_stderr(text: str) -> bool:
    return is_retryable_transport_text(text)


@dataclass
class CompletionRequest:
    system_prompt: str
    user_prompt: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    seed: int | None = None

    def combined_prompt(self) -> str:
        header = dedent(
            f"""
            [SYSTEM]
            {self.system_prompt.strip()}

            [USER]
            {self.user_prompt.strip()}
            """
        ).strip()
        return header + "\n"

    def _effective_float(self, env_name: str, explicit: float | None) -> float | None:
        if explicit is not None:
            return explicit
        raw = os.environ.get(env_name)
        if raw in {None, ""}:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    def _effective_int(self, env_name: str, explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        raw = os.environ.get(env_name)
        if raw in {None, ""}:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def provider_env_overrides(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        temperature = self._effective_float("PAPERO_PROVIDER_TEMPERATURE", self.temperature)
        max_output_tokens = self._effective_int("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", self.max_output_tokens)
        seed = self._effective_int("PAPERO_PROVIDER_SEED", self.seed)
        if temperature is not None:
            overrides["PAPERO_PROVIDER_TEMPERATURE"] = str(temperature)
        if max_output_tokens is not None:
            overrides["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)
        if seed is not None:
            overrides["PAPERO_PROVIDER_SEED"] = str(seed)
        return overrides

    def control_summary(self) -> dict[str, object]:
        overrides = self.provider_env_overrides()
        return {
            "seed": int(overrides["PAPERO_PROVIDER_SEED"]) if "PAPERO_PROVIDER_SEED" in overrides else None,
            "temperature": float(overrides["PAPERO_PROVIDER_TEMPERATURE"]) if "PAPERO_PROVIDER_TEMPERATURE" in overrides else None,
            "max_output_tokens": int(overrides["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"]) if "PAPERO_PROVIDER_MAX_OUTPUT_TOKENS" in overrides else None,
            "env_keys_forwarded": sorted(overrides.keys()),
            "passthrough_only": True,
            "deterministic_generation_guaranteed": False,
        }


class BaseProvider:
    name = "base"

    def complete(self, request: CompletionRequest) -> str:
        raise NotImplementedError

    def fork(self) -> "BaseProvider":
        return self


class ShellProvider(BaseProvider):
    name = "shell"

    def __init__(self, command: str | None = None, timeout_seconds: float | None = None):
        if command is not None:
            self.command_source = "explicit"
        elif os.environ.get("PAPERO_MODEL_CMD"):
            self.command_source = "PAPERO_MODEL_CMD"
        else:
            self.command_source = "missing"
        self.command = command or os.environ.get("PAPERO_MODEL_CMD")
        if not self.command:
            raise ProviderError("Shell provider requires PAPERO_MODEL_CMD or an explicit command.")
        self.argv = self._parse_command(self.command)
        timeout_value = timeout_seconds if timeout_seconds is not None else os.environ.get("PAPERO_PROVIDER_TIMEOUT_SECONDS")
        self.timeout_seconds = float(timeout_value) if timeout_value not in {None, ""} else None
        self.timeout_grace_seconds = _env_float("PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS", 0.0, minimum=0.0, maximum=3600.0)
        self.retry_attempts = _env_int("PAPERO_PROVIDER_RETRY_ATTEMPTS", 0, minimum=0, maximum=10)
        self.retry_backoff_seconds = _env_float("PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS", 2.0, minimum=0.0, maximum=300.0)
        self.retry_jitter_seconds = _env_float("PAPERO_PROVIDER_RETRY_JITTER_SECONDS", 0.0, minimum=0.0, maximum=300.0)
        self.retry_safe = os.environ.get("PAPERO_PROVIDER_RETRY_SAFE", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.retry_trace_dir = Path(os.environ["PAPERO_PROVIDER_RETRY_TRACE_DIR"]) if os.environ.get("PAPERO_PROVIDER_RETRY_TRACE_DIR") else None

    def _parse_command(self, command: str) -> list[str]:
        try:
            parsed = json.loads(command)
            if isinstance(parsed, list) and parsed and all(isinstance(item, str) for item in parsed):
                argv = parsed
            else:
                raise ProviderError("Provider command JSON must be a non-empty string array.")
        except json.JSONDecodeError:
            argv = shlex.split(command)

        if not argv:
            raise ProviderError("Provider command must not be empty.")

        executable = Path(argv[0]).name
        allowlist = {
            item.strip()
            for item in os.environ.get(
                "PAPERO_ALLOWED_PROVIDER_BINARIES",
                "codex,openai,ollama,llm,claude,gemini",
            ).split(",")
            if item.strip()
        }
        if executable not in allowlist:
            raise ProviderError(
                f"Provider executable '{executable}' is not allowlisted. Set PAPERO_ALLOWED_PROVIDER_BINARIES to opt in."
            )
        return argv

    def _record_retry_attempt(self, payload: dict[str, object]) -> None:
        if self.retry_trace_dir is None:
            return
        self.retry_trace_dir.mkdir(parents=True, exist_ok=True)
        path = self.retry_trace_dir / "provider-retry-attempts.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")

    def _run_once(self, prompt: bytes, env: dict[str, str]) -> tuple[int, bytes, bytes, bool]:
        timed_out = False
        with subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        ) as proc:
            try:
                stdout, stderr = proc.communicate(input=prompt, timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                if self.timeout_grace_seconds > 0:
                    try:
                        stdout, stderr = proc.communicate(timeout=self.timeout_grace_seconds)
                        return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", True
                    except subprocess.TimeoutExpired:
                        pass
                proc.kill()
                stdout, stderr = proc.communicate()
            except BaseException:
                proc.kill()
                proc.wait()
                raise
        return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", timed_out

    def complete(self, request: CompletionRequest) -> str:
        env = os.environ.copy()
        env.pop("PAPERO_PROVIDER_SEED", None)
        env.pop("PAPERO_PROVIDER_TEMPERATURE", None)
        env.pop("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", None)
        env.update(request.provider_env_overrides())
        prompt = request.combined_prompt().encode("utf-8")
        max_attempts = self.retry_attempts + 1
        failures: list[str] = []
        for attempt in range(1, max_attempts + 1):
            rc, stdout, stderr, timed_out = self._run_once(prompt, env)
            stderr_text = stderr.decode("utf-8", errors="replace")
            stdout_text = stdout.decode("utf-8", errors="replace")
            if rc == 0:
                self._record_retry_attempt({"attempt": attempt, "status": "success", "timed_out": timed_out, "replayed": attempt > 1})
                return stdout_text
            transport_evidence = is_retryable_provider_stderr(stderr_text)
            retryable = self.retry_safe and transport_evidence
            reason = "transport_reconnect" if transport_evidence else ("plain_timeout" if timed_out else "non_retryable_failure")
            if timed_out:
                failures.append(
                    f"attempt {attempt}/{max_attempts}: timed out after "
                    f"{self.timeout_seconds if self.timeout_seconds is not None else 'unset'}s"
                    f" + grace {self.timeout_grace_seconds:g}s"
                )
            else:
                failures.append(f"attempt {attempt}/{max_attempts}: exit {rc}: {stderr_text.strip() or '<empty stderr>'}")
            self._record_retry_attempt({
                "attempt": attempt,
                "status": "failure",
                "return_code": rc,
                "timed_out": timed_out,
                "reason": reason,
                "retry_safe": self.retry_safe,
                "will_replay": bool(retryable and attempt < max_attempts),
                "stderr_excerpt": stderr_text.strip()[:500],
            })
            if retryable and attempt < max_attempts:
                sleep_seconds = self.retry_backoff_seconds
                if self.retry_jitter_seconds > 0:
                    sleep_seconds += random.uniform(0.0, self.retry_jitter_seconds)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue
            message = "Provider command failed"
            if timed_out:
                message = "Provider command timed out"
            if retryable:
                message += " after retryable transport handling"
            elif timed_out:
                message += " without retryable transport evidence"
            elif is_retryable_provider_stderr(stderr_text) and not self.retry_safe:
                message += " with retry disabled because PAPERO_PROVIDER_RETRY_SAFE is not set"
            details = "\n".join(failures)
            hint = (
                " Increase PAPERO_PROVIDER_TIMEOUT_SECONDS for slow runs, "
                "PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS for Codex reconnect waits, "
                "PAPERO_PROVIDER_RETRY_ATTEMPTS for prompt replay, and "
                "PAPERO_PROVIDER_RETRY_SAFE=1 only for commands that are safe to replay."
            )
            error_cls = TransientProviderError if retryable else ProviderError
            raise error_cls(f"{message}:\n{details}{hint}")
        raise ProviderError("Provider command failed without producing a result.")

    def fork(self) -> "ShellProvider":
        return ShellProvider(command=json.dumps(self.argv), timeout_seconds=self.timeout_seconds)


class MockProvider(BaseProvider):
    name = "mock"

    def _extract_data_block(self, text: str, name: str) -> str | None:
        pattern = re.compile(rf"<DATA_BLOCK name=\"{re.escape(name)}\">\n(.*?)\n</DATA_BLOCK>", re.DOTALL)
        match = pattern.search(text)
        return html.unescape(match.group(1).strip()) if match else None

    def _extract_citation_keys(self, text: str) -> list[str]:
        checklist = self._extract_data_block(text, "citation_checklist")
        if checklist:
            try:
                parsed = json.loads(checklist)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, str)]
            except json.JSONDecodeError:
                pass
        citation_map = self._extract_data_block(text, "citation_map.json")
        if citation_map:
            try:
                parsed = json.loads(citation_map)
                if isinstance(parsed, dict):
                    return [key for key in parsed.keys() if isinstance(key, str)]
            except json.JSONDecodeError:
                pass
        return []

    def _extract_plot_ids(self, text: str) -> list[str]:
        manifest = self._extract_data_block(text, "plot_manifest.json")
        if not manifest:
            return []
        try:
            parsed = json.loads(manifest)
        except json.JSONDecodeError:
            return []
        figures = parsed.get("figures", []) if isinstance(parsed, dict) else []
        result = []
        for figure in figures:
            if isinstance(figure, dict) and isinstance(figure.get("figure_id"), str):
                result.append(figure["figure_id"])
        return result

    def _extract_plot_asset_paths(self, text: str) -> list[str]:
        payload = self._extract_data_block(text, "plot_assets.json")
        if not payload:
            return []
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return []
        assets = parsed.get("assets", []) if isinstance(parsed, dict) else []
        result = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            snippet_path = asset.get("latex_snippet_path")
            latex_path = asset.get("latex_path")
            filename = asset.get("filename")
            if isinstance(snippet_path, str):
                result.append(snippet_path)
            elif isinstance(latex_path, str):
                result.append(latex_path)
            elif isinstance(filename, str):
                result.append(filename)
        return result

    def _extract_metric_tokens(self, text: str) -> list[str]:
        experimental_log = self._extract_data_block(text, "experimental_log.md") or self._extract_data_block(
            text, "project_experimental_log"
        )
        if not experimental_log:
            return []
        return re.findall(r"\b\d+\.\d+%?\b|\b\d+%", experimental_log)

    def _mock_latex_document(self, request: CompletionRequest, *, refined: bool = False) -> str:
        citation_keys = self._extract_citation_keys(request.user_prompt)
        plot_ids = self._extract_plot_ids(request.user_prompt)
        plot_asset_paths = self._extract_plot_asset_paths(request.user_prompt)
        metric_tokens = self._extract_metric_tokens(request.user_prompt)
        cited = ",".join(citation_keys[: max(1, len(citation_keys))]) if citation_keys else ""
        cite_clause = f"\\cite{{{cited}}}" if cited else ""
        plot_id = plot_ids[0] if plot_ids else "fig_framework_overview"
        asset_filename = plot_asset_paths[0] if plot_asset_paths else None
        metric_sentence = ""
        if metric_tokens:
            metric_sentence = " Reported grounded metrics include " + ", ".join(metric_tokens[:3]) + "."
        title_line = "Refined mock paper." if refined else "Mock paper output."
        figure_body = (
            (f"\\input{{{asset_filename}}}\n" if asset_filename.endswith(".tex") else f"\\includegraphics[width=0.85\\linewidth]{{{asset_filename}}}\n")
            if asset_filename
            else ""
        )
        return f"""```latex
\\documentclass{{article}}
\\usepackage{{graphicx}}
\\begin{{document}}
{title_line}
\\section{{Introduction}}
PaperOrchestra frames manuscript generation as an artifact-driven workflow {cite_clause}.
\\section{{Related Work}}
Prior autonomous writing systems often remain tightly coupled to experimental loops {cite_clause}.
\\section{{Method}}
The pipeline follows staged orchestration and references Figure~\\ref{{{plot_id}}}. The method section is intentionally non-empty in the mock provider so validation exercises a complete manuscript shape: it describes how inputs are converted into an outline, how plot and literature lanes produce artifacts, and how later writing stages consume those artifacts.
\\begin{{figure}}
{figure_body}
\\caption{{Overview of the staged pipeline.}}
\\label{{{plot_id}}}
\\end{{figure}}
\\section{{Experiments}}
The evaluation emphasizes grounded writing and verified citations.{metric_sentence}
\\section{{Conclusion}}
The manuscript remains artifact-first and refinement-gated {cite_clause}.
\\end{{document}}
```"""

    def complete(self, request: CompletionRequest) -> str:
        system = request.system_prompt.lower()
        if (
            "content refinement agent" in system
            or "two fenced code blocks" in system
            or "rebuttal via revision" in system
            or "two distinct code blocks" in system
            or "worklog for the current turn" in system
        ):
            return """```json
{
  "addressed_weaknesses": ["Clarified framing"],
  "integrated_answers": ["Added one explanatory sentence"],
  "actions_taken": ["Rewrote introduction paragraph"]
}
```
""" + self._mock_latex_document(request, refined=True)
        if "prior-work seed generator" in system:
            return json.dumps(
                {
                    "references": [dict(item) for item in get_domain().mock_prior_work_references],
                    "research_notes": ["Mock provider returns canonical seed examples without live web access."],
                },
                indent=2,
            )
        if "citation-support verifier" in system:
            ids = re.findall(r'"id"\s*:\s*"(cite-\d+)"', request.user_prompt)
            items = []
            for item_id in ids:
                items.append(
                    {
                        "id": item_id,
                        "support_status": "needs_manual_check",
                        "risk": "medium",
                        "claim_type": "background",
                        "evidence": [],
                        "reasoning": "Mock provider cannot perform live web/source inspection.",
                        "suggested_fix": "Run a web-search-capable provider or manually verify this cited sentence.",
                    }
                )
            return json.dumps(
                {
                    "items": items,
                    "research_notes": ["Mock provider does not claim cited-sentence support."],
                },
                indent=2,
            )
        if "single, valid json object" in system or "json object" in system:
            if "macro_candidates" in system:
                payload = {
                    "macro_candidates": [
                        {
                            "title_guess": "AutoSurvey2",
                            "why_relevant": "Survey-generation baseline for literature synthesis.",
                            "origin_query": "automated literature review generation",
                            "role_guess": "macro",
                            "discovery_source": "model",
                            "discovery_sources": ["model"],
                        }
                    ],
                    "micro_candidates": [
                        {
                            "title_guess": "LiRA",
                            "why_relevant": "Multi-agent literature review system.",
                            "origin_query": "multi-agent literature review generation",
                            "role_guess": "micro",
                            "discovery_source": "model",
                            "discovery_sources": ["model"],
                        }
                    ],
                }
                return json.dumps(payload, indent=2)
            if "top-level key named figures" in system:
                payload = {
                    "figures": [
                        {
                            "figure_id": "fig_framework_overview",
                            "title": "Framework overview",
                            "plot_type": "diagram",
                            "data_source": "both",
                            "objective": "Show the end-to-end writing pipeline and artifact flow.",
                            "aspect_ratio": "16:9",
                            "rendering_brief": "A conceptual pipeline diagram connecting inputs, outline, plot generation, literature review, writing, and refinement.",
                            "caption": "Overview of the multi-agent writing pipeline and its artifact flow from raw inputs to a refined manuscript.",
                            "source_fidelity_notes": "mixed: concept-grounded structure with references to experimental-log-driven outputs.",
                        }
                    ]
                }
                return json.dumps(payload, indent=2)
            if "plotting_plan" in system or "outline" in system:
                payload = {
                    "plotting_plan": [
                        {
                            "figure_id": "fig_framework_overview",
                            "title": "Framework overview",
                            "plot_type": "diagram",
                            "data_source": "both",
                            "objective": "Diagram showing the full writing pipeline and data flow.",
                            "aspect_ratio": "16:9",
                        }
                    ],
                    "intro_related_work_plan": {
                        "introduction_strategy": {
                            "hook_hypothesis": "High-quality literature review and grounded writing remain bottlenecks in AI paper drafting.",
                            "problem_gap_hypothesis": "Existing autonomous writers under-cite and fail to ground manuscript structure in raw materials.",
                            "search_directions": [
                                "automated research paper writing literature review benchmark",
                                "multi-agent literature review generation",
                                "submission-ready latex manuscript generation"
                            ],
                        },
                        "related_work_strategy": {
                            "overview": "Compare end-to-end research agents, literature-review systems, and structure-grounded writing systems.",
                            "subsections": [
                                {
                                    "subsection_title": "Related Work: Autonomous research agents",
                                    "methodology_cluster": "End-to-end research agents",
                                    "sota_investigation_mission": "Find recent autonomous research systems before the cutoff.",
                                    "limitation_hypothesis": "These systems are tightly coupled to internal experimentation loops.",
                                    "limitation_search_queries": [
                                        "autonomous research agent manuscript generation",
                                        "paper writing coupled to experiment pipeline"
                                    ],
                                    "bridge_to_our_method": "The proposed pipeline decouples writing from experimentation and grounds citations via verification."
                                }
                            ],
                        },
                    },
                    "section_plan": [
                        {
                            "section_title": "Method",
                            "subsections": [
                                {
                                    "subsection_title": "Pipeline Overview",
                                    "content_bullets": [
                                        "Describe the five-step orchestration pipeline.",
                                        "Explain the inputs and generated artifact flow."
                                    ],
                                    "citation_hints": [
                                        "research paper or technical report introducing 'Semantic Scholar API'"
                                    ],
                                }
                            ],
                        }
                    ],
                }
                return json.dumps(payload, indent=2)
            if ("reviewer" in system or "overall_score" in system) and "reviewer_feedback" not in system:
                paper_text = request.user_prompt.lower()
                score = 72
                if "refined mock paper" in paper_text:
                    score = 78
                if "regressed mock paper" in paper_text:
                    score = 61
                payload = {
                    "paper_title": "Mock Paper",
                    "citation_statistics": {
                        "estimated_unique_citations": 12,
                        "citation_density_assessment": "appropriate",
                        "breadth_across_subareas": "moderate",
                        "comparison_to_baseline": "roughly on par with the provided baseline expectation",
                        "notes": "Mock citation statistics for regression tests.",
                    },
                    "axis_scores": {
                        "coverage_and_completeness": {"score": score, "justification": "Coverage appears reasonably grounded."},
                        "relevance_and_focus": {"score": max(score - 2, 0), "justification": "Focus remains reasonably grounded."},
                        "critical_analysis_and_synthesis": {"score": max(score - 4, 0), "justification": "Synthesis is acceptable in the mock path."},
                        "positioning_and_novelty": {"score": max(score - 5, 0), "justification": "Positioning is acceptable in the mock path."},
                        "organization_and_writing": {"score": score, "justification": "Organization is acceptable in the mock path."},
                        "citation_practices_and_rigor": {"score": max(score - 3, 0), "justification": "Citation rigor is acceptable in the mock path."},
                    },
                    "penalties": [],
                    "summary": {
                        "strengths": ["Grounded artifact use"],
                        "weaknesses": ["Needs stronger synthesis"],
                        "top_improvements": ["Clarify literature positioning"]
                    },
                    "overall_score": score,
                    "questions": ["Clarify why the pipeline is decoupled from experiment generation."],
                }
                return json.dumps(payload, indent=2)
            payload = {"ok": True}
            return json.dumps(payload, indent=2)

        return self._mock_latex_document(request, refined=False)

    def fork(self) -> "MockProvider":
        return MockProvider()


def get_provider(name: str, command: str | None = None) -> BaseProvider:
    normalized = name.strip().lower()
    if normalized == "mock":
        return MockProvider()
    if normalized == "shell":
        return ShellProvider(command=command)
    raise ProviderError(f"Unsupported provider: {name}")


def default_codex_web_provider_command() -> str:
    model = os.environ.get("PAPERO_OMX_MODEL") or "gpt-5.4-mini"
    effort = os.environ.get("PAPERO_OMX_REASONING_EFFORT") or "low"
    return json.dumps(
        [
            "codex",
            "--search",
            "exec",
            "--skip-git-repo-check",
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{effort}"',
        ]
    )



def provider_command_digest(provider: BaseProvider | None) -> str | None:
    if isinstance(provider, ShellProvider):
        return hashlib_sha256_json(provider.argv)
    return None


def hashlib_sha256_json(value: object) -> str:
    import hashlib as _hashlib

    return _hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()


def _read_wrapper_contract(wrapper_path: Path) -> dict[str, object] | None:
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    if not contract_path.exists():
        return None
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def provider_web_search_capability_proof(provider: BaseProvider) -> dict[str, object] | None:
    """Return auditable web-search capability proof for trusted citation providers.

    Fresh smoke uses a trace wrapper (`bash provider-wrap.sh web`) so prompt/response
    evidence is preserved.  Direct `codex --search exec` remains valid for ordinary
    web-capable shell providers, but wrapper-backed web support is accepted only when
    an adjacent sidecar proves the wrapper path, hash, mode, and inner argv prefix.
    """

    if not isinstance(provider, ShellProvider):
        return None
    argv = provider.argv
    digest = hashlib_sha256_json(argv)
    if len(argv) >= 3 and Path(argv[0]).name == "codex" and argv[1] == "--search" and argv[2] == "exec":
        return {
            "provider_capability_proof": "direct-codex-search/1",
            "provider_command_digest": digest,
            "web_search_capable": True,
        }
    if len(argv) != 3 or Path(argv[0]).name not in {"bash", "sh"} or argv[2] != "web":
        return None
    wrapper_path = Path(argv[1]).resolve()
    if wrapper_path.name != "provider-wrap.sh" or not wrapper_path.exists():
        return None
    payload = _read_wrapper_contract(wrapper_path)
    if not payload or payload.get("schema_version") != "provider-wrapper-contract/1":
        return None
    try:
        recorded_path = Path(str(payload.get("wrapper_path") or "")).resolve()
    except (OSError, RuntimeError):
        return None
    if recorded_path != wrapper_path:
        return None
    import hashlib as _hashlib

    actual_wrapper_sha = _hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
    if payload.get("wrapper_sha256") != actual_wrapper_sha:
        return None
    modes = payload.get("modes")
    mode_payload = modes.get("web") if isinstance(modes, dict) else None
    if not isinstance(mode_payload, dict):
        return None
    if mode_payload.get("trace_wrapped") is not True or mode_payload.get("web_search_capable") is not True:
        return None
    prefix = mode_payload.get("exec_argv_prefix")
    if prefix != ["codex", "--search", "exec"]:
        return None
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    contract_sha = _hashlib.sha256(contract_path.read_bytes()).hexdigest()
    return {
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_command_digest": digest,
        "provider_contract_path": str(contract_path),
        "provider_contract_sha256": contract_sha,
        "provider_wrapper_path": str(wrapper_path),
        "provider_wrapper_sha256": actual_wrapper_sha,
        "provider_wrapper_mode": "web",
        "provider_wrapper_exec_argv_prefix": prefix,
        "web_search_capable": True,
    }

def provider_supports_web_search(provider: BaseProvider) -> bool:
    return provider_web_search_capability_proof(provider) is not None


def get_citation_support_provider(
    name: str,
    *,
    command: str | None = None,
    evidence_mode: str = "heuristic",
) -> BaseProvider | None:
    if evidence_mode == "heuristic":
        return None
    provider_command = command
    if evidence_mode == "web" and name == "shell" and not provider_command and not os.environ.get("PAPERO_MODEL_CMD"):
        provider_command = default_codex_web_provider_command()
    provider = get_provider(name, command=provider_command)
    if evidence_mode == "web" and name == "shell" and command is None and not provider_supports_web_search(provider):
        provider = get_provider(name, command=default_codex_web_provider_command())
    if evidence_mode == "web" and not provider_supports_web_search(provider):
        raise ProviderError(
            "review-citations --evidence-mode web requires a Codex shell provider command containing --search. "
            "Set PAPERO_MODEL_CMD to a codex --search exec command, pass --provider-command with --search, "
            "or use --evidence-mode model for non-web model review."
        )
    return provider
