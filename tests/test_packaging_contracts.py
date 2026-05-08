import tomllib
import unittest
from pathlib import Path

from setuptools import find_packages


class PackagingContractTests(unittest.TestCase):
    def test_package_discovery_includes_domains_and_prompt_assets(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        find_config = pyproject["tool"]["setuptools"]["packages"]["find"]
        include = find_config["include"]
        discovered = set(find_packages(include=include))

        self.assertIn("paperorchestra", discovered)
        self.assertIn("paperorchestra.domains", discovered)
        self.assertIn("prompt_assets/*.md", pyproject["tool"]["setuptools"]["package-data"]["paperorchestra"])

    def test_public_package_metadata_matches_repository_ownership(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]

        self.assertEqual(project["authors"], [{"name": "kosh7707"}])
        self.assertIn("Independent Codex/OMX-native reconstruction", project["description"])
        self.assertNotIn("OpenAI Codex", project["authors"][0]["name"])



if __name__ == "__main__":
    unittest.main()
