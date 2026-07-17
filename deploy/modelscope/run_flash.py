from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def patch_inference_source_for_low_memory(source: Path) -> None:
    """Release the temporary Flash checkpoint after loading it into the model."""
    transformer_script = source / "src" / "wan_transformer3d_audio_2512.py"
    transformer_content = transformer_script.read_text(encoding="utf-8")
    old_import = (
        "            from diffusers.models.modeling_utils import \\\n"
        "                load_model_dict_into_meta\n"
    )
    new_import = (
        "            try:\n"
        "                from diffusers.models.model_loading_utils import load_model_dict_into_meta\n"
        "            except ImportError:\n"
        "                from diffusers.models.modeling_utils import load_model_dict_into_meta\n"
    )
    if new_import not in transformer_content:
        if old_import not in transformer_content:
            raise SystemExit("无法应用低内存补丁：Transformer 加载器结构已变化。")
        transformer_script.write_text(
            transformer_content.replace(old_import, new_import, 1), encoding="utf-8"
        )

    inference_script = source / "infer_flash.py"
    content = inference_script.read_text(encoding="utf-8")
    needle = (
        "        m, u = transformer.load_state_dict(state_dict, strict=False)\n"
        '        print(f"missing keys: {len(m)}, unexpected keys: {len(u)}")\n'
    )
    cleanup = (
        "        del state_dict\n"
        "        import gc\n"
        "        gc.collect()\n"
    )
    if cleanup in content:
        return
    if needle not in content:
        raise SystemExit("无法应用低内存补丁：EchoMimicV3 infer_flash.py 结构已变化。")
    inference_script.write_text(content.replace(needle, needle + cleanup, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the cheapest NOVA real-video vertical slice on ModelScope A10.")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/mnt/workspace/nova"))
    parser.add_argument("--output", type=Path, default=Path("/mnt/workspace/nova/outputs"))
    parser.add_argument("--prompt", default="A person is speaking naturally to the camera.")
    parser.add_argument("--frames", type=int, default=81)
    args = parser.parse_args()

    if not args.image.is_file() or not args.audio.is_file():
        raise SystemExit("请提供真实存在的人物图片和 WAV 音频路径。")
    if not 1 <= args.frames <= 81:
        raise SystemExit("首轮基线限制为 1-81 帧，长视频在质量基线通过后再开启。")

    source = args.root / "source" / "echomimic_v3"
    patch_inference_source_for_low_memory(source)
    base = args.root / "models" / "Wan2.1-Fun-V1.1-1.3B-InP"
    audio_encoder = args.root / "models" / "chinese-wav2vec2-base"
    transformer = (
        args.root
        / "models"
        / "EchoMimicV3"
        / "echomimicv3-flash-pro"
        / "diffusion_pytorch_model.safetensors"
    )
    args.output.mkdir(parents=True, exist_ok=True)

    # PAI images may preinstall Transformer Engine and ONNX. PEFT detects that
    # optional package automatically, even though EchoMimicV3 does not use it.
    # TensorFlow 2.16 and the preinstalled ONNX stack require incompatible
    # ml_dtypes versions, so shadow only this unused optional integration for
    # the inference subprocess instead of mutating the shared Notebook image.
    compat_root = args.root / "compat"
    transformer_engine_shim = compat_root / "transformer_engine" / "__init__.py"
    transformer_engine_shim.parent.mkdir(parents=True, exist_ok=True)
    transformer_engine_shim.write_text(
        '"""NOVA compatibility shim: Transformer Engine is not used here."""\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{compat_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(compat_root)
    )

    command = [
        sys.executable,
        "infer_flash.py",
        "--image_path",
        str(args.image.resolve()),
        "--audio_path",
        str(args.audio.resolve()),
        "--prompt",
        args.prompt,
        "--num_inference_steps",
        "8",
        "--config_path",
        "config/config.yaml",
        "--model_name",
        str(base),
        "--transformer_path",
        str(transformer),
        "--save_path",
        str(args.output),
        "--wav2vec_model_dir",
        str(audio_encoder),
        "--sampler_name",
        "Flow_Unipc",
        "--video_length",
        str(args.frames),
        "--guidance_scale",
        "6.0",
        "--audio_guidance_scale",
        "3.0",
        "--enable_teacache",
        "--teacache_threshold",
        "0.1",
        "--num_skip_start_steps",
        "5",
        "--riflex_k",
        "6",
        "--weight_dtype",
        "bfloat16",
        "--GPU_memory_mode",
        "sequential_cpu_offload",
        "--sample_size",
        "512",
        "512",
        "--fps",
        "25",
        "--shift",
        "5.0",
    ]
    print("执行:", " ".join(command))
    subprocess.run(command, cwd=source, check=True, env=environment)


if __name__ == "__main__":
    main()
