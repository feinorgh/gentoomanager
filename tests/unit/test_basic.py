"""Unit tests for the local.gentoomanager collection structure."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
GALAXY_YML = REPO_ROOT / "galaxy.yml"

REQUIRED_FIELDS = ["namespace", "name", "version", "description", "authors"]
# Ansible Galaxy accepts either `license` (SPDX list) or `license_file`
LICENSE_FIELDS = ["license", "license_file"]


def test_galaxy_yml_exists() -> None:
    """galaxy.yml must exist at the repository root."""
    assert GALAXY_YML.exists(), f"galaxy.yml not found at {GALAXY_YML}"


def test_galaxy_yml_required_fields() -> None:
    """galaxy.yml must contain all required Ansible Galaxy fields."""
    with GALAXY_YML.open() as fh:
        data = yaml.safe_load(fh)
    missing = [field for field in REQUIRED_FIELDS if not data.get(field)]
    assert not missing, f"galaxy.yml is missing required fields: {missing}"
    has_license = any(data.get(f) for f in LICENSE_FIELDS)
    assert has_license, f"galaxy.yml must have at least one of: {LICENSE_FIELDS}"


def test_galaxy_yml_version_format() -> None:
    """galaxy.yml version must follow semantic versioning (MAJOR.MINOR.PATCH)."""
    import re

    with GALAXY_YML.open() as fh:
        data = yaml.safe_load(fh)
    version = str(data.get("version", ""))
    assert re.match(r"^\d+\.\d+\.\d+", version), f"Invalid version format: {version!r}"
