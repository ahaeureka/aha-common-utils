"""空默认占位符与残留占位符的契约（``${env:NAME:-}``）。

## 背景（实测缺陷）

``${env:NAME:-}``（**空默认**）在 ``config.toml`` 里是合法意图：「没配就用空」。
但解析正则的默认值分支是 ``(?::-([^}]+))?`` —— 要求默认值**至少一个字符** ——
于是整条占位符既不匹配、也不进入「未解析」名单：

```text
ENV_VAR_PATTERN.sub(...)  ->  '${env:OTLP_ENDPOINT:-}'   # 字面量原样留在配置里
unresolved_placeholders   ->  ()                          # 连告警都没有
```

结果是**静默的错误值**：配置里最终拿到的是一个像占位符的字符串，
（实测 ``settings.OTLP_ENDPOINT == '${env:OTLP_ENDPOINT:-}'``）。既不是空，
也没有任何一层报警。

## 本文件锁定两件事

1. 空默认被解析为**空串**（环境变量缺失时），且非空默认、环境变量优先等既有语义不变；
2. 插值结束后**仍残留的任何 ``${...}`` 形态必须被报告**（默认收集进 ``residual_placeholders``，
   可选硬失败并指明键路径）—— 「不可识别的占位符形态静默变成字面量」这条路径不可再达。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from aha_common_utils.config_base import BaseParameters
from aha_common_utils.config_store import ConfigStore

#: 参与断言的占位符名 —— 逐个从进程环境里摘掉，否则本机环境会决定测试结果。
PLACEHOLDER_ENV_NAMES = (
    "OTLP_ENDPOINT",
    "SENTRY_DSN",
    "EXAMPLE_VALUE",
    "NOT_A_REAL_ENV_NAME",
)


class PlaceholderConfig(BaseParameters):
    """最小配置模型：只放本文件用到的三个字段。"""

    OTLP_ENDPOINT: str = ""
    SENTRY_DSN: str = ""
    EXAMPLE_VALUE: str = "default"


def _load(
    tmp_path: Path,
    monkeypatch,
    toml_body: str,
    *,
    env: dict[str, str] | None = None,
    **kwargs: Any,
) -> tuple[ConfigStore, BaseParameters]:
    """写入一份 config.toml 并通过真实 ``ConfigStore.load`` 读取（含报告收集）。

    ``env`` 在清空占位符名**之后**注入 —— 顺序反了的话「本机恰好设了这个变量」
    与「测试设了这个变量」会混在一起（写成 fixture 时踩过一次）。
    """
    (tmp_path / "config.toml").write_text(toml_body, encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    for name in PLACEHOLDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)

    store = ConfigStore()
    config = store.load(PlaceholderConfig, base_dir=tmp_path, **kwargs)
    return store, config


def _field(config: BaseParameters, name: str) -> str:
    """按字段名取值（动态生成模型对类型检查器不可见）。"""
    return cast(str, cast(Any, config).__getattribute__(name))


# ── 1. 空默认被解析为空串 ────────────────────────────────────────────────


def test_empty_default_resolves_to_empty_string(tmp_path: Path, monkeypatch) -> None:
    """`${env:OTLP_ENDPOINT:-}` 在环境变量缺失时是**空串**，不是字面量。

    这是 qunapai `config.toml` 的真实写法（``[otel] otlp_endpoint`` / ``sentry_dsn``）。
    """
    _, config = _load(
        tmp_path,
        monkeypatch,
        'OTLP_ENDPOINT = "${env:OTLP_ENDPOINT:-}"\nSENTRY_DSN = "${env:SENTRY_DSN:-}"\n',
    )

    assert _field(config, "OTLP_ENDPOINT") == ""
    assert _field(config, "SENTRY_DSN") == ""


def test_non_empty_default_survives_when_env_is_absent(tmp_path: Path, monkeypatch) -> None:
    """非空默认照旧生效 —— 修空默认不能把带值的默认一起改坏。"""
    _, config = _load(tmp_path, monkeypatch, 'EXAMPLE_VALUE = "${env:EXAMPLE_VALUE:-fallback}"\n')

    assert _field(config, "EXAMPLE_VALUE") == "fallback"


def test_environment_value_beats_the_empty_default(tmp_path: Path, monkeypatch) -> None:
    """环境变量存在时空默认让位给环境变量（优先级没有被改写）。"""
    _, config = _load(
        tmp_path,
        monkeypatch,
        'OTLP_ENDPOINT = "${env:OTLP_ENDPOINT:-}"\n',
        env={"OTLP_ENDPOINT": "http://collector:4317"},
    )

    assert _field(config, "OTLP_ENDPOINT") == "http://collector:4317"


def test_empty_default_keeps_a_default_containing_colons(tmp_path: Path, monkeypatch) -> None:
    """默认值里带 ``:``（URL）仍然完整取出 —— 放宽空默认不能截断默认值。"""
    _, config = _load(tmp_path, monkeypatch, 'EXAMPLE_VALUE = "${env:EXAMPLE_VALUE:-http://h:9000/x}"\n')

    assert _field(config, "EXAMPLE_VALUE") == "http://h:9000/x"


# ── 2. 残留占位符必须被报告 ──────────────────────────────────────────────


def test_recognized_empty_default_leaves_no_residual(tmp_path: Path, monkeypatch) -> None:
    """本缺陷的回归探针：空默认**不再**以字面量形式残留。

    变异验证：把正则退回 ``(?::-([^}]+))?``，本用例即变红（值变回字面量、且残留非空）。
    """
    store, config = _load(tmp_path, monkeypatch, 'OTLP_ENDPOINT = "${env:OTLP_ENDPOINT:-}"\n')

    assert "${" not in _field(config, "OTLP_ENDPOINT")
    assert store.residual_placeholders == ()


def test_unknown_placeholder_form_is_reported_as_residual(tmp_path: Path, monkeypatch) -> None:
    """无法识别的形态（如 ``${NOT_ENV:NAME}``）必须被报告，而不是静默留在配置里。"""
    store, config = _load(tmp_path, monkeypatch, 'EXAMPLE_VALUE = "${NOT_ENV:NAME}"\n')

    assert _field(config, "EXAMPLE_VALUE") == "${NOT_ENV:NAME}", "值可以保留（无可替换内容），但必须被报告"
    assert store.residual_placeholders == (("EXAMPLE_VALUE", "${NOT_ENV:NAME}"),)


def test_unterminated_placeholder_is_reported_as_residual(tmp_path: Path, monkeypatch) -> None:
    """连右花括号都没有的形态同样被报告 —— 它也不会被正则匹配到。"""
    store, _ = _load(tmp_path, monkeypatch, 'EXAMPLE_VALUE = "${env:EXAMPLE_VALUE"\n')

    paths = [path for path, _ in store.residual_placeholders]
    tokens = [token for _, token in store.residual_placeholders]

    assert paths == ["EXAMPLE_VALUE"], "报告必须指明是哪个键"
    assert any(token.startswith("${") for token in tokens)


def test_residual_is_reported_with_its_key_path_when_rejected(tmp_path: Path, monkeypatch) -> None:
    """可选硬失败：拒绝时要同时给出**键路径**与残留 token，否则无法定位。"""
    (tmp_path / "config.toml").write_text('EXAMPLE_VALUE = "${NOT_ENV:NAME}"\n', encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    for name in PLACEHOLDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError) as excinfo:
        ConfigStore().load(PlaceholderConfig, base_dir=tmp_path, reject_residual_placeholders=True)

    message = str(excinfo.value)
    assert "EXAMPLE_VALUE" in message
    assert "${NOT_ENV:NAME}" in message


def test_bare_placeholder_without_default_still_uses_the_unresolved_report(tmp_path: Path, monkeypatch) -> None:
    """既有语义不变：``${env:NAME}``（无默认）仍走未解析报告，并被替换为空串。"""
    store, config = _load(
        tmp_path,
        monkeypatch,
        'EXAMPLE_VALUE = "${env:NOT_A_REAL_ENV_NAME}"\n',
        blank_unresolved_placeholders=True,
    )

    assert _field(config, "EXAMPLE_VALUE") == ""
    assert store.unresolved_placeholders == ("NOT_A_REAL_ENV_NAME",)
    assert store.residual_placeholders == ()


# ── 3. config_base 自己的插值路径（不经过 ConfigStore） ──────────────────


def test_base_parameters_from_dict_resolves_empty_default() -> None:
    """``BaseParameters.from_dict`` 走的是另一份正则，必须同样解析空默认。"""
    config = PlaceholderConfig.from_dict({"OTLP_ENDPOINT": "${env:OTLP_ENDPOINT:-}"})

    assert _field(config, "OTLP_ENDPOINT") == ""
