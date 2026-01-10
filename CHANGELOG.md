# Changelog

All notable changes to the **SQL Agent OSS** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.1.0] - 2026-01-10

### 🚀 Major Performance & Architecture Updates ("Fast Agent")

- **Singleton Pattern Implementation**:
  - Moved tool loading and graph compilation to `__init__`.
  - Reduced agent initialization time from ~3s to <0.1s per request.
  - Implemented thread-safe reuse of the compilation scope.
- **API "Light Mode"**:
  - Replaced heavy LangChain Toolkit loading with a text-based "Swagger Summary" cache.
  - Reduces LLM token consumption by avoiding full JSON schema injection for every query.
- **AsyncIO Core**:
  - Full restructuring of the `Graph` and `Nodes` to operate natively with `async/await`.
  - Fixed `RuntimeError: Event loop is closed` by using `atexit` and explicit session management.

### ✨ New Features

- **Self-Healing SQL Loop**:
  - The agent now captures `pymysql.err` exceptions.
  - Inject DB error messages back into the prompt for an automatic "Constraint/Syntax Correction" retry pass.
- **Smart URL Rewriting**:
  - Added `BaseUrlRequestsWrapper` middleware.
  - Automatically prepends the base domain (e.g., `https://api.myapp.com`) to relative paths (e.g., `/users`) hallucinated by LLMs.
- **Semantic Layer v2.5**:
  - Introduced `business_context.yaml` for defining Logical Busines Models over raw physical tables.

### 🐛 Bug Fixes

- Fixed SSL certificate verification warnings for local development environments.
- Resolved inheritance issues in `RequestsToolkit` by defining a proper Pydantic subclass wrapper.
- Corrected database connection leakage in `generate_dictionary.py`.

### 📚 Documentation

- Updated `01_architecture/` specs to reflect the Hybrid Router and Light Mode.
- Documented the distinction between "Physical Schema" and "Logical Models" in `semantic_spec.md`.

## [v1.0.0] - Initial Release

- Basic Text-to-SQL functionality.
- Simple LangGraph implementation.
- Support for MySQL and PostgreSQL.
