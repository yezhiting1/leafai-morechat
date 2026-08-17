# CowAgent docs
<p align="center"><img src="https://github.com/user-attachments/assets/eca9a9ec-8534-4615-9e0f-96c5ac1d10a3" alt="CowAgent" width="420" /></p>

<p align="center">
  <a href="https://github.com/zhayujie/CowAgent/releases/latest"><img src="https://img.shields.io/github/v/release/zhayujie/CowAgent?cacheSeconds=3600" alt="Latest release"></a>
  <a href="https://github.com/zhayujie/CowAgent/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://github.com/zhayujie/CowAgent"><img src="https://img.shields.io/github/stars/zhayujie/CowAgent?style=flat-square&cacheSeconds=3600" alt="Stars"></a>
  <a href="https://docs.cowagent.ai/"><img src="https://img.shields.io/badge/Docs-cowagent.ai-blue?style=flat&logo=readthedocs&logoColor=white" alt="Docs"></a>
  <a href="https://cdn.link-ai.tech/code/cow/cowagent-wechat-group.png"><img src="https://img.shields.io/badge/WeChat-Group-07C160?style=flat&logo=wechat&logoColor=white" alt="WeChat Group"></a>
  <a href="https://discord.gg/9U8eA8v9TR"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  [<b>中文</b>] | [<a href="../../README.md">English</a>] | [<a href="README-Hant.md">繁體中文</a>] | [<a href="../ja/README.md">日本語</a>]
</p>

**CowAgent** 是开源超级AI助手，能够主动规划任务、操控电脑与外部服务、创建运行技能、搭建个人知识库与长期记忆，通过自我进化伴随你一同成长，是 Agent Harness 工程的参考实现，扩展性强。可接入各大主流大模型，在个人电脑或服务器 24 小时运行，支持网页以及各类主流即时通讯平台。

- **🧠 Agent基础设施** — 统一大模型、知识库、数据库、技能、工作流，开箱即用组件扩展CowAgent能力


<br/>

## 🎬 演示

<p align="center">
  <video src="https://github.com/user-attachments/assets/8625a19f-615c-4343-8be8-3707ce4d4d4e" controls muted playsinline width="720">
    你的浏览器不支持播放视频。
  </video>
</p>

<br/>

## 🌟 核心特性

| 能力 | 说明 |
| :--- | :--- |
| [任务规划](https://docs.cowagent.ai/intro/architecture) | 拆解复杂任务，分步执行，循环调用工具直至目标完成 |
| [记忆系统](https://docs.cowagent.ai/memory/index) | 三层记忆架构（上下文→日常记忆→核心记忆），自动深度梦境蒸馏，关键词+向量混合检索 |
| [知识库](https://docs.cowagent.ai/knowledge/index) | 自动整理结构化知识生成Markdown知识库，构建可可视化浏览的知识图谱 |
| [自我进化](https://docs.cowagent.ai/memory/self-evolution) | 自动复盘对话优化技能、跟进未完成任务、沉淀记忆知识，在日常使用中持续成长 |
| [技能](https://docs.cowagent.ai/skills/index) | 从技能市场、GitHub一键安装，也可以通过对话自然语言创建自定义技能 |
| [工具集](https://docs.cowagent.ai/tools/index) | 内置文件读写、终端、浏览器、定时任务、记忆检索、网页搜索等十多种工具，原生支持MCP协议 |
| [消息通道](https://docs.cowagent.ai/channels/index) | 支持网页、微信、飞书、钉钉、企业微信、QQ、公众号、Telegram、Slack |
| 多模态 | 完整支持文本、图片、语音、文件的识别、生成与消息分发 |
| [大模型](https://docs.cowagent.ai/models/index) | Claude、GPT、Gemini、DeepSeek、通义千问、GLM、Kimi、MiniMax、豆包等，网页控制台一键切换模型厂商 |
| [部署方式](https://docs.cowagent.ai/guide/quick-start) | Docker部署 |

<br/>

## 🏗️ 架构

<img src="https://cdn.jsdelivr.net/gh/zhayujie/cowagent-assets@main/architecture/en/architecture.png" alt="CowAgent Architecture" width="750"/>

CowAgent 是一套完整的 **Agent Harness**：消息经由**消息通道**流入；Agent核心结合记忆、知识库、工具与技能完成规划推理；大模型生成回复，再经由原消息通道返回。各层完全解耦，均可独立扩展。


<br/>
**Docker：**

```bash
curl -O https://cdn.link-ai.tech/code/cow/docker-compose.yml
docker compose up -d
```

启动完成后，浏览器打开 `http://localhost:9899` 进入 **Web控制台**，在这里和Agent对话、配置模型、接入消息通道、安装技能。

> 服务器部署：在 `config.json` 将 `web_host` 设置为 `0.0.0.0`，外部才可访问；务必设置 `web_password` 做访问保护，防火墙开放9899端口。

<br/>

## 🤖 大模型

CowAgent 支持几乎所有主流大模型厂商。聊天、视觉、图片生成、语音识别、语音合成、向量嵌入可以分别配置不同服务商，直接在Web控制台界面配置，无需手动修改配置文件。

| 服务商 | 代表模型 | 对话 | 视觉 | 图片生成 | ASR语音识别 | TTS语音合成 | Embedding向量 |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: |
| [Claude](https://docs.cowagent.ai/models/claude) | claude‑opus‑5 / sonnet‑5 | ✅ | ✅ | | | | |
| [OpenAI](https://docs.cowagent.ai/models/openai) | gpt‑5.6 系列 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Gemini](https://docs.cowagent.ai/models/gemini) | gemini‑3.5‑flash | ✅ | ✅ | ✅ | | | |
| [DeepSeek](https://docs.cowagent.ai/models/deepseek) | deepseek‑v4‑flash / pro | ✅ | | | | | |
| [Qwen通义千问](https://docs.cowagent.ai/models/qwen) | qwen3.7‑plus | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [GLM智谱](https://docs.cowagent.ai/models/glm) | glm‑5.2, glm‑5v‑turbo | ✅ | ✅ | | ✅ | | ✅ |
| [Doubao豆包](https://docs.cowagent.ai/models/doubao) | doubao‑seed‑2.1 系列 | ✅ | ✅ | ✅ | | | ✅ |
| [Kimi](https://docs.cowagent.ai/models/kimi) | kimi‑k3 | ✅ | ✅ | | | | |
| [MiniMax](https://docs.cowagent.ai/models/minimax) | MiniMax‑M3 | ✅ | ✅ | ✅ | | ✅ | |
| [ERNIE文心](https://docs.cowagent.ai/models/qianfan) | ernie‑5.1 | ✅ | ✅ | | | | |
| [MiMo](https://docs.cowagent.ai/models/mimo) | mimo‑v2.5 / pro | ✅ | ✅ | | | ✅ | |
| [LinkAI](https://docs.cowagent.ai/models/linkai) | 一键接入上百款模型 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Custom自定义](https://docs.cowagent.ai/models/custom) | 本地模型/第三方代理 | ✅ | | | | | |



<br/>

## 💬 消息通道

单个Agent实例可同时对接多个消息通道，大部分通道直接在Web控制台即可完成配置。

| 通道 | 文本 | 图片 | 文件 | 语音 | 群聊 |
| --- | :-: | :-: | :-: | :-: | :-: |
| [Web控制台](https://docs.cowagent.ai/channels/web)（默认） | ✅ | ✅ | ✅ | ✅ | |
| [Telegram](https://docs.cowagent.ai/channels/telegram) | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Slack](https://docs.cowagent.ai/channels/slack) | ✅ | ✅ | ✅ | | ✅ |
| [Discord](https://docs.cowagent.ai/channels/discord) | ✅ | ✅ | ✅ | | ✅ |
| [微信](https://docs.cowagent.ai/channels/weixin) | ✅ | ✅ | ✅ | ✅ | |
| [飞书](https://docs.cowagent.ai/channels/feishu) | ✅ | ✅ | ✅ | ✅ | ✅ |
| [钉钉](https://docs.cowagent.ai/channels/dingtalk) | ✅ | ✅ | ✅ | ✅ | ✅ |
| [企业微信机器人](https://docs.cowagent.ai/channels/wecom‑bot) | ✅ | ✅ | ✅ | ✅ | ✅ |
| [QQ](https://docs.cowagent.ai/channels/qq) | ✅ | ✅ | ✅ | | ✅ |
| [企业微信应用](https://docs.cowagent.ai/channels/wecom) | ✅ | ✅ | ✅ | ✅ | |
| [微信客服](https://docs.cowagent.ai/channels/wechat‑kf) | ✅ | ✅ | ✅ | ✅ | |
| [微信公众号](https://docs.cowagent.ai/channels/wechatmp) | ✅ | ✅ | | ✅ | |




*Web控制台是默认通道，也是配置模型、通道、技能、记忆的统一入口。*

<br/>

## 🧠 记忆与知识库

**长期记忆**采用三层架构：对话上下文（短期）→日常记忆（中期）→MEMORY.md核心长期记忆。夜间自动执行**深度梦境**，把零散对话提炼为长期记忆条目与叙事日志。

**个人知识库**和时序记忆互补，按主题组织结构化知识。Agent自动从对话中提取有价值信息，维护索引与交叉引用，Web控制台支持交互式知识图谱可视化。查看：[个人知识库](https://docs.cowagent.ai/knowledge/index)。


<br/>

## 🔧 工具与技能

**工具**是Agent操作系统资源的原子能力。**技能**是更高层级工作流，通过清单文件组合多个工具完成复杂任务。

### 工具系统

**内置工具**包含文件读写(`read`/`write`/`edit`/`ls`)、终端(`bash`)、消息发送(`send`)、记忆检索(`memory`)、环境变量(`env_config`)、网页抓取(`web_fetch`)、定时任务(`scheduler`)、网页搜索(`web_search`)、视觉理解(`vision`)、浏览器自动化(`browser`)。



```bash
/skill list                   # 列出已安装技能
/skill search <关键词>        # 搜索技能市场
/skill install <名称>          # 一键安装技能
```

文档：[技能总览](https://docs.cowagent.ai/skills/index) · [创建技能](https://docs.cowagent.ai/skills/create)。

<br/>

## 🔗 相关项目

- **[Cow Skill Hub](https://github.com/zhayujie/cow‑skill‑hub)** — AI Agent公开技能市场，兼容 CowAgent、OpenClaw、Claude Code 等项目
- **[bot‑on‑anything](https://github.com/zhayujie/bot‑on‑anything)** — 轻量LLM应用框架，大量IM平台对接能力
- **[AgentMesh](https://github.com/MinimalFuture/AgentMesh)** — 开源多智能体框架，通过多Agent协作解决复杂任务
<br/>

## ⚠️ 免责声明

1. 本项目基于 [MIT协议](/LICENSE)开源，仅用于技术研究学习。使用者需遵守所在地区法律法规，项目维护者不对使用产生的任何后果承担责任。
2. **成本与安全提醒**：Agent模式Token消耗远高于普通对话，请权衡模型质量与开销。Agent拥有本地操作系统访问权限，请仅在可信环境部署

<br/>

