# NOVA × 魔搭免费 A10

这套文件把 NOVA 的第一条真实成片纵切放到魔搭 Notebook：本机继续运行 Lite 控制面，魔搭 A10 24GB 只在开发和真实生成时启动。首轮输入为一张已授权人物图片和一段 WAV，输出为 EchoMimicV3 Flash MP4。

## 为什么先用 Notebook

- 魔搭 2026-07-06 的官方入门文档列出 A10 24GB 和 `/mnt/workspace` 下 100GB 持久化存储。
- EchoMimicV3 Flash 官方给出的显存要求是 12GB，A10 24GB 有足够余量。
- xGPU 创空间适合之后发布按请求动态调度的 Gradio 应用，但需要申请 xGPU 权限；Notebook 可以先完成私有素材和质量基线。

免费额度、排队和单次实例时长以账号页面实时显示为准。不要把人物、声音或 token 放到公开创空间。

## 在魔搭执行

1. 登录 <https://modelscope.cn/my/mynotebook>，绑定云账号并领取 Notebook 免费资源。
2. 新建 GPU 实例，选择 A10 24GB；不要选择 CPU 实例。
3. 把整个 `deploy/modelscope` 目录上传到 `/mnt/workspace/NOVA-ModelScope-A10`。
4. 把已授权图片和 WAV 上传到 `/mnt/workspace/nova-inputs/avatar.png` 与 `/mnt/workspace/nova-inputs/voice.wav`。
5. 打开 `NOVA-ModelScope-A10.ipynb`，按顺序运行全部单元格。
6. 结果保存在 `/mnt/workspace/nova/outputs`。完成后停止 Notebook 实例，持久盘内容会保留。

第一次准备会下载约 24GB 模型并安装运行依赖，耗时取决于当时资源与网络。脚本是幂等的，再次运行会复用持久盘。

## 安全与费用护栏

- 仅使用本人或明确授权的人物和声音素材。
- 第一轮限制 512×512、25fps、最多 81 帧、8 个推理步；先验证质量再增加时长。
- `prepare_modelscope.py` 要求至少 45GiB 空闲磁盘，并在下载前验证 NVIDIA GPU。
- 模型全部从魔搭仓库下载；源码取自蚂蚁集团官方 GitHub。真实上线前必须把源码 `main` 固定为审计过的 commit。
- 不在 Notebook 中写 NOVA 管理密钥。后续接控制平面时使用短期任务凭证和出站拉取。

## 后续变成 xGPU Worker

纵切通过后，把同一推理入口包装成 Gradio 创空间并申请 xGPU。xGPU 官方说明会按请求动态调度并在计算结束后释放 GPU，适合避免常驻成本。正式 Worker 仍需补齐任务幂等、取消、超时、产物哈希和 adapter TCK，不能直接把 Notebook 当生产 API。

## 当前私有 Studio

- 仓库：`tangzhengxian/nova-digital-human-a10`
- 地址：<https://modelscope.cn/studios/tangzhengxian/nova-digital-human-a10>
- 当前规格：平台免费 `2 vCPU / 16GB RAM`，仅运行 `studio/app.py` 环境预检页。
- 当前账号的硬件接口暂未返回 xGPU；不要把普通付费 GPU 规格写入部署配置。
- 获得 xGPU 权限后，先用预检页确认 NVIDIA GPU 和至少 45GiB 可用磁盘，再启用 EchoMimicV3。
