# SPDX-License-Identifier: Apache-2.0
include $(TOPDIR)/rules.mk
PKG_NAME:=luci-app-upnp
PKG_VERSION:=23.05-custom
PKG_RELEASE:=3
PKG_LICENSE:=Apache-2.0
PKG_BUILD_DEPENDS:=luci-base/host
include $(INCLUDE_DIR)/package.mk

define Package/luci-app-upnp
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=UPnP IGD / PCP (IPv4 and IPv6)
  DEPENDS:=+luci-base +miniupnpd-nftables +rpcd-mod-ucode
  PKGARCH:=all
endef

define Build/Compile
	$(STAGING_DIR_HOSTPKG)/bin/po2lmo ./po/zh_Hans/upnp.po $(PKG_BUILD_DIR)/upnp.zh-cn.lmo
endef

define Package/luci-app-upnp/install
	$(INSTALL_DIR) $(1)/www $(1)/usr
	$(CP) ./htdocs/* $(1)/www/
	$(CP) ./root/* $(1)/
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/i18n
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/upnp.zh-cn.lmo $(1)/usr/lib/lua/luci/i18n/
endef
$(eval $(call BuildPackage,luci-app-upnp))
