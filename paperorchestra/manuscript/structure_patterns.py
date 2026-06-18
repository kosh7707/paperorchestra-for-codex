from __future__ import annotations

import re

SECTION_COMMAND_RE = re.compile(r"\\section\{([^}]+)\}")
SUBSECTION_COMMAND_RE = re.compile(r"\\subsection\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
