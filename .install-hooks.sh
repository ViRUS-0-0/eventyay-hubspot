#!/bin/sh
set -e

REPO_DIR=$(git rev-parse --show-toplevel)
GIT_DIR="$REPO_DIR/.git"
HOOK_FILE="$GIT_DIR/hooks/pre-commit"

if [ -z "${VIRTUAL_ENV:-}" ] || [ ! -f "$VIRTUAL_ENV/bin/activate" ]; then
    echo "Could not find your virtual environment (VIRTUAL_ENV is not set or activate script missing)" >&2
    exit 1
fi

cat > "$HOOK_FILE" <<'EOF'
#!/bin/sh
set -e
. "${VIRTUAL_ENV:?}/bin/activate"
black --check .
ruff check .
flake8 .
EOF

chmod +x "$HOOK_FILE"
