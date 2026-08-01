---
name: run-cinematic-curriculum
description: 运行电影化个人IP的编剧、导演、摄影、剪辑、声音、表演、美术和真人纪录八轨训练系统，为当前项目生成周计划、单项练习、作品证据评分和补课路径。用户要系统学习编剧/表演课程、训练团队、做阶段考核或把课程蒸馏成实战能力时使用。
---

# 电影工种训练营

训练目标是让用户在自己的真实IP项目上获得可观察能力，不是看完课程、背术语或复刻样片。v4所有工种共享 `desire_behavior_clarity` 评分：能否从人物欲望推到目标、行动、反馈、选择和状态改变。

## 选轨

| 当前瓶颈 | 训练轨 |
|---|---|
| 主线、人物、因果、场景、对白 | `screenwriting` |
| 意图、调度、视点、覆盖、跨部门 | `directing` |
| 焦段、距离、运动、光色、Look | `cinematography` |
| 表演选择、信息时机、节奏、结构 | `editing` |
| 声音视点、空间、动态、音乐 | `sound` |
| 目标、策略、潜台词、身体、镜头尺度 | `performance` |
| 空间、道具、服装、材质、连续性 | `production_design` |
| 真实任务、同意、场景日志、长期变化 | `documentary_reality` |

每轨12周，共96个模块。细节在 `references/curriculum.json`。

## 运行

随包 CLI 只读取课程、生成计划和考核模板，不写项目状态：

```bash
python3 scripts/curriculum_cli.py list
python3 scripts/curriculum_cli.py show --track screenwriting --week 3
python3 scripts/curriculum_cli.py plan \
  --track screenwriting --track directing \
  --start 2026-08-03 --sessions-per-week 2
python3 scripts/curriculum_cli.py assessment-template \
  --track performance --week 5
```

先做诊断样本，再从最低缺口开始，不要求八轨同步。

## 一次训练会话

1. 读模块机制和来源边界；
2. 在机制库选1–3个观察样本；
3. 完成模块练习；
4. 生成指定交付物；
5. 按量表逐项给0–4分；
6. 每项引用页码、时间码、版本差异或拍摄记录；
7. 共同维度任一低于2则补练，总平均不低于3才进入下一模块；
8. 把作品证据作为当前主体的有来源产物；真实发布后的复盘用于修订方法，不能把
   一次练习伪装成普适规律，也不等待服务器晋升证书。

## 评分纪律

- 0：缺失或无关；
- 1：有意图但不可观察/不可执行；
- 2：基本成立但有明显断裂；
- 3：清楚、可执行、可复核；
- 4：在新事件中仍稳定，并能说明取舍。

AI可以评估作品，但必须说明看到的具体证据。没有看到作品就只能生成考核表，不能代打分。

## 课程边界

- 保留查理、Sciamma、Kaufman、Gilroy等体系之间的冲突，不合成万能模板；
- 把查理的欲望—动作方向作为清晰度训练，同时用Sciamma校正“冲突是唯一动力”的误读；
- 未取得课程正文时只使用可核实范围，不猜私有术语；
- 不输出受版权保护的课程正文或长段剧本；
- 表演训练不用私人创伤换强度；
- 真人纪录练习不预写现实结果；
- 每个练习必须转成用户自己的任务、人物和限制。
- 不创建 `training/completion-ledger.jsonl` 或其他平行台账。训练计划和考核表是
  可丢弃产物，发布结果仍由 Personal-IP 原生 preflight、指标和复盘服务管理。
