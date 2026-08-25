"""設定ファイルの読み込み。

APIキーは config.toml から読み込むのみで、値を表示・記録しない。
不足しているときは「どのキーが足りないか」だけを伝える。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """設定の不足・不正。メッセージにキーの値は含めない。"""


@dataclass
class SearchConfig:
    provider: str = "serpapi"
    api_key: str = ""
    candidates: int = 5
    query_template: str = "{name} ロゴ"
    strip_legal_suffix: bool = True


@dataclass
class RemoveBgConfig:
    api_key: str = ""
    size: str = "preview"


@dataclass
class OutputConfig:
    dir: Path = Path("output")
    padding_ratio: float = 0.02
    max_long_edge: int = 1024
    pptx: bool = True


@dataclass
class Config:
    search: SearchConfig = field(default_factory=SearchConfig)
    removebg: RemoveBgConfig = field(default_factory=RemoveBgConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cache_dir: Path = Path("cache")
    root: Path = Path(".")

    def require_keys(self, *, need_search: bool = True, need_removebg: bool = True) -> None:
        """必要なキーが埋まっているか確認する。値そのものは決して出力しない。"""
        missing = []
        if need_search and not self.search.api_key.strip():
            missing.append("[search] api_key(SerpAPI)")
        if need_removebg and not self.removebg.api_key.strip():
            missing.append("[removebg] api_key(remove.bg)")
        if missing:
            raise ConfigError(
                "config.toml に次のAPIキーが未設定です:\n  - "
                + "\n  - ".join(missing)
                + "\nconfig.example.toml を config.toml にコピーして記入してください。"
            )


def load(path: str | Path = "config.toml", root: str | Path = ".") -> Config:
    root = Path(root).resolve()
    path = Path(path)
    if not path.is_absolute():
        path = root / path

    if not path.exists():
        raise ConfigError(
            f"設定ファイルが見つかりません: {path}\n"
            "config.example.toml を config.toml にコピーして、APIキーを記入してください。"
        )

    with path.open("rb") as f:
        raw = tomllib.load(f)

    s = raw.get("search", {})
    r = raw.get("removebg", {})
    o = raw.get("output", {})
    c = raw.get("cache", {})

    cfg = Config(
        search=SearchConfig(
            provider=s.get("provider", "serpapi"),
            api_key=s.get("api_key", ""),
            candidates=int(s.get("candidates", 5)),
            query_template=s.get("query_template", "{name} ロゴ"),
            strip_legal_suffix=bool(s.get("strip_legal_suffix", True)),
        ),
        removebg=RemoveBgConfig(
            api_key=r.get("api_key", ""),
            size=r.get("size", "preview"),
        ),
        output=OutputConfig(
            dir=root / o.get("dir", "output"),
            padding_ratio=float(o.get("padding_ratio", 0.02)),
            max_long_edge=int(o.get("max_long_edge", 1024)),
            pptx=bool(o.get("pptx", True)),
        ),
        cache_dir=root / c.get("dir", "cache"),
        root=root,
    )

    if cfg.search.provider != "serpapi":
        raise ConfigError(
            f"未対応の検索プロバイダです: {cfg.search.provider}(現在は serpapi のみ)"
        )
    if cfg.search.candidates < 1:
        raise ConfigError("[search] candidates は 1 以上にしてください。")
    return cfg
