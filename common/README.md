## Shared common Package
The common directory is a standalone Python package containing utilities and shared code used by tools in this repo.

Each tool that needs it declares a local dependency on common via Poetry in its pyproject.toml:
```toml
[tool.poetry.dependencies]
common = { path = "../common" }
```
### This approach ensures:

* No  code duplication of shared utilities.
* Clean import statements (e.g., from common.config import ...).
