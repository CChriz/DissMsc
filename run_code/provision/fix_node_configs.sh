#!/usr/bin/env bash
# fix_node_configs.sh — provision the clone node configs from the ORIGINAL node
# configs with all coordinates rewritten to the clone (registry 8100, DB
# /srv/jwteam_clone, transport ports +100). The nodes read base_url / endpoint /
# connection_string from THEIR OWN ~/.jiuwenswarm/config/config.yaml, so these must
# be clone-correct or the nodes register into the wrong registry + touch the wrong DB.
#
#   sudo bash ~/jwclone/fix_node_configs.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0" >&2; exit 1; }
GRP=jw_cteam

rewrite() {   # stdin -> stdout : original coords -> clone coords
  sed -E \
    -e 's#/srv/jwteam/node#/srv/jwteam_clone/cnode#g' \
    -e 's#/srv/jwteam\b#/srv/jwteam_clone#g' \
    -e 's#jw_node#jw_cnode#g' \
    -e 's#jw_team\b#jw_cteam#g' \
    -e 's#jiuwenswarm6#jwclone#g' \
    -e 's#28610#28710#g' -e 's#28620#28720#g' -e 's#28630#28730#g' \
    -e 's#28611#28711#g' -e 's#28621#28721#g' -e 's#28631#28731#g' \
    -e 's#18093#18193#g' -e 's#18094#18194#g' -e 's#18095#18195#g' -e 's#18092#18192#g' \
    -e 's#19001#19101#g' -e 's#19000#19100#g' \
    -e 's#28555#28655#g' -e 's#28556#28656#g' -e 's#28557#28657#g' \
    -e 's#\b8000\b#8100#g'
}

for n in 1 2 3; do
  src=/srv/jwteam/node$n/.jiuwenswarm/config/config.yaml
  dstdir=/srv/jwteam_clone/cnode$n/.jiuwenswarm/config
  dst=$dstdir/config.yaml
  [ -f "$src" ] || { echo "ERROR: original config missing: $src" >&2; exit 1; }
  mkdir -p "$dstdir"
  [ -f "$dst" ] && cp -a "$dst" "$dst.autogen.bak"      # preserve the auto-generated default
  rewrite < "$src" > "$dst"
  chown -R "jw_cnode$n:$GRP" "/srv/jwteam_clone/cnode$n/.jiuwenswarm/config"
  chmod 640 "$dst"
  echo "cnode$n <- node$n :  $(grep -m1 -E 'base_url:' "$dst" | tr -s ' ')  |  $(grep -m1 connection_string "$dst" | tr -s ' ')"
done

echo
echo "== node config/.env : install REAL creds (app_agentserver load_dotenv(override=True) =="
echo "   otherwise loads .env.template placeholder API_BASE=https://example.com/... -> model calls fail) =="
TEAMENV=/home/cz776/jwclone/jwrun/team.env
[ -f "$TEAMENV" ] || { echo "ERROR: $TEAMENV missing" >&2; exit 1; }
for n in 1 2 3; do
  envdir=/srv/jwteam_clone/cnode$n/.jiuwenswarm/config
  mkdir -p "$envdir"
  [ -f "$envdir/.env" ] && cp -a "$envdir/.env" "$envdir/.env.template.bak"   # keep the placeholder copy
  # strip leading 'export ' so it is plain dotenv KEY=val (python-dotenv format)
  sed -E 's/^[[:space:]]*export[[:space:]]+//' "$TEAMENV" > "$envdir/.env"
  chown "jw_cnode$n:$GRP" "$envdir/.env"
  chmod 640 "$envdir/.env"
  echo "cnode$n .env <- team.env : $(grep -E '^API_BASE' "$envdir/.env")"
done

echo
echo "== verify: no ORIGINAL coordinates leaked into clone node configs (want: clean) =="
if grep -rlE ':8000"|/srv/jwteam/shared|:28611|:28556|:28557|jw_node' \
     /srv/jwteam_clone/cnode*/.jiuwenswarm/config/config.yaml 2>/dev/null; then
  echo "  ^^^ LEAK — inspect above"
else
  echo "  clean"
fi
echo
echo "== a2x endpoint (should be env-driven TEAM_BOOTSTRAP_PORT, default 28710) =="
grep -m1 -nE 'endpoint:.*TEAM_BOOTSTRAP_PORT' /srv/jwteam_clone/cnode1/.jiuwenswarm/config/config.yaml || true
echo "DONE."
