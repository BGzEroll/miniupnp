#!/usr/bin/env python3
"""Check targeted replacement, preservation and repeatability in a fake tree."""
import pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as temp:
    target=pathlib.Path(temp);(target/'scripts').mkdir();(target/'rules.mk').touch();(target/'scripts/feeds').touch()
    (target/'.config').write_text('CONFIG_KEEP_ME=y\nCONFIG_PACKAGE_miniupnpd-iptables=y\nCONFIG_PACKAGE_luci-i18n-upnp-zh-cn=y\n')
    for feed,name in [('packages','miniupnpd'),('luci','luci-app-upnp')]:
        original=target/'feeds'/feed/name;original.mkdir(parents=True);(original/'Makefile').write_text('upstream')
        link=target/'package/feeds'/feed/name;link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to(original)
    other=target/'package/feeds/luci/luci-app-passwall';other.mkdir();(other/'Makefile').write_text('keep')
    for _ in range(2):subprocess.run(['sh',str(root/'scripts/install-to-openwrt.sh'),str(target)],check=True)
    assert not (target/'package/feeds/packages/miniupnpd').exists()
    assert (target/'feeds/packages/miniupnpd/Makefile').read_text()=='upstream'
    assert (other/'Makefile').read_text()=='keep'
    assert (target/'package/custom-upnp/miniupnpd/Makefile').read_bytes()==(root/'net/miniupnpd/Makefile').read_bytes()
    assert (target/'package/custom-upnp/luci-app-upnp/Makefile').read_bytes()==(root/'applications/luci-app-upnp/Makefile').read_bytes()
    config=(target/'.config').read_text();assert 'CONFIG_KEEP_ME=y' in config
    assert 'CONFIG_PACKAGE_miniupnpd-nftables=y' in config and 'CONFIG_PACKAGE_miniupnpd-iptables=y' not in config
print('PASS：替换旧链接、保留 feed 原源码和 PassWall、包配置正确、重复执行一致。')
