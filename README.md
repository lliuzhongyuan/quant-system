# 智选量化终端 V2100 · 真实数据闭环版

这版把数据链路重构为：**真实行情 → 全市场股票池 → 历史 K 线 → A~H 策略 → 风控 → JSON 数据 → GitHub Pages UI**。

## 当前数据源与可用性

GitHub Actions 实测发现，东方财富 `push2.eastmoney.com` 在 GitHub-hosted runner 上会出现 502/连接被远端关闭，因此生产全市场行情链路已切换为**新浪财经公开列表 API + 新浪日K API**。两条接口均已在本仓库 Actions 环境实测成功：股票列表、日K均可访问。

- 新浪财经列表：`vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData`
- 新浪财经日K：`money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData`
- 东方财富财务摘要：作为可选增强；GitHub Actions 无法访问时显示“待财报数据”，不伪造 ROE/利润。
- 东方财富 7×24：如果接口不可用，新闻区保持为空，不用静态新闻冒充实时资讯。

新浪列表 API 提供名称、最新价、涨跌幅、成交量、成交额、PE、PB、总市值、流通市值、换手率等字段；日K接口提供 OHLCV 历史数据。相关接口结构与字段说明可参考公开接口探查资料。citeturn6view0turn7search0

## 重要边界

1. GitHub Pages 是静态托管，不能提供真正的持续后台服务：
   - `market-snapshot.yml` 每 5 分钟生成一次全市场行情快照；
   - 浏览器盘中每 30 秒直连公开行情接口，刷新指数行情；
   - `daily-scan.yml` 在开盘前/收盘后运行全市场历史 K 线扫描并生成 `signals.json`；
   - 如果要求 5000+ 股票每 30 秒重新计算全部策略，必须部署常驻后端（Cloud Run / VPS / Worker 等）。
2. 不生成假 ROE、假利润增速、假 K 线、假 VWAP、假新闻或假回测指标。ATR 使用历史 K 线计算，数据不足直接放弃该信号。
3. D 策略明确是“筹码结构穿透（成交成本代理）”，公开行情接口没有完整筹码分布，不能把代理指标冒充真实筹码峰。
4. 回测页面不展示旧版固定收益、Sharpe 或胜率；只有真实回测数据生成后才显示。
5. 选股池排除 ST、退市、停牌、科创板（688）和北交所代码（8/4），与此前系统口径保持一致。

## 部署

GitHub Pages 从 `main` 根目录发布。Actions 需要 `contents: write` 才能自动提交数据快照；如果仓库 Settings → Actions → General 的 Workflow permissions 不是 Read and write，需要开启。

GitHub Actions 的计划任务最短间隔为 5 分钟，因此不能把它当作 30 秒后台行情服务器。真正的 30 秒全市场重算需要常驻后端。

## 策略

A 低位启动 / B 主升突破 / C 回踩二波 / D 筹码结构代理 / E 龙头强度 / F 超跌反转 / G 量价异动 / H 风险拦截。

策略计算直接使用历史 K 线，而不是用几个实时字段伪装完整策略。