from __future__ import annotations

import unittest

from paperorchestra.reviews.citation_rendered_references import (
    _duplicate_reference_identity_groups,
    _reference_identity_label,
)


class RenderedReferenceAuditTest(unittest.TestCase):
    def test_reference_identity_hash_drops_sensitive_url_tokens(self) -> None:
        with_secret = _reference_identity_label({"url": "https://example.test/paper?id=1&token=secret"})
        without_secret = _reference_identity_label({"url": "https://example.test/paper?id=1"})

        self.assertEqual(with_secret, without_secret)
        self.assertTrue(with_secret.startswith("url:"))

    def test_duplicate_reference_identity_groups_match_doi(self) -> None:
        groups = _duplicate_reference_identity_groups(
            ["a", "b", "c"],
            {
                "a": {"doi": "10.1000/example"},
                "b": {"doi": "https://doi.org/10.1000/example"},
                "c": {"doi": "10.1000/other"},
            },
        )

        self.assertEqual(groups, [{"identity": "doi:10.1000/example", "keys": ["a", "b"]}])

    def test_reference_identity_uses_report_namespace_and_number(self) -> None:
        identity = _reference_identity_label({"organization": "NIST", "reportnumber": "SP 800-53"})

        self.assertEqual(identity, "report:nist:sp-800-53")

    def test_reference_identity_uses_arxiv_before_generic_eprint(self) -> None:
        identity = _reference_identity_label({"arxiv": " arXiv:2301.01234v2 ", "eprint": "9999.1"})

        self.assertEqual(identity, "arxiv:2301.01234v2")

    def test_reference_identity_namespaces_generic_eprint_archive(self) -> None:
        identity = _reference_identity_label({"archiveprefix": " HAL Archive ", "eprint": " HAL-123 "})

        self.assertEqual(identity, "hal-archive:hal-123")


if __name__ == "__main__":
    unittest.main()
