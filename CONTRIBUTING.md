# Contributing to Eventyay Hubspot Plugin

We welcome contributions to the Eventyay Hubspot plugin! This plugin integrates Eventyay events with HubSpot, syncing data like attendees, orders, and custom fields.

## Support & Community Guidelines

If you need help or want to discuss a feature before building it:
- Check the [Eventyay Documentation](https://docs.eventyay.com) for core platform concepts.
- Review existing GitHub Issues or open a new one to ask questions.
- Read the [FOSSASIA Open Source Developer Guide and Best Practices](https://blog.fossasia.org/open-source-developer-guide-and-best-practices-at-fossasia/).

## Repository Layout

Understanding the repository structure will help you navigate the codebase:

- `hubspot/`: Main application code containing Django models, views, services, signals, forms, and templates.
- `tests/`: Comprehensive test suite using `pytest`.
- `pyproject.toml`: The central configuration file for the Python project. It manages dependencies and registers the Hubspot integration as a discoverable plugin within the core Eventyay platform.
- `Makefile`: Helpful commands for tasks like compiling translations.

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
   - Create a developer account on the [HubSpot Developer Portal](https://developers.hubspot.com/) and create a new app using HubSpot's project-based Developer Platform.
   - In the app settings, set your Redirect URI to match `HUBSPOT_REDIRECT_URI` (e.g., `http://localhost:8000/control/hubspot/callback/`).
   - Configure the required app scopes to match the scopes listed in `.env.hubspot.sample` (e.g., `oauth crm.objects.contacts.read crm.objects.contacts.write crm.objects.deals.read crm.objects.deals.write`).
   - Add these credentials to your `.env.hubspot` file.

   > **Warning:** Never commit `.env.hubspot` or share your `HUBSPOT_CLIENT_SECRET`.
5. Activate the virtual environment you use for Eventyay development.
6. Install the plugin in editable mode:
   ```bash
   uv pip install -e .
   ```
7. Compile the translations (if necessary):
   ```bash
   make
   ```

## Architecture Rules for Contributors

When developing for the Hubspot plugin, respect the following architectural separations:
- **Models**: Defines database schema. Keep logic in models minimal.
- **Views**: Handles HTTP requests and responses. Should generally delegate complex logic to services.
- **Services**: Contains the core business logic, such as data syncing, Hubspot API interactions, and data transformations.
- **Signals**: Listens for core Eventyay events (e.g., ticket purchased, attendee updated) and triggers tasks to sync data to HubSpot.
- **Tasks**: Background processing jobs using Celery to ensure smooth asynchronous data syncs.

Ensure that any queries fetching Eventyay data are appropriately scoped to the event using `django_scopes.scope(event=event)`.

## API and Service Endpoints

The most crucial endpoints in this plugin manage the HubSpot OAuth flow and integration setup:
- **OAuth Callback**: Handled by views that capture the authorization code from HubSpot and exchange it for an access token.
- **Plugin Settings**: Found within the Eventyay Control Panel (under the event's plugin settings). This handles the user interface for authenticating and configuring the integration.
- **Data Sync Services**: Logic residing in the `services/` directory is responsible for pushing data to HubSpot endpoints (e.g., Contacts, Deals).

## AI-Assisted Development

If you use AI tools (like GitHub Copilot, Cursor, Claude, etc.) to help write code:
- **Review everything:** Always review the AI-generated code for accuracy, security, and adherence to our architectural conventions.
- **Test thoroughly:** Do not submit AI-generated code without writing corresponding tests and verifying it works locally.
- **Avoid hallucinations:** AI might invent non-existent Eventyay core functions or imports. Always verify API endpoints and module paths against the actual codebase.

## Branch creation

Create a **new branch from the default branch** for every change. Do not commit directly to the default branch.

### Branch naming

Use a **prefix that describes the kind of change**, then a short slug. Use the same vocabulary in branch names, commit messages, and PR titles.

| Prefix | When to use | Example |
|--------|-------------|---------|
| `feat/` or `feature/` | New functionality | `feat/sync-custom-fields` |
| `fix/` | Bug fix | `fix/attendee-sync-error` |
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

## Troubleshooting

- **Tests fail with "ModuleNotFoundError"**: Ensure you have activated the virtual environment of the *core Eventyay repository* before running pytest.
- **HubSpot OAuth Error**: Double-check that your `HUBSPOT_REDIRECT_URI` exactly matches the one you registered in your HubSpot Developer Portal app.
- **Plugin not showing up in Eventyay**: Ensure you installed it in editable mode (`uv pip install -e .`) within the correct virtual environment, and that you restarted your local Eventyay development server.


## Licensing

All contributions are accepted under the Apache License 2.0. By contributing to this project, you agree to license your contribution under these terms.
