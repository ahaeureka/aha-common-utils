# aha-common-utils — 配置管理系统使用手册

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
- [BaseParameters 配置模型](#baseparameters-配置模型)
  - [基本用法](#基本用法)
  - [嵌套配置模型](#嵌套配置模型)
  - [from_dict / to_dict / update_from](#from_dict--to_dict--update_from)
  - [敏感字段自动屏蔽](#敏感字段自动屏蔽)
  - [生产安全校验](#生产安全校验)
  - [safe_dump()](#safe_dump)
  - [field() 工厂方法](#field-工厂方法)
- [ConfigStore 统一读写 API](#configstore-统一读写-api)
  - [load() — 加载配置](#load--加载配置)
  - [save() — 写入配置](#save--写入配置)
  - [环境变量自动覆盖](#环境变量自动覆盖)
- [从 SecureBaseSettings 迁移](#从-securebasesettings-迁移)
- [项目文件布局参考](#项目文件布局参考)
- [环境变量 APP_ENV](#环境变量-app_env)
- [工具函数 API](#工具函数-api)
- [配置文件示例](#配置文件示例)
- [常见问题](#常见问题)
- [CLI 框架](#cli-框架)

---

## 概述

`aha-common-utils` 提供了一套 **模型驱动的分层配置管理系统**，基于 [pydantic](https://docs.pydantic.dev/) 构建。核心设计原则：

1. **模型即 schema** — 使用 `BaseParameters`（纯 `BaseModel`）定义配置结构、默认值和校验规则，配置文件的层级结构与模型嵌套一一对应。
2. **分层覆盖** — 多来源配置按优先级依次覆盖，灵活适配 `开发 / 测试 / 生产` 各环境。
3. **格式多样** — 同时支持 TOML、YAML、`.env`、进程环境变量。
4. **安全优先** — 敏感字段自动屏蔽、生产环境默认值校验、敏感信息与版本库隔离。
5. **读写闭环** — `ConfigStore` 提供 `load() → 模型 → save()` 的双向 I/O，支持程序化修改配置文件。
6. **零配置启动** — 只要在项目根目录放置约定名称的配置文件，即可自动发现并加载。

---

## 快速上手

### 1. 定义配置模型

```python
from aha_common_utils.config_base import BaseParameters

class AppSettings(BaseParameters):
    """应用配置模型。"""
    app_env: str = BaseParameters.field(default="development", description="运行环境")
    database_url: str = BaseParameters.field(
        default="postgresql+asyncpg://localhost/dev",
        description="PostgreSQL 连接字符串",
    )
    log_level: str = BaseParameters.field(default="INFO")
    llm_api_key: str = BaseParameters.field(
        default="",
        description="LLM API Key — 敏感，仅 .env.local 注入",
        tags=["secret"],
    )
```

### 2. 放置配置文件

在项目根目录（含 `pyproject.toml` 的目录）创建：

```
myproject/
├── pyproject.toml
├── config.toml                    # 基础默认配置（提交版本库）
├── config.development.toml        # 开发环境覆盖（提交版本库）
├── .env.local                     # 敏感值（已 .gitignore，不提交）
└── main.py
```

### 3. 使用 ConfigStore 加载

```python
from aha_common_utils.config_store import ConfigStore

store = ConfigStore()
settings = store.load(AppSettings)

# 安全打印（敏感字段被屏蔽）
print(settings)
# AppSettings(app_env='development', database_url='post****', llm_api_key='****')

# 获取安全字典（适合日志输出）
print(settings.safe_dump())
```

### 4. 程序化修改并写回

```python
# 修改并保存
settings.update_from({"log_level": "DEBUG"})
store.save(settings, "config.development.toml")

# 部分更新（仅修改 [app] 段，保留其他段不变）
store.save({"debug": True}, "config.toml", path="app")
```

---

## 配置加载优先级

加载优先级 **从低到高** 排列——后加载的值会 **覆盖** 先加载的同名字段：

| 优先级 | 来源 | 说明 | 提交版本库 |
|:---:|------|------|:---:|
| 1（最低） | 代码默认值 | `BaseParameters` 子类中声明的字段默认值 | ✅ |
| 2 | `config.toml` | TOML 基础非敏感配置 | ✅ |
| 3 | `config.<APP_ENV>.toml` | TOML 环境专属覆盖 | ✅ |
| 4 | `.env` | dotenv 本地默认值（兼容标准 dotenv 工具） | ❌ |
| 5 | `.env.local` | 通用本地敏感值（密码/API Key） | ❌ |
| 6 | `.env.<APP_ENV>.local` | 环境专属敏感值 | ❌ |
| 7（最高） | 进程环境变量 | 容器/CI 注入，最终覆盖 | — |

> 环境变量支持 `SECTION_FIELD` 命名模式自动路由到嵌套模型。例如 `LLM_API_KEY` 自动映射到 `llm.api_key`，`EMBEDDING_OPENAI_BASE_URL` 自动映射到 `embedding.openai.base_url`。无需手动配置 `env_prefix`。

---

## 支持的配置文件格式

### TOML 配置文件

标准 [TOML](https://toml.io/) 格式，**推荐作为主配置格式**。支持嵌套 section 匹配模型层级：

```toml
# config.toml — 基础默认配置
[app]
env   = "development"
name  = "skillforge"
debug = false
log_level = "INFO"

[database]
url = "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
provider = "sqlmodel-pg"

[redis]
url = "redis://localhost:6379/0"
key_prefix = "skillforge:development"

[llm]
default_model = "openai:gpt-4o-mini"
provider = "langchain-openai"
api_key = ""   # 通过 .env.local 或 ${env:LLM_API_KEY} 注入

[llm.langchain_openai]
model = "gpt-4o-mini"
base_url = "https://api.openai.com"
```

```toml
# config.development.toml — 开发环境覆盖
[app]
debug = true
log_level = "DEBUG"

[database]
url = "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge_dev"
```

自动发现的文件名：
- `config.toml` — 基础配置
- `config.<APP_ENV>.toml` — 环境配置（如 `config.development.toml`）

### YAML 配置文件

标准 [YAML](https://yaml.org/) 格式，适合习惯 YAML 的团队或需要嵌套结构的场景。

```yaml
# config.yaml — 基础默认配置
app:
  env: development
  name: skillforge
  debug: false
  log_level: INFO

database:
  url: "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
  provider: sqlmodel-pg

redis:
  url: "redis://localhost:6379/0"
```

自动发现的文件名（`.yaml` 优先于 `.yml`）：
- `config.yaml` 或 `config.yml` — 基础配置
- `config.<APP_ENV>.yaml` 或 `config.<APP_ENV>.yml` — 环境配置

### .env.local 敏感文件

标准 dotenv 格式，**仅存放敏感值**，**必须加入 `.gitignore`**。

环境变量名使用 `SECTION_FIELD` 命名模式自动路由到嵌套模型：

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
export LLM_API_KEY=sk-prod-xxxxxxxx
```

环境变量名会自动按 `SECTION_FIELD` 模式路由到嵌套模型字段。无需配置 `env_prefix`。

---

## 配置文件命名与发现规则

系统通过 `find_project_root()` 自动定位项目根目录（向上查找包含 `pyproject.toml` 的最近目录），然后在该目录中查找约定名称的配置文件。

### 自动发现列表

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `config.toml` | TOML | 基础默认值 |
| `config.<APP_ENV>.toml` | TOML | 环境专属覆盖 |
| `config.yaml` | YAML | 基础默认值 |
| `config.yml` | YAML | 基础默认值（`config.yaml` 不存在时使用） |
| `config.<APP_ENV>.yaml` | YAML | 环境专属覆盖 |
| `config.<APP_ENV>.yml` | YAML | 环境专属覆盖（`.yaml` 不存在时使用） |
| `.env` | dotenv | 本地默认值（⚠️ 不提交版本库） |
| `.env.local` | dotenv | 通用敏感值（优先级高于 `.env`，⚠️ 不提交版本库） |
| `.env.<APP_ENV>.local` | dotenv | 环境专属敏感值（优先级高于 `.env.local`） |

所有文件均为 **可选**。只存在的文件才会被加载，不存在的文件会被安静跳过。

---

## BaseParameters 配置模型

### 基本用法

所有配置模型应继承 `BaseParameters`，而非 `pydantic.BaseModel`：

```python
from aha_common_utils.config_base import BaseParameters

class AppSettings(BaseParameters):
    app_env: str = BaseParameters.field(
        default="development",
        description="运行环境",
        tags=["app"],
    )
    database_url: str = BaseParameters.field(
        default="postgresql+asyncpg://localhost/dev",
        description="PostgreSQL 连接字符串",
    )
    secret_key: str = BaseParameters.field(
        default="change-me-in-production",
        description="JWT 签名密钥",
        tags=["secret"],
    )
    log_level: str = BaseParameters.field(default="INFO")
```

### 嵌套配置模型

推荐将相关配置组织为嵌套模型，与 TOML 文件层级一一对应：

```python
class DatabaseConfig(BaseParameters):
    url: str = BaseParameters.field(default="postgresql+asyncpg://localhost/db")
    provider: str = BaseParameters.field(default="sqlmodel-pg")
    pool_size: int = BaseParameters.field(default=10)

class LLMConfig(BaseParameters):
    default_model: str = BaseParameters.field(default="openai:gpt-4o-mini")
    api_key: str = BaseParameters.field(default="", tags=["secret"])

class AppConfig(BaseParameters):
    """根配置模型。"""
    app_env: str = BaseParameters.field(default="development")
    database: DatabaseConfig = BaseParameters.field(default=DatabaseConfig())
    llm: LLMConfig = BaseParameters.field(default=LLMConfig())
```

嵌套模型路径 `app_config.llm.api_key` 对应 TOML 的 `[llm]` section + `api_key` key，也对应环境变量 `LLM_API_KEY`。

### from_dict / to_dict / update_from

```python
# 从字典构造（自动解析 ${env:VAR} 插值）
cfg = AppConfig.from_dict({"app_env": "test", "database": {"url": "pg://test/db"}})

# 序列化为字典
data = cfg.to_dict()
# {'app_env': 'test', 'database': {'url': 'pg://test/db', ...}, ...}

# 合并更新（跳过 fixed 字段和 None 值）
cfg.update_from({"app_env": "production"})  # 返回 True 表示有更新
```

### 敏感字段自动屏蔽

字段名中包含以下关键词时，会被自动识别为敏感字段，在 `__repr__` / `__str__` / `safe_dump()` 中被屏蔽：

```
password, passwd, secret, api_key, apikey, token, private_key,
access_key, secret_key, dsn, auth, credential, database_url, redis_url
```

屏蔽效果示例：

```python
>>> print(settings)
AppSettings(app_env='development', database_url='post****', llm_api_key='****')

>>> settings.safe_dump()
{'app_env': 'development', 'database_url': 'post****', 'llm_api_key': '****'}
```

#### 追加自定义敏感字段

子类可通过 `_EXTRA_SENSITIVE_FIELDS` 类变量添加额外的敏感字段名：

```python
class AppSettings(BaseParameters):
    _EXTRA_SENSITIVE_FIELDS = {"internal_admin_token", "webhook_secret"}

    internal_admin_token: str = ""
    webhook_secret: str = ""
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
class AppSettings(BaseParameters):
    secret_key: str = BaseParameters.field(default="change-me-in-production")

# ValueError: [Security] Field 'secret_key' has insecure default 'change-me-in-production'
#             in production (APP_ENV=production).
#             Override via .env.local or process environment variable.
```

### safe_dump()

返回屏蔽了敏感字段的配置字典，递归处理嵌套 `BaseParameters` 子模型：

```python
import json

settings = AppConfig()
print(json.dumps(settings.safe_dump(), indent=2, ensure_ascii=False))
```

### field() 工厂方法

`BaseParameters.field()` 是 `pydantic.Field()` 的封装，支持额外元数据：

```python
class MyConfig(BaseParameters):
    timeout: int = BaseParameters.field(
        default=60,
        description="超时时间（秒）",
        tags=["network", "timeout"],
        fixed=False,   # True 时 update_from() 跳过此字段
        ge=0,           # 透传 pydantic Field 参数
    )
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `default` | `Any` | 字段默认值 |
| `description` | `str \| None` | 字段描述，存入 `json_schema_extra` |
| `tags` | `list[str] \| None` | 分类标签，如 `["secret"]`, `["llm"]` |
| `fixed` | `bool` | True 时 `update_from()` 不修改此字段 |
| `**kwargs` | — | 透传给 `pydantic.Field()` |

---

## ConfigStore 统一读写 API

`ConfigStore` 是配置 I/O 的统一入口，负责文件发现、解析、合并、环境变量覆盖和模型构造。

### load() — 加载配置

```python
from aha_common_utils.config_store import ConfigStore
from myapp.config import AppConfig

store = ConfigStore()

# 自动发现并加载
config = store.load(AppConfig)

# 指定环境
config = store.load(AppConfig, app_env="production")

# 指定查找目录
config = store.load(AppConfig, base_dir=Path("/app"))

# 获取原始合并数据（用于 ProviderRegistry 同步）
raw = store.raw_data  # TOML + YAML 原始 dict（模型构造前）
```

加载流程：
1. 发现配置文件（`config.toml` → `config.<ENV>.toml`）
2. 解析并合并（后者覆盖前者，嵌套 dict 递归合并）
3. 加载 `.env` / `.env.local` / `.env.<ENV>.local` 到进程环境变量
4. 解析 dict 中的 `${env:VAR:-default}` 环境变量插值
5. 应用进程环境变量覆盖（最高优先级，自动类型强制）
6. 构造并返回模型实例

### save() — 写入配置

```python
# 完整写入
store.save(config, "config.output.toml")

# 写入 YAML
store.save(config, "config.output.yaml")

# 部分更新 — 仅修改 [llm] 段，保留其他 section 不变
store.save({"model": "gpt-5"}, "config.toml", path="llm.langchain_openai")

# 使用 tomlkit 保留注释和格式
store.save(config, "config.toml")
```

### 环境变量自动覆盖

环境变量支持 **`SECTION_FIELD`** 和 **`SECTION_SUBSECTION_FIELD`** 命名模式，自动路由到嵌套模型路径：

| 环境变量 | 映射路径 | 说明 |
|---------|---------|------|
| `LLM_API_KEY` | `llm.api_key` | 一级嵌套 |
| `LLM_BASE_URL` | `llm.base_url` | 一级嵌套 |
| `EMBEDDING_MODEL` | `embedding.model` | 一级嵌套 |
| `EMBEDDING_OPENAI_BASE_URL` | `embedding.openai.base_url` | 二级嵌套 |
| `LLM_LANGCHAIN_OPENAI_MODEL` | `llm.langchain_openai.model` | 二级嵌套 |
| `GRAPHRAG_EMBEDDING_DIMENSION` | `graphrag.embedding_dimension` | 深层嵌套 |

支持 `${env:VAR:-default}` 值级别环境变量插值：

```toml
# config.toml
[llm]
api_key = "${env:LLM_API_KEY}"            # 必填，无默认值时未设置会报错
model = "${env:LLM_MODEL:-gpt-4o}"        # 有默认值，未设置时使用 gpt-4o
base_url = "${env:LLM_BASE_URL:-https://api.openai.com}"
```

---

## 从 SecureBaseSettings 迁移

`SecureBaseSettings`（基于 pydantic-settings）已被 `BaseParameters`（纯 pydantic BaseModel）+ `ConfigStore` 替代。

### 迁移步骤

**1. 替换基类**

```python
# 旧
from aha_common_utils.settings import SecureBaseSettings
from pydantic_settings import SettingsConfigDict

class AppSettings(SecureBaseSettings):
    model_config = SettingsConfigDict(env_prefix="MYAPP_")
    APP_ENV: str = "development"

# 新
from aha_common_utils.config_base import BaseParameters

class AppSettings(BaseParameters):
    app_env: str = BaseParameters.field(default="development")
```

**2. 替换扁平字段为嵌套模型**

```python
# 旧（扁平 50+ 字段）
class AppSettings(SecureBaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "..."
    FALKORDB_HOST: str = "localhost"
    FALKORDB_PORT: int = 16379
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""

# 新（嵌套领域模型）
class DatabaseConfig(BaseParameters):
    url: str = BaseParameters.field(default="...")

class FalkorDBConfig(BaseParameters):
    host: str = BaseParameters.field(default="localhost")
    port: int = BaseParameters.field(default=16379)

class LLMConfig(BaseParameters):
    api_key: str = BaseParameters.field(default="", tags=["secret"])
    base_url: str = BaseParameters.field(default="")

class AppConfig(BaseParameters):
    app_env: str = BaseParameters.field(default="development")
    database: DatabaseConfig = BaseParameters.field(default=DatabaseConfig())
    falkordb: FalkorDBConfig = BaseParameters.field(default=FalkorDBConfig())
    llm: LLMConfig = BaseParameters.field(default=LLMConfig())
```

**3. 替换 env_prefix 为 SECTION_FIELD 环境变量**

```bash
# 旧（env_prefix="W5_FLOW_"）
W5_FLOW_DATABASE_URL=pg://...
W5_FLOW_LLM_API_KEY=sk-...

# 新（SECTION_FIELD 自动路由）
DATABASE_URL=pg://...
LLM_API_KEY=sk-...
```

**4. 替换实例化方式**

```python
# 旧
settings = AppSettings()

# 新
from aha_common_utils.config_store import ConfigStore
store = ConfigStore()
settings = store.load(AppConfig)
```

**5. 替换字段访问**

```python
# 旧
settings.LLM_API_KEY

# 新
settings.llm.api_key
```

### 导入路径变化

| 旧路径 | 新路径 |
|-------|-------|
| `from aha_common_utils.settings import SecureBaseSettings` | `from aha_common_utils.config_base import BaseParameters` |
| `from aha_common_utils.settings import find_project_root` | `from aha_common_utils.config_store import _find_project_root` |
| `from aha_common_utils.settings import read_config, write_config` | `from aha_common_utils.settings import read_config, write_config`（兼容保留） |
| `from aha_common_utils.settings import is_sensitive_field, mask_value` | `from aha_common_utils.config_base import is_sensitive_field, mask_value` |

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
├── .env.test.local                 # ❌ gitignore — 测试环境专属敏感值
├── .gitignore                      # 必须包含 .env*.local
│
└── src/
    └── myapp/
        ├── config.py               # 配置模型定义（BaseParameters 子类）
        └── main.py                 # ConfigStore.load(AppConfig) 启动加载
```

`.gitignore` 中确保包含：

```gitignore
.env*.local
```

---

## 环境变量 APP_ENV

`APP_ENV` 是核心环境变量，决定：

1. 加载哪个环境配置文件（`config.<APP_ENV>.toml`）
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

### 配置模型相关（config_base）

```python
from aha_common_utils.config_base import (
    BaseParameters,          # 配置模型基类
    is_sensitive_field,       # 判断字段是否敏感
    mask_value,               # 屏蔽敏感值（保留前4位）
    SENSITIVE_SUBSTRINGS,     # 敏感字段关键词集合
    INSECURE_DEFAULT_VALUES,  # 不安全默认值集合
)
```

### 配置读写相关（config_store）

```python
from aha_common_utils.config_store import ConfigStore

store = ConfigStore()
config = store.load(AppConfig)          # 加载
store.save(config, "config.toml")       # 完整写入
store.save(data, "config.toml", path="llm")  # 部分更新
raw = store.raw_data                     # 原始合并 dict
```

### 低级读写（settings — 兼容保留）

```python
from aha_common_utils.settings import (
    read_config,     # 统一读入口（自动检测格式）
    write_config,    # 统一写入口（自动检测格式）
    merge_configs,   # 深度合并多个配置字典
)
```

### BaseParameters 实例方法

| 方法 | 说明 |
|------|------|
| `from_dict(data, ignore_extra_fields=False)` | 从字典构造（含 `${env:VAR}` 插值） |
| `to_dict()` | 序列化为字典 |
| `update_from(source)` | 合并更新（跳过 fixed 和 None），返回 `bool` |
| `safe_dump()` | 字典输出（敏感字段屏蔽，递归处理嵌套模型） |
| `to_command_args(prefix="--")` | 转换为 CLI 参数列表 |
| `get_parameter_descriptions()` | 获取所有字段元数据列表 |

---

## 配置文件示例

### TOML 格式（推荐）

```toml
# config.toml — 基础默认配置（非敏感，提交版本库）

[app]
env              = "development"
name             = "skillforge"
debug            = false
log_level        = "INFO"

[database]
url      = "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
provider = "sqlmodel-pg"

[redis]
url         = "redis://localhost:6379/0"
key_prefix  = "skillforge:development"

[llm]
default_model   = "openai:gpt-4o-mini"
provider        = "langchain-openai"
base_url        = ""
daily_budget_usd = 10.0

[llm.langchain_openai]
model    = "gpt-4o-mini"
base_url = "https://api.openai.com"
```

```toml
# config.production.toml — 生产环境覆盖

[app]
env   = "production"
debug = false
log_level = "WARNING"

[llm]
daily_budget_usd = 100.0
```

### YAML 格式

```yaml
# config.yaml — 基础默认配置
app:
  env: development
  name: skillforge
  debug: false
  log_level: INFO

database:
  url: "postgresql+asyncpg://postgres:postgres@localhost:5432/skillforge"
  provider: sqlmodel-pg
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

### Q: 配置模型未声明的字段，配置文件中写了会报错吗？

不会。`ConfigStore.load()` 使用 `from_dict(ignore_extra_fields=True)`，未声明的字段会被安静忽略。

### Q: 如何在测试中覆盖配置？

直接传入嵌套字典构造模型：

```python
settings = AppConfig.from_dict({"database": {"url": "sqlite+aiosqlite:///test.db"}})
```

或使用 monkeypatch 设置环境变量后通过 ConfigStore 加载：

```python
monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///test.db")
settings = store.load(AppConfig)
```

### Q: 如何自定义项目根目录？

使用 `ConfigStore.load()` 的 `base_dir` 参数：

```python
store = ConfigStore()
config = store.load(AppConfig, base_dir=Path("/custom/path"))
```

### Q: 从 SecureBaseSettings 迁移需要改什么？

参见上方 [从 SecureBaseSettings 迁移](#从-securebasesettings-迁移) 章节，包含完整的 5 步迁移指南和导入路径对照表。

### Q: `${env:VAR}` 插值在哪些地方生效？

在 TOML/YAML 配置文件的任意字符串值中均可使用。ConfigStore 在解析文件后、构造模型前统一解析所有 `${env:VAR:-default}` 引用。如果环境变量未设置且无默认值，会抛出 `ValueError`。

### Q: BaseParameters 支持 pydantic v2 的所有校验功能吗？

**支持。** `BaseParameters` 是 `pydantic.BaseModel` 的直接子类，支持所有 pydantic v2 特性：类型强制、`Field(ge=0, le=100)` 约束、`@model_validator`、`@field_validator`、`Annotated` 类型等。

---

## CLI 框架

`aha_common_utils.cli` 提供类 FastAPI 风格的声明式 CLI 框架，基于 [typer](https://typer.tiangolo.com/) 封装。

### 使用约束

> **业务包（`packages/know-know-app` 等）必须复用 `aha_common_utils.cli` 构建 CLI 入口。**
>
> - ✅ 使用 `CliApp` / `Router` 和 `Annotated[Opt(...)]` 等声明式参数注解
> - ❌ 禁止直接使用 `argparse`、`click` 或其他底层 CLI 库
> - ❌ 禁止在 `packages/know-know-core`、`packages/know-know-commons` 或 `packages/aha-common-utils` 中定义产品 CLI 入口
>
> CLI 测试统一使用 `typer.testing.CliRunner`，不通过子进程或手动 `parser.parse_args()` 测试。

核心特性：

- **`Annotated` 参数注解** — 用 `Annotated[T, Opt(...)]` 语法声明选项和位置参数，与 FastAPI 参数风格一致
- **五种参数助手** — `Opt`、`Arg`、`EnvOpt`、`SecretOpt`、`FlagOpt`，覆盖常见场景
- **两级子命令** — `CliApp → Router → command`，对应 FastAPI 的 `FastAPI + APIRouter`
- **`async def` 自动包装** — 命令函数可以是 `async def`，框架自动用 `asyncio.run` 包装

### 快速上手

```python
from typing import Annotated
from aha_common_utils.cli import CliApp, Router, Opt, Arg, EnvOpt, SecretOpt, FlagOpt

app = CliApp(name="myapp", help="示例应用", no_args_is_help=True)

db = Router(name="db", help="数据库命令")

@db.command("upgrade")
async def db_upgrade(
    url: Annotated[str, EnvOpt("DATABASE_URL", help="DB 连接 URL")],
    dry_run: Annotated[bool, FlagOpt(help="仅预览变更", short="-n")] = False,
):
    """升级数据库 schema。"""
    ...

@db.command("init")
def db_init(
    password: Annotated[str, SecretOpt(help="DB 密码", envvar="DB_PASSWORD")],
):
    """初始化数据库。"""
    ...

app.include_router(db)

@app.command("serve")
def serve(
    host: Annotated[str, Opt(help="绑定地址", envvar="HOST")] = "0.0.0.0",
    port: Annotated[int, Opt(help="端口号", short="-p")] = 8080,
    verbose: Annotated[bool, FlagOpt(help="详细输出", short="-v")] = False,
):
    """启动服务。"""
    ...

if __name__ == "__main__":
    app.run()
```

产生的 CLI 命令：

```
myapp serve NAME [--host TEXT] [-p INT] [-v | --no-verbose]
myapp db upgrade [--url / $DATABASE_URL] [--dry-run / -n]
myapp db init                    # 交互式密码输入 或 $DB_PASSWORD
```

### 参数助手 API

#### `Opt` — 通用选项

```python
host: Annotated[str, Opt(
    help="绑定地址",
    envvar="HOST",       # 从环境变量读取
    short="-H",          # 短选项
    show_default=True,
)] = "0.0.0.0"
```

#### `Arg` — 位置参数

```python
name: Annotated[str, Arg(help="服务名称")]
```

#### `EnvOpt` — 环境变量绑定选项

```python
url: Annotated[str, EnvOpt("DATABASE_URL", help="数据库连接 URL")]
```

#### `SecretOpt` — 密码/密钥选项

```python
password: Annotated[str, SecretOpt(
    help="数据库密码",
    envvar="DB_PASSWORD",
    confirmation_prompt=True,
)]
```

#### `FlagOpt` — 布尔开关

```python
verbose: Annotated[bool, FlagOpt(help="详细输出", short="-v")] = False
```

### `CliApp` API

```python
app = CliApp(
    name="myapp",
    help="My application",
    no_args_is_help=True,
    add_completion=True,
)
```

| 方法 | 说明 |
|---|---|
| `.command(name)` | 注册顶层命令，支持 `async def` |
| `.include_router(router)` | 挂载子命令组 |
| `.callback()` | 注册顶层全局选项 |
| `.run(args=None)` | 启动 CLI |

### `Router` API

```python
db = Router(name="db", help="数据库命令")
```

| 方法 | 说明 |
|---|---|
| `.command(name)` | 注册子命令，支持 `async def` |
| `.callback()` | 组级共享选项 |

### 测试 CLI 命令

```python
from typer.testing import CliRunner

runner = CliRunner()

def test_serve():
    result = runner.invoke(app._typer, ["serve", "myapp", "--port", "9000"])
    assert result.exit_code == 0
```

---

## 其他使用手册

- [日志系统使用手册](docs/logging.md) — Loguru + OpenTelemetry 上下文注入、文件轮转、请求 ID 注入
- [链路追踪使用手册](docs/tracing.md) — OpenTelemetry Tracing 初始化、FastAPI 中间件、Span 操作
