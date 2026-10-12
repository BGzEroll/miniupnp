# SPDX-License-Identifier: GPL-2.0-only
# OpenWrt packaging derived from openwrt/packages net/miniupnpd.
include $(TOPDIR)/rules.mk

PKG_NAME:=miniupnpd
PKG_VERSION:=2.3.11-git20261009
PKG_RELEASE:=1
UPSTREAM_COMMIT:=f8c4f4c3320820e615b281147b3043f66c195f17
PKG_SOURCE:=miniupnp-$(UPSTREAM_COMMIT).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/miniupnp/miniupnp/tar.gz/$(UPSTREAM_COMMIT)?
PKG_HASH:=341e76bce32f93660fa9cf022b07dc10bea3dbcaff9953097c2329d05fa408fc
PKG_BUILD_DIR:=$(BUILD_DIR)/miniupnp-$(UPSTREAM_COMMIT)
PKG_LICENSE:=BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE
PKG_BUILD_PARALLEL:=1
PKG_INSTALL:=1
PKG_CPE_ID:=cpe:/a:miniupnp_project:miniupnpd

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/version.mk

define Package/miniupnpd-nftables
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Firewall
  TITLE:=MiniUPnPd IGDv2, NAT-PMP, PCP and IPv6 (fw4)
  URL:=https://github.com/miniupnp/miniupnp
  DEPENDS:=+libmnl +libnftnl +libcap-ng +firewall4
  PROVIDES:=miniupnpd
  CONFLICTS:=miniupnpd-iptables
endef

define Package/miniupnpd-nftables/conffiles
/etc/config/upnpd
endef

CONFIGURE_VARS += DEBUG=
CONFIGURE_PATH:=miniupnpd
MAKE_PATH:=miniupnpd
CONFIGURE_ARGS:=--disable-fork --disable-pppconn --disable-tests \
	--firewall=nftables --igd2 --ipv6 --leasefile --portinuse --regex --vendorcfg
TARGET_CFLAGS += $(FPIC)
TARGET_LDFLAGS += -Wl,--gc-sections,--as-needed

define Build/Prepare
	$(call Build/Prepare/Default)
	echo "$(VERSION_NUMBER)" | tr '() ' '_' > $(PKG_BUILD_DIR)/miniupnpd/os.openwrt
	echo 'CPPFLAGS += -DMINIUPNPD_GIT_REF=\"$(UPSTREAM_COMMIT)-iwrt23.05\"' > $(PKG_BUILD_DIR)/miniupnpd/gitrev.mk
endef

define Build/Install
	$(call Build/Install/Default)
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/miniupnpd/miniupnpdctl $(PKG_INSTALL_DIR)/usr/sbin/
endef

define Package/miniupnpd-nftables/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/init.d $(1)/etc/config
	$(INSTALL_DIR) $(1)/etc/hotplug.d/iface $(1)/etc/uci-defaults $(1)/usr/share/miniupnpd
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/sbin/miniupnpd $(1)/usr/sbin/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/sbin/miniupnpdctl $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/miniupnpd.init $(1)/etc/init.d/miniupnpd
	$(INSTALL_CONF) ./files/upnpd.config $(1)/etc/config/upnpd
	$(INSTALL_DATA) ./files/miniupnpd.hotplug $(1)/etc/hotplug.d/iface/50-miniupnpd
	$(INSTALL_BIN) ./files/miniupnpd.defaults $(1)/etc/uci-defaults/99-miniupnpd
	$(INSTALL_BIN) ./files/firewall.include $(1)/usr/share/miniupnpd/firewall.include
	$(INSTALL_DIR) $(1)/usr/share/nftables.d
	$(CP) ./files/nftables.d/* $(1)/usr/share/nftables.d/
endef

$(eval $(call BuildPackage,miniupnpd-nftables))
