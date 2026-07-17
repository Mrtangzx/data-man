from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


SOURCE_ARCHIVE = "https://github.com/antgroup/echomimic_v3/archive/refs/heads/main.zip"
MODEL_REPOS = {
    "base": ("PAI/Wan2.1-Fun-V1.1-1.3B-InP", "Wan2.1-Fun-V1.1-1.3B-InP"),
    "audio": ("TencentGameMate/chinese-wav2vec2-base", "chinese-wav2vec2-base"),
    "flash": ("BadToBest/EchoMimicV3", "EchoMimicV3"),
}


def require_capacity(root: Path) -> None:
    free_gib = shutil.disk_usage(root).free / 1024**3
    if free_gib < 45:
        raise SystemExit(f"至少需要 45 GiB 可用空间，当前只有 {free_gib:.1f} GiB。")


def require_gpu() -> None:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit("未检测到 NVIDIA GPU。请在魔搭 Notebook 中选择 A10 24GB 实例后重试。")
    print("GPU:", result.stdout.strip())


def download_source(root: Path) -> Path:
    source = root / "source" / "echomimic_v3"
    if (source / "infer_flash.py").is_file():
        print("源码已存在，跳过下载:", source)
        return source

    archive = root / "downloads" / "echomimic_v3-main.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    print("下载 EchoMimicV3 官方源码...")
    urllib.request.urlretrieve(SOURCE_ARCHIVE, archive)
    extract_root = root / "source"
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extract_root)
    extracted = extract_root / "echomimic_v3-main"
    extracted.rename(source)
    return source


def download_models(root: Path) -> dict[str, Path]:
    from modelscope_hub import HubApi

    api = HubApi()
    model_root = root / "models"
    model_root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, (repo_id, folder) in MODEL_REPOS.items():
        destination = model_root / folder
        patterns = ["echomimicv3-flash-pro/*"] if key == "flash" else None
        print(f"同步 {repo_id} -> {destination}")
        paths[key] = Path(
            api.download_repo(
                repo_id,
                "model",
                revision="master",
                local_dir=destination,
                allow_patterns=patterns,
                max_workers=4,
            )
        )
    return paths


def verify(root: Path) -> None:
    required = {
        "官方推理脚本": root / "source" / "echomimic_v3" / "infer_flash.py",
        "基础模型配置": root / "models" / "Wan2.1-Fun-V1.1-1.3B-InP" / "config.json",
        "基础模型 VAE": root / "models" / "Wan2.1-Fun-V1.1-1.3B-InP" / "Wan2.1_VAE.pth",
        "音频编码器": root / "models" / "chinese-wav2vec2-base" / "config.json",
        "Flash 权重": root
        / "models"
        / "EchoMimicV3"
        / "echomimicv3-flash-pro"
        / "diffusion_pytorch_model.safetensors",
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
    if missing:
        raise SystemExit("准备结果不完整:\n" + "\n".join(missing))
    print("模型与源码准备完成。")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/mnt/workspace/nova"))
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    require_gpu()
    require_capacity(args.root)
    download_source(args.root)
    download_models(args.root)
    verify(args.root)


if __name__ == "__main__":
    main()
