"""1社分の処理(検索 → ダウンロード → 背景削除 → トリミング → 保存)。

APIを無駄に呼ばないことを最優先に、各段階の結果を cache/ に残す。
同じ企業を再実行したときはキャッシュを使い、検索も remove.bg も呼ばない。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from PIL import Image

import bg_remove
import downloader
import naming
import trim as trim_mod
from config import Config
from report import LogoResult
from search.base import ImageCandidate, SearchError, SearchProvider


def _replace_with_retry(tmp: Path, dst: Path) -> None:
    """os.replace は Windows で読み取り中に一時的に失敗することがあるため少し粘る。"""
    for i in range(5):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, dst)


def _atomic_save_png(img: Image.Image, dst: Path) -> None:
    """一時ファイルに書いてから置き換える。

    書き込み途中のファイルが Web 配信や強制終了で外部に見えると、
    壊れた PNG がそのままキャッシュ・配信されてしまうため。
    """
    tmp = dst.with_name(dst.name + ".tmp")
    img.save(tmp, format="PNG")
    _replace_with_retry(tmp, dst)


def _atomic_write_bytes(data: bytes, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_bytes(data)
    _replace_with_retry(tmp, dst)


class CompanyCache:
    """1社分の中間生成物の置き場。"""

    def __init__(self, root: Path, company: str) -> None:
        self.dir = root / naming.safe_filename(company)
        self.search_json = self.dir / "search.json"
        self.removed_png = self.dir / "removed.png"
        self.meta_json = self.dir / "meta.json"

    def ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def load_candidates(self) -> list[ImageCandidate] | None:
        if not self.search_json.exists():
            return None
        try:
            raw = json.loads(self.search_json.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return [ImageCandidate(**item) for item in raw]

    def save_candidates(self, candidates: list[ImageCandidate]) -> None:
        self.ensure()
        payload = [
            {
                "url": c.url, "title": c.title, "width": c.width,
                "height": c.height, "source": c.source, "page_url": c.page_url,
            }
            for c in candidates
        ]
        self.search_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_meta(self) -> dict:
        if not self.meta_json.exists():
            return {}
        try:
            return json.loads(self.meta_json.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}

    def save_meta(self, meta: dict) -> None:
        self.ensure()
        self.meta_json.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def build_query(company: str, cfg: Config) -> str:
    name = naming.strip_legal(company) if cfg.search.strip_legal_suffix else company
    return cfg.search.query_template.format(name=name)


def process_company(
    company: str,
    cfg: Config,
    provider: SearchProvider,
    *,
    force: bool = False,
    skip_index: int = 0,
    retry: bool = False,
) -> LogoResult:
    """1社を処理する。

    retry=True のとき、前回使った候補(meta の used_rank)の次から取り直す。
    skip_index を直接指定した場合はそちらを優先する。
    """
    result = LogoResult(company=company)
    cache = CompanyCache(cfg.cache_dir, company)
    out_path = cfg.output.dir / f"{naming.safe_filename(company)}.png"

    if retry and skip_index == 0:
        # 「やり直し回数」ではなく「前回実際に使った候補の位置」を基準にする。
        # 候補0のダウンロードに失敗して候補1が使われていた場合でも、同じ画像を
        # もう一度処理してしまわないため。
        skip_index = int(cache.load_meta().get("used_rank", -1)) + 1

    # すでに出力があり、やり直し指定もなければ何も呼ばない
    if out_path.exists() and not force and skip_index == 0 and not retry:
        meta = cache.load_meta()
        result.ok = True
        result.from_cache = True
        result.png_path = out_path
        result.source_url = meta.get("source_url", "")
        result.source_domain = meta.get("source_domain", "")
        return result

    # --- 検索(キャッシュがあれば使う) ---
    candidates = None if force else cache.load_candidates()
    if candidates is None:
        try:
            candidates = provider.search_images(build_query(company, cfg), cfg.search.candidates)
        except SearchError as e:
            result.error = str(e)
            return result
        cache.save_candidates(candidates)

    ranked = downloader.rank(candidates, company)
    if not ranked:
        result.error = "処理できる画像候補がありませんでした。"
        return result

    # --- ダウンロード(上位から順に試す) ---
    downloaded = None
    used_rank = -1
    errors: list[str] = []
    for idx in range(skip_index, len(ranked)):
        cand = ranked[idx]
        result.tried_candidates.append(cand.url)
        try:
            downloaded = downloader.download(cand)
            used_rank = idx
            break
        except downloader.DownloadError as e:
            errors.append(f"{cand.domain or cand.url}: {e}")

    if downloaded is None:
        result.error = "候補をすべて取得できませんでした。" + (" / ".join(errors[:3]))
        return result

    result.source_url = downloaded.candidate.url
    result.source_domain = downloaded.candidate.domain

    # --- 背景削除(すでに透過ならスキップ。キャッシュがあれば再利用) ---
    # やり直しでは別候補の画像になるため、前回の透過結果は使えない
    if cache.removed_png.exists() and not force and skip_index == 0 and not retry:
        transparent = Image.open(cache.removed_png)
        transparent.load()
        transparent = transparent.convert("RGBA")
    elif downloader.has_transparency(downloaded.image):
        transparent = downloaded.image.convert("RGBA")
        cache.ensure()
        _atomic_save_png(transparent, cache.removed_png)
    else:
        png_bytes = bg_remove.remove_background(
            downloaded.data, cfg.removebg.api_key, size=cfg.removebg.size
        )
        cache.ensure()
        _atomic_write_bytes(png_bytes, cache.removed_png)
        transparent = bg_remove.to_image(png_bytes)
        result.used_removebg = True

    # --- トリミングと保存 ---
    final = trim_mod.process(
        transparent,
        padding_ratio=cfg.output.padding_ratio,
        max_long_edge=cfg.output.max_long_edge,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_save_png(final, out_path)

    cache.save_meta({
        "company": company,
        "source_url": result.source_url,
        "source_domain": result.source_domain,
        "used_removebg": result.used_removebg,
        "used_rank": used_rank,
    })

    result.ok = True
    result.png_path = out_path
    return result
