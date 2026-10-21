"""
Workspace Storage Module (Deep Module)

Encapsulates dataset resolution, scenario directory structures, and artifact persistence.
Eliminates relative path leaks (e.g. mas_ciclo/data vs grafos-accesibilidad/data)
by anchoring to a canonical project repository root and supporting pluggable adapters.
"""

from abc import ABC, abstractmethod
import os
from pathlib import Path
from typing import Dict, List, Optional, Union


class WorkspaceAdapter(ABC):
    """Abstract adapter interface for workspace storage."""

    @abstractmethod
    def resolve_input(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Resolve a readable input path for an artifact or dataset."""
        pass

    @abstractmethod
    def stage_output(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Resolve a writable path for a staged scenario output."""
        pass

    @abstractmethod
    def read_artifact(
        self,
        key: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """Read artifact content using logical key."""
        path = self.resolve_input(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.read_text(path)

    def write_artifact(
        self,
        key: str,
        data: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Write artifact content using logical key."""
        path = self.stage_output(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.write_text(path, data)

    def read_text(self, path: Union[Path, str]) -> str:
        """Read content from path as text."""
        pass

    @abstractmethod
    def write_text(self, path: Union[Path, str], content: str) -> Path:
        """Write content to path as text."""
        pass

    @abstractmethod
    def exists(self, path: Union[Path, str]) -> bool:
        """Check if path exists."""
        pass

    @abstractmethod
    def list_files(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> List[str]:
        """List files matching key and parameters."""
        pass

    @abstractmethod
    def initialize_city_structure(self, city_key: str) -> None:
        """Initialize the standard folder hierarchy for a city."""
        pass


class DiskWorkspaceAdapter(WorkspaceAdapter):
    """
    Filesystem storage adapter anchored to canonical project root.
    Eliminates drift between top-level and submodule relative paths.
    """

    def __init__(self, root_dir: Optional[Union[Path, str]] = None):
        if root_dir is not None:
            self.root_dir = Path(root_dir).resolve()
        else:
            self.root_dir = self._detect_canonical_root()

        self.data_dir = self.root_dir / "data"

    def _detect_canonical_root(self) -> Path:
        """
        Locates the canonical repo root by walking upwards looking for markers
        such as plus-ciclo.sh, pyproject.toml, or .git.
        """
        current = Path(__file__).resolve().parent
        for parent in [current] + list(current.parents):
            if (parent / "plus-ciclo.sh").exists() or (parent / ".git").exists():
                return parent
            # Fallback to grafos-accesibilidad repo root if running stand-alone
            if (parent / "docker-compose.yml").exists() and (parent / "api").exists():
                # Check if its parent is the outer project
                if (parent.parent / "plus-ciclo.sh").exists():
                    return parent.parent
                return parent
        return Path(os.getcwd()).resolve()

    def _resolve_base_dir(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        is_output: bool = False,
    ) -> Path:
        city = city_key or "shared"
        if key == "maps":
            base = self.data_dir / city / "out" / "maps"
        elif key == "qgis":
            base = self.data_dir / city / "out" / "qgis"
        elif key == "raw":
            base = self.data_dir / city / "raw"
        elif key == "proc":
            base = self.data_dir / city / "proc"
        elif key == "map_layers":
            base = self.data_dir / "map_layers"
        elif key == "telemetry":
            base = self.data_dir / "telemetry"
        else:
            base = self.data_dir / city / key

        if scenario_id:
            base = base / scenario_id
        if is_output:
            base.mkdir(parents=True, exist_ok=True)
        return base

    def resolve_input(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        base = self._resolve_base_dir(key, city_key, scenario_id, is_output=False)
        if filename:
            target = base / filename
            if target.exists():
                return target
            # Fallback: check within submodule data directory if not found in root data
            submodule_target = self.root_dir / "grafos-accesibilidad" / "data" / (city_key or "shared") / key / filename
            if submodule_target.exists():
                return submodule_target
            return target
        return base

    def stage_output(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        base = self._resolve_base_dir(key, city_key, scenario_id, is_output=True)
        if filename:
            return base / filename
        return base

    def read_artifact(
        self,
        key: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """Read artifact content using logical key."""
        path = self.resolve_input(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.read_text(path)

    def write_artifact(
        self,
        key: str,
        data: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Write artifact content using logical key."""
        path = self.stage_output(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.write_text(path, data)

    def read_text(self, path: Union[Path, str]) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_text(self, path: Union[Path, str], content: str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return target

    def exists(self, path: Union[Path, str]) -> bool:
        return Path(path).exists()

    def list_files(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> List[str]:
        base = self._resolve_base_dir(key, city_key, scenario_id, is_output=False)
        if not base.exists():
            return []
        return [str(p) for p in base.glob("*") if p.is_file()]

    def initialize_city_structure(self, city_key: str) -> None:
        subdirs = [
            "raw",
            "raw/projects",
            f"raw/{city_key}_demand",
            f"raw/{city_key}_zones",
            "proc",
            "out/maps",
            "out/qgis",
        ]
        for sub in subdirs:
            (self.data_dir / city_key / sub).mkdir(parents=True, exist_ok=True)


class InMemoryWorkspaceAdapter(WorkspaceAdapter):
    """
    Virtual in-memory workspace adapter for fast isolated testing.
    Requires no disk access or cleanup.
    """

    def __init__(self):
        self._store: Dict[str, str] = {}
        self.virtual_root = Path("/virtual/data")

    def _build_virtual_path(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        city = city_key or "shared"
        prefix = f"{city}/{key}"
        if scenario_id:
            prefix = f"{prefix}/{scenario_id}"
        if filename:
            return self.virtual_root / prefix / filename
        return self.virtual_root / prefix

    def resolve_input(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        return self._build_virtual_path(key, city_key, scenario_id, filename)

    def stage_output(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        return self._build_virtual_path(key, city_key, scenario_id, filename)

    def read_artifact(
        self,
        key: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """Read artifact content using logical key."""
        path = self.resolve_input(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.read_text(path)

    def write_artifact(
        self,
        key: str,
        data: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Write artifact content using logical key."""
        path = self.stage_output(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.write_text(path, data)

    def read_text(self, path: Union[Path, str]) -> str:
        key = str(path)
        if key not in self._store:
            raise FileNotFoundError(f"Virtual file not found: {key}")
        return self._store[key]

    def write_text(self, path: Union[Path, str], content: str) -> Path:
        target = Path(path)
        self._store[str(target)] = content
        return target

    def exists(self, path: Union[Path, str]) -> bool:
        return str(path) in self._store

    def list_files(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> List[str]:
        prefix = str(self._build_virtual_path(key, city_key, scenario_id))
        return [k for k in self._store.keys() if k.startswith(prefix)]

    def initialize_city_structure(self, city_key: str) -> None:
        pass


class WorkspaceStorage:
    """
    Workspace Storage (Deep Module Facade).

    Unified interface for dataset resolution, directory management,
    and artifact staging across all pipeline stages.
    """

    def __init__(self, adapter: Optional[WorkspaceAdapter] = None):
        self.adapter = adapter or DiskWorkspaceAdapter()

    @property
    def root_dir(self) -> Path:
        if isinstance(self.adapter, DiskWorkspaceAdapter):
            return self.adapter.root_dir
        return Path("/virtual")

    @property
    def data_dir(self) -> Path:
        if isinstance(self.adapter, DiskWorkspaceAdapter):
            return self.adapter.data_dir
        return Path("/virtual/data")

    def resolve_input(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        return self.adapter.resolve_input(
            key=key, city_key=city_key, scenario_id=scenario_id, filename=filename
        )

    def stage_output(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        return self.adapter.stage_output(
            key=key, city_key=city_key, scenario_id=scenario_id, filename=filename
        )

    def read_artifact(
        self,
        key: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """Read artifact content using logical key."""
        path = self.resolve_input(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.read_text(path)

    def write_artifact(
        self,
        key: str,
        data: str,
        scenario_id: Optional[str] = None,
        city_key: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Path:
        """Write artifact content using logical key."""
        path = self.stage_output(key=key, scenario_id=scenario_id, city_key=city_key, filename=filename)
        return self.write_text(path, data)

    def read_text(self, path: Union[Path, str]) -> str:
        return self.adapter.read_text(path)

    def write_text(self, path: Union[Path, str], content: str) -> Path:
        return self.adapter.write_text(path, content)

    def exists(self, path: Union[Path, str]) -> bool:
        return self.adapter.exists(path)

    def list_files(
        self,
        key: str,
        city_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> List[str]:
        return self.adapter.list_files(
            key=key, city_key=city_key, scenario_id=scenario_id
        )

    def initialize_city_structure(self, city_key: str) -> None:
        self.adapter.initialize_city_structure(city_key)
