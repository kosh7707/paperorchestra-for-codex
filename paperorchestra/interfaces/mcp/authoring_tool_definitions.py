from __future__ import annotations

from paperorchestra.interfaces.mcp.tool_schema import JSON, _schema

AUTHORING_TOOLS: list[JSON] = [
    {
        "name": "orchestrate",
        "description": "Run the orchestrator until the next bounded action or stop.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "material": {"type": "string"},
                "execute_local": {"type": "boolean"},
                "plan_full_loop": {"type": "boolean"},
                "execute_omx": {"type": "boolean"},
                "write_evidence": {"type": "boolean"},
                "evidence_output": {"type": "string"},
            }
        ),
    },
    {
        "name": "research_prior_work",
        "description": "Generate/import a prior-work seed using the configured provider, including web-capable provider commands.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "output": {"type": "string"},
                "paper": {"type": "string"},
                "artifact_repo": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "source": {"type": "string"},
                "import_seed": {"type": "boolean"},
                "require_complete_metadata": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "import_prior_work",
        "description": "Import a curated prior-work seed file.",
        "inputSchema": _schema(
            {"cwd": {"type": "string"}, "seed_file": {"type": "string"}, "source": {"type": "string"}, "require_complete_metadata": {"type": "boolean"}},
            ["seed_file"],
        ),
    },
    {
        "name": "write_sections",
        "description": "Draft or rewrite manuscript sections.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "only_sections": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "output_path": {"type": "string"},
                "claim_safe": {"type": "boolean"},
                "bypass_plan_gate": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "critique",
        "description": "Run whole-paper, section, and citation critics and produce revision suggestions.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "source_paper": {"type": "string"},
                "output_dir": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "citation_evidence_mode": {"type": "string", "enum": ["heuristic", "model", "web", "source"]},
            }
        ),
    },
]
