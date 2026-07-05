# CROWD v0.1 — AI硬件链挤压强度监视看板 工程规格

**文档角色**：Claude（架构/审计）→ CodeBuddy（实现）交接规格
**决策人**：Alice
**版本**：v0.1.1（MVP：面板一 + 面板四 + §7.5 ICS日历订阅生成；面板二、三为 Phase 2，本文档已给出完整规格但明确标注不在MVP范围）
**日期**：2026-07-04
**修订记录**：v0.1.1 新增 §7.5 ICS生成规格、负向测试N8、验收标准第6条；面板四由"仅页面渲染"升级为"页面渲染 + Google日历订阅投影"

---

## 0. 项目定位声明（必须逐字渲染在页面顶部，不得省略）

> **本看板为人眼研究监视器（human-eye research monitor），定位对标SR3看板。**
> 不产生任何机械信号，不接入 ABCD v3.5 / ABCDS v0.5 的任何状态机、信号管线或仓位模块。
> 全部输出仅供人工判断AI硬件链内短线切换参考。
> 禁止未来任何版本在未经独立审计的情况下将本看板数据接入主框架（防 "integrated but never declared" 风险）。

该声明同时写入 `README.md` 第一段和页面 `<header>` 区。

---

## 1. 看板要回答的三个问题（设计锚）

1. **钱现在在链内怎么流**（日频，自动）→ 面板一、二
2. **真值锚最近一次说了什么**（季度，手动）→ 面板三
3. **下一个能改变判断的信息节点是哪天**（日历，手动）→ 面板四

任何不服务于这三个问题的功能一律视为范围蔓延，拒绝实现。

---

## 2. Repo 结构

```
crowd-monitor/
├── README.md                  # 含定位声明、面板说明、维护手册
├── config/
│   └── baskets.json           # 篮子成分配置（唯一成分来源，页面必须渲染）
├── data/
│   ├── prices/                # 自动管线输出，daily parquet，按ticker分文件
│   ├── trendforce_vintage.json  # 面板三手动数据（Phase 2）
│   └── calendar.json          # 面板四手动数据
├── scripts/
│   ├── fetch_prices.py        # yfinance 拉取
│   ├── build_panels.py        # 计算比值/动量/z-score，产出渲染用JSON
│   └── validate.py            # 负向测试 + 数据完整性检查（CI阻断）
├── site/
│   ├── index.html             # 静态单页，读 site/data/*.json 渲染
│   └── crowd_calendar.ics     # 构建产物，由 calendar.json 生成（§7.5），供Google日历URL订阅
├── .github/workflows/
│   └── daily.yml              # 定时任务
└── tests/
    └── test_negative.py       # 见 §8
```

单repo、单静态页，部署 GitHub Pages，与现有基建同构。**不与 ABCD/ABCDS 任何repo共享代码或数据文件。**

---

## 3. 篮子配置（config/baskets.json）

```json
{
  "config_version": "2026-07-04",
  "benchmark": {"ticker": "SOXX", "note": "用SOXX ETF而非^SOX指数，yfinance数据可靠性优先；口径差异可接受，因本看板只看相对形态"},
  "baskets": {
    "MEM":   {"label": "存储",   "tickers": ["MU", "SNDK"],           "weight": "equal"},
    "OPT":   {"label": "光通信", "tickers": ["COHR", "LITE", "FN"],   "weight": "equal"},
    "GPU":   {"label": "GPU链",  "tickers": ["NVDA", "AMD", "AVGO"],  "weight": "equal"},
    "NCLOUD":{"label": "新云",   "tickers": ["CRWV", "NBIS", "IREN"], "weight": "equal"},
    "OPT_CN":{"label": "A股光模块", "tickers": ["300308.SZ", "300502.SZ"], "weight": "equal", "phase": 2}
  },
  "changelog": [
    {"date": "2026-07-04", "change": "初始成分", "reason": "v0.1规格"}
  ]
}
```

**成分纪律**：
- 成分表及 `changelog` 必须完整渲染在页面底部。任何成分变更必须追加 changelog 条目（日期+变更+理由），禁止直接覆盖。
- 篮子收益 = 成分等权**日收益率**均值，再累积成指数（基期100）。禁止用价格均值（除权/股本差异会污染）。
- 成分变更日起新口径生效，页面上该篮子曲线在变更日画一条垂直虚线并标注 config_version，防止口径不一致段被人眼误读为连续序列。

---

## 4. 面板一：链内相对强度矩阵（MVP，日频自动）

**目的**：买方"多存储/空光模块"对冲结构的日频影子；挤出效应叙事强度计。

**计算**（全部在 `build_panels.py`，渲染层不做计算——终值渲染纪律）：
- 每篮子对基准的比值序列：`R_basket(t) = Index_basket(t) / Index_SOXX(t)`，基期归一为1.0，回溯起点 2025-07-01（一年历史，覆盖本轮存储行情全程）。
- 每比值序列附三个派生读数：20日动量（20日比值变化%）、60日动量、比值z-score（相对自身250日均值/标准差；不足250日则用全样本并标注"样本不足"）。
- **核心剪刀差**：`MEM/SOXX − OPT/SOXX`（两比值各自归一后作差），单独一张图，这是看板的第一屏。

**渲染**：
- 第一屏：剪刀差曲线 + 当前值 + 20日方向箭头。
- 第二屏：四篮子比值曲线（同图，SOXX基准线=1.0水平虚线）。
- 第三屏：读数表格（篮子 × [比值当前值, 20d动量, 60d动量, z-score]）。z-score 绝对值 ≥ 2 的单元格视觉高亮，但**不附带任何操作建议文案**——高亮只表示"值得人眼注意"。
- 每张图右上角标注数据 as-of 日期。若数据日期 < 最近一个美股交易日，整个面板顶部渲染醒目 STALE 横幅（黄底），标注滞后天数。

**读法说明**（页面上以折叠说明块渲染，文案如下）：
> 剪刀差走阔 = 挤压叙事升温；剪刀差见顶回落而季度真值锚（面板三）仍在上修 = price-in 完成的候选信号，光模块折价回吐观察点。反之剪刀差与真值锚同向再加速 = 均值回归情景权重上调。本说明为读法参考，非信号规则。

---

## 5. 面板二：A股-美股时差面板（Phase 2，日频自动）

**目的**：量化"A股滞后美股约一个月的传导时差"，为跨市场短线提供结构参考。

**计算**：
- `OPT_CN` 与 `OPT` 各自计算20日滚动收益（各用本市场交易日历，互不插值）。
- 时差指标 = `RollRet20(OPT) − RollRet20(OPT_CN)`，仅在两市场均为交易日的日历日上计算；任一方休市则该日渲染断点（N/A），**禁止前值填充**。
- 附一个辅助读数：两序列的滚动60日互相关峰值滞后期（单位：交易日），作为"当前传导时差"估计。互相关样本不足60日渲染 N/A。

**时区纪律**：A股收盘（UTC+8 15:00）早于美股同日开盘。对齐规则固定为：日历日 T 的时差指标 = A股T日收盘 vs 美股 T-1 日收盘。此规则写入代码注释和页面说明，防止未来维护时静默改变对齐方向。

---

## 6. 面板三：TrendForce vintage 表（Phase 2，季度手动）

**数据文件** `data/trendforce_vintage.json`：

```json
{
  "records": [
    {
      "quarter": "2026Q1",
      "metric": "dram_contract",
      "vintage_date": "2026-01-05",
      "type": "forecast_initial",
      "value_low": 55, "value_high": 60,
      "source_url": "https://...",
      "note": ""
    },
    {
      "quarter": "2026Q1",
      "metric": "dram_contract",
      "vintage_date": "2026-02-10",
      "type": "forecast_revised",
      "value_low": 90, "value_high": 95,
      "source_url": "https://..."
    }
  ]
}
```

**字段纪律**：
- `type` 枚举严格限定 `forecast_initial | forecast_revised | realized`。**同一序列图中 forecast 与 realized 必须以不同视觉样式区分（如空心点 vs 实心点），且 realized 缺失时该季渲染"实现值：N/A（待财报确认）"，禁止用最新 forecast 顶替。**（本条源于一次真实审计事故：预测值被当作已实现值引用。）
- `metric` 枚举：`dram_contract | nand_contract`。口径混杂（PC DRAM / server DRAM / blended）时在 `note` 字段注明原文口径，宁可留note也不得静默归并。
- 派生字段 `revision_gap`（最新vintage中值 − initial中值）由渲染层现算，**不落盘**。
- 每个数值旁强制渲染 vintage_date。

**渲染**：每季一行的表格：`初始预测 → 最新修正 → 实现值 → 修正差`，外加一张"修正差历史轨迹"小图（修正差收敛到零附近 = 价格动能见顶的领先特征候选）。

**维护手册**（写入README）：录入时机为 TrendForce press center 每次发布后人工读原文录入；实现值以次季初 TrendForce 回顾 + 美光/三星财报 ASP 口径人工确认。一季度预计 4–8 条记录。**不做爬虫。**

---

## 7. 面板四：信息节点日历（MVP，手动）

**数据文件** `data/calendar.json`：

```json
{
  "events": [
    {
      "date": "2026-07-07",
      "date_confirmed": false,
      "name": "三星 2026Q2 初步业绩（preliminary）",
      "category": "memory_truth",
      "hypothesis": "存储ASP动能是否兑现Q2的58-63%/70-75%合同价预测",
      "note": "三大存储厂最快真值，早于正式财报约3周"
    },
    {
      "date": "2026-07-29",
      "date_confirmed": false,
      "name": "四大巨头财报季开始（META首发待确认）",
      "category": "capex_guidance",
      "hypothesis": "总盘子约束是否松动：Capex指引上修=挤出效应被总量稀释"
    }
  ]
}
```

**字段纪律**：
- `hypothesis` 为必填字段——每个节点必须回答"该节点验证什么假设"，不允许只写事件名。这是本面板与普通财经日历的唯一区别，也是其存在的全部理由。
- `date_confirmed`：false 表示预估日期，渲染时日期后加"（预估）"。
- `category` 枚举：`memory_truth | capex_guidance | trendforce_release | optics_earnings | other`。

**渲染**：按时间升序列出未来8周节点，每条显示倒计时天数（T-N）、假设文案、类别色标。已过期节点自动移入页面底部折叠区（保留，不删除——事后复盘用）。倒计时由渲染层基于当前日期现算。

**初始日历内容由 Alice 首次录入**（涉及具体日期确认，不在CodeBuddy范围；CodeBuddy只需实现渲染，可用上述两条示例数据作为开发用假数据，但示例数据必须在验收前清空并由 `validate.py` 检查 note 字段不含 "示例" 字样）。

---

## 7.5 ICS日历订阅生成（MVP，随面板四交付）

**目的**：将 calendar.json 投影为 iCalendar 文件，供 Google 日历通过 URL 订阅，使信息节点自动同步到手机/桌面日历。

**架构原则（必须写入README）**：
> calendar.json 是信息节点的**唯一真值来源**，ICS 及 Google 日历均为其只读投影。禁止在 Google 日历侧直接编辑事件后反向同步；日期变更一律修改 calendar.json，由构建流程重新生成 ICS。

**实现**：
- `build_panels.py` 末尾新增步骤：读取 `data/calendar.json`，生成 `site/crowd_calendar.ics`。依赖 `icalendar` 包（pip），生成逻辑约30行，不引入其他依赖。
- 随每日 Actions 部署到 Pages，订阅URL固定为 `https://<pages域名>/crowd_calendar.ics`。Google 日历侧由 Alice 一次性"通过网址添加日历"完成订阅（Google轮询周期约12–24小时，对季度级事件足够）。**CI 不持有任何 Google 凭证——本方案的选型理由即零OAuth/零secrets，禁止后续改为 Google Calendar API 直写。**

**事件映射规则（逐条实现）**：

| calendar.json 字段 | ICS 字段 | 规则 |
|---|---|---|
| `name` | `SUMMARY` | `date_confirmed=false` 时加前缀 `（预估）`；`category` 以中文标签后缀，如 `［存储真值］` |
| `hypothesis` + `note` | `DESCRIPTION` | 第一行固定为 `验证假设：` + hypothesis 全文；note 非空则另起一行 `备注：` + note。**hypothesis 必须完整进入 DESCRIPTION**——手机通知里看到的应是"该节点验证什么"，而非裸事件名 |
| `date` | `DTSTART`/`DTEND` | 一律生成**全天事件**（`VALUE=DATE`），DTEND=次日（RFC 5545 排他约定）。禁止生成具体时刻——财报发布时刻通常未知，具体时间是虚假精度 |
| — | `UID` | 确定性生成：`sha1(date + name)@crowd-monitor`。**同一事件改期后 UID 不变**（用改期前后不变的 name 参与哈希；若 name 也变则视为新事件），保证订阅端更新而非重复 |
| — | `VALARM` | 每事件附一个提前1天的 DISPLAY 提醒 |
| 已过期事件 | 保留输出 | 过去事件仍写入 ICS（订阅端历史可见，供复盘），与面板四页面折叠区行为一致 |

**category 中文标签映射**：`memory_truth→存储真值`、`capex_guidance→Capex指引`、`trendforce_release→TrendForce发布`、`optics_earnings→光链财报`、`other→其他`。

**日历元数据**：`X-WR-CALNAME: CROWD 信息节点`；`X-WR-TIMEZONE: Asia/Shanghai`（全天事件本身无时区歧义，此项仅为订阅端显示友好）。

**维护流程（写入README维护手册）**：IR/交易所公布或变更日期 → Alice 修改 calendar.json（确认日期时将 `date_confirmed` 翻 `true`）→ 下次 Actions 运行自动重生成 ICS → Google 日历约一天内自动同步。日期发现本身不自动化（不做爬虫），一季度人工维护成本约十几分钟。

---

## 8. 自动化与负向测试

**GitHub Actions（daily.yml）**：
- 触发：cron 美东收盘后（UTC 22:30，工作日），另加 workflow_dispatch 手动触发。
- 流程：fetch_prices → validate → build_panels（含 §7.5 ICS生成）→ commit site/data/*.json 及 site/crowd_calendar.ics → Pages 自动部署。
- **validate 失败则阻断 commit，页面保持上一次成功状态并依赖 STALE 横幅提示**——宁可陈旧且标注，不可错误且新鲜。

**负向测试清单（tests/test_negative.py，全部必须实现，验收硬条件）**：

| # | 测试 | 防的事故类别 |
|---|------|-------------|
| N1 | 某ticker当日无数据时，篮子该日渲染N/A，禁止前值填充 | stale passthrough |
| N2 | vintage文件中 forecast 类型混入 realized 序列时 validate 报错 | 预测当实现值（已发生过的真实事故） |
| N3 | 篮子成分变更但 changelog 未追加条目时 validate 报错 | 口径静默漂移 |
| N4 | yfinance 返回价格为0/负数/单日涨跌幅>±40%时标记异常并阻断，人工确认 | 脏数据入库 |
| N5 | calendar.json 存在 hypothesis 为空的事件时 validate 报错 | 面板四退化为普通日历 |
| N6 | 页面header缺失定位声明全文时 validate 报错（字符串比对） | 定位漂移 |
| N7 | site/data 中出现落盘的派生字段（revision_gap、倒计时等）时报错 | 终值渲染纪律 |
| N8 | ICS生成时任一事件 hypothesis 为空/缺失则构建失败；生成后校验每个 VEVENT 的 DESCRIPTION 含 `验证假设：` 前缀，且同一事件改期前后 UID 不变（改期幂等测试） | 面板四纪律穿透到日历层；订阅端重复事件 |

---

## 9. 验收标准（MVP）

1. 面板一 + 面板四按上述规格渲染，Pages 可访问。
2. 负向测试 N1/N3/N4/N5/N6/N7/N8 通过（N2 属 Phase 2 面板三，可延后但接口需预留）。
3. 定位声明逐字出现在 README 与页面 header。
4. 连续5个交易日 Actions 自动运行无人工干预。
5. README 含面板三/四的手动维护手册及 §7.5 的架构原则与维护流程。
6. `crowd_calendar.ics` 可被 Google 日历成功订阅，事件通知中可见完整 hypothesis 文本；人工改期一个测试事件后，订阅端更新为新日期且不产生重复事件。

**明确不在范围内（拒绝实现）**：任何形式的信号打分、买卖建议文案、与ABCD/ABCDS的数据互通、TrendForce爬虫、消息推送、Google Calendar API 直写（日历同步仅走 §7.5 ICS订阅，CI不得持有Google凭证）、财报日期自动抓取。

---

## 10. Phase 2 触发条件（由 Alice 决定，写在此处备忘）

MVP 上线后运行两周，若确认日常决策流中实际使用（人眼每日查看剪刀差 + 依据面板四节点安排短线仓位动作），再启动面板二、三。若两周内未形成使用习惯，项目冻结于 v0.1，不再投入。
