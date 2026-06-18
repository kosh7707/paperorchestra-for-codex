from __future__ import annotations

import unittest

from paperorchestra.reviews.source_support_cases import _sentence_for_cite_in_paragraph


class SourceSupportCasesTest(unittest.TestCase):
    def test_sentence_for_cite_in_paragraph_ignores_decimal_periods(self) -> None:
        paragraph = r"Precision is 1.0 in the benchmark. Prior work differs~\cite{x}."
        cite_start = paragraph.index(r"\cite")
        cite_end = cite_start + len(r"\cite{x}")

        sentence = _sentence_for_cite_in_paragraph(paragraph, cite_start, cite_end)

        self.assertEqual(sentence, r"Prior work differs~\cite{x}.")


if __name__ == "__main__":
    unittest.main()
