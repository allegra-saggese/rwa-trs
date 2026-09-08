#!/usr/bin/env bash
# get_gfw_key.sh — obtain a Global Forest Watch data-API key.
#
# Run this yourself; it asks for a password and must not be run by anyone else.
# The key is written to .gfw_api_key (gitignored) and never printed in full.
#
#   ./get_gfw_key.sh --signup     first time only: creates the account
#   ./get_gfw_key.sh              you already have a password: get the key
#
# What the key unlocks: WRI SDPT (planted trees) and RADD deforestation alerts.

set -euo pipefail
API="https://data-api.globalforestwatch.org"
EMAIL="${GFW_EMAIL:-absagges@ucsc.edu}"
NAME="${GFW_NAME:-Allegra Saggese}"
ORG="${GFW_ORG:-UC Santa Cruz}"
OUT="$(cd "$(dirname "$0")" && pwd)/.gfw_api_key"

need() { command -v "$1" >/dev/null || { echo "missing: $1"; exit 1; }; }
need curl; need python3
json() { python3 -c 'import sys,json;d=json.load(sys.stdin)
k=sys.argv[1]
def find(o):
    if isinstance(o,dict):
        if k in o: return o[k]
        for v in o.values():
            r=find(v)
            if r is not None: return r
    elif isinstance(o,list):
        for v in o:
            r=find(v)
            if r is not None: return r
    return None
r=find(d); print(r if r is not None else "")' "$1"; }

if [[ "${1:-}" == "--signup" ]]; then
  echo "Signing up $EMAIL ..."
  curl -sS -X POST "$API/auth/sign-up" -H "Content-Type: application/json" \
    -d "{\"name\":\"$NAME\",\"email\":\"$EMAIL\"}" | head -c 400; echo
  echo
  echo "Check your email and set a password, then re-run WITHOUT --signup."
  exit 0
fi

# Password is read silently: never echoed, never stored, never in a shell history.
printf "GFW password for %s: " "$EMAIL"
read -rs PASSWORD
echo

echo "Requesting access token ..."
# NOTE: this endpoint is form-encoded, and the field is 'username' but takes the email.
TOKEN=$(curl -sS -X POST "$API/auth/token" \
  --data-urlencode "username=$EMAIL" \
  --data-urlencode "password=$PASSWORD" | json access_token)

if [[ -z "$TOKEN" ]]; then
  echo "Failed to get a token. Wrong password, or the account is not confirmed yet."
  echo "If you have not signed up: ./get_gfw_key.sh --signup"
  exit 1
fi
echo "  token acquired."

echo "Creating API key ..."
# 'domains' is deliberately omitted. Setting it restricts the key to those
# origins, and it then fails silently from a script.
KEY=$(curl -sS -X POST "$API/auth/apikey" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"alias\":\"rwa-trs\",\"organization\":\"$ORG\",\"email\":\"$EMAIL\"}" | json api_key)

if [[ -z "$KEY" ]]; then
  echo "Key creation failed. Existing keys:"
  curl -sS "$API/auth/apikeys" -H "Authorization: Bearer $TOKEN" | head -c 600; echo
  exit 1
fi

umask 077
printf '%s' "$KEY" > "$OUT"
echo "  key written to $OUT  (chmod 600, gitignored)"
echo "  fingerprint: ${KEY:0:8}...${KEY: -4}"

echo
echo "Verifying ..."
curl -sS "$API/auth/apikey/$KEY/validate" -H "x-api-key: $KEY" | head -c 200; echo
echo
echo "Done. Tell Claude the key is in place - do not paste the key itself."
