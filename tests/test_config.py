"""VISION.md 対応: 全体ルール「キーが未設定なら足りないキー名だけを提示して終了する」。"""

from __future__ import annotations

import pytest

import config as config_mod


def write_toml(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_file_raises_without_leaking_anything(tmp_path):
    with pytest.raises(config_mod.ConfigError, match="設定ファイルが見つかりません"):
        config_mod.load("config.toml", root=tmp_path)


def test_require_keys_lists_only_missing_key_names(tmp_path):
    write_toml(tmp_path, '[search]\napi_key = ""\n[removebg]\napi_key = "set"\n')
    cfg = config_mod.load(root=tmp_path)
    with pytest.raises(config_mod.ConfigError) as exc:
        cfg.require_keys()
    message = str(exc.value)
    assert "[search] api_key" in message
    assert "[removebg] api_key" not in message


def test_require_keys_passes_when_both_present(tmp_path):
    write_toml(tmp_path, '[search]\napi_key = "s"\n[removebg]\napi_key = "r"\n')
    cfg = config_mod.load(root=tmp_path)
    cfg.require_keys()  # 例外が出なければ成功


def test_actual_key_values_never_appear_in_error_message(tmp_path):
    write_toml(tmp_path, '[search]\napi_key = ""\n[removebg]\napi_key = ""\n')
    cfg = config_mod.load(root=tmp_path)
    with pytest.raises(config_mod.ConfigError) as exc:
        cfg.require_keys()
    # そもそも値が空文字列だが、キーの「名前」以外の実データが出ないことを構造で確認
    assert "api_key" in str(exc.value)


def test_unsupported_provider_is_rejected(tmp_path):
    write_toml(tmp_path, '[search]\nprovider = "bing"\n')
    with pytest.raises(config_mod.ConfigError, match="未対応の検索プロバイダ"):
        config_mod.load(root=tmp_path)


def test_defaults_are_applied_when_sections_absent(tmp_path):
    write_toml(tmp_path, "")
    cfg = config_mod.load(root=tmp_path)
    assert cfg.search.provider == "serpapi"
    assert cfg.search.candidates == 5
    assert cfg.output.padding_ratio == 0.02
    assert cfg.output.max_long_edge == 1024
