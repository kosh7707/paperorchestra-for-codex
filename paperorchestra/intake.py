from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .aggregation import (
    aggregate_intake,
    enrich_with_prior_work,
    render_experimental_log_from_registry,
    render_idea_from_selection,
)
from .io_utils import read_json, write_json, write_text
from .models import InputBundle, utc_now_iso
from .session import create_session, project_root, runtime_root

INTAKE_CURRENT_FILE = "current_intake.txt"
INTAKE_ID_RE = re.compile(r"^intake-[a-f0-9]{12}$")


@dataclass(frozen=True)
class IntakeQuestion:
    key: str
    prompt: str
    required: bool
    help_text: str


@dataclass
class IntakeState:
    intake_id: str
    created_at: str
    updated_at: str
    status: str
    answers: dict[str, Any] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)
    adaptive_followups: list[dict[str, Any]] = field(default_factory=list)
    ambiguity_score: float = 1.0
    notes: list[str] = field(default_factory=list)
    generated_paths: dict[str, str] = field(default_factory=dict)
    aggregation_paths: dict[str, str] = field(default_factory=dict)
    review_required: bool = False
    selected_story_candidate_id: str | None = None
    selected_claim_candidate_ids: list[str] = field(default_factory=list)
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntakeState":
        return cls(**payload)


QUESTION_BANK: list[IntakeQuestion] = [
    IntakeQuestion(
        key="problem_statement",
        prompt="이 논문이 해결하려는 핵심 문제를 2~4문장으로 설명해 주세요.",
        required=False,
        help_text="무엇이 어렵고 왜 중요한지 적습니다.",
    ),
    IntakeQuestion(
        key="method_summary",
        prompt="실제로 수행한 실험의 방법론을 한 단락으로 설명해 주세요.",
        required=True,
        help_text="사용자가 반드시 직접 제공해야 하는 최소 핵심 정보 중 하나입니다.",
    ),
    IntakeQuestion(
        key="core_contributions",
        prompt="핵심 기여 1~3개를 bullet 또는 쉼표로 적어 주세요.",
        required=False,
        help_text="없으면 시스템이 candidate를 제안하지만 최종 확정은 사용자 승인 대상입니다.",
    ),
    IntakeQuestion(
        key="target_user_or_setting",
        prompt="이 연구의 대상 사용자, 환경, 적용 도메인이 있으면 적어 주세요.",
        required=False,
        help_text="없으면 비워둘 수 있습니다.",
    ),
    IntakeQuestion(
        key="datasets_or_benchmarks",
        prompt="사용한 데이터셋, 벤치마크, 평가 환경을 적어 주세요.",
        required=False,
        help_text="정확하지 않으면 아는 범위만 적고 모르는 것은 unknown으로 둡니다.",
    ),
    IntakeQuestion(
        key="experiments_ran",
        prompt="실제로 수행한 실험을 bullet로 적어 주세요.",
        required=False,
        help_text="방법론을 더 구조화하는 데 도움이 되며, 하지 않은 실험은 쓰지 않습니다.",
    ),
    IntakeQuestion(
        key="key_results",
        prompt="확정된 결과와 수치를 적어 주세요.",
        required=True,
        help_text="사용자가 반드시 직접 제공해야 하는 최소 핵심 정보 중 하나입니다.",
    ),
    IntakeQuestion(
        key="baselines",
        prompt="비교한 베이스라인이나 관련 경쟁 방법을 적어 주세요.",
        required=False,
        help_text="정확한 이름이 없으면 비워둘 수 있고, 시스템이 later suggestion을 만들 수 있습니다.",
    ),
    IntakeQuestion(
        key="figure_story",
        prompt="그림/도표로 보여줘야 할 핵심 스토리를 적어 주세요.",
        required=False,
        help_text="선호가 있다면 적고, 없으면 시스템이 후보를 제안합니다.",
    ),
    IntakeQuestion(
        key="venue",
        prompt="목표 venue가 있으면 적어 주세요.",
        required=False,
        help_text="예: ICLR, NeurIPS, ACL",
    ),
    IntakeQuestion(
        key="page_limit",
        prompt="페이지 제한이 있으면 숫자로 적어 주세요.",
        required=False,
        help_text="예: 8, 12",
    ),
    IntakeQuestion(
        key="cutoff_date",
        prompt="관련연구 cutoff 날짜가 있으면 YYYY-MM-DD 형식으로 적어 주세요.",
        required=False,
        help_text="예: 2024-11-01",
    ),
    IntakeQuestion(
        key="template_path",
        prompt="기존 LaTeX 템플릿 경로가 있으면 적어 주세요.",
        required=False,
        help_text="없으면 기본 템플릿이 복사됩니다.",
    ),
    IntakeQuestion(
        key="figures_dir",
        prompt="기존 figure 디렉터리 경로가 있으면 적어 주세요.",
        required=False,
        help_text="없으면 figure 디렉터리는 비워 둡니다.",
    ),
    IntakeQuestion(
        key="evidence_paths",
        prompt="추가로 참고할 로그/노트/실험 결과 파일 또는 디렉터리 경로가 있으면 적어 주세요.",
        required=False,
        help_text="콤마, 줄바꿈, 리스트 형태 모두 허용합니다.",
    ),
    IntakeQuestion(
        key="open_questions",
        prompt="아직 확실하지 않거나 나중에 확인해야 할 점이 있으면 적어 주세요.",
        required=False,
        help_text="불확실성은 숨기지 말고 적습니다.",
    ),
]

QUESTION_INDEX = {question.key: question for question in QUESTION_BANK}
REQUIRED_KEYS = [question.key for question in QUESTION_BANK if question.required]
UNCERTAINTY_TOKENS = ("unknown", "todo", "tbd", "unclear", "모름", "미정", "불명", "확인 필요")
COMPARATIVE_TOKENS = ("better", "improv", "outperform", "sota", "state of the art", "우수", "향상", "개선", "높았", "낮았")


def intakes_root(cwd: str | Path | None = None) -> Path:
    path = runtime_root(cwd) / "intake"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validated_intake_id(intake_id: str) -> str:
    if not INTAKE_ID_RE.fullmatch(intake_id):
        raise ValueError(f"Invalid intake_id: {intake_id}")
    return intake_id


def intake_dir(cwd: str | Path | None = None, intake_id: str | None = None) -> Path:
    if intake_id is None:
        intake_id = get_current_intake_id(cwd)
    intake_id = _validated_intake_id(intake_id)
    root = intakes_root(cwd)
    path = (root / intake_id).resolve()
    if not _is_within(path, root.resolve()):
        raise ValueError(f"Invalid intake path for id: {intake_id}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def intake_session_path(cwd: str | Path | None = None, intake_id: str | None = None) -> Path:
    return intake_dir(cwd, intake_id) / "session.json"


def set_current_intake(cwd: str | Path | None, intake_id: str) -> None:
    (intakes_root(cwd) / INTAKE_CURRENT_FILE).write_text(_validated_intake_id(intake_id) + "\n", encoding="utf-8")


def get_current_intake_id(cwd: str | Path | None = None) -> str:
    path = intakes_root(cwd) / INTAKE_CURRENT_FILE
    if not path.exists():
        raise FileNotFoundError("No current intake. Run `start_intake` first.")
    return _validated_intake_id(path.read_text(encoding="utf-8").strip())


def save_intake(cwd: str | Path | None, state: IntakeState) -> Path:
    state.updated_at = utc_now_iso()
    path = intake_session_path(cwd, state.intake_id)
    path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_intake(cwd: str | Path | None, intake_id: str | None = None) -> IntakeState:
    path = intake_session_path(cwd, intake_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing intake session file: {path}")
    return IntakeState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _normalize_list(text: str) -> list[str]:
    if text is None:
        return []
    if isinstance(text, list):
        return [str(item).strip() for item in text if str(item).strip()]
    text = str(text)
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        for prefix in ("- ", "* ", "• "):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
                break
        lines.append(line)
    if len(lines) > 1:
        return lines
    if "," in text:
        items = [item.strip() for item in text.split(",") if item.strip()]
        if len(items) > 1:
            return items
    return [text.strip()] if text.strip() else []


def normalize_answer(key: str, answer: Any) -> Any:
    if isinstance(answer, list):
        values = [str(item).strip() for item in answer if str(item).strip()]
        return values if key in {"core_contributions", "experiments_ran", "key_results", "baselines", "open_questions", "evidence_paths"} else "\n".join(values)
    if isinstance(answer, (int, float)):
        return answer
    if answer is None:
        return ""
    text = str(answer).strip()
    if key in {"core_contributions", "experiments_ran", "key_results", "baselines", "open_questions", "evidence_paths"}:
        return _normalize_list(text)
    if key == "page_limit":
        try:
            return int(text)
        except ValueError:
            return text
    return text


def _answer_is_missing(answer: Any) -> bool:
    if answer is None:
        return True
    if isinstance(answer, str):
        return not answer.strip()
    if isinstance(answer, list):
        return len([item for item in answer if str(item).strip()]) == 0
    return False


def _derive_open_questions(answers: dict[str, Any]) -> list[str]:
    derived: list[str] = []
    for key in REQUIRED_KEYS:
        if _answer_is_missing(answers.get(key)):
            derived.append(f"Required intake slot `{key}` is still missing.")
    for key, answer in answers.items():
        haystack = json.dumps(answer, ensure_ascii=False).lower()
        if any(token in haystack for token in UNCERTAINTY_TOKENS):
            derived.append(f"`{key}` still contains uncertainty markers that should be verified before final paper claims.")
    extra = answers.get("open_questions")
    if isinstance(extra, list):
        derived.extend(item for item in extra if item not in derived)
    elif isinstance(extra, str) and extra.strip():
        derived.append(extra.strip())
    return derived


def _followup(code: str, key: str, prompt: str, rationale: str, *, priority: int = 50) -> dict[str, Any]:
    return {
        "code": code,
        "key": key,
        "prompt": prompt,
        "rationale": rationale,
        "priority": priority,
    }


def _contains_any(answer: Any, needles: tuple[str, ...]) -> bool:
    haystack = json.dumps(answer, ensure_ascii=False).lower()
    return any(token in haystack for token in needles)


def _has_numeric_signal(answer: Any) -> bool:
    return bool(re.search(r"\d", json.dumps(answer, ensure_ascii=False)))


def _derive_adaptive_followups(answers: dict[str, Any]) -> list[dict[str, Any]]:
    followups: list[dict[str, Any]] = []
    if _answer_is_missing(answers.get("problem_statement")) and not _answer_is_missing(answers.get("method_summary")):
        followups.append(
            _followup(
                "problem-needed",
                "problem_statement",
                "이 실험이 겨냥하는 문제나 pain point를 한두 문장으로 적어 주세요. 없으면 시스템이 later candidate로 추론하지만, 있으면 훨씬 도움이 됩니다.",
                "문제 정의가 없으면 story framing이 약해집니다.",
                priority=75,
            )
        )
    if not _answer_is_missing(answers.get("experiments_ran")) and _answer_is_missing(answers.get("datasets_or_benchmarks")):
        followups.append(
            _followup(
                "datasets-needed",
                "datasets_or_benchmarks",
                "실험은 있다고 했는데, 어떤 데이터셋/벤치마크/평가 환경에서 돌렸는지 적어 주세요.",
                "실험 설명이 있지만 평가 환경이 비어 있습니다.",
                priority=95,
            )
        )
    key_results = answers.get("key_results")
    if not _answer_is_missing(key_results) and not _has_numeric_signal(key_results) and not _contains_any(key_results, UNCERTAINTY_TOKENS):
        followups.append(
            _followup(
                "result-numbers",
                "key_results",
                "결과는 적어 주셨는데 숫자/측정값이 보이지 않습니다. 확정된 수치가 있으면 추가해 주세요. 없으면 unknown이라고 명시해 주세요.",
                "결과 항목이 정성적 설명만 포함하고 있습니다.",
                priority=90,
            )
        )
    if _contains_any(key_results, COMPARATIVE_TOKENS) and _answer_is_missing(answers.get("baselines")):
        followups.append(
            _followup(
                "comparative-baselines",
                "baselines",
                "비교/개선 표현이 있는데 베이스라인 정보가 없습니다. 정확한 비교 대상 이름을 적어 주세요.",
                "비교 주장에는 grounding될 baseline 이름이 필요합니다.",
                priority=92,
            )
        )
    if not _answer_is_missing(answers.get("method_summary")) and _answer_is_missing(answers.get("figure_story")):
        followups.append(
            _followup(
                "figure-story",
                "figure_story",
                "방법 설명은 있는데 어떤 그림/도표로 설명할지 아직 없습니다. 시스템 개요, 성능 비교, ablation 중 무엇이 핵심인지 적어 주세요.",
                "초기 plot plan 생성을 위해 figure story가 필요합니다.",
                priority=80,
            )
        )
    if _answer_is_missing(answers.get("evidence_paths")) and _answer_is_missing(answers.get("baselines")) and _answer_is_missing(answers.get("problem_statement")):
        followups.append(
            _followup(
                "supporting-materials",
                "evidence_paths",
                "추가 로그/노트/실험 결과 파일이나 폴더가 있다면 경로를 알려 주세요. 시스템이 거기서 더 많은 단서를 끌어올 수 있습니다.",
                "현재 입력만으로는 prior-work seed와 story framing에 필요한 보조 증거가 부족할 수 있습니다.",
                priority=72,
            )
        )
    if not _answer_is_missing(answers.get("venue")) and _answer_is_missing(answers.get("page_limit")):
        followups.append(
            _followup(
                "page-limit",
                "page_limit",
                "목표 venue가 있다면 페이지 제한도 아는 범위에서 적어 주세요.",
                "후속 템플릿/section planning에 page limit이 유용합니다.",
                priority=35,
            )
        )
    if _contains_any(answers, UNCERTAINTY_TOKENS) and _answer_is_missing(answers.get("open_questions")):
        followups.append(
            _followup(
                "capture-uncertainty",
                "open_questions",
                "답변 안에 unknown/TODO 성격의 정보가 있습니다. 따로 확인이 필요한 open question을 정리해 주세요.",
                "불확실성을 숨기지 않고 downstream artifact에 남겨야 합니다.",
                priority=70,
            )
        )
    return sorted(followups, key=lambda item: (-int(item["priority"]), item["code"]))


def _ambiguity_score(answers: dict[str, Any], followups: list[dict[str, Any]], open_questions: list[str]) -> float:
    required_answered = sum(0 if _answer_is_missing(answers.get(key)) else 1 for key in REQUIRED_KEYS)
    required_ratio = required_answered / max(1, len(REQUIRED_KEYS))
    uncertainty_penalty = min(0.35, 0.05 * len(open_questions))
    followup_penalty = min(0.35, 0.07 * len(followups))
    score = 1.0 - required_ratio + uncertainty_penalty + followup_penalty
    return max(0.0, min(1.0, round(score, 3)))


def _next_question(answers: dict[str, Any], *, required_only: bool) -> IntakeQuestion | None:
    for question in QUESTION_BANK:
        if required_only and not question.required:
            continue
        if _answer_is_missing(answers.get(question.key)):
            return question
    return None


def _load_json_if_exists(path_text: str | None) -> Any | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def _load_existing_aggregation(aggregation_paths: dict[str, str]) -> dict[str, Any] | None:
    required = [
        "evidence_registry_path",
        "story_candidates_path",
        "claim_candidates_path",
        "missing_evidence_suggestions_path",
        "prior_work_seeds_path",
    ]
    if not aggregation_paths or any(not aggregation_paths.get(key) for key in required):
        return None
    payload = {
        "evidence_registry": _load_json_if_exists(aggregation_paths.get("evidence_registry_path")),
        "discovered_sources": (_load_json_if_exists(aggregation_paths.get("source_inventory_path")) or {}).get("sources", []),
        "story_candidates": _load_json_if_exists(aggregation_paths.get("story_candidates_path")) or [],
        "claim_candidates": _load_json_if_exists(aggregation_paths.get("claim_candidates_path")) or [],
        "missing_evidence_suggestions": _load_json_if_exists(aggregation_paths.get("missing_evidence_suggestions_path")) or [],
        "prior_work_seeds": (_load_json_if_exists(aggregation_paths.get("prior_work_seeds_path")) or {}).get("queries", []),
        "prior_work_candidates": _load_json_if_exists(aggregation_paths.get("prior_work_candidates_path")) or [],
        "grounded_gap_suggestions": _load_json_if_exists(aggregation_paths.get("grounded_gap_suggestions_path")) or [],
        "warnings": (_load_json_if_exists(aggregation_paths.get("warnings_path")) or {}).get("warnings", []),
        "artifact_paths": aggregation_paths,
    }
    if payload["evidence_registry"] is None:
        return None
    return payload


def _status_payload(state: IntakeState, cwd: str | Path | None) -> dict[str, Any]:
    required_answered = sum(0 if _answer_is_missing(state.answers.get(key)) else 1 for key in REQUIRED_KEYS)
    next_item: dict[str, Any] | None = None
    required_question = _next_question(state.answers, required_only=True)
    optional_question = _next_question(state.answers, required_only=False)
    if required_question is not None:
        next_item = {
            "key": required_question.key,
            "prompt": required_question.prompt,
            "required": required_question.required,
            "help_text": required_question.help_text,
            "source": "required",
        }
    elif state.adaptive_followups:
        next_item = {**state.adaptive_followups[0], "required": False, "help_text": state.adaptive_followups[0]["rationale"], "source": "adaptive"}
    elif optional_question is not None:
        next_item = {
            "key": optional_question.key,
            "prompt": optional_question.prompt,
            "required": optional_question.required,
            "help_text": optional_question.help_text,
            "source": "optional",
        }
    generated = state.generated_paths.copy()
    if state.session_id:
        generated["session_id"] = state.session_id
    story_candidates = _load_json_if_exists(state.aggregation_paths.get("story_candidates_path"))
    claim_candidates = _load_json_if_exists(state.aggregation_paths.get("claim_candidates_path"))
    missing_suggestions = _load_json_if_exists(state.aggregation_paths.get("missing_evidence_suggestions_path"))
    prior_work_candidates = _load_json_if_exists(state.aggregation_paths.get("prior_work_candidates_path"))
    warnings = (_load_json_if_exists(state.aggregation_paths.get("warnings_path")) or {}).get("warnings", [])
    return {
        "intake_id": state.intake_id,
        "status": state.status,
        "answers": state.answers,
        "missing_required_keys": [key for key in REQUIRED_KEYS if _answer_is_missing(state.answers.get(key))],
        "completion": {
            "required_answered": required_answered,
            "required_total": len(REQUIRED_KEYS),
            "answered_total": sum(0 if _answer_is_missing(state.answers.get(question.key)) else 1 for question in QUESTION_BANK),
            "question_total": len(QUESTION_BANK),
            "ambiguity_score": state.ambiguity_score,
        },
        "next_question": next_item,
        "open_questions": state.open_questions,
        "adaptive_followups": state.adaptive_followups,
        "review_required": state.review_required,
        "selected_story_candidate_id": state.selected_story_candidate_id,
        "selected_claim_candidate_ids": state.selected_claim_candidate_ids,
        "aggregation_paths": state.aggregation_paths,
        "story_candidates": story_candidates or [],
        "claim_candidates": claim_candidates or [],
        "missing_evidence_suggestions": missing_suggestions or [],
        "prior_work_candidates": prior_work_candidates or [],
        "warnings": warnings or [],
        "notes": state.notes,
        "generated_paths": generated,
        "paths": {
            "session_json": str(intake_session_path(cwd, state.intake_id)),
            "answers_json": str(intake_dir(cwd, state.intake_id) / "answers.json"),
            "open_questions_json": str(intake_dir(cwd, state.intake_id) / "open_questions.json"),
        },
    }


def start_intake(
    cwd: str | Path | None,
    *,
    seed_answers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intake_id = f"intake-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()
    answers = {key: normalize_answer(key, value) for key, value in (seed_answers or {}).items() if key in QUESTION_INDEX}
    open_questions = _derive_open_questions(answers)
    adaptive_followups = _derive_adaptive_followups(answers)
    state = IntakeState(
        intake_id=intake_id,
        created_at=now,
        updated_at=now,
        status="ready" if _next_question(answers, required_only=True) is None else "collecting",
        answers=answers,
        open_questions=open_questions,
        adaptive_followups=adaptive_followups,
        ambiguity_score=_ambiguity_score(answers, adaptive_followups, open_questions),
        notes=["Guided intake started."],
    )
    intake_directory = intake_dir(cwd, intake_id)
    intake_directory.mkdir(parents=True, exist_ok=True)
    write_json(intake_directory / "answers.json", state.answers)
    write_json(intake_directory / "open_questions.json", state.open_questions)
    save_intake(cwd, state)
    set_current_intake(cwd, intake_id)
    return _status_payload(state, cwd)


def answer_intake_question(
    cwd: str | Path | None,
    *,
    key: str | None = None,
    answer: Any | None = None,
    answers: dict[str, Any] | None = None,
    intake_id: str | None = None,
) -> dict[str, Any]:
    state = load_intake(cwd, intake_id)
    updates = dict(answers or {})
    if key:
        updates[key] = answer
    if not updates:
        raise ValueError("Provide `key` + `answer` or an `answers` object.")
    unknown = sorted(set(updates) - set(QUESTION_INDEX))
    if unknown:
        raise ValueError(f"Unknown intake keys: {', '.join(unknown)}")
    for update_key, update_value in updates.items():
        state.answers[update_key] = normalize_answer(update_key, update_value)
    state.open_questions = _derive_open_questions(state.answers)
    state.adaptive_followups = _derive_adaptive_followups(state.answers)
    state.ambiguity_score = _ambiguity_score(state.answers, state.adaptive_followups, state.open_questions)
    state.status = "ready" if _next_question(state.answers, required_only=True) is None else "collecting"
    state.notes.append(f"Updated intake answers: {', '.join(sorted(updates))}.")
    directory = intake_dir(cwd, state.intake_id)
    write_json(directory / "answers.json", state.answers)
    write_json(directory / "open_questions.json", state.open_questions)
    save_intake(cwd, state)
    set_current_intake(cwd, state.intake_id)
    return _status_payload(state, cwd)


def get_intake_status(cwd: str | Path | None, *, intake_id: str | None = None) -> dict[str, Any]:
    return _status_payload(load_intake(cwd, intake_id), cwd)


def get_intake_review(cwd: str | Path | None, *, intake_id: str | None = None) -> dict[str, Any]:
    payload = get_intake_status(cwd, intake_id=intake_id)
    return {
        "intake_id": payload["intake_id"],
        "status": payload["status"],
        "review_required": payload["review_required"],
        "story_candidates": payload["story_candidates"],
        "claim_candidates": payload["claim_candidates"],
        "missing_evidence_suggestions": payload["missing_evidence_suggestions"],
        "prior_work_candidates": payload["prior_work_candidates"],
        "aggregation_paths": payload["aggregation_paths"],
        "selected_story_candidate_id": payload["selected_story_candidate_id"],
        "selected_claim_candidate_ids": payload["selected_claim_candidate_ids"],
    }


def _render_guidelines_markdown(answers: dict[str, Any]) -> str:
    venue = answers.get("venue", "unknown")
    page_limit = answers.get("page_limit", "unknown")
    cutoff_date = answers.get("cutoff_date", "unknown")
    return (
        "# Conference Guidelines\n\n"
        f"- Target venue: {venue}\n"
        f"- Page limit: {page_limit}\n"
        f"- Related-work cutoff date: {cutoff_date}\n"
        "- Do not cite papers outside the verified citation registry.\n"
        "- Do not invent unsupported experimental claims.\n"
        "- Preserve uncertainty as open questions instead of fabricating facts.\n"
    )


def _resolve_user_path(
    path_value: str | Path,
    *,
    cwd: str | Path | None,
    label: str,
    allow_outside_workspace: bool,
    expect_directory: bool | None = None,
    must_exist: bool = True,
) -> Path:
    root = project_root(cwd)
    raw = Path(path_value)
    resolved = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    if not allow_outside_workspace and not _is_within(resolved, root):
        raise ValueError(f"{label} must stay inside the workspace unless allow_outside_workspace is enabled: {resolved}")
    if must_exist and expect_directory is True and not resolved.is_dir():
        raise NotADirectoryError(f"{label} is not a directory: {resolved}")
    if must_exist and expect_directory is False and not resolved.is_file():
        raise FileNotFoundError(f"{label} is not a file: {resolved}")
    return resolved


def _copy_default_template(destination: Path) -> str:
    source = project_root(__file__).resolve().parent.parent / "examples" / "minimal" / "template.tex"
    if not source.exists():
        raise FileNotFoundError(f"Default template not found: {source}")
    shutil.copy2(source, destination)
    return str(destination)


def _copy_optional_figures(source_dir: str | None, destination_dir: Path) -> str | None:
    if not source_dir:
        return None
    source = Path(source_dir).resolve()
    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source, destination_dir)
    return str(destination_dir)


def _normalize_candidate_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[\n,;]+", str(value)) if item.strip()]


def finalize_intake(
    cwd: str | Path | None,
    *,
    intake_id: str | None = None,
    output_dir: str | Path | None = None,
    template_path: str | None = None,
    figures_dir: str | None = None,
    initialize_session: bool = True,
    allow_overwrite: bool = False,
    allow_outside_workspace: bool = False,
    selected_story_candidate_id: str | None = None,
    selected_claim_candidate_ids: Any | None = None,
) -> dict[str, Any]:
    state = load_intake(cwd, intake_id)
    missing = [key for key in REQUIRED_KEYS if _answer_is_missing(state.answers.get(key))]
    if missing:
        raise ValueError(f"Cannot finalize intake; missing required answers: {', '.join(missing)}")

    destination_root = (
        _resolve_user_path(
            output_dir,
            cwd=cwd,
            label="output_dir",
            allow_outside_workspace=allow_outside_workspace,
            expect_directory=True,
            must_exist=False,
        )
        if output_dir
        else intake_dir(cwd, state.intake_id) / "generated"
    )
    destination_root.mkdir(parents=True, exist_ok=True)
    plan_path = destination_root / "input-plan.json"
    idea_path = destination_root / "idea.md"
    experimental_log_path = destination_root / "experimental_log.md"
    guidelines_path = destination_root / "conference_guidelines.md"
    template_output_path = destination_root / "template.tex"
    figures_output_dir = destination_root / "figures"
    aggregation_output_dir = destination_root / "aggregation"

    managed_paths = [idea_path, experimental_log_path, guidelines_path, template_output_path, plan_path]
    if not allow_overwrite:
        existing = [str(path) for path in managed_paths if path.exists()]
        if existing:
            raise FileExistsError(f"Refusing to overwrite existing generated artifacts: {', '.join(existing)}")

    aggregation = _load_existing_aggregation(state.aggregation_paths)
    if aggregation is None:
        aggregation = aggregate_intake(
            cwd,
            answers=state.answers,
            output_dir=aggregation_output_dir,
            allow_outside_workspace=allow_outside_workspace,
        )
    state.aggregation_paths = aggregation["artifact_paths"]
    story_candidates = aggregation["story_candidates"]
    claim_candidates = aggregation["claim_candidates"]
    missing_suggestions = aggregation["missing_evidence_suggestions"]
    evidence_registry = aggregation["evidence_registry"]
    selected_claim_ids = _normalize_candidate_ids(selected_claim_candidate_ids)
    provided_contributions = _normalize_list(state.answers.get("core_contributions"))
    user_direction_context = bool(str(state.answers.get("problem_statement", "")).strip() or _normalize_list(state.answers.get("figure_story")))
    user_already_set_direction = bool(provided_contributions) and user_direction_context
    selected_story: dict[str, Any] | None = None
    selected_claims: list[dict[str, Any]] = []

    if selected_story_candidate_id:
        selected_story = next((item for item in story_candidates if item["candidate_id"] == selected_story_candidate_id), None)
        if selected_story is None:
            raise ValueError(f"Unknown story candidate id: {selected_story_candidate_id}")
    if selected_claim_ids:
        selected_claims = [item for item in claim_candidates if item["candidate_id"] in selected_claim_ids]
        if len(selected_claims) != len(selected_claim_ids):
            missing_claims = sorted(set(selected_claim_ids) - {item["candidate_id"] for item in selected_claims})
            raise ValueError(f"Unknown claim candidate id(s): {', '.join(missing_claims)}")

    review_required = not user_already_set_direction and (selected_story is None or not selected_claim_ids)
    if review_required:
        state.review_required = True
        state.status = "review_required"
        state.selected_story_candidate_id = selected_story_candidate_id
        state.selected_claim_candidate_ids = selected_claim_ids
        if selected_story is None:
            state.notes.append("Aggregation produced story/claim candidates; user review is required before thesis-level direction is locked in.")
        else:
            state.notes.append("Story direction was selected, but contribution claim approval is still required before finalization.")
        directory = intake_dir(cwd, state.intake_id)
        write_json(directory / "answers.json", state.answers)
        write_json(directory / "open_questions.json", state.open_questions)
        save_intake(cwd, state)
        set_current_intake(cwd, state.intake_id)
        return _status_payload(state, cwd)

    write_text(idea_path, render_idea_from_selection(state.answers, selected_story, selected_claims))
    write_text(experimental_log_path, render_experimental_log_from_registry(evidence_registry, state.answers, missing_suggestions))
    write_text(guidelines_path, _render_guidelines_markdown(state.answers))

    resolved_template = template_path or state.answers.get("template_path")
    if resolved_template:
        resolved_template_path = _resolve_user_path(
            resolved_template,
            cwd=cwd,
            label="template_path",
            allow_outside_workspace=allow_outside_workspace,
            expect_directory=False,
        )
        shutil.copy2(resolved_template_path, template_output_path)
    else:
        _copy_default_template(template_output_path)

    resolved_figures_dir = figures_dir or state.answers.get("figures_dir")
    if resolved_figures_dir:
        resolved_figures_dir = str(
            _resolve_user_path(
                resolved_figures_dir,
                cwd=cwd,
                label="figures_dir",
                allow_outside_workspace=allow_outside_workspace,
                expect_directory=True,
            )
        )
    copied_figures_dir = _copy_optional_figures(resolved_figures_dir, figures_output_dir) if resolved_figures_dir else None

    input_plan = {
        "generated_from_intake_id": state.intake_id,
        "required_keys": REQUIRED_KEYS,
        "answers": state.answers,
        "open_questions": state.open_questions,
        "aggregation_artifacts": state.aggregation_paths,
        "selected_story_candidate_id": selected_story_candidate_id,
        "selected_claim_candidate_ids": selected_claim_ids,
        "paths": {
            "idea": str(idea_path),
            "experimental_log": str(experimental_log_path),
            "conference_guidelines": str(guidelines_path),
            "template": str(template_output_path),
            "figures_dir": copied_figures_dir,
        },
    }
    write_json(plan_path, input_plan)

    state.generated_paths = {
        "idea_path": str(idea_path),
        "experimental_log_path": str(experimental_log_path),
        "guidelines_path": str(guidelines_path),
        "template_path": str(template_output_path),
        "figures_dir": copied_figures_dir or "",
        "input_plan_path": str(plan_path),
    }
    state.review_required = False
    state.selected_story_candidate_id = selected_story_candidate_id
    state.selected_claim_candidate_ids = selected_claim_ids
    state.status = "finalized"
    state.notes.append("Generated intake artifacts.")

    if initialize_session:
        created = create_session(
            cwd,
            InputBundle(
                idea_path=str(idea_path),
                experimental_log_path=str(experimental_log_path),
                template_path=str(template_output_path),
                guidelines_path=str(guidelines_path),
                figures_dir=copied_figures_dir,
                cutoff_date=str(state.answers.get("cutoff_date")).strip() if state.answers.get("cutoff_date") else None,
                venue=str(state.answers.get("venue")).strip() if state.answers.get("venue") else None,
                page_limit=state.answers.get("page_limit") if isinstance(state.answers.get("page_limit"), int) else None,
            ),
            allow_outside_workspace=allow_outside_workspace,
        )
        state.session_id = created.session_id
        state.notes.append(f"Initialized PaperOrchestra session: {created.session_id}.")

    directory = intake_dir(cwd, state.intake_id)
    write_json(directory / "answers.json", state.answers)
    write_json(directory / "open_questions.json", state.open_questions)
    save_intake(cwd, state)
    set_current_intake(cwd, state.intake_id)
    return _status_payload(state, cwd)


def research_prior_work(
    cwd: str | Path | None,
    *,
    intake_id: str | None = None,
    mode: str = "live",
    max_per_seed: int = 2,
    allow_outside_workspace: bool = False,
) -> dict[str, Any]:
    state = load_intake(cwd, intake_id)
    aggregation_output_dir = intake_dir(cwd, state.intake_id) / "aggregation"
    payload = enrich_with_prior_work(
        cwd,
        answers=state.answers,
        output_dir=aggregation_output_dir,
        mode=mode,
        allow_outside_workspace=allow_outside_workspace,
        max_per_seed=max_per_seed,
    )
    state.aggregation_paths = payload["artifact_paths"]
    state.review_required = True
    state.status = "review_required"
    state.notes.append(f"Prior-work enrichment completed in {mode} mode.")
    directory = intake_dir(cwd, state.intake_id)
    write_json(directory / "answers.json", state.answers)
    write_json(directory / "open_questions.json", state.open_questions)
    save_intake(cwd, state)
    set_current_intake(cwd, state.intake_id)
    return _status_payload(state, cwd)


def approve_intake_direction(
    cwd: str | Path | None,
    *,
    intake_id: str | None = None,
    story_candidate_id: str,
    claim_candidate_ids: Any,
    output_dir: str | Path | None = None,
    template_path: str | None = None,
    figures_dir: str | None = None,
    initialize_session: bool = True,
    allow_overwrite: bool = False,
    allow_outside_workspace: bool = False,
) -> dict[str, Any]:
    return finalize_intake(
        cwd,
        intake_id=intake_id,
        output_dir=output_dir,
        template_path=template_path,
        figures_dir=figures_dir,
        initialize_session=initialize_session,
        allow_overwrite=allow_overwrite,
        allow_outside_workspace=allow_outside_workspace,
        selected_story_candidate_id=story_candidate_id,
        selected_claim_candidate_ids=claim_candidate_ids,
    )
