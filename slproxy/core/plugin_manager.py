"""
Plugin Manager Contract & Stub
"""

from typing import Dict, List, Optional
from pathlib import Path
from slproxy.core.plugin_base import BasePlugin


class PluginManager:
    """
    Manages loading, validating, reloading (<1s hot deploy),
    and registering Python plugins.
    """
    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_files: Dict[str, Path] = {}

    def discover_and_load_all(self) -> int:
        raise NotImplementedError

    def load_plugin_from_file(self, file_path: Path) -> Optional[BasePlugin]:
        raise NotImplementedError

    def reload_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        raise NotImplementedError

    def save_and_deploy_plugin(self, plugin_id: str, code: str) -> BasePlugin:
        raise NotImplementedError

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        return self.plugins.get(plugin_id)

    def list_plugins(self) -> List[BasePlugin]:
        return list(self.plugins.values())

    def get_plugin_source(self, plugin_id: str) -> str:
        raise NotImplementedError
