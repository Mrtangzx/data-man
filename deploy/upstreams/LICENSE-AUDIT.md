# 上游许可证审计（Milestone 0）

核对日期：2026-07-16

本文件只记录固定源码提交的初步审计结果。模型权重、测试数据、上游所调用的第三方模型及运行时依赖必须在真实 GPU 部署前逐项确认；源码许可证通过不等于整套推理链可直接用于生产。

| 上游 | 固定版本 | 源码许可证 | 当前结论 |
| --- | --- | --- | --- |
| OpenAvatarChat | `0.6.0` / `b28cc34714660fb9bbf4d9d456c011769cc84e76` | Apache-2.0 | 源码通过；所选 ASR、LLM、TTS、Avatar 权重待审 |
| OpenAvatarChat-WebUI | `1b23c2658f71aba93d222bc042f93faf7feed7d5` | Apache-2.0 | 作为通信协议参考可用 |
| SoulX-FlashHead | `12467cef31a9554cd9682a0521e6e87deaef9810` | Apache-2.0 | 实时单图说话头候选；权重与基础模型待最终审计 |
| EchoMimicV3 | `7e89489ca51c0d008fc1963ec6c03fc5bd0b9397` | Apache-2.0 | 离线单图动作候选；权重、基础模型及显存基线待审 |
| MuseTalk | `0a89dec45a0192b824e3cf4daf96c239440c5ed8` | MIT | 源码通过；1.5 权重及全部间接模型仍需形成最终 NOTICE |
| CosyVoice | `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc` | Apache-2.0 | 源码通过；部署时选定的权重模型卡待审 |
| LiveTalking | `fd5cda269780d410405a08d819074fa9af0db29d` | Apache-2.0 | 仅保留为可选适配器，不进入默认链路 |

## 素材边界

- 当前人物图与两段语音仅用于本地内部兼容性验证。
- 未经使用者明确选择并授权具体 GPU/API target，不向第三方上传人物或声音素材。
- 对外发布前必须补齐肖像、声音、输出内容和数据留存授权记录。

## 仍需通过的门槛

1. 选定 OpenAvatarChat 的具体 ASR、LLM、TTS 与 Avatar handler，并固定各自权重哈希和条款。
2. 对 SoulX-FlashHead、EchoMimicV3 及各自基础模型/音频编码器形成权重哈希与条款记录。
3. 选定 CosyVoice 具体模型版本，记录模型卡、权重哈希和是否允许目标使用场景。
4. 对 MuseTalk 依赖的 Whisper、VAE、DWPose、S3FD 等生成最终依赖与许可证清单。
5. 在 Linux GPU target 上生成 SBOM/NOTICE，并使用当前合规素材完成真实质量测试。
