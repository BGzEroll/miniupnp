#!/bin/sh
set -eu
TASK_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_VM=root@192.168.114.210
scp -O "$TASK_ROOT/tests/lab.sh" "$TASK_ROOT/tests/integration.py" "$TASK_ROOT/tests/passwall.py" "$TASK_ROOT/tests/passwall-driver.sh" "$TASK_VM:/tmp/"
ssh "$TASK_VM" 'set -e; test "$(uci -q get passwall.@global[0].enabled)" = 0; test -z "$(uci changes passwall)"; test ! -d /root/upnp-passwall-backup; mkdir /root/upnp-passwall-backup; cp /etc/config/passwall /root/upnp-passwall-backup/config; sysctl -n net.bridge.bridge-nf-call-iptables > /root/upnp-passwall-backup/bridge4 2>/dev/null || :; sysctl -n net.bridge.bridge-nf-call-ip6tables > /root/upnp-passwall-backup/bridge6 2>/dev/null || :; if [ -f /var/etc/passwall.include ]; then cp /var/etc/passwall.include /root/upnp-passwall-backup/include; fi'
restore_vm() {
	TASK_STATUS=$?
	trap - EXIT HUP INT TERM
	scp -O "$TASK_VM:/root/upnp-passwall-result.json" "$TASK_VM:/root/upnp-passwall-result.stdout" "$TASK_VM:/root/upnp-passwall-result.nft" "$TASK_ROOT/reports/" || :
	ssh "$TASK_VM" 'sh /tmp/passwall-driver.sh stop; uci revert passwall; cp /root/upnp-passwall-backup/config /etc/config/passwall; if [ -s /root/upnp-passwall-backup/bridge4 ]; then sysctl -w net.bridge.bridge-nf-call-iptables=$(cat /root/upnp-passwall-backup/bridge4); fi; if [ -s /root/upnp-passwall-backup/bridge6 ]; then sysctl -w net.bridge.bridge-nf-call-ip6tables=$(cat /root/upnp-passwall-backup/bridge6); fi; if [ -f /root/upnp-passwall-backup/include ]; then cp /root/upnp-passwall-backup/include /var/etc/passwall.include; else rm -f /var/etc/passwall.include; fi; /tmp/lab.sh cleanup; mv /root/upnp-passwall-backup "/root/upnp-passwall-backup-$(date +%s)"' || :
	exit "$TASK_STATUS"
}
trap restore_vm EXIT HUP INT TERM
ssh "$TASK_VM" 'set -e; if [ -f /root/upnp-passwall-result.json ]; then TASK_ARCHIVE=/root/passwall-archive-$(date +%s); mkdir "$TASK_ARCHIVE"; mv /root/upnp-passwall-result.json /root/upnp-passwall-result.stdout /root/upnp-passwall-result.nft "$TASK_ARCHIVE/"; fi; /tmp/lab.sh setup; uci set passwall.upnp_rule_test=nodes; uci set passwall.upnp_rule_test.type=Xray; uci set passwall.upnp_rule_test.protocol=socks; uci set passwall.upnp_rule_test.address=127.0.0.1; uci set passwall.upnp_rule_test.port=10999'
ssh "$TASK_VM" 'sh /tmp/passwall-driver.sh start; python3 /tmp/passwall.py /root/upnp-passwall-result.json > /root/upnp-passwall-result.stdout 2>&1'
