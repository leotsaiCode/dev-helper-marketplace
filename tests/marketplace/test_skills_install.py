"""Run the actual installer under pytest, with failures reported as test failures."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_skills_cli_selected_multiple_and_all_install_only_runtime_files():
    spec = importlib.util.spec_from_file_location("verify_skills_install", ROOT / "scripts/verify_skills_install.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    verifier.verify()
