# NOVA

NOVA 是一个组装式双引擎数字人工作室。实时链路预留 OpenAvatarChat，离线成片预留 MuseTalk + CosyVoice；`dev` profile 先用确定性 Mock 跑通同一套产品协议。

> 当前里程碑：可运行的协议级开发版本。Mock 能验证互动、打断、任务状态、SSE 恢复和 MP4 交付，但不代表真实人物、声音或口型质量。

## 2 分钟零成本启动（Windows）

前置：已安装 `uv`、Node.js 与 `pnpm`，至少 2GB 可用磁盘。无需 NVIDIA 显卡；Docker 未运行时启动器会自动使用 SQLite + 本地进程的 `lite` profile。

```powershell
.\nova.ps1 start
```

启动器会执行 doctor、选择可用运行时、等待健康检查，然后打开 <http://127.0.0.1:8787>。如需显式选择最低资源路径，可执行 `./nova.ps1 start --lite`。Docker 已运行且未指定 `--lite` 时仍使用 Compose `dev` profile。

常用命令：

```powershell
.\nova.ps1 status
.\nova.ps1 doctor
.\nova.ps1 logs api
.\nova.ps1 stop
```

## 工作区

- 实时互动：Mock 文字/麦克风、字幕、Listening/Thinking/Speaking、打断。
- 视频创作：提交带幂等键的异步任务，通过 SSE 查看阶段，下载示例 MP4。
- 形象与声音：上传素材并查看格式、时长和兼容性预检。
- 系统设置：查看 EngineDeployment、capability、健康与后续 GPU/API 接入入口。

## 本地开发

```powershell
uv run --project backend uvicorn nova.main:app --reload --port 8788
pnpm install
pnpm dev
```

后端默认可使用 SQLite；Compose 使用 PostgreSQL。前端开发服务器把 `/api` 代理到 `127.0.0.1:8788`。

## 测试

```powershell
uv run --project backend pytest backend/tests -q
pnpm install
pnpm typecheck
pnpm test
pnpm build
```

## 真实引擎状态

### 当前最低成本算力策略

- 本机只运行 Web、控制平面、SQLite 和确定性 Mock，闲置 GPU 成本为 0。
- 第一条真实链路只做离线成片，优先使用魔搭 Notebook 免费 A10 24GB 和 100GB 持久盘；不为实时链路保留常驻 GPU。
- 已提供可上传的 Notebook、自检、魔搭模型下载和 EchoMimicV3 Flash 运行脚本，见 [魔搭 A10 运行包](./deploy/modelscope/README.md)。
- 免费额度、排队和单次实例时长以魔搭账户页面为准；额度不足时再回退到 Modal/RunPod 按量方案，在此之前不买显卡、不包月。

价格会变化，设置页展示核对日期，环境变量可覆盖单价和额度。实施边界、切换条件和上线步骤见 [最低成本算力方案](./deploy/economy/README.md)。

真实引擎接入受以下门控制约：

1. `upstream-lock.yml` 已固定源码 commit 和源码许可证哈希；升级必须显式更新锁文件。
2. 模型权重、间接依赖、CUDA/驱动矩阵必须形成证据，详见 `deploy/upstreams/LICENSE-AUDIT.md`。
3. OpenAvatarChat、GPU Worker 或 HTTP provider 必须通过 adapter conformance suite。
4. 正式人物和声音素材由使用者提供并完成授权确认。

详细架构与验收门见 [PLAN.md](./PLAN.md)。
