# aha-common-utils — 配置文件加载系统使用手册

## 目录

- [概述](#概述)
- [快速上手](#快速上手)
- [配置加载优先级](#配置加载优先级)
- [支持的配置文件格式](#支持的配置文件格式)
  - [TOML 配置文件](#toml-配置文件)
  - [YAML 配置文件](#yaml-配置文件)
  - [.env.local 敏感文件](#envlocal-敏感文件)
  - [环境变量](#环境变量)
- [配置文件命名与发现规则](#配置文件命名与发现规则)
- [SecureBaseSettings 基类](#securebasesettings-基类)
  - [基本用法](#基本用法)
  - [手动指定配置文件路径](#手动指定配置文件路径)
  - [敏感字段自动屏蔽](#敏感字段自动屏蔽)
  - [生产安全校验](#生产安全校验)
  - [safe_dump()](#safe_dump)
- [项目文件布局参考](#项目文件布局参考)
- [环境变量 APP\_ENV](#环境变量-app_env)
- [工具函数 API](#工具函数-api)
- [配置文件示例](#配置文件示例)
- [常见问题](#常见问题)

---

## 概述

`aha-common-utils` 提供了一套 **安全分层配置加载系统**，基于 [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 构建。核心设计原则：

1. **分层覆盖** — 多来源配置按优先级依次覆盖，灵活适配 `开发 / 测试 / 生产` 各环境。
2. **格式多样** — 同时支持 TOML、YAML、`.env`、进程环境变量。
3. **安全优先** — 敏感字段自动屏蔽、生产环境默认值校验、敏感信息与版本库隔离。
4. **零配置启动** — 只要在项目根目录放置约定名称的配置文件，即可自动发现并加载。

---

## 快速上手

### 1. 安装依赖

```bash
uv add aha-common-utils
```

### 2. 定义配置类

```python
from aha_common_utils.settings import SecureBaseSettings
from pydantic_settings import SettingsConfigDict

class AppSettings(SecureBaseSettings):
    model_config = SettingsConfigDict(env_prefix="MYAPP_")

    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://localhost/dev"
    SECRET_KEY: str = "change-me-in-production"
    LOG_LEVEL: str = "INFO"
    LLM_API_KEY: str = ""
```

### 3. 放置配置文件

在项目根目录（含 `pyproject.toml` 的目录）创建：

```
myproject/
├── pyproject.toml
├── config.toml                    # 基础默认配置（提交版本库）
├── config.development.toml        # 开发环境覆盖（提交版本库）
├── config.production.toml         # 生产环境覆盖（提交版本库）
├── .env.local                     # 敏感值（已 .gitignore，不提交）
└── main.py
```

### 4. 实例化并使用

```python
settings = AppSettings()

# 安全打印（敏感字段被屏蔽）
print(settings)
# AppSettings(APP_ENV='development', DATABASE_URL='post****', SECRET_KEY='chan****', ...)

# 获取安全字典（适合日志输出）
print(settings.safe_dump())
```

---

## 配置加载优先级

加载优先级 **从低到高** 排列如下——后加载的值会 **覆盖** 先加载的同名字段：

| 优先级 | 来源 | 说明 | 提交版本库 |
|:---:|------|------|:---:|
| 1（最低） | 代码默认值 | Settings 类中声明的字段默认值 | ✅ |
| 2 | `config.yaml` / `config.yml` | YAML 基础非敏感配置 | ✅ |
| 3 | `config.<APP_ENV>.yaml/yml` | YAML 环境专属覆盖 | ✅ |
| 4 | `config.toml` | TOML 基础非敏感配置 | ✅ |
| 5 | `config.<APP_ENV>.toml` | TOML 环境专属覆盖 | ✅ |
| 6 | `.env.local` | 仅存放敏感值（密码/API Key） | ❌ |
| 7（最高） | 进程环境变量 | 容器/CI 注入，最终覆盖 | — |

> **示例**：如果 `config.toml` 中设置了 `LOG_LEVEL = "INFO"`，而 `config.development.toml` 中设置了 `LOG_LEVEL = "DEBUG"`，则开发环境最终值为 `"DEBUG"`。环境变量 `LOG_LEVEL=WARNING` 可以覆盖以上所有。

> **提示**：TOML 和 YAML 配置文件可以同时存在。TOML 的优先级高于 YAML，因此当两者定义了相同字段时，TOML 中的值会生效。

---

## 支持的配置文件格式

### TOML 配置文件

标准 [TOML](https://toml.io/) 格式，**推荐作为主配置格式**。

```toml
# config.toml — 基础默认配置
APP_ENV   = "development"
APP_NAME  = "skillforge"
DEBUG     = false
LOG_LEVEL = "INFO"

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
REDIS_URL    = "redis://localhost:6379/0"

DEFAULT_LLM_MODEL = "openai:gpt-4o-mini"
```

```toml
# config.development.toml — 开发环境覆盖
DEBUG     = true
LOG_LEVEL = "DEBUG"

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge_dev"
```

自动发现的文件名：
- `config.toml` — 基础配置
- `config.<APP_ENV>.toml` — 环境配置（如 `config.development.toml`、`config.production.toml`）

### YAML 配置文件

标准 [YAML](https://yaml.org/) 格式，适合习惯 YAML 的团队或需要嵌套结构的场景。

```yaml
# config.yaml — 基础默认配置
APP_ENV: development
APP_NAME: skillforge
DEBUG: false
LOG_LEVEL: INFO

DATABASE_URL: "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
REDIS_URL: "redis://localhost:6379/0"
```

```yaml
# config.development.yaml — 开发环境覆盖
DEBUG: true
LOG_LEVEL: DEBUG
```

自动发现的文件名（`.yaml` 优先于 `.yml`）：
- `config.yaml` 或 `config.yml` — 基础配置
- `config.<APP_ENV>.yaml` 或 `config.<APP_ENV>.yml` — 环境配置

> **注意**：同一优先级层级中，`.yaml` 和 `.yml` 只会加载其中一个，`.yaml` 优先。

### .env.local 敏感文件

标准 dotenv 格式，**仅存放敏感值**，**必须加入 `.gitignore`**。

```bash
# .env.local — 个人本地敏感变量，绝不提交版本库
SECRET_KEY=my-super-secret-key-xxxxxxxxxxxxxxxx
LLM_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx
DATABASE_URL=postgresql+asyncpg://user:real-password@localhost:5432/mydb
SENTRY_DSN=https://xxxxxx@sentry.io/12345
```

### 环境变量

进程环境变量拥有 **最高优先级**，适合在容器编排（Docker/K8s）或 CI/CD 中注入：

```bash
export APP_ENV=production
export SECRET_KEY=prod-secret-xxxxxxxx
export DATABASE_URL=postgresql+asyncpg://user:pass@db-prod:5432/app
```

如果 Settings 子类配置了 `env_prefix`，环境变量名需要加上前缀：

```python
class AppSettings(SecureBaseSettings):
    model_config = SettingsConfigDict(env_prefix="MYAPP_")
    LOG_LEVEL: str = "INFO"

# 对应的环境变量名：MYAPP_LOG_LEVEL=DEBUG
```

---

## 配置文件命名与发现规则

系统通过 `find_project_root()` 自动定位项目根目录（向上查找包含 `pyproject.toml` 的最近目录），然后在该目录中查找约定名称的配置文件。

### 自动发现列表

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `config.toml` | TOML | 基础默认值 |
| `config.<APP_ENV>.toml` | TOML | 环境专属覆盖（如 `config.production.toml`） |
| `config.yaml` | YAML | 基础默认值 |
| `config.yml` | YAML | 基础默认值（`config.yaml` 不存在时使用） |
| `config.<APP_ENV>.yaml` | YAML | 环境专属覆盖 |
| `config.<APP_ENV>.yml` | YAML | 环境专属覆盖（`.yaml` 不存在时使用） |
| `.env.local` | dotenv | 敏感值（⚠️ 不提交版本库） |

所有文件均为 **可选**。只存在的文件才会被加载，不存在的文件会被安静跳过。

---

## SecureBaseSettings 基类

### 基本用法

所有需要分层配置加载的 Settings 类应继承 `SecureBaseSettings`，而非直接继承 `pydantic_settings.BaseSettings`：

```python
from aha_common_utils.settings import SecureBaseSettings
from pydantic_settings import SettingsConfigDict

class AppSettings(SecureBaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYAPP_",    # 可选：环境变量前缀
    )

    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://localhost/dev"
    SECRET_KEY: str = "change-me-in-production"
    LOG_LEVEL: str = "INFO"

settings = AppSettings()
```

### 手动指定配置文件路径

如果不想使用自动发现，可以在 `model_config` 中显式指定文件路径：

```python
class AppSettings(SecureBaseSettings):
    model_config = SettingsConfigDict(
        toml_file="path/to/custom.toml",    # 指定 TOML 文件
    )
    # ...
```

```python
class AppSettings(SecureBaseSettings):
    model_config = SettingsConfigDict(
        yaml_file="path/to/custom.yaml",    # 指定 YAML 文件
    )
    # ...
```

> 设置 `toml_file` 时会跳过 TOML 自动探测，但 YAML 自动探测不受影响（反之亦然）。

### 敏感字段自动屏蔽

字段名中包含以下关键词时，会被自动识别为敏感字段，在 `__repr__` / `__str__` / `safe_dump()` 中被屏蔽：

```
password, passwd, secret, api_key, apikey, token, private_key,
access_key, secret_key, dsn, auth, credential, database_url, redis_url
```

屏蔽效果示例：

```python
>>> print(settings)
AppSettings(APP_ENV='development', DATABASE_URL='post****', SECRET_KEY='chan****')

>>> settings.safe_dump()
{'APP_ENV': 'development', 'DATABASE_URL': 'post****', 'SECRET_KEY': 'chan****'}
```

#### 追加自定义敏感字段

子类可通过 `_EXTRA_SENSITIVE_FIELDS` 类变量添加额外的敏感字段名（精确匹配，忽略大小写）：

```python
class AppSettings(SecureBaseSettings):
    _EXTRA_SENSITIVE_FIELDS = {"INTERNAL_ADMIN_TOKEN", "WEBHOOK_SECRET"}

    INTERNAL_ADMIN_TOKEN: str = ""
    WEBHOOK_SECRET: str = ""
```

### 生产安全校验

当 `APP_ENV=production` 时，系统会在实例化时自动检测敏感字段是否仍为已知的不安全默认值。如果检测到，会 **立即抛出 `ValueError`**，阻止应用启动。

已知不安全默认值包括：

```
change-me-in-production, changeme, change_me, secret, password,
postgres, admin, your-secret-key, dev-only
```

```python
# 生产环境中以下代码会抛出 ValueError：
class AppSettings(SecureBaseSettings):
    SECRET_KEY: str = "change-me-in-production"

# ValueError: [Security] 生产环境中字段 'SECRET_KEY' 使用了不安全的默认值: 'change-me-in-production'。
#             请在 .env.local 或进程环境变量中覆盖为强值。
```

### safe_dump()

返回屏蔽了敏感字段的配置字典，适合用于启动日志或诊断 API 端点：

```python
import json

settings = AppSettings()
print(json.dumps(settings.safe_dump(), indent=2, ensure_ascii=False))
```

---

## 项目文件布局参考

```
myproject/
├── pyproject.toml                  # 项目定义 (用于定位项目根目录)
│
├── config.toml                     # ✅ 提交 — 基础非敏感默认值
├── config.development.toml         # ✅ 提交 — 开发环境覆盖
├── config.test.toml                # ✅ 提交 — 测试环境覆盖
├── config.production.toml          # ✅ 提交 — 生产环境覆盖
│
├── config.yaml                     # ✅ 提交 — (可选) YAML 基础配置
├── config.development.yaml         # ✅ 提交 — (可选) YAML 开发覆盖
│
├── .env.local                      # ❌ gitignore — 密码/API Key 等敏感值
├── .gitignore                      # 必须包含 .env.local
│
└── src/
    └── myapp/
        └── config.py               # 配置类定义
```

`.gitignore` 中确保包含：

```gitignore
.env.local
```

---

## 环境变量 APP_ENV

`APP_ENV` 是核心环境变量，决定：

1. 加载哪个环境配置文件（`config.<APP_ENV>.toml` / `config.<APP_ENV>.yaml`）
2. 是否启用生产安全校验

| APP_ENV | 说明 | 安全校验 |
|---------|------|:---:|
| `development`（默认） | 本地开发 | ❌ |
| `test` | 单元/集成测试 | ❌ |
| `production` | 生产环境 | ✅ |

设置方式：

```bash
# 环境变量（推荐在容器/CI 中使用）
export APP_ENV=production

# config.toml 中设置默认值
APP_ENV = "development"
```

---

## 工具函数 API

所有工具函数均可从 `aha_common_utils.settings` 导入：

```python
from aha_common_utils.settings import (
    find_project_root,
    build_toml_config_files,
    build_yaml_config_files,
    build_sensitive_env_file,
    build_layered_env_files,   # 已废弃，向后兼容
    is_sensitive_field,
    mask_value,
)
```

### find_project_root(start=None) → Path

从 `start`（默认 cwd）向上查找包含 `pyproject.toml` 的最近目录。

```python
>>> from aha_common_utils.settings import find_project_root
>>> root = find_project_root()
>>> print(root)
/app
```

### build_toml_config_files(base_dir=None, app_env=None) → list[Path]

返回磁盘上实际存在的 TOML 配置文件列表，按优先级从低到高排列。

```python
>>> from aha_common_utils.settings import build_toml_config_files
>>> files = build_toml_config_files()
>>> [f.name for f in files]
['config.toml', 'config.development.toml']
```

### build_yaml_config_files(base_dir=None, app_env=None) → list[Path]

返回磁盘上实际存在的 YAML 配置文件列表，按优先级从低到高排列。同一层级中 `.yaml` 优先于 `.yml`。

```python
>>> from aha_common_utils.settings import build_yaml_config_files
>>> files = build_yaml_config_files()
>>> [f.name for f in files]
['config.yaml', 'config.development.yaml']
```

### build_sensitive_env_file(base_dir=None) → Path | None

返回 `.env.local` 的路径（若存在），否则返回 `None`。

```python
>>> from aha_common_utils.settings import build_sensitive_env_file
>>> p = build_sensitive_env_file()
>>> print(p)
/app/.env.local
```

### is_sensitive_field(field_name) → bool

判断字段名是否对应敏感信息。

```python
>>> from aha_common_utils.settings import is_sensitive_field
>>> is_sensitive_field("DATABASE_URL")
True
>>> is_sensitive_field("LOG_LEVEL")
False
```

### mask_value(value) → str

将值屏蔽为安全的显示字符串，保留前 4 位。

```python
>>> from aha_common_utils.settings import mask_value
>>> mask_value("sk-proj-abc123")
'sk-p****'
```

---

## 配置文件示例

### TOML 格式

```toml
# config.toml — 基础默认配置（非敏感，提交版本库）
APP_ENV              = "development"
APP_NAME             = "skillforge"
DEBUG                = false
LOG_LEVEL            = "INFO"

DATABASE_URL         = "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
REDIS_URL            = "redis://localhost:6379/0"

DEFAULT_LLM_MODEL   = "openai:gpt-4o-mini"
LLM_BASE_URL         = ""
LLM_DAILY_BUDGET_USD = 10.0
```

```toml
# config.production.toml — 生产环境覆盖
APP_ENV   = "production"
DEBUG     = false
LOG_LEVEL = "WARNING"

LLM_DAILY_BUDGET_USD = 100.0
```

### YAML 格式

```yaml
# config.yaml — 基础默认配置
APP_ENV: development
APP_NAME: skillforge
DEBUG: false
LOG_LEVEL: INFO

DATABASE_URL: "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
REDIS_URL: "redis://localhost:6379/0"

DEFAULT_LLM_MODEL: "openai:gpt-4o-mini"
```

```yaml
# config.production.yaml — 生产环境覆盖
APP_ENV: production
DEBUG: false
LOG_LEVEL: WARNING
```

### .env.local

```bash
# .env.local — 敏感值（绝不提交版本库）
SECRET_KEY=a7f3b2e1-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LLM_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_URL=postgresql+asyncpg://user:strong-password@db-host:5432/mydb
SENTRY_DSN=https://key@sentry.io/12345
```

---

## 常见问题

### Q: TOML 和 YAML 可以同时使用吗？

**可以。** 两种格式的配置文件会同时被加载。TOML 优先级高于 YAML，因此当两者定义了相同字段时，TOML 文件中的值会生效。

### Q: 如何仅使用 YAML 而不使用 TOML？

只需不在项目根目录放 `config.toml` / `config.<env>.toml` 文件即可。系统只加载磁盘上实际存在的文件。

### Q: 配置类声明中没有的字段，配置文件中写了会报错吗？

不会。基类默认配置了 `extra="ignore"`，未声明的字段会被安静忽略。

### Q: 如何在测试中覆盖配置？

可以通过构造函数参数直接传入（`init_settings` 优先级最高）：

```python
settings = AppSettings(DATABASE_URL="sqlite+aiosqlite:///test.db")
```

或设置环境变量：

```python
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
settings = AppSettings()
```

### Q: 从旧的 `layered_settings` 模块迁移需要改什么？

将导入路径从：

```python
from aha_common_utils.layered_settings import SecureBaseSettings
```

改为：

```python
from aha_common_utils.settings import SecureBaseSettings
```

旧路径仍可用但已废弃，未来版本将移除。

### Q: 如何自定义项目根目录？

使用 `build_toml_config_files` / `build_yaml_config_files` 的 `base_dir` 参数：

```python
from pathlib import Path
from aha_common_utils.settings import build_toml_config_files

files = build_toml_config_files(base_dir=Path("/custom/path"))
```

### Q: pydantic-settings 版本要求？

需要 `pydantic-settings >= 2.7.0`，因为 `YamlConfigSettingsSource` 是在该版本引入的。项目 `pyproject.toml` 中已声明此依赖。

---

## 其他使用手册

- [日志系统使用手册](docs/logging.md) — Loguru + OpenTelemetry 上下文注入、文件轮转、请求 ID 注入
- [链路追踪使用手册](docs/tracing.md) — OpenTelemetry Tracing 初始化、FastAPI 中间件、Span 操作
