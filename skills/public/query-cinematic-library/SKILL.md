---
name: query-cinematic-library
description: 检索本地电影化个人IP研究库中的权威影片目录、导演/编剧/摄影/剪辑/声音/美术/表演创作者和机制卡，并按证据等级、工种、题材与转译问题选择样本。用户问“该研究哪些影片/主创”“找某种情绪、镜头或结构的案例”“从片库挑对标”或要核对机制来源时使用。
---

# 影视机制库检索

先明确创作问题，再检索样本。不要用名人名字代替问题，也不要把检索结果写成“仿某某风格”。

## 检索

本Skill自带离线SQLite库。运行：

```bash
python3 scripts/query_library.py "悬疑" --type card --limit 8
python3 scripts/query_library.py "Jordan Peele" --type creator --json
python3 scripts/query_library.py "Arrival" --type film --json
```

类型：

- `film`：358部权威片单影片，含年份、榜单、导演/编剧和研究工种；
- `creator`：393位创作者/团队，含角色、样本和本项目已有机制摘要；
- `card`：304张原创机制卡，含证据等级、可观察执行、失效方式和迁移问题；
- `all`：跨三层查找。

字段见 `references/library-schema.md`。

## 选择样本

围绕一个具体问题选3–6个互补样本：

1. 一个经典范式；
2. 一个现代重构；
3. 一个非好莱坞或非主流工业变体；
4. 一个制作规模接近用户的样本；
5. 必要时补女性创作者、动画、纪录或工种样本。

同一部影片可因编剧、摄影、声音或表演问题被重复选择，但每次必须写明本轮观察轴。

## 输出机制包

每个入选样本输出：

```yaml
sample:
problem:
evidence_label:
source_ref:
mechanism:
observable_execution:
transfer_to_ip:
transfer_limit:
failure_check:
next_test:
```

`catalogued`影片只有来源元数据和观察问题时，不得声称已经证明某个机制。优先使用已有机制卡；没有卡时调用 `$distill-screen-methods` 深挖并新增有来源的机制卡。

## 边界

- 榜单证明“进入样本池”，不证明机制；
- `analyst_inference` 必须在具体场景、镜头或制作材料中复核；
- 不输出受版权保护的剧本、课程正文或长段影片转录；
- 不复刻在世创作者的独特措辞、签名镜头或风格拼贴；
- 真实个人IP最终要通过自己的内容数据验证，不以经典地位代替测试。
