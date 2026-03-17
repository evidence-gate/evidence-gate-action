"""Tests for NemoClaw gate types (nemoclaw_blueprint, nemoclaw_policy).

Covers:
- Blueprint validation: required fields, semver, profiles, sandbox
- Policy validation: enforcement, TLS, wildcard methods, dangerous paths
- YAML and JSON parsing
- evaluate_local() integration for NemoClaw gates
- Preset expansion for nemoclaw-baseline
"""

from __future__ import annotations

import json

import pytest

from local_evaluator import (
    NEMOCLAW_GATE_TYPES,
    _check_blueprint,
    _check_policy,
    _parse_yaml_or_json,
    evaluate_local,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_blueprint(tmp_path):
    """Create a valid NemoClaw blueprint JSON file."""
    data = {
        "version": "0.1.0",
        "min_openshell_version": "1.0.0",
        "min_openclaw_version": "0.5.0",
        "profiles": {
            "default": {
                "provider_type": "nvidia",
                "endpoint_url": "https://integrate.api.nvidia.com",
                "model": "nvidia/llama-3.3-nemotron-super-49b-v1",
                "credential_env": "NVIDIA_API_KEY",
            },
            "agentgov": {
                "provider_type": "openai-compatible",
                "endpoint_url": "http://localhost:8787",
                "model": "gpt-4o",
                "credential_env": "OPENAI_API_KEY",
            },
        },
        "sandbox": {
            "image": "ghcr.io/nvidia/openshell-community/sandboxes/openclaw:latest",
            "ports": [18789],
        },
    }
    path = tmp_path / "blueprint.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture()
def valid_policy(tmp_path):
    """Create a valid NemoClaw OpenShell policy JSON file."""
    data = {
        "version": 1,
        "network_policies": {
            "agentgov_proxy": {
                "endpoints": [
                    {
                        "host": "localhost",
                        "port": 8787,
                        "protocol": "http",
                        "enforcement": "enforce",
                        "rules": [
                            {"allow": {"method": "POST", "path": "/v1/**"}},
                        ],
                    },
                ],
            },
            "github": {
                "endpoints": [
                    {
                        "host": "api.github.com",
                        "port": 443,
                        "protocol": "https",
                        "enforcement": "enforce",
                        "tls": "terminate",
                        "rules": [
                            {"allow": {"method": "GET", "path": "/**"}},
                        ],
                    },
                ],
            },
        },
        "filesystem_policy": {
            "read_write": ["/sandbox", "/tmp"],
            "read_only": ["/usr", "/lib", "/etc"],
        },
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data))
    return str(path)


# ---------------------------------------------------------------------------
# Blueprint validation
# ---------------------------------------------------------------------------


class TestCheckBlueprint:
    """Test _check_blueprint validation."""

    def test_valid_blueprint(self):
        data = {
            "version": "0.1.0",
            "profiles": {
                "default": {"model": "nvidia/llama-3.3-nemotron-super-49b-v1"},
            },
            "sandbox": {"image": "ghcr.io/nvidia/sandboxes/openclaw:latest"},
        }
        issues = _check_blueprint(data)
        assert issues == []

    def test_missing_version(self):
        data = {
            "profiles": {"default": {"model": "test"}},
            "sandbox": {"image": "test:latest"},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_MISSING_VERSION" in i for i in issues)

    def test_invalid_version_format(self):
        data = {
            "version": "not-semver",
            "profiles": {"default": {"model": "test"}},
            "sandbox": {"image": "test:latest"},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_INVALID_VERSION" in i for i in issues)

    def test_missing_profiles(self):
        data = {
            "version": "0.1.0",
            "sandbox": {"image": "test:latest"},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_MISSING_PROFILES" in i for i in issues)

    def test_empty_profiles(self):
        data = {
            "version": "0.1.0",
            "profiles": {},
            "sandbox": {"image": "test:latest"},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_EMPTY_PROFILES" in i for i in issues)

    def test_profile_missing_model(self):
        data = {
            "version": "0.1.0",
            "profiles": {
                "default": {"provider_type": "nvidia"},
            },
            "sandbox": {"image": "test:latest"},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_PROFILE_MISSING_MODEL" in i for i in issues)

    def test_missing_sandbox(self):
        data = {
            "version": "0.1.0",
            "profiles": {"default": {"model": "test"}},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_MISSING_SANDBOX" in i for i in issues)

    def test_sandbox_missing_image(self):
        data = {
            "version": "0.1.0",
            "profiles": {"default": {"model": "test"}},
            "sandbox": {"ports": [8080]},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_MISSING_IMAGE" in i for i in issues)

    def test_invalid_min_version(self):
        data = {
            "version": "0.1.0",
            "min_openshell_version": "bad",
            "profiles": {"default": {"model": "test"}},
            "sandbox": {"image": "test:latest"},
        }
        issues = _check_blueprint(data)
        assert any("BLUEPRINT_INVALID_MIN_OPENSHELL_VERSION" in i for i in issues)


# ---------------------------------------------------------------------------
# Policy validation (security audit)
# ---------------------------------------------------------------------------


class TestCheckPolicy:
    """Test _check_policy security validation."""

    def test_valid_policy(self):
        data = {
            "version": 1,
            "network_policies": {
                "proxy": {
                    "endpoints": [
                        {
                            "host": "proxy.local",
                            "port": 8787,
                            "enforcement": "enforce",
                            "rules": [{"allow": {"method": "POST", "path": "/v1/**"}}],
                        },
                    ],
                },
            },
        }
        issues = _check_policy(data)
        assert issues == []

    def test_missing_version(self):
        data = {"network_policies": {"test": {"endpoints": []}}}
        issues = _check_policy(data)
        assert any("POLICY_MISSING_VERSION" in i for i in issues)

    def test_missing_network_policies(self):
        data = {"version": 1}
        issues = _check_policy(data)
        assert any("POLICY_MISSING_NETWORK" in i for i in issues)

    def test_weak_enforcement(self):
        data = {
            "version": 1,
            "network_policies": {
                "test": {
                    "endpoints": [
                        {
                            "host": "api.example.com",
                            "port": 443,
                            "enforcement": "monitor",
                            "tls": "terminate",
                        },
                    ],
                },
            },
        }
        issues = _check_policy(data)
        assert any("POLICY_WEAK_ENFORCEMENT" in i for i in issues)

    def test_missing_tls_on_443(self):
        data = {
            "version": 1,
            "network_policies": {
                "test": {
                    "endpoints": [
                        {
                            "host": "api.example.com",
                            "port": 443,
                            "enforcement": "enforce",
                        },
                    ],
                },
            },
        }
        issues = _check_policy(data)
        assert any("POLICY_MISSING_TLS" in i for i in issues)

    def test_wildcard_method(self):
        data = {
            "version": 1,
            "network_policies": {
                "test": {
                    "endpoints": [
                        {
                            "host": "api.example.com",
                            "port": 443,
                            "enforcement": "enforce",
                            "tls": "terminate",
                            "rules": [{"allow": {"method": "*", "path": "/**"}}],
                        },
                    ],
                },
            },
        }
        issues = _check_policy(data)
        assert any("POLICY_WILDCARD_METHOD" in i for i in issues)

    def test_dangerous_writable_path(self):
        data = {
            "version": 1,
            "network_policies": {"test": {"endpoints": []}},
            "filesystem_policy": {
                "read_write": ["/sandbox", "/etc"],
            },
        }
        issues = _check_policy(data)
        assert any("POLICY_DANGEROUS_WRITABLE" in i for i in issues)

    def test_safe_writable_paths(self):
        data = {
            "version": 1,
            "network_policies": {"test": {"endpoints": []}},
            "filesystem_policy": {
                "read_write": ["/sandbox", "/tmp"],
            },
        }
        issues = _check_policy(data)
        assert issues == []


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------


class TestParseYamlOrJson:
    """Test _parse_yaml_or_json."""

    def test_parse_json(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"key": "value"}')
        result = _parse_yaml_or_json(str(path))
        assert result == {"key": "value"}

    def test_parse_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{broken")
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_yaml_or_json(str(path))

    def test_parse_missing_file(self):
        with pytest.raises(ValueError, match="File not found"):
            _parse_yaml_or_json("/nonexistent/file.json")

    def test_parse_yaml_without_pyyaml(self, tmp_path, monkeypatch):
        """YAML files produce clear error when PyYAML is not installed."""
        path = tmp_path / "test.yaml"
        path.write_text("key: value")
        # Simulate PyYAML not installed by patching builtins import
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ValueError, match="PyYAML"):
            _parse_yaml_or_json(str(path))


# ---------------------------------------------------------------------------
# NemoClaw evaluate_local integration
# ---------------------------------------------------------------------------


class TestEvaluateNemoclaw:
    """Test evaluate_local() with NemoClaw gate types."""

    def test_blueprint_gate_passes(self, valid_blueprint):
        result = evaluate_local(
            gate_type="nemoclaw_blueprint",
            phase_id="1a",
            evidence_files=[valid_blueprint],
        )
        assert result["passed"] is True
        assert result["mode"] == "free"
        assert result["gate_type"] == "nemoclaw_blueprint"

    def test_blueprint_gate_fails_on_invalid(self, tmp_path):
        bad = tmp_path / "bad-blueprint.json"
        bad.write_text('{"version": "not-semver"}')
        result = evaluate_local(
            gate_type="nemoclaw_blueprint",
            phase_id="1a",
            evidence_files=[str(bad)],
        )
        assert result["passed"] is False
        assert len(result["issues"]) > 0

    def test_policy_gate_passes(self, valid_policy):
        result = evaluate_local(
            gate_type="nemoclaw_policy",
            phase_id="1a",
            evidence_files=[valid_policy],
        )
        assert result["passed"] is True
        assert result["gate_type"] == "nemoclaw_policy"

    def test_policy_gate_fails_on_insecure(self, tmp_path):
        bad = tmp_path / "insecure-policy.json"
        data = {
            "version": 1,
            "network_policies": {
                "test": {
                    "endpoints": [{
                        "host": "evil.com",
                        "port": 443,
                        "enforcement": "monitor",
                    }],
                },
            },
        }
        bad.write_text(json.dumps(data))
        result = evaluate_local(
            gate_type="nemoclaw_policy",
            phase_id="1a",
            evidence_files=[str(bad)],
        )
        assert result["passed"] is False
        assert any("POLICY_WEAK_ENFORCEMENT" in i for i in result["issues"])
        assert any("POLICY_MISSING_TLS" in i for i in result["issues"])

    def test_no_evidence_files_fails(self):
        result = evaluate_local(
            gate_type="nemoclaw_blueprint",
            phase_id="1a",
        )
        assert result["passed"] is False
        assert any("No evidence files" in i for i in result["issues"])

    def test_nemoclaw_gate_types_constant(self):
        assert "nemoclaw_blueprint" in NEMOCLAW_GATE_TYPES
        assert "nemoclaw_policy" in NEMOCLAW_GATE_TYPES


class TestNemoClawRecommendations:
    """Test that NemoClaw issues produce useful recommendations."""

    def test_blueprint_missing_field_gets_recommendation(self):
        from entrypoint import _generate_suggested_actions

        result = {
            "passed": False,
            "issues": ["BLUEPRINT_MISSING_VERSION: 'version' field is required"],
        }
        actions = _generate_suggested_actions("nemoclaw_blueprint", result)
        assert len(actions) > 0
        assert any("blueprint" in a.lower() for a in actions)

    def test_policy_weak_enforcement_gets_recommendation(self):
        from entrypoint import _generate_suggested_actions

        result = {
            "passed": False,
            "issues": [
                "POLICY_WEAK_ENFORCEMENT: test.endpoints[0] has enforcement='monitor'"
            ],
        }
        actions = _generate_suggested_actions("nemoclaw_policy", result)
        assert len(actions) > 0
        assert any("enforce" in a.lower() for a in actions)
