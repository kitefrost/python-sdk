#!/usr/bin/env bash
# KiteFrost alpha - one-command SDK setup against the alpha environment.
#
#   curl -fsSL https://raw.githubusercontent.com/kitefrost/python-sdk/main/staging-setup.sh | bash -s -- ttrpg-gm
#   curl -fsSL https://raw.githubusercontent.com/kitefrost/python-sdk/main/staging-setup.sh | bash -s -- game-narrative
#
# Creates ./kitefrost-alpha (a Python virtual environment), installs the alpha SDK
# for your pack, and makes the environment point at the alpha API automatically.
# Afterwards:   source kitefrost-alpha/bin/activate
# and use the SDK with no base_url - it already knows where to go.
#
# Why pinned: alpha SDKs are pre-releases, and a plain `pip install` skips
# pre-releases, which would give you an older build that cannot reach the alpha API.
set -euo pipefail

PACK="${1:-}"
VERSION="1.2.0a4"
API="https://api-staging.kitefrost.ai"
DIR="${KITEFROST_VENV:-kitefrost-alpha}"

case "$PACK" in
  ttrpg-gm|game-narrative) ;;
  *) echo "usage: staging-setup.sh <ttrpg-gm|game-narrative>" >&2; exit 2 ;;
esac

PY="$(command -v python3 || command -v python || true)"
[[ -n "$PY" ]] || { echo "Python 3.10+ is required" >&2; exit 1; }

echo "==> creating $DIR"
"$PY" -m venv "$DIR"
"$DIR/bin/pip" install --quiet --upgrade pip
echo "==> installing kitefrost-$PACK==$VERSION"
"$DIR/bin/pip" install --quiet "kitefrost-$PACK==$VERSION"

# Persist the API address inside the venv so every `activate` sets it.
if ! grep -q "KITEFROST_BASE_URL" "$DIR/bin/activate"; then
  printf '\nexport KITEFROST_BASE_URL="%s"\n' "$API" >> "$DIR/bin/activate"
fi

echo "==> checking the connection"
KITEFROST_BASE_URL="$API" "$DIR/bin/python" -c "
from kitefrost_core import KiteFrostCore
print('   API reachable:', KiteFrostCore(api_key='check').health.check().get('status'))
"

cat <<EOF

Done. To use it:

  source $DIR/bin/activate
  python

EOF
if [[ "$PACK" == "ttrpg-gm" ]]; then CLS="TtrpgGmClient"; MOD="kitefrost_ttrpg_gm"; else CLS="GameNarrativeClient"; MOD="kitefrost_game_narrative"; fi
cat <<EOF
  >>> from $MOD import $CLS
  >>> client = $CLS.from_api_key("sk_...")   # key from the API keys page of your dashboard
  >>> client.core.health.check()

EOF
