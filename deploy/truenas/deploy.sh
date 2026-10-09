#!/bin/sh
# Build the image on the TrueNAS SCALE host and create/update the "wedding" custom app.
#
#   deploy/truenas/deploy.sh root@nas.local
#
# Reads deploy/truenas/deploy.private.env (see deploy.env.example) and prod.private.env (the app settings,
# see ../../.env.example); both are git-ignored. Needs a clean git tree: the image is tagged with the commit.
# SSH_OPTS can carry extra ssh options, e.g. SSH_OPTS="-i ~/.ssh/deploy_key -o IdentitiesOnly=yes".
set -eu

TARGET=${1:?usage: deploy.sh user@host}
cd "$(dirname "$0")/../.."
DEPLOY_ENV=${DEPLOY_ENV:-deploy/truenas/deploy.private.env}
APP_ENV=${APP_ENV:-prod.private.env}
SSH_OPTS=${SSH_OPTS:-}

git diff --quiet && git diff --cached --quiet || { echo "Commit your changes first (the image is tagged with HEAD)" >&2; exit 1; }
TAG=$(git rev-parse --short HEAD)
APP_DIR=$(sed -n 's/^APP_DIR=//p' "$DEPLOY_ENV")
[ -n "$APP_DIR" ] || { echo "APP_DIR missing in $DEPLOY_ENV" >&2; exit 1; }

# shellcheck disable=SC2086
ssh_run() { ssh $SSH_OPTS "$TARGET" "$@"; }

echo "==> Uploading $TAG to $TARGET:$APP_DIR"
ssh_run "mkdir -p $APP_DIR/src $APP_DIR/data $APP_DIR/content $APP_DIR/caddy && chown 568:568 $APP_DIR/data && find $APP_DIR/src -mindepth 1 -delete"
git archive HEAD | ssh_run "tar -x -C $APP_DIR/src"
# shellcheck disable=SC2086
scp -q $SSH_OPTS "$APP_ENV" "$TARGET:$APP_DIR/wedding.env"
sed "s/^APP_TAG=.*/APP_TAG=$TAG/" "$DEPLOY_ENV" | ssh_run "cat > $APP_DIR/deploy.env"
ssh_run "cp $APP_DIR/src/deploy/truenas/Caddyfile $APP_DIR/Caddyfile && chmod 600 $APP_DIR/wedding.env $APP_DIR/deploy.env"
if [ -d content ]; then
  echo "==> Mirroring the private overlay (content/)"
  tar -C content -c . | ssh_run "find $APP_DIR/content -mindepth 1 -delete; tar -x -C $APP_DIR/content && chmod -R a+rX $APP_DIR/content"
fi

echo "==> Building the image on the host"
ssh_run "cd $APP_DIR/src && docker build -q -t wedding:$TAG ."

echo "==> Creating or updating the app"
ssh_run "cd $APP_DIR && docker compose --env-file deploy.env -f src/compose.yaml config > rendered.yaml && python3 -c '
import json
yaml = open(\"rendered.yaml\").read()
open(\"create.json\", \"w\").write(json.dumps({\"custom_app\": True, \"app_name\": \"wedding\", \"custom_compose_config_string\": yaml}))
open(\"update.json\", \"w\").write(json.dumps({\"custom_compose_config_string\": yaml}))
' && if midclt call app.query '[[\"name\",\"=\",\"wedding\"]]' | grep -q '\"name\": \"wedding\"'; then
    midclt call --job app.update wedding \"\$(cat update.json)\" >/dev/null && echo updated
  else
    midclt call --job app.create \"\$(cat create.json)\" >/dev/null && echo created
  fi; rm -f create.json update.json"

echo "==> Done. Containers:"
ssh_run "docker ps --filter name=wedding --format '{{.Names}}  {{.Status}}'"
