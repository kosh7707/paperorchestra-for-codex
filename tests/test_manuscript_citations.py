from __future__ import annotations

from paperorchestra.manuscript import citations


def test_extract_citation_keys_handles_common_cite_commands_and_ignores_nocite() -> None:
    latex = r"Prior work \citet[see][p. 2]{Smith2024, Jones2025}; ignore \nocite{Hidden2020}."

    assert citations.extract_citation_keys(latex) == {"Smith2024", "Jones2025"}


def test_canonicalize_citation_keys_replaces_unambiguous_generated_aliases() -> None:
    latex = r"We compare against \cite{SN2024, Other2020}."
    citation_map = {
        "SiftingNoise2024": {"title": "Sifting the Noise"},
        "Other2020": {"title": "Other"},
    }

    repaired, replacements = citations.canonicalize_citation_keys(latex, citation_map)

    assert repaired == r"We compare against \cite{SiftingNoise2024, Other2020}."
    assert replacements == {"SN2024": "SiftingNoise2024"}


def test_canonical_citation_map_collapses_alias_entries_to_canonical_keys() -> None:
    citation_map = {
        "Alias2024": {"canonical_bibtex_key": "Real2024", "title": "Alias"},
        "Real2024": {"title": "Real"},
    }

    assert citations.canonical_citation_keys(citation_map) == ["Real2024"]
    assert citations.allowed_citation_keys(citation_map) == {"Alias2024", "Real2024"}
