#!/bin/sh
# OpenWrt BusyBox ash supports arguments to sourced scripts.
# shellcheck disable=SC2240
# Load the VM's actual PassWall nft generator with a synthetic local node.
# No proxy core or external connection is started. Physical interfaces bypass it.
. /usr/share/passwall/app.sh no-op
ENABLED=1
ENABLED_DEFAULT_ACL=1
TCP_NODE=upnp_rule_test
UDP_NODE=upnp_rule_test
TCP_UDP=0
LOCALHOST_PROXY=0
. /usr/share/passwall/nftables.sh no-op
DIR=/usr/share/passwall
case "$1" in
start)
	start
	for chain in dstnat mangle_prerouting hwnat_pass; do
		nft "insert rule inet passwall $chain iifname != \"upnp-l\" iifname != \"upnp-w\" counter return comment \"UPnP isolated test boundary\""
	done
	# A real netifd WAN is added by setup_sets. The raw lab WAN is independent.
	nft 'add element inet passwall passwall_lanlist { 8.8.4.1 }'
	;;
stop) stop ;;
*) exit 2 ;;
esac
