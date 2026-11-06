"""
Tests for SLProxy PluginManager
Verifies discovery, dynamic loading, <1s hot reloading, syntax validation,
atomic deployment, and rollback.
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from slproxy.core.plugin_base import BasePlugin
from slproxy.core.plugin_manager import PluginManager


@pytest.fixture
def temp_plugins_dir(tmp_path: Path) -> Path:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir


def test_discover_and_load_built_in_plugins():
    # Verify templates directory contains the 7 reference templates
    templates_dir = Path(__file__).resolve().parent.parent / "slproxy" / "templates" / "plugins"
    pm_templates = PluginManager(templates_dir)
    loaded_count = pm_templates.discover_and_load_all()

    assert loaded_count == 7
    plugins = pm_templates.list_plugins()
    assert len(plugins) == 7

    expected_ids = {
        "google_antigravity",
        "openai_codex",
        "anthropic_claude",
        "openrouter",
        "opencode",
        "openai_compatible",
        "anthropic_compatible",
    }
    loaded_ids = {p.id for p in plugins}
    assert loaded_ids == expected_ids

    # Verify default active plugins directory starts clean with 0 plugins (plain website)
    default_plugins_dir = Path(__file__).resolve().parent.parent / "slproxy" / "plugins"
    pm_default = PluginManager(default_plugins_dir)
    assert pm_default.discover_and_load_all() == 0
    assert len(pm_default.list_plugins()) == 0


def test_load_plugin_and_measure_time(temp_plugins_dir: Path):
    plugin_code = """
from slproxy.core.plugin_base import BasePlugin

class FastPlugin(BasePlugin):
    id = "fast_plugin"
    name = "Fast Test Plugin"
"""
    plugin_file = temp_plugins_dir / "fast_plugin.py"
    plugin_file.write_text(plugin_code, encoding="utf-8")

    pm = PluginManager(temp_plugins_dir)
    plugin = pm.load_plugin_from_file(plugin_file)

    assert plugin is not None
    assert plugin.id == "fast_plugin"
    assert plugin.name == "Fast Test Plugin"
    assert pm.get_plugin("fast_plugin") is plugin

    # Load time must be under 1 second (< 1.0s), typically under 10ms
    load_time = pm.load_times.get("fast_plugin")
    assert load_time is not None
    assert load_time < 1.0
    assert getattr(plugin, "last_load_time", None) == load_time


def test_ignore_init_and_underscore_files(temp_plugins_dir: Path):
    (temp_plugins_dir / "__init__.py").write_text("# init", encoding="utf-8")
    (temp_plugins_dir / "_private.py").write_text("# private", encoding="utf-8")

    valid_plugin = """
from slproxy.core.plugin_base import BasePlugin

class ValidPlugin(BasePlugin):
    id = "valid_plugin"
    name = "Valid Plugin"
"""
    (temp_plugins_dir / "valid_plugin.py").write_text(valid_plugin, encoding="utf-8")

    pm = PluginManager(temp_plugins_dir)
    count = pm.discover_and_load_all()
    assert count == 1
    assert pm.get_plugin("valid_plugin") is not None


def test_reload_plugin(temp_plugins_dir: Path):
    code_v1 = """
from slproxy.core.plugin_base import BasePlugin

class ReloadablePlugin(BasePlugin):
    id = "reload_test"
    name = "Version 1"
"""
    code_v2 = """
from slproxy.core.plugin_base import BasePlugin

class ReloadablePlugin(BasePlugin):
    id = "reload_test"
    name = "Version 2"
"""
    plugin_file = temp_plugins_dir / "reload_test.py"
    plugin_file.write_text(code_v1, encoding="utf-8")

    pm = PluginManager(temp_plugins_dir)
    p1 = pm.load_plugin_from_file(plugin_file)
    assert p1 is not None
    assert p1.name == "Version 1"

    # Update file content
    plugin_file.write_text(code_v2, encoding="utf-8")

    # Hot reload
    t_start = time.perf_counter()
    p2 = pm.reload_plugin("reload_test")
    elapsed = time.perf_counter() - t_start

    assert elapsed < 1.0
    assert p2 is not None
    assert p2.name == "Version 2"
    assert pm.get_plugin("reload_test").name == "Version 2"


def test_save_and_deploy_hot_reload_under_1s(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)

    code_v1 = """
from slproxy.core.plugin_base import BasePlugin

class HotDeployPlugin(BasePlugin):
    id = "hot_deploy"
    name = "Initial Version"
"""
    t0 = time.perf_counter()
    plugin = pm.save_and_deploy_plugin("hot_deploy", code_v1)
    deploy_time = time.perf_counter() - t0

    assert deploy_time < 1.0
    assert plugin.id == "hot_deploy"
    assert plugin.name == "Initial Version"
    assert (temp_plugins_dir / "hot_deploy.py").exists()

    code_v2 = """
from slproxy.core.plugin_base import BasePlugin

class HotDeployPlugin(BasePlugin):
    id = "hot_deploy"
    name = "Updated Version"
"""
    t1 = time.perf_counter()
    updated_plugin = pm.save_and_deploy_plugin("hot_deploy", code_v2)
    update_time = time.perf_counter() - t1

    assert update_time < 1.0
    assert updated_plugin.name == "Updated Version"
    assert pm.get_plugin("hot_deploy").name == "Updated Version"


def test_save_and_deploy_syntax_error_preserves_previous(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)

    valid_code = """
from slproxy.core.plugin_base import BasePlugin

class StablePlugin(BasePlugin):
    id = "stable_plugin"
    name = "Stable 1.0"
"""
    pm.save_and_deploy_plugin("stable_plugin", valid_code)
    assert pm.get_plugin("stable_plugin").name == "Stable 1.0"

    invalid_syntax_code = """
def broken_syntax(
    this is completely invalid python syntax :::
"""
    with pytest.raises(ValueError, match="Syntax validation failed"):
        pm.save_and_deploy_plugin("stable_plugin", invalid_syntax_code)

    # Previous version must be preserved both in memory and on disk
    preserved = pm.get_plugin("stable_plugin")
    assert preserved is not None
    assert preserved.name == "Stable 1.0"
    source = pm.get_plugin_source("stable_plugin")
    assert "Stable 1.0" in source


def test_save_and_deploy_instantiation_error_rollback(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)

    valid_code = """
from slproxy.core.plugin_base import BasePlugin

class WorkingPlugin(BasePlugin):
    id = "working_plugin"
    name = "Working 1.0"
"""
    pm.save_and_deploy_plugin("working_plugin", valid_code)
    assert pm.get_plugin("working_plugin").name == "Working 1.0"

    runtime_error_code = """
from slproxy.core.plugin_base import BasePlugin

class CrashingPlugin(BasePlugin):
    id = "working_plugin"
    name = "Crashes on init"

    def __init__(self):
        super().__init__()
        raise RuntimeError("Fatal initialization failure!")
"""
    with pytest.raises(ValueError, match="Failed to deploy plugin"):
        pm.save_and_deploy_plugin("working_plugin", runtime_error_code)

    # In-memory and disk must retain Working 1.0
    preserved = pm.get_plugin("working_plugin")
    assert preserved is not None
    assert preserved.name == "Working 1.0"
    assert "Working 1.0" in pm.get_plugin_source("working_plugin")


def test_get_plugin_source(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)
    code = """
from slproxy.core.plugin_base import BasePlugin

class SourceTestPlugin(BasePlugin):
    id = "source_test"
    name = "Source Test"
"""
    pm.save_and_deploy_plugin("source_test", code)

    source = pm.get_plugin_source("source_test")
    assert "class SourceTestPlugin(BasePlugin):" in source

    with pytest.raises(FileNotFoundError):
        pm.get_plugin_source("non_existent_plugin")


def test_load_plugin_without_subclass_returns_none(temp_plugins_dir: Path):
    plain_script = """
x = 10
y = 20
def helper():
    return x + y
"""
    file_path = temp_plugins_dir / "no_plugin.py"
    file_path.write_text(plain_script, encoding="utf-8")

    pm = PluginManager(temp_plugins_dir)
    result = pm.load_plugin_from_file(file_path)
    assert result is None


def test_reload_non_existent_plugin(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)
    assert pm.reload_plugin("does_not_exist") is None


def test_get_non_existent_plugin(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)
    assert pm.get_plugin("missing_id") is None


def test_discover_with_broken_file_continues_loading_others(temp_plugins_dir: Path):
    broken_code = "raise RuntimeError('Broken on import')"
    valid_code = """
from slproxy.core.plugin_base import BasePlugin
class GoodPlugin(BasePlugin):
    id = "good_plugin"
    name = "Good Plugin"
"""
    (temp_plugins_dir / "broken.py").write_text(broken_code, encoding="utf-8")
    (temp_plugins_dir / "good.py").write_text(valid_code, encoding="utf-8")

    pm = PluginManager(temp_plugins_dir)
    count = pm.discover_and_load_all()

    assert count == 1
    assert pm.get_plugin("good_plugin") is not None
    assert pm.get_plugin("broken") is None


def test_save_and_deploy_no_subclass_raises_value_error(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)
    script_without_subclass = "foo = 'bar'\ndef baz(): pass"

    with pytest.raises(ValueError, match="No valid BasePlugin subclass found"):
        pm.save_and_deploy_plugin("no_subclass", script_without_subclass)

    assert pm.get_plugin("no_subclass") is None
    assert not (temp_plugins_dir / "no_subclass.py").exists()


def test_save_and_deploy_mismatched_id_raises_value_error(temp_plugins_dir: Path):
    pm = PluginManager(temp_plugins_dir)
    mismatched_code = """
from slproxy.core.plugin_base import BasePlugin
class MismatchedPlugin(BasePlugin):
    id = "actual_id"
    name = "Mismatched"
"""
    with pytest.raises(ValueError, match="does not match target deploy ID"):
        pm.save_and_deploy_plugin("intended_id", mismatched_code)

    assert pm.get_plugin("intended_id") is None
    assert not (temp_plugins_dir / "intended_id.py").exists()


