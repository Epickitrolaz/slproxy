"""
SLProxy Dynamic Python Plugin Loader & Manager
Supports <1s hot reload, syntax validation, in-memory registration, and rollback.
"""

import ast
import importlib.util
import inspect
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Union

from slproxy.core.plugin_base import BasePlugin

try:
    from slproxy.config import TEMPLATES_DIR as DEFAULT_TEMPLATES_DIR
except ImportError:  # pragma: no cover - config always importable in practice
    DEFAULT_TEMPLATES_DIR = None


class PluginManager:
    """
    Manages loading, validating, reloading (<1s hot deploy),
    and registering Python plugins.
    """

    def __init__(self, plugins_dir: Union[Path, str], templates_dir: Optional[Union[Path, str]] = None):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir = (
            Path(templates_dir) if templates_dir is not None
            else Path(DEFAULT_TEMPLATES_DIR) if DEFAULT_TEMPLATES_DIR is not None
            else self.plugins_dir.parent / "templates" / "plugins"
        )
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_files: Dict[str, Path] = {}
        self.load_times: Dict[str, float] = {}

    def discover_and_load_all(self) -> int:
        """
        Discovers and loads all .py plugin files in plugins_dir
        (ignoring __init__.py and files starting with _).
        Returns the number of plugins successfully loaded.
        """
        loaded_count = 0
        if not self.plugins_dir.exists():
            return 0

        for file_path in sorted(self.plugins_dir.glob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue

            try:
                plugin = self.load_plugin_from_file(file_path)
                if plugin is not None:
                    loaded_count += 1
            except Exception:
                # Continue loading remaining plugins if one encounters an error
                continue

        return loaded_count

    def load_plugin_from_file(self, file_path: Path) -> Optional[BasePlugin]:
        """
        Dynamically loads the class subclassing BasePlugin from file_path.
        Measures load time (<1s, typically <10ms).
        Registers the plugin in self.plugins and self.plugin_files.
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            return None

        t_start = time.perf_counter()

        # Generate a unique module name to avoid module cache collisions on hot reload
        unique_suffix = uuid.uuid4().hex[:8]
        module_name = f"slproxy.plugins.{file_path.stem}_{unique_suffix}"

        import types
        module = types.ModuleType(module_name)
        module.__file__ = str(file_path)
        sys.modules[module_name] = module

        try:
            source = file_path.read_text(encoding="utf-8")
            compiled_code = compile(source, str(file_path), "exec")
            exec(compiled_code, module.__dict__)

            # Find the subclass of BasePlugin defined in this module
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                    and getattr(attr, "__module__", None) == module_name
                ):
                    plugin_class = attr
                    break

            # Fallback: if not matched by module name, find any BasePlugin subclass
            if plugin_class is None:
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin
                    ):
                        plugin_class = attr
                        break

            if plugin_class is None:
                sys.modules.pop(module_name, None)
                return None

            plugin_instance = plugin_class()
            if not isinstance(plugin_instance, BasePlugin):
                sys.modules.pop(module_name, None)
                return None
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        t_end = time.perf_counter()
        elapsed = t_end - t_start
        self.load_times[plugin_instance.id] = elapsed
        setattr(plugin_instance, "last_load_time", elapsed)

        previous_plugin = self.plugins.get(plugin_instance.id)
        if previous_plugin is not None:
            plugin_instance.set_settings(getattr(previous_plugin, "settings", {}))

        self.plugins[plugin_instance.id] = plugin_instance
        self.plugin_files[plugin_instance.id] = file_path

        return plugin_instance

    def reload_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        """
        Hot-reloads the plugin from its file in place without restarting.
        """
        file_path = self.plugin_files.get(plugin_id)
        if file_path is None or not file_path.exists():
            file_path = self.plugins_dir / f"{plugin_id}.py"

        if not file_path.exists():
            return None

        return self.load_plugin_from_file(file_path)

    def save_and_deploy_plugin(self, plugin_id: str, code: str) -> BasePlugin:
        """
        Validates python syntax (ast.parse), writes to disk file plugins/<plugin_id>.py,
        and hot-reloads it immediately into memory.
        If syntax or instantiation fails, raises ValueError and preserves previous plugin version.
        """
        # 1. Validate Python syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Syntax validation failed for plugin '{plugin_id}': {e}") from e

        file_path = self.plugins_dir / f"{plugin_id}.py"

        # 2. Preserve backup of existing state
        backup_content: Optional[str] = None
        if file_path.exists():
            backup_content = file_path.read_text(encoding="utf-8")

        previous_plugin = self.plugins.get(plugin_id)
        previous_file = self.plugin_files.get(plugin_id)
        previous_load_time = self.load_times.get(plugin_id)

        # 3. Write new code to disk
        file_path.write_text(code, encoding="utf-8")

        # 4. Attempt to load and instantiate
        try:
            plugin = self.load_plugin_from_file(file_path)
            if plugin is None:
                raise ValueError(f"No valid BasePlugin subclass found in plugin '{plugin_id}'")
            if plugin.id != plugin_id:
                raise ValueError(
                    f"Plugin defined ID '{plugin.id}' does not match target deploy ID '{plugin_id}'"
                )
            return plugin
        except Exception as e:
            # Rollback file on disk
            if backup_content is not None:
                file_path.write_text(backup_content, encoding="utf-8")
            else:
                if file_path.exists():
                    file_path.unlink()

            # Rollback in-memory state
            if previous_plugin is not None:
                self.plugins[plugin_id] = previous_plugin
            else:
                self.plugins.pop(plugin_id, None)

            if previous_file is not None:
                self.plugin_files[plugin_id] = previous_file
            else:
                self.plugin_files.pop(plugin_id, None)

            if previous_load_time is not None:
                self.load_times[plugin_id] = previous_load_time
            else:
                self.load_times.pop(plugin_id, None)

            raise ValueError(f"Failed to deploy plugin '{plugin_id}': {e}") from e

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        """
        Returns plugin instance by id, or None if not registered.
        """
        return self.plugins.get(plugin_id)

    def list_plugins(self) -> List[BasePlugin]:
        """
        Returns all currently loaded plugin instances.
        """
        return list(self.plugins.values())

    def get_plugin_source(self, plugin_id: str) -> str:
        """
        Reads the .py source code of the plugin from disk.
        Falls back to the templates directory for reference templates that are
        available but not installed (e.g. Google Antigravity in a fresh install).
        """
        file_path = self.plugin_files.get(plugin_id)
        if file_path is None or not file_path.exists():
            file_path = self.plugins_dir / f"{plugin_id}.py"

        if not file_path.exists():
            # Reference templates live outside the active plugins directory;
            # they remain selectable sources until the user installs/edits them.
            template_path = self.templates_dir / f"{plugin_id}.py"
            if template_path.exists():
                return template_path.read_text(encoding="utf-8")

            raise FileNotFoundError(f"Source file for plugin '{plugin_id}' not found at {file_path}")

        return file_path.read_text(encoding="utf-8")
