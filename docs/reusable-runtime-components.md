# Reusable Runtime Components

`aha_common_utils` provides business-independent runtime building blocks that project templates and services can reuse.

## Ports

- `aha_common_utils.ports.cache_store.CacheStorePort`
- `aha_common_utils.ports.file_scan.FileScanPort`
- `aha_common_utils.ports.file_storage.FileStoragePort`
- `aha_common_utils.ports.llm_provider.LLMProviderPort`
- `aha_common_utils.ports.ocr_provider.OcrProviderPort`
- `aha_common_utils.ports.task_queue.TaskQueuePort`

These contracts carry only generic identifiers, bytes, metadata, messages, and task envelopes. They must not depend on project-specific proto models, database tables, or domain DTOs.

## Runtime Lifecycle

- `LifecycleRegistry` initializes resources in registration order and closes them in reverse order.
- `close_once()` closes shared resources idempotently by object identity.
- `ServiceRegistry` stores servicer-like resources with installer callbacks, initializes them, installs them into a server object, and closes them in reverse order.
- `ServiceRegistry.register()` accepts an explicit installer callback, or subclasses can override `resolve_add_to_server()` for project-specific service installer lookup.
- `runtime.provider_registry` wraps the shared `ProviderRegistry` with typed helpers for registering, creating, and listing providers by actual port subclass.
- `RequestContext` propagates request ids, task ids, user ids, optional session ids, generic metadata, and billable adapter spans through `contextvars`.

## Adapters And Fakes

- `LocalFileStorageAdapter` is a filesystem-backed file store for local development and tests.
- `RedisCacheAdapter` and `RedisStreamsTaskQueue` provide Redis-backed implementations when the consuming project includes Redis runtime configuration.
- `RemoteOcrClient` adapts no-auth OCR `/v1/ocr` compatible endpoints into canonical OCR page results and layout blocks.
- `AlwaysCleanScanner`, `MimeTypeAllowlistScanner`, and `ChainFileScanner` provide reusable upload scanning primitives.
- `aha_common_utils.testing.fakes` contains deterministic fakes for cache, file storage, LLM, embedding, OCR, and task queue ports.
- `storage.helpers` provides shared file-storage adapter helpers for scan enforcement, object-key path sanitization, and metadata-key sanitization.
- `json_values.flatten_numeric_list()` normalizes nested JSON number lists from provider responses.

Scanner results use `scanner_name` and `detail` as the stable fields consumed by storage adapters. `provider` and `details` remain read-only aliases for older common-utils call sites.
Testing fakes share the same one-shot `fail_next()` helper; callers may pass either an exception instance or a string message. `FakeFileStorage` accepts an optional scanner and supports `reset()` for per-test isolation. `FakeEmbeddingProvider` supports fixed-vector responses plus query/document call tracking, so consuming projects can wrap it for richer embedding ports without duplicating fake state management.

## Cache Stores

- `aha_common_utils.cache.provider_registry.CacheStoreConfig` describes the generic provider name, connection URL, and key prefix.
- `register_cache_store()`, `available_cache_stores()`, and `create_cache_store()` provide a typed wrapper around `ProviderRegistry` for `CacheStorePort`.
- `RedisCacheAdapter` is registered as `redis-cache`; consuming projects should pass resolved configuration instead of importing Redis directly.
- `RedisCacheAdapter` connects lazily on first operation, validates empty or already-prefixed keys, and can be closed repeatedly.

## Task Queues

- `aha_common_utils.task_queue.provider_registry.TaskQueueConfig` describes the generic provider name, connection URL, stream, and consumer group.
- `register_task_queue()`, `available_task_queues()`, and `create_task_queue()` provide a typed wrapper around `ProviderRegistry` for `TaskQueuePort`.
- `RedisStreamsTaskQueue` is registered as `redis-streams`; consuming projects should pass resolved configuration instead of constructing Redis clients directly.
- `RedisStreamsTaskQueue` uses Redis consumer groups, `XACK`, bounded `XADD maxlen`, and `XAUTOCLAIM`-based pending recovery with configurable stream, group, consumer prefix, max length, and idle claim time.
- Projects with domain-specific task envelope classes can inject `envelope_to_dict`, `envelope_from_dict`, and `increment_attempt` hooks while reusing the same Redis transport behavior.

## LLM Providers

- `aha_common_utils.llm.provider_registry.LLMProviderConfig` describes the generic provider name, endpoint, credential, model, and timeout.
- `register_llm_provider()`, `available_llm_providers()`, and `create_llm_provider()` provide a typed wrapper around `ProviderRegistry` for `LLMProviderPort`.
- `LLMProviderPort` exposes four generic async methods, all business-independent:
  - `chat(messages, temperature, max_tokens) -> str` — raw assistant content string.
  - `complete_json(messages, schema, temperature, max_tokens) -> JsonObject` — JSON-parsed response, with optional schema-backed structured output.
  - `stream_text(messages, temperature, max_tokens) -> AsyncIterator[str]` — text chunk stream.
  - `stream_events(messages, temperature, max_tokens) -> AsyncIterator[dict[str, object]]` — normalized LangChain event stream.
- `OpenAICompatibleLLMProvider` is backed by LangChain `ChatOpenAI`:
  - `chat()` / `complete_json()` invoke the bound chat model via `ainvoke()`.
  - `complete_json(schema=...)` uses `with_structured_output(schema)` for schema-constrained responses.
  - `stream_text()` uses `astream()`; `stream_events()` uses `astream_events(version="v2")`.
  - `temperature` and `max_tokens` are bound per-call through `runnable.bind()`, never placed in `RunnableConfig`.
  - Constructor accepts `base_url`, `api_key`, `model`, `request_timeout_seconds`; a test double can be injected via `chat_model`.
- `OpenAICompatibleEmbeddingProvider` is backed by LangChain `OpenAIEmbeddings.aembed_documents()`, preserves caller input order, and returns `[]` for empty input.
- Custom OpenTelemetry spans (`llm.chat`, `llm.complete_json`, `llm.stream_text`, `llm.stream_events`, `embedding.embed_texts`) record exceptions and non-secret metadata only — never `api_key` or message content.
- `llm.json_helpers` contains reusable LLM response helpers for extracting text content, parsing fenced JSON objects, coercing Pydantic/dataclass/dict responses, and reading request ids from provider exceptions.

The LLM layer is intentionally limited to transport, provider construction, JSON parsing, and generic streaming. Project-specific prompts, response schemas, retry policy, budgets, LangGraph agents, and domain mapping belong in the consuming service. The adapters do not require LangSmith or `LANGCHAIN_TRACING_V2`.

## OCR Providers

- `aha_common_utils.ocr.provider_registry.OcrProviderConfig` describes the generic provider name, endpoint, timeout, response format, and extra construction parameters.
- `register_ocr_provider()`, `available_ocr_providers()`, and `create_ocr_provider()` provide a typed wrapper around `ProviderRegistry` for `OcrProviderPort`.
- `RemoteOcrClient` is registered as `remote-ocr`; consuming projects can expose their own compatibility provider names if needed.
- `canonical_blocks_from_verbose_json()` converts PP-DocLayout-style verbose JSON blocks into `OcrLayoutBlock` values with normalized numeric bbox and polygon fields.
- `FakeOcrProvider` provides deterministic page results and records `(path, language)` calls for tests.

OCR common-utils owns only provider transport and canonical response normalization. PDF rendering, document parsing, page concurrency, textbook semantics, and domain-specific OCR policies belong in the consuming project.

## HTTP Fetch and Anti-Detection Layer

- `aha_common_utils.ports.http_fetch` defines `HttpFetchPort` plus the frozen value objects `HttpFetchRequest` / `HttpFetchResponse` and the `AntiCrawlSignal` enum. All crawl/probe/download traffic goes through this port; domain code must not construct httpx/curl clients directly.
- `http_fetch.anti_crawl_detector` provides `SiteProfile` and `AntiCrawlDetector`: status-code branches (403/429/503), empty/minimal body checks, site-specific regex patterns, generic signals (captcha / JS challenge / blocked keywords), and header challenges (cf-ray, server: cloudflare, x-challenge). The library ships only the generic signal set; domain profiles (FRED/OpenBB etc.) are injected via `register_site()`.
- `http_fetch.anti_detection` provides the `AntiDetectionStrategy` ABC and `AntiDetectionManager` (default `anti-detection` provider). The default policy starts with `CurlCffiStrategy` (TLS fingerprint) and escalates on failure through `CloakBrowserStrategy → CamoufoxStrategy`; blocked requests without a proxy are retried once through `ProxyManager`. Optional dependencies (`curl-cffi`, `cloakbrowser`, `camoufox`) are lazily imported and missing ones are skipped by the manager instead of failing startup.
- `http_fetch.auto_planning.AutoPlanningEngine` adaptively rate-limits per domain (429/503 exponential backoff, 200 slow recovery); `http_fetch.proxy.ProxyManager` rotates egress proxies by success rate and health-checks them.
- `http_fetch.provider_registry` exposes `HttpFetchProviderConfig` and the typed helpers `register_http_fetch_provider()`, `available_http_fetch_providers()`, `create_http_fetch_provider()`. `anti-detection` is the default; single-strategy providers such as `httpx` / `curl-cffi` are also registered. Unknown providers raise `UnknownHttpFetchProviderError` (fail-fast, no Fake fallback). The default chain is `curl-cffi → cloakbrowser → camoufox`; plain `httpx` is intentionally not in the default chain (its TLS fingerprint is weaker than curl-cffi) but remains selectable.
- `http_fetch.proxy_server.HttpProxyServer` is an anti-detection-aware HTTP forward proxy: plain HTTP requests and `CONNECT` tunnels are forwarded upstream through an injected `HttpFetchPort` (default `AntiDetectionManager`). With a `CertificateAuthority` (see `http_fetch.mitm_ca.MitmCertificateAuthority`), `CONNECT` is MITM-intercepted so HTTPS is also dispatched through the strategy chain; without one it falls back to a raw byte tunnel. Hop-by-hop headers are stripped, request bodies are size-capped, and anti-crawl signals are echoed via the `X-Anti-Crawl-Signal` response header.
- `http_fetch.mitm_ca.MitmCertificateAuthority` persists a self-signed root CA (`ca.key`/`ca.crt`) and signs per-host leaf certificates (default 30 days) for MITM interception.
- `testing.fakes.http_fetch.FakeHttpFetchProvider` records requests, serves configured responses by URL or FIFO order with status codes / anti-crawl signals, and supports one-shot `fail_next()` and `reset()`.

## Boundary Rules

- Keep these modules business-independent.
- Do not import project packages, proto-generated modules, ORM table models, or domain DTOs.
- Keep secrets in consuming-project config; common-utils should receive resolved values through constructors.
