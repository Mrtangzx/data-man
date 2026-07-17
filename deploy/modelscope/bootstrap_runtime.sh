#!/usr/bin/env bash
set -euo pipefail

NOVA_MS_ROOT="${1:-/mnt/workspace/nova}"
SOURCE_DIR="$NOVA_MS_ROOT/source/echomimic_v3"

if [[ ! -f "$SOURCE_DIR/requirements.txt" ]]; then
  echo "请先运行 prepare_modelscope.py 下载源码和模型。" >&2
  exit 1
fi

python -m pip install --upgrade pip
python -m pip install --upgrade modelscope-hub

REQUIREMENTS_FILE="$SOURCE_DIR/requirements.txt"
PYTHON_MINOR="$(python -c 'import sys; print(sys.version_info.minor)')"
if [[ "$PYTHON_MINOR" -ge 12 ]]; then
  # EchoMimicV3 currently pins TensorFlow 2.15, which has no CPython 3.12 wheel.
  # RetinaFace only needs a compatible TensorFlow runtime, so use the first
  # Python-3.12-compatible release without modifying the downloaded source.
  PY312_REQUIREMENTS="$NOVA_MS_ROOT/requirements-py312.txt"
  sed 's/tensorflow==2\.15\.0/tensorflow>=2.16,<2.17/' \
    "$SOURCE_DIR/requirements.txt" > "$PY312_REQUIREMENTS"
  REQUIREMENTS_FILE="$PY312_REQUIREMENTS"
  echo "检测到 Python 3.$PYTHON_MINOR，使用 TensorFlow 2.16 兼容依赖。"
fi

python -m pip install -r "$REQUIREMENTS_FILE" pyloudnorm

ffmpeg -version | head -n 1
python - <<'PY'
import torch
print("torch", torch.__version__, "cuda", torch.version.cuda)
assert torch.cuda.is_available(), "当前 Python 环境没有可用 CUDA"
props = torch.cuda.get_device_properties(0)
print(props.name, round(props.total_memory / 1024**3, 1), "GiB")
assert props.total_memory >= 20 * 1024**3, "请使用 A10 24GB 或更高规格"
PY
