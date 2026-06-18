from __future__ import annotations

import re

from paperorchestra.domains import get_domain

HIGH_RISK_CLAIM_RE = get_domain().high_risk_claim_re
LIMITATION_SCOPE_RE = re.compile(
    r"\b("
    r"do not claim|does not claim|does not make (?:stronger )?(?:analytical )?claims?|not claim|limited to|only|scope|limitations?|omits?|not end-to-end|we do not|we leave|future work|"
    r"do not support claims?|does not support claims?|do not support (?:any )?claim|does not support (?:any )?claim|"
    r"does not guarantee|do not guarantee|no guarantee|cannot guarantee|"
    r"contains no (?:external )?(?:dataset|benchmark|evaluation|experiment)|"
    r"includes no (?:external )?(?:dataset|benchmark|evaluation|experiment)|"
    r"reports no (?:standard )?(?:benchmark|metric|runtime|comparison)|"
    r"no standard benchmark|no optimizer setting|no model-architecture comparison|no reported runtime profile|"
    r"outside (?:the )?(?:present )?scope|beyond (?:the )?(?:present )?scope|"
    r"remain(?:s)? within the stated assumptions|bounded by the stated assumptions|"
    r"stronger analytical claims require|separate argument beyond|"
    r"should therefore be read within"
    r")\b",
    re.IGNORECASE,
)
SECURITY_CLAIM_RE = get_domain().security_claim_re
BENCHMARK_CLAIM_RE = get_domain().benchmark_claim_re
PROOF_INTERNAL_SCOPE_RE = re.compile(
    r"\b(we now examine|conditioned game|proof proceeds|combining the game hops|union bound over|the proof proceeds)\b",
    re.IGNORECASE,
)
PAPER_SPECIFIC_SELF_CLAIM_RE = re.compile(
    r"\b("
    r"this\s+paper|we\s+(?:prove|show|construct|propose|implement|measure|report)|"
    r"our\s+(?:construction|scheme|method|proof|theorem|benchmark|result|evaluation|implementation)|"
    r"(?:proposed|presented|evaluated)\s+(?:construction|scheme|method|proof|benchmark|result)"
    r")\b",
    re.IGNORECASE,
)
STRUCTURAL_REFERENCE_RE = re.compile(
    r"^(?:[A-Za-z][^.]{0,80}\.\s+)?(?:Table|Figure|Listing|Algorithm)~?\s*(?:\S+\s+)?"
    r"(?:reports?|shows?|presents?|summari[sz]es|lists?|contains?|defines?|gives?)\b",
    re.IGNORECASE,
)
STRUCTURAL_STRONG_CLAIM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:x|×|%|ms|s|jobs/s|qps)|faster|slower|outperform|better than|stronger|weaker|novel|first|secure|guarantee|baseline)\b",
    re.IGNORECASE,
)
