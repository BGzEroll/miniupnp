# SPDX-License-Identifier: Apache-2.0
include $(TOPDIR)/rules.mk
PKG_NAME:=luci-app-upnp
PKG_VERSION:=23.05-custom
PKG_RELEASE:=1
PKG_LICENSE:=Apache-2.0
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
endef

define Package/luci-app-upnp/install
	$(INSTALL_DIR) $(1)/www $(1)/usr
	$(CP) ./htdocs/* $(1)/www/
	$(CP) ./root/* $(1)/
endef
$(eval $(call BuildPackage,luci-app-upnp))
