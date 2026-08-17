# 智选量化终端 V2100 · 真实数据闭环版

这版把数据链路重构为：**真实行情 → 全市场股票池 → 历史 K 线 → A~H 策略 → 风控 → JSON 数据 → GitHub Pages UI**。

## 重要边界

1. GitHub Pages 是静态托管，不能提供真正的持续后台服务：
   - `market-snapshot.yml` 每 5 分钟生成一次全市场行情快照；
   - 浏览器盘中每 30 秒直连东方财富公开行情接口，刷新指数行情；
   - `daily-scan.yml` 在开盘前/收盘后运行全市场历史 K 线扫描并生成 `signals.json`；
   - 如果要求 5000+ 股票每 30 秒重新计算全部策略，必须部署常驻后端（Cloud Run / VPS / Worker 等）。
2. 不生成假 ROE、假利润增速、假 K 线、假 VWAP、假新闻或假回测指标。ATR 使用历史 K 线计算；数据不足时不应把估算值当成真实 ATR。
3. D 策略明确是“筹码结构穿透（成交成本代理）”，公开行情接口没有完整筹码分布，不能把代理指标冒充真实筹码峰。
4. 回测页面不展示旧版固定的 +142.8%、Sharpe 2.35、78.5% 胜率。只有真实回测数据生成后才显示。

## 部署

把整个目录覆盖到 `lliuzhongyuan/quant-system` 仓库后：

1. GitHub Settings → Actions → General → Workflow permissions 允许 `Read and write permissions`。
2. 手动运行一次 `每日全市场量化扫描` 和 `盘中实时市场快照`。
3. GitHub Pages 从 `main` 分支根目录发布。
4. Actions 正常运行后，网页读取 `data/market.json`、`data/signals.json`、`data/news.json`。

GitHub Actions 的计划任务最短间隔为 5 分钟，因此不能把它当作 30 秒后台行情服务器。真正的 30 秒全市场重算需要常驻后端。

## 数据源

- 东方财富 `push2.eastmoney.com`：全市场行情
- 东方财富 `push2his.eastmoney.com`：前复权日 K
- 东方财富 `np-listapi.eastmoney.com`：7×24 快讯

## 策略

A 低位启动 / B 主升突破 / C 回踩二波 / D 筹码结构代理 / E 龙头强度 / F 超跌反转 / G 量价异动 / H 风险拦截。

策略计算直接使用历史 K 线，而不是用几个实时字段伪装完整策略。