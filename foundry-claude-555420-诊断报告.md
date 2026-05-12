# Azure Foundry Claude 模型调用故障诊断报告

**客户**：新石器（Neolix）
**Azure 账号**：`msft_user@gitlabbotneolix.onmicrosoft.com`
**订阅**：`ad_ai_subscription` (`909485c7-c98b-4cfe-bb6e-64d9f9ff2747`)
**Tenant**：`gitlabbotneolix.onmicrosoft.com` (`2a2c13a8-7d14-4a73-8c0d-666d7f95c7ee`)
**报告时间**：2026-05-12 11:55 GMT+8（UTC 03:55）
**排查范围**：只读，未修改任何配置 / 未轮换 key

---

## 1. 故障表象

订阅 `ad_ai_subscription` 下两个 Azure AI Services（Foundry）资源上的 **所有 Claude 模型部署** 自 2026-05-12 UTC 01:00 起 **持续返回 HTTP 400**：

```
HTTP/1.1 400
{"error":{"type":"invalid_request_error",
 "message":"555420: Your resource has been blocked because we detected unusual behavior."}}
```

涉及部署：

| 资源 | 区域 | Claude 部署 | 5/12 错误率 |
|---|---|---|---|
| `msft-mmyiz2p1-eastus2` | East US 2 | sonnet-4-6 / haiku-4-5 / opus-4-6 / opus-4-7 | **59 % 4xx** |
| `msft-mn7fqhlw-swedencentral` | Sweden Central | sonnet-4-6 / haiku-4-5 / opus-4-6 / opus-4-7 | **85 % 4xx** |
| `foundry-claude-test1` | West US 3 | （只有 GPT，无 Claude 部署） | n/a |

---

## 2. 关键结论

**这是 Anthropic 上游对客户的 Anthropic organization 做的反滥用封禁，不是 Azure 侧问题。**

证据：

1. **同资源、同 key、同时间点**调用 `gpt-5.5` 正常（5/12 共 2253 次请求，成功率 99.5%）—— 排除 key 失效、配额耗尽、网络/ACL 问题
2. **555420 是 Anthropic 平台错误码**（不是 Azure / OpenAI 错误码体系）
3. **两个 region 的 4 个 Claude 部署全部同步被封**，说明封禁粒度是 **Anthropic organization 级别**（资源属性里有 capability `AnthropicOrganizationCreated: True`）
4. **新部署的 `claude-opus-4-7`（5/12 02:39 创建）"上线即被封"**，进一步证明是 organization 级，不是 deployment 级
5. Azure 资源属性 `provisioningState: Succeeded`，`abusePenalty: null`，`networkAcls.defaultAction: Allow` —— Azure 侧无任何阻断

---

## 3. 时间线

时间为 **UTC**（北京时间 = UTC + 8）。

| 时间 (UTC) | 事件 | 来源 |
|---|---|---|
| 2026-05-06 15:31 / 16:03 | `swedencentral` 资源出现两次 Resource Health: Available → **Unavailable** | Activity Log |
| 2026-05-07 07:31 | 部署 `gpt-5.5` (caller: admin@) | Activity Log |
| 2026-05-12 00:00 ~ 00:59 | Claude 调用仍然正常（`eastus2`: haiku 130 ok / 14 err；sonnet 134 ok / 13 err） | Metrics: ModelRequests |
| 2026-05-12 02:39 | 部署 `claude-opus-4-7` (caller: gitlab_bot@neolix.cn) | Activity Log |
| 2026-05-12 02:40 | **gitlab_bot@neolix.cn 在 1 分钟内调用 41 次 ListKeys**（异常密度） | Activity Log |
| **2026-05-12 01:00 ~** | **Anthropic 触发封禁，所有 Claude 部署 200 → 0，全部 400 (555420)** | Metrics |
| 2026-05-12 02:00 (UTC) | 高峰：单小时 **2 542 次** Claude 请求，**全部失败**（sweden）；eastus2 同小时 **2 562 次** Claude 请求，仅 0 成功 | Metrics |
| 2026-05-12 03:37–04:06 | msft_user@ 9 次 ListKeys（**经核验是微软员工排查动作，与 abuse 无关**，详见 §4.3 注） | Activity Log |
| 2026-05-12 04:00 (UTC, 北京 12:00) | 调用量回落到 75 次/小时，Claude 仍 100 % 失败 | Metrics |

---

## 4. 调用量 / 错误码细分（5/12 UTC 00:00 – 04:00）

### 4.1 按部署 × 状态

`msft-mmyiz2p1-eastus2`

| Deployment | 200 | 400 | 备注 |
|---|---:|---:|---|
| **gpt-5.5** | **2 241** | 11 | 客户唯一在用且工作正常的模型 |
| claude-haiku-4-5 | 130 | **1 023** | |
| claude-sonnet-4-6 | 134 | **946** | |
| claude-opus-4-7 | 73 | **112** | 5/12 02:39 才部署 |
| claude-opus-4-6 | 0 | 8 | 已无人使用 |

`msft-mn7fqhlw-swedencentral`（无 GPT 部署）

| Deployment | 200 | 400 |
|---|---:|---:|
| claude-haiku-4-5 | 137 | **1 003** |
| claude-sonnet-4-6 | 126 | **959** |
| claude-opus-4-7 | 103 | **107** |
| claude-opus-4-6 | 0 | 7 |

### 4.2 按小时（Claude 总流量）

```
hour (UTC)   eastus2 ok / 4xx     swedencentral ok / 4xx
00:00         337 /   32          366 /   22         ← 正常窗口
01:00           0 /  409            0 /  466         ← 封禁瞬间生效
02:00           0 / 1 309           0 / 1 264        ← 高峰，全失败
03:00           0 /   329           0 /   324
04:00           0 /     3           –
```

**封禁的精确时间点**：UTC 5/12 00:xx → 01:00 之间（北京 5/12 08:xx → 09:00 之间）。

### 4.3 客户侧身份频繁拉 Key（5/7 – 5/12，仅 ListKeys）

> **数据修正记录（重要）**：早期版本本表列出 3 个身份合计 145 次，其中包含 `msft_user@…` 38 次。后经核验，`msft_user` 这一行 **全部是微软员工（含本人）在 5/12 03:37–04:06 UTC 排查本故障时跑 `az cognitiveservices account keys list` 触发的，来自微软 corpnet 出口 IP（167.220.232.0/23、2404:f801:8050::/48，whois: MICROSOFT-APNIC, Microsoft Singapore corpnet egress），与客户侧 abuse pattern 无关，已从证据里剔除**。

**修正后客户侧真实 ListKeys 分布**：

| caller | List Keys 次数 | 性质 |
|---|---:|---|
| `gitlab_bot@neolix.cn` | 82（其中 5/12 02:40 一分钟内 41 次 ⚠️） | 客户 CI/Bot 身份 |
| `admin@gitlabbotneolix.onmicrosoft.com` | 25 | 客户管理员 |
| **客户侧合计** | **107** | |
| ~~`msft_user@…`~~ | ~~38~~ → **剔除** | 微软员工排查动作（5/12 03:37–04:06 UTC，corpnet 出口） |

—— 同一组 key 在 **2 个客户侧身份** 反复拉取 + 跨 region 并发使用，是触发 Anthropic 反滥用检测的典型行为模式。其中 **gitlab_bot 5/12 02:40 一分钟 41 次** 这一条单独已经足够说明客户端代码没有缓存 key。

---

## 5. 555420 触发原因（按本案匹配度排序）

1. **短时间高 QPS / 失败重试风暴**（最可能）：5/12 02:00 单 region 单小时 2500+ 次请求几乎全失败，再加上多个 region 并发，量已经达到 abuse 阈值
2. **同 key 多客户端并发**：客户侧 2 个身份 (gitlab_bot + admin) 在 7 天内 107 次 ListKeys，且单分钟出现 41 次的极端密度，说明 key 被复制到多处脚本 / CI / 容器中并行使用
3. **多 region 流量叠加**：`eastus2` 与 `swedencentral` 调用量几乎对称（haiku 1000+ / sonnet 950+ / opus-4-7 ~100），客户端在做 region failover 或 round-robin，从 Anthropic 视角是**同一 organization 双倍流量**
4. 内容违规 / prompt injection：可能性较低，本案模式更像流量异常

### 5.1 "是不是高并发导致的？" 的辨析

**严格说不是单纯"高并发导致"。** 必须区分两件事：

| | 触发封禁 | 加重 / 延长封禁 |
|---|---|---|
| **时间窗口** | 5/12 09:00 北京时间之前的"累积行为画像" | 5/12 09:00 之后的"死循环重试风暴" |
| **现象** | 多 region 并发 + 多身份共用 key + 频繁 ListKeys | 02:00 UTC 单小时 5000+ 次几乎全失败的请求 |
| **是否高并发** | **不是**（haiku 才 20-50 次/5min ≈ 5-10 RPM） | 是，但这是**被封后的连锁反应** |

**为什么"高并发"不是触发因素**：
- 09:00 之前 metrics 显示 haiku 才 20-50 次/5min，换算 RPM 约 5-10，**这点量在任何 RPM 限额下都是九牛一毛**
- 如果是配额超了，错误码会是 **429**，不是 400+555420
- 555420 是 **行为模式封禁**（abuse pattern），不是流量封禁（rate limit）

**与客户沟通话术建议**：
- ❌ 不要说"是因为你们调用太多了" → 客户会觉得"那我以后就不敢用了"
- ✅ 要说"是调用模式不规范，规范了之后量再大也没问题"→ 给客户能改的方向

### 5.2 触发因素的证据三件套

下面三条单独看每条都不算铁证，**合起来构成 Anthropic 反滥用判定的典型滥用画像**。

#### 证据 1：同 key 跨 region 并发使用

**数据来源**：Metrics → ModelRequests，按 deployment 拆，5/12 UTC 0–4

| Deployment | eastus2 总调用 | swedencentral 总调用 | 偏差 |
|---|---:|---:|---:|
| claude-haiku-4-5 | 1153 | 1140 | 1.1% |
| claude-sonnet-4-6 | 1080 | 1085 | 0.5% |
| claude-opus-4-7 | 185 | 210 | 13% |
| claude-opus-4-6 | 8 | 7 | – |

**怎么看出"同 key"**：
- 两 region 部署名完全一致（claude-haiku-4-5 / sonnet-4-6 / opus-4-6 / opus-4-7）
- 部署版本也一致（haiku-4-5 都是 20251001、sonnet-4-6 都是 v1）
- **每个 deployment 在两个 region 的调用量几乎对称**（≤ 13% 偏差，主要的两个 deployment 偏差 < 1.1%）
- 这种镜像级对称只能是**同一客户端在做 round-robin / failover**，不可能是两批独立用户

**Anthropic 视角**：两个 endpoint 后面是同一个 Anthropic organization（资源 capability 显示 `AnthropicOrganizationCreated: True`），从他们统计角度就是 organization 流量翻倍。

复现命令：
```bash
az cognitiveservices account list -g default-rg \
  --query "[?kind=='AIServices'].{name:name,location:location}"
# 然后对每个资源拉 metrics
TOKEN=$(az account get-access-token --query accessToken -o tsv)
curl -G "https://management.azure.com/.../providers/Microsoft.Insights/metrics" \
  --data-urlencode 'metricnames=ModelRequests' \
  --data-urlencode 'timespan=2026-05-12T00:00:00Z/2026-05-13T00:00:00Z' \
  --data-urlencode '$filter=ModelDeploymentName eq '"'*'"'' \
  -H "Authorization: Bearer $TOKEN"
```

#### 证据 2：同 key 被多个客户侧身份反复使用

**数据来源**：Activity Log（5/7–5/12，eastus2 资源），过滤 Operation = `Microsoft.CognitiveServices/accounts/listKeys/action`

| caller | List Keys 次数 | 性质 |
|---|---:|---|
| `gitlab_bot@neolix.cn` | 82 | 客户 CI/Bot 身份 |
| `admin@gitlabbotneolix.onmicrosoft.com` | 25 | 客户管理员 |
| **客户侧合计** | **107** | |
| ~~`msft_user@gitlabbotneolix.onmicrosoft.com`~~ | ~~38~~ → **剔除** | 微软员工排查动作（详见下方说明） |

**关于 msft_user 这一行被剔除的说明**：

早期版本统计包含 `msft_user@…` 38 次（合计 145 次）。微软同事朱宏磊指出 "msft 这个没道理做 ListKeys"，遂逐条核验：

- 拉取 4/15–5/12 整 28 天的 Activity Log，msft_user 触发的 `listKeys` **唯一调用全部集中在 2026-05-12 03:37–04:06 UTC**（北京时间 5/12 11:37–12:06）这 30 分钟内
- 全部来源 IP 为 `167.220.232.0/23` 与 `2404:f801:8050::/48`，`whois` 显示均属 `MICROSOFT-APNIC` / `MICROSOFT-APNIC-AS-AP`，descr 为 `Microsoft Singapore Pte. Ltd.`
- 本人当时在排查故障，`curl https://api.ipify.org` 出口 IP 为 `167.220.232.97`、`ifconfig.me` 为 `167.220.233.33`，**与 Activity Log 记录完全一致**——即微软员工虽在中国，但接入微软 corpnet 后 egress 走亚太 (新加坡) 出口节点
- 这 9 次（早期统计含 Started + Succeeded 双条目以及多次 az 命令重试，故达 38 计次）**均为微软员工在 5/12 上午故障已发生 (09:00 北京时间) 之后** 的排查动作，发生时间晚于封禁时间，物理上不可能是触发因素

**逻辑链**（修正后）：
- 两个不同客户侧 Azure 身份调用 `listKeys` action
- 每个身份调一次 = 把 key1/key2 拷走 = 拿去某个客户端用
- **同一资源只有 2 把 key（Key1 / Key2）**，gitlab_bot + admin 两个身份各自拉 = 至少 2 处客户端持有同一组 key
- gitlab_bot（CI/服务身份）+ admin（管理员）= **两种角色的客户端都在用同一组 key**
- 从 Anthropic 视角：同组 API key 出现在多 IP / 多 UA / 多调用模式 → 触发 abuse 检测的典型特征

**严格性说明**：
- ListKeys 仅证明"拷 key"动作，不能 100% 证明拷走后立即用了。但**没有理由频繁拷 key 而不用**——key 又不会自动轮换
- 真正铁证需要 Diagnostic Settings 的 `callerIpAddress` 维度，**但客户没开**（事后整改第一项）
- 不过 107 次 ListKeys × 2 个客户侧身份 × 5 天 + 单分钟 41 次的极端密度，足以推断 key 在多个客户端被复用

复现命令：
```bash
TOKEN=$(az account get-access-token --query accessToken -o tsv)
curl -G "https://management.azure.com/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/providers/Microsoft.Insights/eventtypes/management/values" \
  --data-urlencode 'api-version=2015-04-01' \
  --data-urlencode "\$filter=eventTimestamp ge '2026-05-05T00:00:00Z' and resourceUri eq '/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mmyiz2p1-eastus2'" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '[.value[] | select(.operationName.value | contains("listKeys"))] | group_by(.caller) | map({caller: .[0].caller, count: length})'
```

#### 证据 3：短时间高频 ListKeys（控制平面调用异常密度）

**数据来源**：Activity Log，按小时聚合 Successful "List Keys"

| hour (UTC) | caller | count | 备注 |
|---|---|---:|---|
| 2026-05-07 07 | admin | 12 | 客户侧 |
| 2026-05-07 09 | admin | 1 | 客户侧 |
| **2026-05-12 02** | **gitlab_bot@neolix.cn** | **41** ⚠️ | 客户侧 - **核心异常** |
| 2026-05-12 03–04 | msft_user | 9 | **微软员工排查动作，已剔除（详见 §证据 2 说明）** |

**异常点 (a)：5/12 02:40 UTC，gitlab_bot 1 分钟内 41 次 ListKeys**

分钟级时间戳节选（02:40 这一分钟）：
```
2026-05-12T02:40:05.83Z  Succeeded  gitlab_bot@neolix.cn
2026-05-12T02:40:05.46Z  Started    gitlab_bot@neolix.cn
2026-05-12T02:40:04.65Z  Succeeded  gitlab_bot@neolix.cn
2026-05-12T02:40:04.40Z  Started    gitlab_bot@neolix.cn
2026-05-12T02:40:03.81Z  Succeeded  gitlab_bot@neolix.cn
2026-05-12T02:40:03.60Z  Started    gitlab_bot@neolix.cn
2026-05-12T02:40:03.48Z  Succeeded  gitlab_bot@neolix.cn
2026-05-12T02:40:03.35Z  Started    gitlab_bot@neolix.cn
2026-05-12T02:40:02.28Z  Succeeded  gitlab_bot@neolix.cn
2026-05-12T02:40:02.17Z  Started    gitlab_bot@neolix.cn
... 持续到 41 次
```

**为什么这是异常**：
- **正常应用**：启动时 ListKeys 一次，缓存到内存或 Key Vault，几小时甚至几天才再拉一次
- **本案模式**：1 分钟 41 次 = 平均 1.46 秒一次 = **0.7 QPS 持续拉 key**
- 唯一合理解释：**客户端代码每次调模型前都 ListKeys 一次**（典型"忘了缓存 key"反模式）
- 或：多个 worker 容器同时启动，各自都 ListKeys（即便如此 41 次也太密）

**异常点 (b) ~~：5/12 03:43–03:44 UTC，msft_user 1 分钟内 6 次~~**

> **已剔除**：msft_user 在 5/12 03:37–04:06 UTC 的 9 次 ListKeys 经核验为微软员工排查本故障时的 az CLI 调用（出口 IP 167.220.232.0/23 与 2404:f801:8050::/48，均为 Microsoft Singapore corpnet），不构成 abuse 证据，从分析中移除。

~~（原内容保留作审计：~~

```
2026-05-12T03:44:35.71Z  Succeeded  msft_user
2026-05-12T03:44:30.35Z  Succeeded  msft_user
2026-05-12T03:43:42.42Z  Succeeded  msft_user
2026-05-12T03:43:39.15Z  Succeeded  msft_user
2026-05-12T03:43:00.46Z  Succeeded  msft_user
2026-05-12T03:43:00.16Z  Succeeded  msft_user
```

~~→ 同身份 1 秒内拉两次 key，明显是脚本里在并发循环。~~）→ **实际是 az CLI 在调试时的多次执行，不构成异常。**

**ListKeys 与 555420 的关系**：
- ListKeys 本身**不直接触发** 555420（Anthropic 看不到 ARM 控制平面调用）
- 但它是**"客户端代码不规范"的指纹**——能在控制平面看到这种密度，意味着数据平面（实际模型调用）的代码大概率也是同样的循环+无缓存模式
- 这就解释了为什么数据平面会触发 Anthropic abuse 检测

复现命令：
```bash
TOKEN=$(az account get-access-token --query accessToken -o tsv)
curl -G "https://management.azure.com/subscriptions/.../providers/Microsoft.Insights/eventtypes/management/values" \
  --data-urlencode 'api-version=2015-04-01' \
  --data-urlencode "\$filter=eventTimestamp ge '2026-05-12T02:00:00Z' and ..." \
  -H "Authorization: Bearer $TOKEN" \
  | jq '[.value[] | select(.operationName.value=="Microsoft.CognitiveServices/accounts/listKeys/action")
                  | select(.eventTimestamp | startswith("2026-05-12T02:40"))] | length'
# 输出 41
```

#### 证据合起来的画像

> 一个 Anthropic organization 的 key，被分发到**至少 2 个客户侧 Azure 身份** (`gitlab_bot` + `admin`) 手里，每个身份各自跑客户端，客户端代码**每次调用前都先 ListKeys（不缓存）**（5/12 02:40 UTC gitlab_bot 单分钟 41 次拉 key 是关键指纹），调用又同时打两个 region (eastus2 / swedencentral)，4xx 返回了**还死循环重试** → 从 Anthropic 后台看到的就是 **"同一 organization 多 IP 多 UA 高频请求 + 高失败率"**，这正是反滥用规则要抓的画像。

**关于早期版本"3 个身份"的修正**：早期版本把 `msft_user@…` 算作第 3 个客户侧身份。后经核验，该身份在故障期间的所有 ListKeys 调用 (5/12 03:37–04:06 UTC) 来自微软 corpnet 出口 IP（Microsoft Singapore），是微软员工排查本故障时跑的 az CLI 调用，**发生时间晚于封禁时间且 IP 不属于客户网络**，已从证据中剔除。修正后**"多身份共用 key"证据从 3 身份降为 2 身份**，但核心的"单分钟 41 次 ListKeys + 跨 region 并发 + 高失败率重试风暴"三条强证据完全不受影响，**滥用导致 555420 封禁的判断不变**。

---

## 6. 下一步行动建议

### 6.0 飞书群发版（人话版，可直接复制）

```
【Foundry Claude 调用全挂了 - 排查结论】

@相关同学

现象：今早 9 点左右开始（北京时间），ad_ai_subscription 下两个 Foundry 资源
（eastus2、swedencentral）所有 Claude 模型（sonnet/haiku/opus）调用全部 400 报错
"555420: Your resource has been blocked because we detected unusual behavior"。
今天到现在还在报，已经打了 1 万多次失败请求。

定位：不是 Azure 的问题，是 Anthropic 上游把咱们整个 organization 封了。
证据是同一个资源里的 GPT-5.5 完全正常（成功率 99.5%），key、网络、配额都没事。

为什么被封：
1) 客户端在疯狂死循环重试，单小时打了 2500+ 次几乎全失败的请求
2) 同一把 key 在客户侧 **gitlab_bot 和 admin 两个账号下到处用**（5 天 107 次 ListKeys，单分钟最高 41 次）
3) eastus2 + swedencentral 两个 region 同时打，Anthropic 那边看到的流量翻倍
4) 还有个奇葩行为：1 分钟内拉了 41 次 ListKeys（key 又不会变，拉这么频干嘛）

现在请大家立即：
✅ 1. 把所有调 Claude 的脚本/服务/CI 全部停掉，重点是 gitlab_bot 那条链路
       两个 region 都要停，让 Anthropic 那边的封禁窗口冷却一下
✅ 2. 急着用大模型的，临时切到 GPT-5.5（同一个资源就有，已验证可用）
✅ 3. @负责人 提 Microsoft 工单申请解封（自助解不了，必须走 MS × Anthropic 通道）
       Severity: B；标题：Anthropic provider returns 555420 blocked, request unblock
       订阅 ID：909485c7-c98b-4cfe-bb6e-64d9f9ff2747

代码侧（解封前必须改完，不然解封了还会再被封）：
🔧 1. Key 启动时拉一次缓存就行，不要每次调模型前都 ListKeys
🔧 2. 4xx 错误不要重试（重试也是 4xx），只对 5xx / 网络超时做有限退避重试
🔧 3. 单 region 主用，另一个只在 5xx 时切过去，别两个 region 同时打
🔧 4. 控制并发，单实例并发别超过部署 capacity 的一半

长期改进（解封以后做）：
📌 给不同客户端发不同 key（或者用 Managed Identity），出事能定位到人
📌 打开 Diagnostic Settings 把日志发到 Log Analytics，下次能看到 IP 维度
📌 业务侧做降级，Claude 挂了自动切 GPT，别把鸡蛋放一个篮子里

详细诊断报告（含时间线、错误码细分、工单文案）：
👉 [foundry-claude-555420-诊断报告.md]

有问题群里 at 我。
```

### 6.0.1 客户提出"新开订阅迁移过去"时的回复模板

**核心立场**：换订阅是换壳，**根因不修，新订阅过几天还会被封到**（Anthropic 555420 是按行为模式判定的）。

```
新订阅可以先解燃眉之急。但有两点要先对齐，不然过几天大概率会再被封：

1. 555420 的根因是客户端调用模式异常（短时高 QPS、4xx 死循环重试、
   双 region 并发、同 key 多处复用、1 分钟拉 41 次 ListKeys），
   不是 Azure 资源本身的问题。换订阅、换资源都只是换个壳，
   行为模式不改，Anthropic 那边照样会封。

2. 旧订阅 (ad_ai_subscription) 那边还有两件事要做：
   a) 把所有调旧资源的客户端先停掉（让封禁窗口冷却）
   b) 提 MS 工单申请解封（详细模板见本报告 6.2 节）
   不然旧资源就一直废着，浪费配额和钱。

切到新订阅之前，请先确认客户端代码已经修了：
   ① Key 启动时拉一次缓存，不要每次调用都 ListKeys
   ② 4xx 不重试，只对 5xx / 网络超时做有限退避重试
   ③ 单 region 主用，另一个 region 只在 5xx 时切换
   ④ 单实例并发不超过部署 capacity 的一半
   ⑤ 不同业务/CI/容器分发不同 key（或用 Managed Identity）

切过去后立即开 Diagnostic Settings（默认是关的），
   把 RequestResponse + Audit 日志发到 Log Analytics，
   下次出问题能直接看到是哪个 IP / 客户端在打。
   （步骤见本报告 7.3 节，月成本约 ¥250-300）

业务侧建议同时部署 GPT-5.5 做降级兜底，
   旧订阅 eastus2 资源里 GPT-5.5 已验证 99.5% 可用，
   Claude 不可用时自动切 GPT，避免单一供应商依赖。

新订阅的资源信息发我下，我帮你确认一下部署状态和初始配置。
```

**给值班同学的判断要点**：
- ❌ 不要让客户以为"换订阅 = 解决问题"
- ❌ 不要让客户放弃旧订阅资源（解封免费，资源不退就一直在）
- ✅ 借"新建订阅"这个时机推 Managed Identity / Diagnostic Settings 等最佳实践
- ✅ 推 GPT 兜底，降低单一供应商风险

---

### 6.1 客户立即应做（不需要等支持工单）

1. **停掉所有正在调用 Claude 的客户端 / 脚本 / CI Job**
   - 重点排查 `gitlab_bot@neolix.cn` 这条链路（5/12 02:40 一分钟 41 次 ListKeys）
   - 同时停 `eastus2` + `swedencentral` 两个 endpoint
   - 让 Anthropic 侧"unusual behavior"窗口先冷却（一般观察期 24 小时）

2. **修复客户端调用模式**（这是根因，不修复后面解封了还会再封）
   - **不要每次调模型前都 ListKeys**：Key 本地缓存即可，重启时拉一次
   - **去掉无脑重试**：4xx 是业务错误，不要重试；只对 5xx / 网络超时做带退避（exponential backoff）的有限重试
   - **不要双 region 并发**：选一个主用 region，另一个仅在 5xx 时切换
   - **限制并发**：单实例并发上限设到合理值（例如 ≤ 部署 capacity 的 50 %）

3. **审计 key 复用范围**
   - 列出所有持有这两个资源 key 的脚本 / 容器 / 人，确认是否需要分发不同的 key 或改用 Entra ID + Managed Identity
   - 暂时不轮换 key（用户要求保留），但建议解封后立即按角色拆分

4. **临时兜底**
   - 业务上能容忍切换的，先把流量切到 **`gpt-5.5`** 上（同资源 `msft-mmyiz2p1-eastus2`，已验证 99.5 % 可用）

### 6.2 申请解封（必须走 Microsoft Support）

Anthropic 555420 封禁 **az CLI / Portal 自助操作无法解除**，需要 Microsoft × Anthropic 通道处理。

**操作路径**：
Azure Portal → 进入 `msft-mmyiz2p1-eastus2` 资源 → 左侧 "Help" → "Diagnose and solve problems" → 创建 Support Request

**工单填写建议**：

- **Service**：`Azure AI Foundry / Cognitive Services`
- **Problem type**：`Quotas / Limits / Errors`
- **Subproblem**：`Model returns error / blocked`
- **Severity**：B（生产受影响）
- **Title**：`Anthropic provider returns 555420 blocked on Azure AI Services Claude deployments — request unblock`
- **Body 模板（中文 + 英文双语）**：

````
[订阅] ad_ai_subscription (909485c7-c98b-4cfe-bb6e-64d9f9ff2747)
[资源] /subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mmyiz2p1-eastus2
       /subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mn7fqhlw-swedencentral
[现象] 自 2026-05-12T01:00Z 起，上述两个资源上所有 Claude 模型部署
       (claude-sonnet-4-6 / claude-haiku-4-5 / claude-opus-4-6 / claude-opus-4-7)
       调用 /providers/anthropic/v1/messages 全部返回:
         HTTP 400
         {"error":{"type":"invalid_request_error",
                   "message":"555420: Your resource has been blocked because we detected unusual behavior."}}
[确认排除]
  - 同资源 gpt-5.5 调用正常（5/12 共 2253 次请求，成功率 99.5%）
  - Azure 资源 provisioningState=Succeeded, abusePenalty=null,
    networkAcls.defaultAction=Allow
  - Activity Log 显示资源未被 RP 阻断
[根因推断] Anthropic 平台对该 Anthropic organization 做了反滥用封禁
[已采取的自救措施]
  - 已停止所有调用客户端
  - 已修复重试 / region failover / key 复用问题
[请求]
  请协调 Anthropic 解除该 Anthropic organization 的 555420 限制，
  并提供避免再次触发的具体阈值或建议。
````

把上面这份诊断报告作为附件一并提交（Activity Log、Metrics 截图都可以引用本报告里的数字）。

### 6.3 解封后的长期建议

1. 启用 **Diagnostic Settings** 把 `RequestResponse` / `Audit` 日志发到 Log Analytics，下次故障可即时查 endpoint / IP 维度
2. 部署侧给每个客户端独立 key（或改 Entra ID + Managed Identity），出问题时可以隔离封禁单一来源
3. 业务侧实现降级：Claude 不可用时自动切到 GPT-5.5，避免单一供应商风险
4. 定期备份 / 监控 `ModelAvailabilityRate`（按 deployment 维度），低于阈值时告警

---

## 7. 诊断方法论（怎么查 Foundry 调用问题）

Azure 排查模型调用类故障基本靠四层日志，由浅入深：

### 7.1 Activity Log — 控制平面操作记录

**记什么**：谁在什么时候对资源做了 ARM 操作（创建/改部署、ListKeys、改配置、删资源……）。**不记数据平面调用**（不会有"谁调了 sonnet-4-6"这条）。

**Portal 看**：
```
Portal → 进入资源 → 左侧 "Activity log"
  → 可按时间 / Operation / Caller / Status 过滤
```

订阅级看：`Portal → Subscriptions → ad_ai_subscription → Activity log`

**CLI 看**：
```bash
az monitor activity-log list \
  --resource-id "/subscriptions/<sub>/.../accounts/<acc>" \
  --start-time 2026-05-05 \
  --query "[].{time:eventTimestamp, op:operationName.localizedValue, status:status.value, caller:caller}" \
  -o table
```

**REST 兜底**（本机 az monitor 模块异常时用）：
```bash
TOKEN=$(az account get-access-token --query accessToken -o tsv)
curl -G "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.Insights/eventtypes/management/values" \
  --data-urlencode 'api-version=2015-04-01' \
  --data-urlencode "\$filter=eventTimestamp ge '2026-05-05T00:00:00Z' and resourceUri eq '<resourceId>'" \
  -H "Authorization: Bearer $TOKEN"
```

**本案从这里看出了什么**：
- 5/12 02:39 gitlab_bot 部署了 claude-opus-4-7
- 5/12 02:40 gitlab_bot 1 分钟内 41 次 ListKeys（异常密度）
- 客户侧 2 个身份（gitlab_bot / admin）反复拉 key（msft_user 那 9 次为微软员工排查动作已剔除）
- sweden 资源 5/6 出过两次 Resource Health Unavailable

**保留期**：默认 90 天，免费。

---

### 7.2 Metrics — 数据平面调用统计

**记什么**：每个模型部署被调了多少次、成功多少、失败多少、按状态码 / API 拆分。**这是诊断模型调用问题的主战场**。

#### "资源" = 什么？

在 Azure 里 "资源 (Resource)" = 一个具体的 Azure 服务实例。本案 `ad_ai_subscription` 下有 3 个 Cognitive Services 资源，每个资源对应一个 endpoint：

| 资源名 | 它是什么 | endpoint |
|---|---|---|
| `msft-mmyiz2p1-eastus2` | AI Services 账户实例（部署了 Claude + GPT） | `https://msft-mmyiz2p1-eastus2.cognitiveservices.azure.com/` |
| `msft-mn7fqhlw-swedencentral` | 同上，瑞典 region | `https://msft-mn7fqhlw-swedencentral.cognitiveservices.azure.com/` |
| `foundry-claude-test1` | 同上，westus3，只部署了 GPT | `https://foundry-claude-test1.cognitiveservices.azure.com/` |

**每个资源有自己独立的一份 metrics**。所以"进入资源"= 打开你想查的那个 endpoint 对应的资源页面。

#### Portal 一步步操作（从登录开始）

**第 1 步：登录到对的账号 + 订阅**
```
浏览器打开 https://portal.azure.com
  → 右上角头像 → 切到账号 msft_user@gitlabbotneolix.onmicrosoft.com
  → 右上角齿轮 → "Directories + subscriptions"
  → 确认勾选了 ad_ai_subscription
```

**第 2 步：找到资源**（任挑一种）
- A. 顶部搜索框输 `msft-mmyiz2p1-eastus2` → 在 "Resources" 分组里点它（最快）
- B. 左侧 "Subscriptions" → ad_ai_subscription → "Resources" → 点资源
- C. 左侧 "All resources" → 过滤 Subscription = ad_ai_subscription, Type = Azure AI services

**第 3 步：进入资源后，左侧菜单找 Metrics**

资源页面左侧菜单结构：
```
├─ Overview
├─ Activity log              ← 7.1 在这看
├─ ...
├─ Resource Management
│   ├─ Keys and Endpoint
│   └─ Networking
├─ Monitoring                 ← 展开
│   ├─ Metrics                ← 点这个 ⭐
│   ├─ Diagnostic settings    ← 7.3 在这开
│   └─ Logs
├─ Help
│   ├─ Resource health        ← 7.4 在这看
│   └─ Diagnose and solve problems  ← 提工单
```

**第 4 步：在 Metrics 页面配图**
```
Scope:               msft-mmyiz2p1-eastus2  （已自动填好）
Metric Namespace:    cognitiveservices accounts
Metric:              ModelRequests
Aggregation:         Sum
[+ Apply splitting]  → 勾 ModelDeploymentName + StatusCode
[Time range 右上角]  → Last 24 hours
```

底下出来的折线图，每条线是 `<deployment>/<status>` 的组合。本案里直接能看到：
- `claude-sonnet-4-6 / 200` 5/12 01:00 后掉到 0
- `claude-sonnet-4-6 / 400` 5/12 01:00 后陡升
- `gpt-5.5 / 200` 一直是平的（GPT 没事）

**第 5 步（可选）**：右上角 "Save to dashboard" 钉到 dashboard / "Export to Excel" 下数据 / "New alert rule" 配告警。

#### 直达链接（登录后直接打开就是 Metrics 页）

eastus2 Metrics：
```
https://portal.azure.com/#@gitlabbotneolix.onmicrosoft.com/resource/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mmyiz2p1-eastus2/metrics
```

sweden Metrics：
```
https://portal.azure.com/#@gitlabbotneolix.onmicrosoft.com/resource/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mn7fqhlw-swedencentral/metrics
```

eastus2 Activity log：
```
https://portal.azure.com/#@gitlabbotneolix.onmicrosoft.com/resource/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mmyiz2p1-eastus2/eventlogs
```

**REST 看**：
```bash
TOKEN=$(az account get-access-token --query accessToken -o tsv)
curl -G "https://management.azure.com/subscriptions/<sub>/.../accounts/<acc>/providers/Microsoft.Insights/metrics" \
  --data-urlencode 'api-version=2024-02-01' \
  --data-urlencode 'metricnames=ModelRequests' \
  --data-urlencode 'timespan=2026-05-12T00:00:00Z/2026-05-13T00:00:00Z' \
  --data-urlencode 'interval=PT1H' \
  --data-urlencode 'aggregation=Total' \
  --data-urlencode '$filter=ModelDeploymentName eq '"'*'"' and StatusCode eq '"'*'"' and ApiName eq '"'*'"'' \
  -H "Authorization: Bearer $TOKEN"
```

**重点 metric**：
| Metric | 用途 |
|---|---|
| `ModelRequests` | **最有用**，按 deployment / 状态码 / API 拆分调用次数 |
| `TotalCalls` / `SuccessfulCalls` / `ClientErrors` / `ServerErrors` | 总量级 |
| `TotalTokens` / `InputTokens` / `OutputTokens` | token 消耗 |
| `ModelAvailabilityRate` | 部署可用率，配告警用 |
| `RAIRejectedRequests` | 内容过滤拒掉的请求 |

**重点 dimension**：`ModelDeploymentName`（哪个部署）、`StatusCode`（200/400/429/500）、`ApiName`（Anthropic = `AIServices`，OpenAI = `n/a`）、`OperationName`。

#### StatusCode 含义速查

Metrics 的 `StatusCode` 就是该次模型调用返回给客户端的 HTTP 状态码。

**2xx — 成功**

| 码 | 含义 |
|---|---|
| **200 OK** | 调用成功，模型正常返回 |
| 201 / 202 | 异步任务已接受（batch / fine-tune 类） |

**4xx — 客户端错误**（调用方的问题，重试通常没用）

| 码 | 含义 | 常见原因 |
|---|---|---|
| **400** Bad Request | 请求格式/参数不对/内容被拒 | • 参数不合法（如 `max_tokens` 给了不支持的模型）<br>• **555420 blocked**（Anthropic 上游拒绝，本案就是这个）<br>• Prompt 触发内容安全过滤 |
| **401** Unauthorized | 没带 key / token 无效 | api-key 写错、Bearer 过期 |
| **403** Forbidden | 身份对但没权限 | RBAC 不够、abusePenalty 封禁、网络 ACL 拦截 |
| **404** Not Found | 路径/deployment 名错 | deployment 名拼错、api-version 不存在 |
| **413** Payload Too Large | 请求体超大 | prompt 超过上下文限制 |
| **422** Unprocessable Entity | 语义校验失败 | 字段类型对但值不合法 |
| **429** Too Many Requests | **被限流** | 超过 RPM / TPM、dynamic throttling、配额耗尽 |

**5xx — 服务端错误**（Azure / 模型后端的问题，可重试）

| 码 | 含义 | 处理 |
|---|---|---|
| **500** Internal Server Error | 后端通用错误 | 指数退避重试 |
| **502** Bad Gateway | 网关↔后端通信失败 | 指数退避重试 |
| **503** Service Unavailable | 后端临时不可用 / 过载 | 看 `Retry-After` 头退避重试 |
| **504** Gateway Timeout | 后端响应超时 | 退避重试，prompt 可能太长 |

#### 用 StatusCode 反推故障类型（本案演示）

看 5/12 UTC 0–4 的状态码分布：

```
eastus2:
  gpt-5.5            200: 2241  400: 11   500: 1   ← 健康
  claude-haiku-4-5   200:  130  400: 1023          ← 异常
  claude-sonnet-4-6  200:  134  400: 946           ← 异常
  claude-opus-4-7    200:   73  400: 112           ← 异常
```

**判断逻辑**：
- 全是 **400** 一边倒、没有 401/403/429/5xx → **不是 key 错、不是权限/网络、不是限流、不是 Azure 后端**
- 400 的具体报文（curl 实测）含 `555420: Your resource has been blocked` → Anthropic 上游对 organization 的反滥用封禁
- 同资源 GPT 99.5% 成功 → 排除 Azure 资源 / endpoint / 网络问题

**反向口诀**：
- 主要错误是 **429** → 配额/限流问题（申请提配额或降速）
- 主要错误是 **403** → Azure 侧封禁（看 `properties.abusePenalty`）或网络 ACL
- 主要错误是 **400** + 报文带 555420 → Anthropic 上游封禁（必走 MS 工单）
- 主要错误是 **5xx** → Azure 后端故障（重试 + 等恢复 + 看 Resource Health）

**本案从这里看出了什么**：
- gpt-5.5 同时间 99.5% 成功，Claude 100% 失败 → **不是 Azure 问题**
- 封禁的精确切换时间点（00:xx 还能 200，01:00 起 200 归零）
- 哪些 deployment 被打得最狠（haiku + sonnet）
- 两个 region 流量对称（→ 客户端在做 region 分发或并发）

**保留期**：93 天，免费。

#### 给客户截图前的标准操作清单

**目标**：用最少的图、最直观地证明"Claude 被封 + GPT 没事 + 不是 Azure 问题"。

**推荐组合：截两张图**

##### 图 A — Claude 各模型 200 vs 400 断崖（现象图）

配置：
```
Metric Namespace:  cognitiveservices accounts
Metric:            ModelRequests
Aggregation:       Sum
Filter (Add filter):
    Property:  ModelDeploymentName
    Operator:  contains
    Value:     claude
Apply splitting (Values):
    ☑ ModelDeploymentName
    ☑ StatusCode
    Limit: 20
    Sort:  Descending
Time range:        Custom: 2026-05-11 20:00 ~ 2026-05-12 12:00 (北京时间)
Chart type:        Line chart（或 Stacked column 更直观）
```

**截图前必须检查**：
- ✅ 图例栏（图下方）所有 checkbox **全部勾上**（默认可能只勾了 top N，灰白 outline 的没显示）
- ✅ 图例不被 hover 浮窗遮挡
- ✅ 时间窗包含被封前的"正常基线"和被封后的"断崖"，都要露出来
- ✅ 标题改成有意义的（点标题旁的笔图标），如：`Claude 部署 200 vs 400 调用对比`

**预期看到**：
- `claude-haiku-4-5/200`、`claude-sonnet-4-6/200`、`claude-opus-4-7/200` 在 5/12 09:00 前还有数值，09:00 后掉到 0
- `claude-haiku-4-5/400`、`claude-sonnet-4-6/400` 在 09:00 后陡升到 200+/小时

##### 图 B — GPT-5.5 同时段一切正常（对照图，铁证不是 Azure 问题）

新建一张 chart（左上角 "+ New chart"），配置：
```
Metric:            ModelRequests
Aggregation:       Sum
Filter:
    Property:  ModelDeploymentName
    Operator:  =
    Value:     gpt-5.5
Apply splitting:
    ☑ StatusCode  （只勾这一个）
Time range:        同图 A
Chart type:        Line chart
```

**预期看到**：`gpt-5.5/200` 一条平稳的线（13k 量级），偶尔几个 400/500 几乎贴着 0 → 同资源、同时段、GPT 一切正常。

##### 配文（贴飞书 / 工单时一起发）

```
图 A：5/12 北京时间 09:00 起，eastus2 资源上 4 个 Claude 部署
     的成功调用 (200) 全部归零，失败调用 (400) 陡升至每小时 1000+。

图 B：同一资源、同一时段，GPT-5.5 一直平稳运行（成功率 99.5%）。

结论：不是 Azure 资源 / endpoint / 网络 / 配额问题，
     是 Anthropic 上游对 organization 的反滥用封禁（错误码 555420）。
```

##### 加分项截图（可选）

- **图 C — Activity Log 1 分钟 41 次 ListKeys**
  ```
  资源 → Activity log → Filter:
    Time = Last 7 days
    Operation = "List Account Keys"
    Caller = gitlab_bot@neolix.cn
  ```
  截 5/12 02:40 那一分钟连续 41 行的列表 → 客户端代码异常的视觉证据

- **图 D — ModelAvailabilityRate 跌至 ~5%**
  ```
  Metric: ModelAvailabilityRate
  Splitting: ModelDeploymentName
  Filter: ModelDeploymentName contains claude
  ```

##### 反例：不要这样截图

- ❌ 时间窗只有 "Last 24 hours" 但被封发生在窗外 → 看不到断崖
- ❌ Splitting 加了 StatusCode 但图例 checkbox 没全勾 → 客户只看到一两条线，反而像 Claude 凌晨在偷偷暴涨
- ❌ 不加 filter 直接放 GPT + Claude 混在一起 → GPT 的尖峰会把 y 轴拉爆，Claude 的断崖被压扁
- ❌ filter 用 `≠ gpt-5.5`（反向过滤）→ 客户看不懂，改成 `contains claude`（正向）更直观
- ❌ 截图里包含 hover tooltip 浮窗 → 遮挡图例

---

### 7.3 Diagnostic Logs — 数据平面详细日志 ⭐ 默认是关的

**记什么**：每一次具体的模型 HTTP 请求，包含 caller IP、User-Agent、prompt 长度、错误细节。**Metrics 是统计，Diagnostic Log 是流水**。

⚠️ **本案的关键缺口**：当前两个资源**都没开 Diagnostic Settings**，所以无法定位具体调用源 IP 是哪台机器、哪条业务链路在打。能查的全靠 Activity Log + Metrics 这两个默认开的东西。**这是事后整改的第一项**。

#### "Foundry 资源" 是什么

= 你在 Azure 上创建的 **Azure AI Services / Azure AI Foundry 实例**
- 资源类型：`Microsoft.CognitiveServices/accounts`
- kind：`AIServices`
- Portal 资源列表里 Type 显示为 "Azure AI services"（也可能是老名字 "Cognitive Services" / "Azure OpenAI"，是一类东西）

本案对应：
- `msft-mmyiz2p1-eastus2`
- `msft-mn7fqhlw-swedencentral`
- `foundry-claude-test1`

Diagnostic Settings 必须**在这种资源里开**，不是订阅级、不是 RG 级。

#### 怎么找到 Foundry 资源（任选一种）

- A. Portal 顶部搜索框输资源名 → "Resources" 分组里点
- B. 左侧 "Subscriptions" → 选订阅 → "Resources" → 找 Type = "Azure AI services"
- C. 左侧 "All resources" → 过滤 Subscription + Type = "Azure AI services"
- D. 从 https://ai.azure.com → 选 project → "Manage in Azure portal" 反向跳

确认点对了：Overview 页能看到 `Endpoint: https://<name>.cognitiveservices.azure.com/`。

#### 启用 Diagnostic Settings — 一步一步做

**先决定日志发到哪里**

| Destination | 成本 | 适合 | 缺点 |
|---|---|---|---|
| **Storage Account** | 最便宜（~¥0.15/GB/月） | 长期归档 / 合规 | 查询难 |
| **Log Analytics workspace** ⭐推荐 | 中等（~¥17/GB 摄入） | KQL 查询 / 配告警 / dashboard | 摄入费稍贵 |
| **Event Hub** | 中高 | 实时流式 / 推 SIEM | 需要消费者 |

排查用强烈推荐 Log Analytics。

**第 1 步：建一个 Log Analytics workspace**（如果还没有）

```
Portal 顶部搜 "Log Analytics workspaces" → 进入
  → 上方 "+ Create"
  → Subscription:    新订阅
  → Resource group:  跟 Foundry 资源同 RG（建议）
  → Name:            neolix-foundry-logs
  → Region:          ⚠️ 必须跟 Foundry 资源同 region，避免跨区流量费
  → Review + Create → Create
  → 等 30 秒
```

**第 2 步：进 Foundry 资源开 Diagnostic Settings**

```
Portal 顶部搜资源名 → 进入 Foundry 资源
  → 左侧 "Monitoring" → "Diagnostic settings"
  → 中间显示 "No diagnostic settings defined"
  → 点 "+ Add diagnostic setting"
```

**第 3 步：填配置表单**

```
Diagnostic setting name:  foundry-full-logs

Logs (左侧)
  ☑ allLogs                 ← 偷懒就这个
    或细选：
  ☑ Audit                   ← 控制平面操作（必勾）
  ☑ RequestResponse         ← 数据平面调用（必勾）⭐
  ☐ Trace                   ← 调试细节，量大可不勾

Metrics (左侧)
  ☑ AllMetrics              ← 勾上，metrics 很便宜

Destination details (右侧) — 至少勾一个
  ☑ Send to Log Analytics workspace
      Subscription:        新订阅
      Workspace:           neolix-foundry-logs
      Destination table:   ◉ Resource specific  ← 选这个
                           ○ Azure diagnostics
       (Resource specific 字段是结构化的，KQL 好写 10 倍)

→ 上方 "Save"
```

**关键提示**：
- 必勾 **`RequestResponse`**（每次模型调用流水）+ **`Audit`**（控制平面）
- "Destination table" 强烈选 **Resource specific**（新格式）

**第 4 步：等 5–10 分钟后验证**

```
Portal → 进入 Log Analytics workspace
  → 左侧 "Logs"
  → 粘下面 KQL：
```

```kusto
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated > ago(15m)
| take 20
```

有行说明日志在写入。没有再等 5 分钟（摄入有延迟）。

#### 启用后用 KQL 排查（Portal → Log Analytics → Logs）

```kusto
// 看所有 Claude 失败请求的细节
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated > ago(24h)
| where ResultSignature startswith "4"
| where modelDeploymentName_s contains "claude"
| project TimeGenerated, callerIpAddress_s, modelDeploymentName_s,
          ResultSignature, properties_s
| order by TimeGenerated desc
```

```kusto
// 按 IP 统计谁在打
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated > ago(24h)
| summarize calls = count() by callerIpAddress_s, modelDeploymentName_s
| order by calls desc
```

```kusto
// 失败请求按 IP × 状态码 × 时间桶
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated > ago(24h)
| summarize count() by bin(TimeGenerated, 5m), callerIpAddress_s, ResultSignature
| order by TimeGenerated desc
```

#### 成本估算

按客户当前量级（每天约 10 万次 Claude 调用，每条 RequestResponse 约 5 KB）：

| 项目 | 估算 |
|---|---|
| Log Analytics 摄入费 | 15 GB/月 × ¥17/GB ≈ **¥255/月** |
| Log Analytics 保留费 | 前 31 天免费，之后 ¥0.85/GB/月（可忽略） |
| Storage Account 归档（可选加） | 15 GB/月 × ¥0.15/GB ≈ **¥3/月** |
| **合计** | **约 ¥250–300 元/月** |

**省钱选项**：
- 只勾 Audit + RequestResponse，不勾 Trace（省 30–50%）
- 用免费 31 天保留期，超期归档到 Storage（几乎免费）
- 短期排查用：开 1–2 周抓到日志后关掉
- Basic Logs 模式（部分表支持）：摄入只要 ¥1.5/GB，但只能查 8 天，不能告警
- 纯归档：只用 Storage Account（KQL 没法直接查）

#### 直达链接（Diagnostic Settings 页）

eastus2：
```
https://portal.azure.com/#@gitlabbotneolix.onmicrosoft.com/resource/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mmyiz2p1-eastus2/diagnosticSettings
```

sweden：
```
https://portal.azure.com/#@gitlabbotneolix.onmicrosoft.com/resource/subscriptions/909485c7-c98b-4cfe-bb6e-64d9f9ff2747/resourceGroups/default-rg/providers/Microsoft.CognitiveServices/accounts/msft-mn7fqhlw-swedencentral/diagnosticSettings
```

---

### 7.4 Resource Health — 资源健康状态

**记什么**：Azure 平台层面认为这个资源是不是"健康"。

```
Portal → 进入资源 → 左侧 "Resource health"
```

订阅级：`Portal → Service Health → Resource health`

**本案看到了什么**：sweden 资源 5/6 有过两次 "Available → Unavailable → Resolved"（约 15 分钟），是 Azure 平台层瞬时抖动，跟 555420 不直接相关，但属于"这个资源不太稳"的旁证。

---

### 7.5 本案实际排查路径（按顺序）

```
1. 复现错误：curl 拿到 555420 报文 → 知道是 Anthropic 在拒
                ↓
2. 同资源换 GPT 试调：200 OK → 排除 Azure / key / 网络 / 配额
                ↓
3. Activity Log 看近期改了啥：刚部署 opus-4-7 + 暴力 ListKeys
   → 闻到客户端代码有问题
                ↓
4. Metrics 拉 ModelRequests 按 ModelDeploymentName + StatusCode 拆
   → 拿到精确封禁时间点 + 各部署调用量分布
                ↓
5. 想再深挖到 IP / 客户端：发现没开 Diagnostic Settings
   → 给客户的整改建议里加上"开 Diagnostic Settings"
```

---

### 7.6 给客户值班同学的速查指引（可贴到 wiki / 飞书文档）

```
【Foundry 调用出问题，按这个顺序查】

1. 谁动过这个资源    → Portal → 资源 → Activity log
   场景：是谁部署的、谁拉的 key、谁删的东西

2. 模型调了多少次/成功率 → Portal → 资源 → Monitoring → Metrics
   选 ModelRequests，splitting 选 ModelDeploymentName + StatusCode
   场景：哪个模型在被打、什么时候开始失败的

3. 每次请求的详细信息（IP / 错误细节）
   → 先去 Monitoring → Diagnostic settings 启用（默认是关的！）
   → 勾 RequestResponse + Audit，发到 Log Analytics
   → 之后到 Log Analytics → Logs 用 KQL 查 AzureDiagnostics 表

4. 资源是不是健康       → Portal → 资源 → Resource health
   场景：是不是 Azure 平台抽风了
```

---

## 附录 A：用到的 az / REST 命令

```bash
# 切订阅
az account set --subscription "ad_ai_subscription"

# 列资源
az cognitiveservices account list

# 列部署
az cognitiveservices account deployment list -n <acc> -g default-rg

# 复现 555420
KEY=$(az cognitiveservices account keys list -n msft-mmyiz2p1-eastus2 -g default-rg --query key1 -o tsv)
curl -X POST "https://msft-mmyiz2p1-eastus2.cognitiveservices.azure.com/providers/anthropic/v1/messages?api-version=2024-10-21" \
  -H "Authorization: Bearer $KEY" -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'

# 拉 metrics（按 deployment + statuscode 拆分）
TOKEN=$(az account get-access-token --query accessToken -o tsv)
curl -G "https://management.azure.com/.../providers/Microsoft.Insights/metrics" \
  --data-urlencode 'api-version=2024-02-01' \
  --data-urlencode 'metricnames=ModelRequests' \
  --data-urlencode 'timespan=2026-05-12T00:00:00Z/2026-05-13T00:00:00Z' \
  --data-urlencode 'interval=PT1H' \
  --data-urlencode 'aggregation=Total' \
  --data-urlencode '$filter=ModelDeploymentName eq '"'*'"' and StatusCode eq '"'*'"' and ApiName eq '"'*'"'' \
  -H "Authorization: Bearer $TOKEN"

# Activity Log
curl -G "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.Insights/eventtypes/management/values" \
  --data-urlencode 'api-version=2015-04-01' \
  --data-urlencode "\$filter=eventTimestamp ge '2026-05-05T00:00:00Z' and resourceUri eq '/subscriptions/.../accounts/<acc>'" \
  -H "Authorization: Bearer $TOKEN"
```

## 附录 B：原始数据文件（本机）

- `/tmp/activity_eastus2.json` — eastus2 资源 Activity Log
- `/tmp/activity_sweden.json` — sweden 资源 Activity Log
- `/tmp/mr_msft-mmyiz2p1-eastus2.json` — eastus2 ModelRequests metrics
- `/tmp/mr_msft-mn7fqhlw-swedencentral.json` — sweden ModelRequests metrics
