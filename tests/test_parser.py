"""Tests for the parser module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from depgraph.parser.models import Package, Service
from depgraph.parser.toml_parser import (
    _parse_pep508_constraint,
    _parse_poetry_version,
    parse_pyproject,
    scan_workspace,
)
from depgraph.parser.lock_parser import parse_poetry_lock


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_monorepo"


class TestParsePEP508Constraint:
    """Test PEP 508 requirement string parsing."""

    def test_simple_package(self):
        name, constraint = _parse_pep508_constraint("requests")
        assert name == "requests"
        assert constraint == ""

    def test_with_version(self):
        name, constraint = _parse_pep508_constraint("requests>=2.28.0")
        assert name == "requests"
        assert constraint == ">=2.28.0"

    def test_with_extras(self):
        name, constraint = _parse_pep508_constraint("pandas[sql]>=2.0")
        assert name == "pandas"
        assert constraint == ">=2.0"

    def test_with_environment_marker(self):
        name, constraint = _parse_pep508_constraint(
            'tomli>=2.0; python_version < "3.11"'
        )
        assert name == "tomli"
        assert constraint == ">=2.0"

    def test_complex_constraint(self):
        name, constraint = _parse_pep508_constraint("numpy>=1.21.0,<1.23.0")
        assert name == "numpy"
        assert constraint == ">=1.21.0,<1.23.0"


class TestParsePoetryVersion:
    """Test Poetry version specifier conversion."""

    def test_caret_version(self):
        result = _parse_poetry_version("^2.28.0")
        assert result == ">=2.28.0,<3.0.0"

    def test_tilde_version(self):
        result = _parse_poetry_version("~1.5")
        assert result == ">=1.5.0,<1.6.0"

    def test_exact_version(self):
        result = _parse_poetry_version("2.28.0")
        assert result == "==2.28.0"

    def test_range_constraint(self):
        result = _parse_poetry_version(">=2.0,<3.0")
        assert result == ">=2.0,<3.0"

    def test_wildcard(self):
        result = _parse_poetry_version("*")
        assert result == ""

    def test_dict_format(self):
        result = _parse_poetry_version({"version": "^1.7.4", "extras": ["bcrypt"]})
        assert result == ">=1.7.4,<2.0.0"

    def test_caret_zero_major(self):
        result = _parse_poetry_version("^0.5.0")
        assert result == ">=0.5.0,<0.6.0"


class TestParsePyproject:
    """Test pyproject.toml parsing."""

    def test_parse_poetry_format(self):
        path = FIXTURES_DIR / "ml-service" / "pyproject.toml"
        service = parse_pyproject(str(path))

        assert service is not None
        assert service.name == "ml-service"
        assert len(service.dependencies) > 0

        # Check requests dep
        requests_dep = service.get_package("requests")
        assert requests_dep is not None
        assert requests_dep.version == "2.28.0"
        assert requests_dep.constraint == "==2.28.0"

    def test_parse_analytics_api(self):
        path = FIXTURES_DIR / "analytics-api" / "pyproject.toml"
        service = parse_pyproject(str(path))

        assert service is not None
        assert service.name == "analytics-api"

        requests_dep = service.get_package("requests")
        assert requests_dep is not None
        assert requests_dep.version == "2.25.1"

    def test_nonexistent_file(self):
        result = parse_pyproject("/nonexistent/path/pyproject.toml")
        assert result is None

    def test_package_name_normalization(self):
        path = FIXTURES_DIR / "ml-service" / "pyproject.toml"
        service = parse_pyproject(str(path))

        # scikit-learn should be normalized to scikit_learn
        pkg = service.get_package("scikit-learn")
        assert pkg is not None
        assert pkg.name == "scikit_learn"


class TestParsePoetryLock:
    """Test poetry.lock file parsing."""

    def test_parse_ml_service_lock(self):
        path = FIXTURES_DIR / "ml-service" / "poetry.lock"
        packages = parse_poetry_lock(str(path))

        assert len(packages) > 0

        # Find numpy
        numpy_pkgs = [p for p in packages if p.name == "numpy"]
        assert len(numpy_pkgs) == 1
        assert numpy_pkgs[0].version == "1.22.4"

    def test_transitive_dependencies(self):
        path = FIXTURES_DIR / "ml-service" / "poetry.lock"
        packages = parse_poetry_lock(str(path))

        # pandas should have numpy as a transitive dep
        pandas_pkgs = [p for p in packages if p.name == "pandas"]
        assert len(pandas_pkgs) == 1
        assert "numpy" in pandas_pkgs[0].depends_on

    def test_nonexistent_lock(self):
        result = parse_poetry_lock("/nonexistent/poetry.lock")
        assert result == []


class TestScanWorkspace:
    """Test workspace scanning."""

    def test_finds_all_services(self):
        services = scan_workspace(str(FIXTURES_DIR))
        assert len(services) == 3

        names = {s.name for s in services}
        assert "ml-service" in names
        assert "analytics-api" in names
        assert "auth-service" in names

    def test_each_service_has_deps(self):
        services = scan_workspace(str(FIXTURES_DIR))
        for service in services:
            assert len(service.dependencies) > 0, f"{service.name} has no dependencies"

    def test_empty_workspace(self, tmp_path):
        services = scan_workspace(str(tmp_path))
        assert services == []
