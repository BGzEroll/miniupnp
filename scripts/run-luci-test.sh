#!/bin/sh
# Requires host Playwright/Chromium and VM Python as documented in README.
set -eu
TASK_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_VM=root@192.168.114.210
TASK_BROWSER_PYTHON=${BROWSER_PYTHON:-python3}
scp -O "$TASK_ROOT/scripts/lab.sh" "$TASK_ROOT/scripts/integration.py" "$TASK_VM:/tmp/"
ssh "$TASK_VM" '/tmp/lab.sh setup'
restore_lab() {
	TASK_STATUS=$?
	trap - EXIT HUP INT TERM
	ssh "$TASK_VM" '/tmp/lab.sh cleanup' || :
	exit "$TASK_STATUS"
}
trap restore_lab EXIT HUP INT TERM
ssh "$TASK_VM" 'python3 -' <<'PY'
import sys
sys.path.insert(0,'/tmp')
import integration as t
t.ok(t.mapping(eport=51910,iport=51911,lease=240))
t.ok(t.pinhole(port=51912,lease=240))
PY
ssh "$TASK_VM" 'nft list chain inet fw4 upnp_prerouting; nft list chain inet fw4 upnp_forward' > "$TASK_ROOT/reports/luci-fixture.nft"
"$TASK_BROWSER_PYTHON" "$TASK_ROOT/scripts/luci-browser.py"
