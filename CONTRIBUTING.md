# Contributing to Eventyay Hubspot Plugin

We welcome contributions to the Eventyay Hubspot plugin! This plugin integrates Eventyay events with HubSpot, syncing data like attendees, orders, and custom fields.

## Getting Started

1. Set up a working [Eventyay Development Setup](https://github.com/fossasia/eventyay) as this plugin requires the core platform to run.
2. Fork this repository and clone your fork:
   ```bash
   git clone https://github.com/your-username/eventyay-hubspot.git
   cd eventyay-hubspot
   ```
3. Create a new branch for your feature or bugfix (see [Branch creation](#branch-creation)).
4. Set up the environment variables:
   ```bash
   cp .env.hubspot.sample .env.hubspot
   ```
   To obtain your `HUBSPOT_CLIENT_ID` and `HUBSPOT_CLIENT_SECRET`:
   - Create a developer account on the [HubSpot Developer Portal](https://developers.hubspot.com/).
   - Under the **Legacy Apps** section, click **Create legacy app** (it will be created as a Public app) to generate a Client ID and Client Secret.
   - In the app settings, set your Redirect URI to match `HUBSPOT_REDIRECT_URI` (e.g., `http://localhost:8000/control/hubspot/callback/`).
   - Add these credentials to your `.env.hubspot` file.
5. Activate the virtual environment you use for Eventyay development.
6. Install the plugin in editable mode:
   ```bash
   uv pip install -e .
   ```
7. Compile the translations (if necessary):
   ```bash
   make
   ```

## Branch creation

Create a **new branch from the default branch** for every change. Do not commit directly to the default branch.

### Branch naming

Use a **prefix that describes the kind of change**, then a short slug. Use the same vocabulary in branch names, commit messages, and PR titles.

| Prefix | When to use | Example |
|--------|-------------|---------|
| `feat/` or `feature/` | New functionality | `feat/sync-custom-fields` |
| `fix/` or `fix-` | Bug fix | `fix/attendee-sync-error` |
| `chore/` or `patch/` | Tooling, deps, housekeeping | `chore/update-dependencies` |
| `docs/` | Documentation only | `docs/add-setup-guide` |
| `test/` | Test-only changes | `test/hubspot-auth-mock` |
| `refactor/` | Restructure without behavior change | `refactor/api-client` |

**Tips:**
- Use lowercase and hyphens in the slug (`fix/sync-timeout`, not `fix/SyncTimeout`).
- Tie work to an issue when one exists (e.g., `fix/12-sync-timeout`).
- One concern per branch. Split unrelated fixes into separate PRs.

## Commit messages

Write messages that explain **what** changed and **why**. We follow the [Conventional Commits](https://www.conventionalcommits.org/) style:

```text
type(optional-scope): short summary

Optional longer body when the summary is not enough.
```

**Examples:**
- `feat(sync): add support for custom properties syncing`
- `fix(auth): handle expired hubspot tokens gracefully`
- `chore(deps): bump requests to 2.31.0`

## Code Style & Linting

This repository enforces code style guidelines via CI. We use `pre-commit` to run `ruff` for both linting and formatting.

To set up the hooks locally:
```bash
pip install pre-commit
pre-commit install
```

To manually run the checks on all files:
```bash
pre-commit run --all-files
```

## Running Tests

The test suite uses `pytest`. Because this is a plugin, **you must use the Eventyay repository's virtual environment** to run the tests, as it contains all the necessary Django settings and core dependencies.

To run the tests, activate your core eventyay development virtual environment and run:
```bash
pytest tests/
```

## Further Reading

- The `hubspot/` directory contains the main application code (models, views, services, signals).
- The `tests/` directory contains the comprehensive pytest suite.
- Refer to the main [Eventyay documentation](https://docs.eventyay.com) for broader platform architecture and plugin development concepts.

## Licensing

All contributions are accepted under the Apache License 2.0. By contributing to this project, you agree to license your contribution under these terms.
