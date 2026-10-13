# nft 命名与上游对照

对照固定的 OpenWrt packages 9f24e4f3 和 MiniUPnP f8c4f4c3 源码：

- `inet fw4`、`upnp_forward`、`upnp_prerouting` 沿用 OpenWrt 包的命名。
- `pinhole-<ID> ts-<时间戳>: <描述>` 来自 MiniUPnPd 上游 nftpinhole.c 的 PINEHOLE_LABEL_FORMAT，格式未改变。
- IPv4 描述和 `PCP MAP <nonce>` 保留上游内容；LuCI 仅隐藏显示 nonce。
- 本地修改：forward hook 放到 chain-pre，接口从 IIF/ifindex 改为 IIFNAME，IPv6 增加 counter，userdata 使用标准 nft comment TLV；未新增自定义名称前缀。
- 未启用 PCP PEER，因此省略上游 OpenWrt 的 upnp_postrouting 空链。

实际规则已在 VM 隔离实验中验证，实验现已清理；原始 nft 记录随历史测试报告在仓库外归档。
