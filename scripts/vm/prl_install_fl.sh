#!/usr/bin/env bash
set -euo pipefail

# Installs FL Studio into a Parallels macOS VM by resolving Image-Line's
# redirect URL at runtime, then downloading and installing the current DMG.
#
# Why this shape:
# - The concrete DMG filename changes by release.
# - We run everything inside the guest to avoid host/guest file-copy friction.
# - We support both .pkg and .app payload patterns defensively.

VM_NAME="${CORTEX_PRL_VM:-Cortex Runner}"
REDIRECT_URL="${CORTEX_FL_REDIRECT_URL:-https://support.image-line.com/redirect/flstudio_mac_installer}"
REMOTE_SCRIPT_PATH="/tmp/cortex_install_fl_studio.sh"

if ! command -v prlctl >/dev/null 2>&1; then
  echo "prlctl not found. Install Parallels Desktop first."
  exit 1
fi

status="$(prlctl status "${VM_NAME}" 2>/dev/null | awk '{print $NF}')" || {
  echo "VM '${VM_NAME}' not found."
  echo "Check available VMs:"
  prlctl list --all || true
  exit 1
}

if [[ "${status}" != "running" ]]; then
  echo "VM '${VM_NAME}' is not running (status=${status}). Start it first:"
  echo "  ./scripts/vm/prl_start.sh"
  exit 1
fi

payload="$(cat <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REDIRECT_URL="$1"
DMG_PATH="/tmp/flstudio_mac_latest.dmg"

# Resolve the real installer URL from the vendor redirect endpoint.
URL="$(curl -fsSI "$REDIRECT_URL" | grep -i '^location:' | tail -n1 | awk '{print $2}' | tr -d '\r')"
if [[ -z "$URL" ]]; then
  echo "ERROR: could not resolve installer URL from redirect: $REDIRECT_URL" >&2
  exit 1
fi
echo "resolved_url=$URL"

echo "Downloading installer to $DMG_PATH ..."
rm -f "$DMG_PATH"
curl -fL "$URL" -o "$DMG_PATH"
ls -lh "$DMG_PATH"

echo "Mounting DMG ..."
ATTACH_OUT="$(hdiutil attach -nobrowse "$DMG_PATH")"
printf '%s\n' "$ATTACH_OUT"

VOLUME_PATH="$(printf '%s\n' "$ATTACH_OUT" | sed -n 's#^.*\(/Volumes/.*\)$#\1#p' | tail -n1)"
if [[ -z "$VOLUME_PATH" ]]; then
  echo "ERROR: failed to detect mounted volume path" >&2
  exit 1
fi
echo "mounted_volume=$VOLUME_PATH"

PKG_PATH="$(find "$VOLUME_PATH" -maxdepth 3 -name '*.pkg' -print -quit || true)"
APP_PATH="$(find "$VOLUME_PATH" -maxdepth 3 -name '*.app' -print -quit || true)"
echo "pkg=$PKG_PATH"
echo "app=$APP_PATH"

if [[ -n "$PKG_PATH" ]]; then
  echo "Installing PKG payload ..."
  installer -pkg "$PKG_PATH" -target /
elif [[ -n "$APP_PATH" ]]; then
  APP_NAME="$(basename "$APP_PATH")"
  DEST_APP="/Applications/$APP_NAME"
  echo "Copying APP payload to $DEST_APP ..."
  rm -rf "$DEST_APP"
  ditto "$APP_PATH" "$DEST_APP"
else
  echo "ERROR: no .pkg or .app payload found on mounted image" >&2
  ls -la "$VOLUME_PATH"
  exit 1
fi

echo "Detaching DMG ..."
hdiutil detach "$VOLUME_PATH" || hdiutil detach "$VOLUME_PATH" -force || true

INSTALLED_APP="$(find /Applications -maxdepth 1 -iname '*fl*studio*.app' -print -quit || true)"
if [[ -z "$INSTALLED_APP" ]]; then
  echo "ERROR: FL Studio app not found after install" >&2
  ls -la /Applications | sed -n '1,200p'
  exit 1
fi
echo "installed_app=$INSTALLED_APP"

# Avoid first-launch Gatekeeper friction in an ephemeral test VM.
xattr -dr com.apple.quarantine "$INSTALLED_APP" || true
echo "SUCCESS: install completed"
EOF
)"

b64_payload="$(printf '%s' "${payload}" | base64 | tr -d '\n')"

echo "Pushing installer script into VM '${VM_NAME}' ..."
prlctl exec "${VM_NAME}" "bash -lc 'echo \"${b64_payload}\" | base64 -d > ${REMOTE_SCRIPT_PATH} && chmod +x ${REMOTE_SCRIPT_PATH}'"

echo "Running FL Studio installer in VM '${VM_NAME}' ..."
prlctl exec "${VM_NAME}" "bash -lc '${REMOTE_SCRIPT_PATH} \"${REDIRECT_URL}\"'"

echo
echo "Install flow completed."
echo "Next manual step: open FL Studio in the VM and sign in with your Image-Line account."
