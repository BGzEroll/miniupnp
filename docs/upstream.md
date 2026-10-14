# 上游调查与取舍（2026-10-12）

固定 MiniUPnP 源码为 [f8c4f4c3320820e615b281147b3043f66c195f17](https://github.com/miniupnp/miniupnp/commit/f8c4f4c3320820e615b281147b3043f66c195f17)，即 2.3.11 正式版之后截至 2026-10-09 的已合并提交。没有直接使用浮动 master 来构建。选用整个固定 commit，避免 HTTP 接收重构的互相依赖修复遗漏；非 Linux、防火墙其他后端不参与编译。

## 已合并的重点修复

| 主题 | 已采用的上游提交或基线 |
|---|---|
| nftables 删除 filter、内外端口解析、TCP/UDP | 2.3.6–2.3.9 累积修复，包含 2025-01-10 删除问题；通过实际转发验证 |
| 2.3.10 转发回归 | 2.3.11 包含 2026-04-13 恢复修复 |
| 私有 WAN 恢复 | [2dcf639](https://github.com/miniupnp/miniupnp/commit/2dcf639)，2026-08-28，允许 private 标志时重新启用映射 |
| HTTP 请求大小限制及缓冲扩容 | d5fd424、1917228、37656e7 等 2026-08-29 提交；以及 89231db、c2e1278、4409ecb、c47f961 的边界/OOM 修复 |
| RemoteHost 租约恢复、内容过滤 | 671e5c0、5afea3c、7ce1ba5、a8ef16d、b2b496a |
| IPv6 地址解析 | 9942b0d |
| inet 表中的 IPv4/IPv6 区分 | [a8de55a](https://github.com/miniupnp/miniupnp/commit/a8de55a)，2026-10-09 |
| SSDP MX=0 | 8f13b7a，上游 Changelog 关联 CVE-2026-107159 |
| PinholeVerification 堆溢出、PCP option 解析、nft userdata 长度 | 2.3.11 正式版内的修复；上游/打包 PR 引用 CVE-2026-5720 |

完整源码基线与补丁校验值见 [sources.json](../sources.json)；详细调查记录已随原始测试报告归档。发布版基础 commit 为 `b91c025446d3ec3d9161cd56c91e200484af7906`。

## OpenWrt 与未合并 PR

- [openwrt/packages MiniUPnPd](https://github.com/openwrt/packages/tree/master/net/miniupnpd) 的参考检出：`9f24e4f3d4a13617cd141c43fa8811b18be32808`，版本 2.3.11。保留传统 UCI 键，移除 iptables 分支，修正 fw4 的 IPv6 forward 钩子位置和 reload 恢复。
- LuCI master 参考检出：`d12d55376188343d790fa40377c084245a4d2b86`。实际页面基于固定的 openwrt-23.05 页面版本，commit 在 `sources.json.luci_23_05_view_base`。
- [packages PR #28765](https://github.com/openwrt/packages/pull/28765)：检查时 open、未合并，head `312cf40a2ee98c9bf893c2ef40c7fdaf64b95a48`。参考其 IPv6 lease_file6、日志和 IGD 兼容性议题，**没有套用约 2000 行的 UCI/ACL/STUN 重构**。
- [LuCI PR #8415](https://github.com/openwrt/luci/pull/8415)：检查时 open、未合并，head `ec863ba66270c14dfc4943eb0b5ba7fa2c8d6f9e`。没有整体移植新界面和新 UCI schema。
- 原固件工作流仍引用分支形式的 ImmortalWrt/packages/LuCI。已读取用户的 360T7 工作流和分享会话；按最新指示没有修改任何 CI 文件或构建 aarch64。

## 本地补丁

`100-native-lifecycle-wan-and-admin.patch`：WAN 状态去重、缺址日志分级、IPv6/link netlink 事件、LAN 定向 PCP 组播、IPv4 PCP nonce 续期检查、同进程 SIGUSR2 恢复和 root 专用删除；IPv4 缺址 LAN 不视为通配授权网段；预期的离线发送错误降到 DEBUG，未知发送错误仍记录。复用上游已有控制 socket，没有新增常驻进程。

`110-nftables-comments-pinhole-and-cache.patch`：标准 nft comment TLV、IPv6 L4 protocol/计数器解析、Pinhole 不存在返回错误、UID 保留及避免碰撞、缓存失效、时间戳 upsert、接口名称匹配，支持同名 WAN ifindex 变化。

`120-ipv6-lease-records-and-restore.patch`：保留其他 IPv6 租约的 ID、去除重复换行、删除记录时检查边界、扩大恢复记录缓冲、保留 RemoteHost/nonce/ID，验证可路由 LAN/有效单播目标，禁止禁用 IPv6 时恢复其规则；无活跃规则不循环改写 IPv6 租约文件。IPv4 租约恢复增加可转发目标检查。

`130-soap-numeric-bounds-and-missing-pinhole.patch`：数字参数在缩窄到端口/整数之前检查，防止负数、超范围与尾随字符变成另一合法端口；GetPinholePackets 对不存在条目返回协议错误，保留正常租约语义。

nft forward hook 放在 `chain-pre/forward`，以便新 IPv6 请求到达动态 Pinhole 链；原 `chain-post` 会在 WAN zone 已拒绝后才运行。删除无用 postrouting 链。fw4 的 post-script include 只向服务发送恢复信号。

发现后复核确认：IPv6 lease_file6_add 中的“先加 epoch 再减 uptime”是正确的时间基准转换，没有把它误改成相对租约。实际缺陷是续期时写了传入 uid 到所有行、重复换行、查询缺失条目返回成功以及计数器缓存等。

`140-nft-delete-errors-and-atomic-ipv4.patch`：IPv4 DNAT 与对应放行规则在同一 nft 事务中删除，只请求末条操作的成功 ACK；失败后重置接收状态并只读确认规则是否仍在，不重发删除。IPv6 同样检查删除结果。已不存在与实际失败分开返回，失败保留租约；过期清理仅移除内核确认删除成功的 UID 对应记录。包仍仅启用 PCP MAP/ANNOUNCE，PCP PEER 不参与构建。
