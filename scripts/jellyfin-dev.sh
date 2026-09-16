#!/bin/sh
# Set up a local Jellyfin for development and print the JELLYFIN_* lines for
# backend/.env. Idempotent: safe to re-run against a server already set up.
#   scripts/jellyfin-dev.sh <films-dir>
# Env: JELLYFIN_URL (default http://localhost:8096), JELLYFIN_DEV_PASSWORD
# (default livdev). Needs curl and python3.
set -eu
FILMS=${1:?usage: jellyfin-dev.sh <films-dir>}
J=${JELLYFIN_URL:-http://localhost:8096}
PW=${JELLYFIN_DEV_PASSWORD:-livdev}
JSON='Content-Type: application/json'
CLIENT='Authorization: MediaBrowser Client="livs-dev", Device="dev", DeviceId="livs-dev", Version="0"'
py() { python3 -c "import sys, json; d = json.load(sys.stdin); $1"; }

curl -sf "$J/health" >/dev/null || { echo "no Jellyfin at $J" >&2; exit 1; }

# Jellyfin answers camelCase before the wizard and PascalCase after it.
if [ "$(curl -s "$J/System/Info/Public" | py 'print(d.get("StartupWizardCompleted", d.get("startupWizardCompleted")))')" != "True" ]; then
  echo "completing the first-run wizard"
  curl -sf -X POST "$J/Startup/Configuration" -H "$JSON" \
    -d '{"UICulture":"en-GB","MetadataCountryCode":"GB","PreferredMetadataLanguage":"en"}'
  curl -sf "$J/Startup/User" >/dev/null
  curl -sf -X POST "$J/Startup/User" -H "$JSON" -d "{\"Name\":\"liv\",\"Password\":\"$PW\"}"
  curl -sf -X POST "$J/Startup/RemoteAccess" -H "$JSON" \
    -d '{"EnableRemoteAccess":false,"EnableAutomaticPortMapping":false}'
  curl -sf -X POST "$J/Startup/Complete"
fi

AUTH=$(curl -sf -X POST "$J/Users/AuthenticateByName" -H "$JSON" -H "$CLIENT" \
  -d "{\"Username\":\"liv\",\"Pw\":\"$PW\"}")
TOKEN=$(echo "$AUTH" | py 'print(d["AccessToken"])')
USER_ID=$(echo "$AUTH" | py 'print(d["User"]["Id"])')
T="Authorization: MediaBrowser Token=\"$TOKEN\""

if ! curl -sf "$J/Auth/Keys" -H "$T" | py 'sys.exit(0 if any(k["AppName"] == "livs" for k in d["Items"]) else 1)'; then
  echo "creating API key 'livs'"
  curl -sf -X POST "$J/Auth/Keys?app=livs" -H "$T"
fi
KEY=$(curl -sf "$J/Auth/Keys" -H "$T" | py 'print([k["AccessToken"] for k in d["Items"] if k["AppName"] == "livs"][0])')

if ! curl -sf "$J/Library/VirtualFolders" -H "$T" | py 'sys.exit(0 if any(f["Name"] == "Films" for f in d) else 1)'; then
  echo "adding the Films library at $FILMS"
  curl -sf -X POST "$J/Library/VirtualFolders?name=Films&collectionType=movies&refreshLibrary=true" -H "$T" -H "$JSON" \
    -d "{\"LibraryOptions\":{\"PathInfos\":[{\"Path\":\"$FILMS\"}],\"EnableRealtimeMonitor\":false}}"
fi

echo "waiting for the scan"
i=0
while [ $i -lt 60 ]; do
  N=$(curl -s "$J/Items?IncludeItemTypes=Movie&Recursive=true" -H "$T" | py 'print(d["TotalRecordCount"])')
  [ "$N" -gt 0 ] && break
  sleep 3; i=$((i + 1))
done
echo "films indexed: $N"
echo
echo "JELLYFIN_URL=$J"
echo "JELLYFIN_API_KEY=$KEY"
echo "JELLYFIN_USER_ID=$USER_ID"
