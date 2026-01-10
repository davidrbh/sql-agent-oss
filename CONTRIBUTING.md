# Contributing to SQL Agent OSS

Thank you for your interest in contributing to SQL Agent OSS! 🚀

We welcome contributions of all forms: bug reports, feature requests, documentation improvements, and code changes.

## 🛠️ Development Setup

1.  **Prerequisites**:

    - Python 3.11+
    - Poetry (Dependency Management)
    - Docker (Optional, for local DB)

2.  **Installation**:

    ```bash
    git clone https://github.com/your-username/sql-agent-oss.git
    cd sql-agent-oss
    poetry install
    poetry shell
    ```

3.  **Environment Variables**:
    Copy the example file and configure it:
    ```bash
    cp .env.example .env
    ```

## 🧪 Running Tests

Currently, we rely on manual integration scripts due to the complex nature of LLM interactions.

- **Run the Agent:** `python scripts/run_agent.py`
- **Test Schema:** `python scripts/test_schema.py`
- **Validate Connection:** `python scripts/test_connection.py`

_Note: Future versions will include `pytest` suites._

## 📝 Code Style

- We use **Type Hints** strictly.
- We follow **PEP 8** guidelines.
- Prefer **AsyncIO** for all I/O operations.
- **Documentation**: If you change the logic, update the `docs/` folder.

## 🔄 Pull Request Process

1.  Create a new branch: `git checkout -b feature/my-new-feature`
2.  Commit your changes: `git commit -m 'Add some feature'`
3.  Push to the branch: `git push origin feature/my-new-feature`
4.  Open a Pull Request.

## 🤝 Community

If you have questions, please open an Issue on GitHub.
