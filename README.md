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

# 日志系统使用手册

## 目录

- [概述](#日志概述)
- [快速上手](#日志快速上手)
- [初始化 init_logging / setup_logging](#初始化-init_logging--setup_logging)
- [获取 Logger](#获取-logger)
- [日志级别](#日志级别)
- [携带业务 extra 字段](#携带业务-extra-字段)
- [请求 ID 注入](#请求-id-注入)
- [日志输出格式](#日志输出格式)
- [日志文件轮转](#日志文件轮转)
- [OpenTelemetry 上下文自动注入](#opentelemetry-上下文自动注入)
- [与 FastAPI lifespan 集成](#与-fastapi-lifespan-集成)
- [日志常见问题](#日志常见问题)

---

## 日志概述

日志系统基于 [Loguru](https://github.com/Delgan/loguru) 构建，并自动注入 [OpenTelemetry](https://opentelemetry.io/) 的 `trace_id` / `span_id`，实现日志与链路追踪的天然关联。核心特性：

- **结构化格式** — 每行日志包含时间、级别、模块位置、trace/span ID、消息
- **OTel 上下文自动注入** — 日志自动携带当前活跃 Span 的 trace_id 和 span_id
- **双路输出** — 同时输出到 stderr（带颜色）和日志文件（纯文本）
- **日志文件轮转** — 按天轮转，自动压缩，错误日志单独存档
- **业务 extra 字段** — 支持在日志中携带任意业务 KV 信息
- **多进程安全** — 文件写入使用 `enqueue=True`

---

## 日志快速上手

```python
# 1. 应用启动时初始化（只需调用一次）
from aha_common_utils.logging import setup_logging

setup_logging(level="INFO", log_dir="logs")

# 2. 各模块中获取 logger
from aha_common_utils.logging import get_logger

logger = get_logger(__name__)

# 3. 记录日志
logger.info("应用启动成功")
logger.debug("调试信息")
logger.warning("注意事项")
logger.error("发生错误")
logger.critical("严重故障")
```

---

## 初始化 init_logging / setup_logging

```python
from aha_common_utils.log import init_logging
# 或等价的高层封装：
from aha_common_utils.logging import setup_logging
```

### 函数签名

```python
def init_logging(level: str = "DEBUG", log_dir: str = "logs") -> None: ...
def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None: ...
```

`setup_logging` 是 `init_logging` 的高层封装，默认级别为 `"INFO"`；`init_logging` 默认级别为 `"DEBUG"`。

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | `str` | `"INFO"` / `"DEBUG"` | 日志最低输出级别 |
| `log_dir` | `str` | `"logs"` | 日志文件输出目录；传空字符串 `""` 则仅输出到控制台 |

### 调用示例

```python
# 仅输出到控制台（不写文件）
setup_logging(level="DEBUG", log_dir="")

# 输出到控制台 + logs/ 目录
setup_logging(level="INFO", log_dir="logs")

# 输出到自定义目录
setup_logging(level="WARNING", log_dir="/var/log/myapp")
```

> **注意**：`init_logging` / `setup_logging` 不会在模块加载时自动调用，必须在应用启动阶段显式调用一次。

---

## 获取 Logger

```python
from aha_common_utils.logging import get_logger

# 推荐：传入模块名，日志来源字段显示为准确的模块路径
logger = get_logger(__name__)

# 不传名称时使用全局 loguru logger
logger = get_logger()
```

`get_logger(__name__)` 与直接使用 `from loguru import logger` 的区别：前者将 `__name__` 绑定为 `extra["name"]` 字段，日志中的 `name` 字段会显示为调用方模块路径，而非 loguru 内部模块名。

---

## 日志级别

| 级别 | 方法 | 适用场景 |
|------|------|----------|
| `TRACE` | `logger.trace()` | 极细粒度调试（默认不显示） |
| `DEBUG` | `logger.debug()` | 开发调试信息 |
| `INFO` | `logger.info()` | 正常运行流程事件 |
| `SUCCESS` | `logger.success()` | 操作成功（Loguru 特有） |
| `WARNING` | `logger.warning()` | 非预期但可恢复的情况 |
| `ERROR` | `logger.error()` | 发生错误，需关注 |
| `CRITICAL` | `logger.critical()` | 严重故障，系统不可用 |

各环境建议级别：

| 环境 | 推荐级别 |
|------|---------|
| `development` | `DEBUG` |
| `test` | `WARNING` |
| `production` | `INFO` 或 `WARNING` |

---

## 携带业务 extra 字段

Loguru 支持在单次日志调用或绑定时携带任意 KV 字段，这些字段会出现在日志行末尾（`| key='value' ...` 格式）：

```python
# 方式 1：bind() 创建绑定了字段的子 logger，适合请求级上下文
request_logger = logger.bind(user_id="u-123", request_id="r-abc")
request_logger.info("开始处理请求")
request_logger.info("请求处理完成")

# 方式 2：单条日志绑定
logger.bind(order_id="o-789", amount=99.9).info("订单创建成功")
```

输出示例：

```
2026-03-18 10:23:45.123 | INFO | myapp:api.py:handle:42 | [trace_id=abc span_id=def] | 订单创建成功 | amount=99.9 order_id='o-789'
```

内部保留字段（`name`、`otelSpanID`、`otelTraceID` 等）会被自动过滤，不出现在 `businessExtra` 中。

---

## 请求 ID 注入

日志模块暴露了 `request_id_var`（`ContextVar[str]`），供中间件注入请求级追踪 ID。当 OTel 无活跃 Span 时，`otelTraceID` 字段会回退使用此值：

```python
from aha_common_utils.log import request_id_var
import uuid

# 在 HTTP 中间件中注入
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_var.set(req_id)
    try:
        return await call_next(request)
    finally:
        request_id_var.reset(token)
```

---

## 日志输出格式

```
2026-03-18 10:23:45.123 | INFO     | myapp.api:api.py:handle:42 | [trace_id=abc123… span_id=def456…] | 请求处理完成 | order_id='o-789'
```

| 字段 | 说明 |
|------|------|
| 时间戳 | 毫秒精度 |
| 级别 | 右对齐 8 位 |
| `name:file:function:line` | 模块名、文件名、函数名、行号 |
| `trace_id` | OTel trace ID（无活跃 Span 时为 `0` 或 request_id） |
| `span_id` | OTel span ID（无活跃 Span 时为 `0`） |
| 消息 | 日志文本 |
| `businessExtra` | 业务 KV 字段（有则追加 `\| key=value …`，无则省略） |

---

## 日志文件轮转

`init_logging` 在 `log_dir` 下创建两类日志文件：

| 文件名模式 | 最低级别 | 轮转时间 | 保留时长 | 压缩格式 |
|-----------|---------|---------|---------|---------|
| `app_YYYY-MM-DD.log` | ≥ `level` 参数 | 每天 00:00 | 30 天 | zip |
| `error_YYYY-MM-DD.log` | ERROR+ | 每天 00:00 | 7 天 | zip |

文件写入使用 `enqueue=True`，保证多进程/多线程安全。

---

## OpenTelemetry 上下文自动注入

日志模块在每条记录写入前，通过 Loguru 的 `patcher` 机制自动注入以下字段：

| 字段 | 来源 | 说明 |
|------|------|------|
| `otelTraceID` | 当前活跃 OTel Span | 32 位十六进制 |
| `otelSpanID` | 当前活跃 OTel Span | 16 位十六进制 |
| `otelTraceSampled` | 当前活跃 OTel Span | 是否被采样 |
| `otelServiceName` | TracerProvider resource | 服务名称 |

无活跃 Span 时，`otelTraceID` 回退到 `request_id_var` 注入的值；若两者均无，显示为 `"0"`。

---

## 与 FastAPI lifespan 集成

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aha_common_utils.logging import setup_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level="INFO", log_dir="logs")
    yield

app = FastAPI(lifespan=lifespan)
```

---

## 日志常见问题

### Q: 日志中 trace_id 一直显示 0？

说明没有活跃的 OTel Span 且 `request_id_var` 未注入。确保已调用 `setup_tracing()` 并安装了请求追踪中间件（见下方 Tracing 手册）。

### Q: 如何关闭文件日志输出？

```python
setup_logging(level="DEBUG", log_dir="")
```

### Q: 如何在测试中屏蔽所有日志输出？

```python
import loguru
loguru.logger.disable("")   # 禁用所有模块的日志
```

### Q: 多次调用 setup_logging 会怎样？

Loguru 的 `logger.remove()` 在 `init_logging` 内部每次都会清除已有 handler 再重新添加，多次调用是安全的，但会导致之前自定义的 handler 丢失。建议只在应用启动时调用一次。

---

# 链路追踪（Tracing）使用手册

## 目录

- [概述](#tracing-概述)
- [快速上手](#tracing-快速上手)
- [setup_tracing — 初始化追踪](#setup_tracing--初始化追踪)
- [install_fastapi_trace_middleware — HTTP 请求追踪](#install_fastapi_trace_middleware--http-请求追踪)
- [get_tracer — 获取 Tracer](#get_tracer--获取-tracer)
- [Span 操作参考](#span-操作参考)
- [与日志关联](#与日志关联)
- [与 FastAPI lifespan 完整集成](#与-fastapi-lifespan-完整集成)
- [Tracing 常见问题](#tracing-常见问题)

---

## Tracing 概述

链路追踪模块基于 [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/) 构建，提供：

- **统一初始化** — 一行代码完成 TracerProvider + OTLP 导出器配置
- **FastAPI 中间件** — 自动为每个 HTTP 请求创建根 Span，命名为 `METHOD /path`
- **日志关联** — trace_id / span_id 自动注入到日志，实现日志与链路的双向关联
- **幂等安装** — 中间件防重复注册，可安全多次调用

---

## Tracing 快速上手

```python
from fastapi import FastAPI
from aha_common_utils.tracing import setup_tracing, install_fastapi_trace_middleware, get_tracer

app = FastAPI()

# 1. 初始化 TracerProvider（应用启动时调用一次）
setup_tracing(
    service_name="my-service",
    otlp_endpoint="http://localhost:4317",
)

# 2. 安装 HTTP 请求自动追踪中间件
install_fastapi_trace_middleware(app)

# 3. 业务代码中手动创建子 Span
tracer = get_tracer(__name__)

def process_order(order_id: str):
    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.id", order_id)
        # ... 业务逻辑
```

---

## setup_tracing — 初始化追踪

```python
from aha_common_utils.tracing import setup_tracing
```

### 函数签名

```python
def setup_tracing(
    service_name: str = "app",
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False,
) -> trace.Tracer:
    ...
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `service_name` | `str` | `"app"` | 服务名称，显示在 Jaeger / Grafana Tempo 等追踪后端中；也会注入到日志的 `otelServiceName` 字段 |
| `otlp_endpoint` | `str \| None` | `None` | OTLP gRPC 导出端点（如 `"http://otel-collector:4317"`）；为 `None` 时不导出 Span |
| `enable_console` | `bool` | `False` | 将 Span 数据打印到控制台，仅用于本地调试 |

### 返回值

返回一个以 `aha_common_utils.tracing` 为 instrumentation 名称的 `trace.Tracer` 实例。

### 调用示例

```python
# 生产：导出到 OTLP Collector
setup_tracing(
    service_name="skillforge-api",
    otlp_endpoint="http://otel-collector:4317",
)

# 开发：打印到控制台（不需要 Collector）
setup_tracing(
    service_name="skillforge-api",
    enable_console=True,
)

# 最小化：仅初始化 Provider（日志中 trace_id / otelServiceName 仍会注入）
setup_tracing(service_name="my-service")
```

---

## install_fastapi_trace_middleware — HTTP 请求追踪

```python
from aha_common_utils.tracing import install_fastapi_trace_middleware
```

### 函数签名

```python
def install_fastapi_trace_middleware(
    app: FastAPI,
    tracer_name: str = "aha_common_utils.tracing",
) -> None:
    ...
```

为 FastAPI 安装请求级 Tracing 中间件。每个 HTTP 请求会自动创建一个根 Span，名称为 `"METHOD /path"`，例如：

```
GET /api/v1/users
POST /api/v1/orders
```

> **幂等保证**：通过 `app.state._trace_middleware_installed` 标记防止重复安装，可以安全多次调用。

---

## get_tracer — 获取 Tracer

```python
from aha_common_utils.tracing import get_tracer

tracer = get_tracer(__name__)
```

### 函数签名

```python
def get_tracer(name: str = "aha_common_utils.tracing") -> trace.Tracer:
    ...
```

获取一个以 `name` 为 instrumentation library 名称的 `Tracer` 实例。业务代码始终传入 `__name__`。

---

## Span 操作参考

### 创建子 Span（同步）

```python
tracer = get_tracer(__name__)

with tracer.start_as_current_span("do_something") as span:
    span.set_attribute("item.id", item_id)
    span.set_attribute("item.count", 10)
    result = do_something()
```

### 创建子 Span（异步）

```python
async def fetch_data(user_id: str):
    with tracer.start_as_current_span("fetch_user_data") as span:
        span.set_attribute("user.id", user_id)
        data = await db.get_user(user_id)
        return data
```

### 记录异常

```python
with tracer.start_as_current_span("risky_operation") as span:
    try:
        result = risky_operation()
    except Exception as e:
        span.record_exception(e)
        span.set_status(trace.StatusCode.ERROR, str(e))
        raise
```

### 添加事件（时间点标记）

```python
with tracer.start_as_current_span("process_batch") as span:
    span.add_event("batch_started", {"batch.size": 100})
    process()
    span.add_event("batch_completed")
```

### 读取当前 Span 的 trace_id / span_id

```python
from opentelemetry.trace import get_current_span

span = get_current_span()
ctx = span.get_span_context()
trace_id = format(ctx.trace_id, "032x")
span_id  = format(ctx.span_id,  "016x")
```

---

## 与日志关联

`setup_tracing()` 初始化后，日志系统（`log.py`）中的 `_add_trace_context` patcher 会自动将当前 Span 的上下文注入到每条日志记录中：

```
2026-03-18 10:23:45.123 | INFO | myapp.api:api.py:process:58 | [trace_id=a1b2c3d4e5f6… span_id=7890abcd…] | 订单处理完成
```

在 Grafana / Jaeger / Tempo 等工具中，可以直接用日志中的 `trace_id` 跳转到对应的完整请求链路。

---

## 与 FastAPI lifespan 完整集成

推荐的完整启动配置（Tracing + Logging + 中间件）：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aha_common_utils.logging import setup_logging
from aha_common_utils.tracing import setup_tracing, install_fastapi_trace_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 顺序：1. Tracing  2. Logging  3. 中间件
    setup_tracing(
        service_name="skillforge-api",
        otlp_endpoint="http://otel-collector:4317",
    )
    setup_logging(level="INFO", log_dir="logs")
    install_fastapi_trace_middleware(app)
    yield

app = FastAPI(lifespan=lifespan)
```

---

## Tracing 常见问题

### Q: Span 创建了但追踪后端看不到数据？

1. 确认 `otlp_endpoint` 地址正确，Collector 正在监听该端口（默认 `4317`）；
2. 本地调试时设置 `enable_console=True` 确认 Span 是否被正常创建；
3. OTLP 导出器初始化失败时会打印 WARNING 而非抛异常，检查启动日志。

### Q: 开发环境不接追踪后端怎么办？

```python
# 不传 otlp_endpoint，Span 不导出但日志 trace_id 仍正常注入
setup_tracing(service_name="my-service")

# 或打印到终端方便调试
setup_tracing(service_name="my-service", enable_console=True)
```

### Q: 与 `opentelemetry-instrumentation-fastapi` 有冲突吗？

`install_fastapi_trace_middleware` 是手动实现的轻量中间件，与 `FastAPIInstrumentor` 同时使用时会产生两个根 Span。建议二者只选其一；若追求更完整的属性覆盖（HTTP 状态码、路由参数等），推荐使用官方 `FastAPIInstrumentor`。

### Q: `setup_tracing` 的返回值和 `get_tracer()` 有什么区别？

`setup_tracing` 返回以 `aha_common_utils.tracing` 为 instrumentation 名称的 Tracer；`get_tracer(__name__)` 返回以调用方模块名为 instrumentation 名称的 Tracer。功能完全相同，区别仅在于追踪 UI 中显示的 instrumentation library 标签。业务代码统一使用 `get_tracer(__name__)` 即可。
