"""
YOLO model indirme ve yerel önbellekleme.
İlk çalıştırmada Hugging Face'ten indirir, sonra yerel kopyayı kullanır.
"""
import os
from pathlib import Path

from .config import log


def write_file_atomic(src_path: Path, dst_path: Path) -> None:
    """Güç kesintisine karşı atomik dosya kopyası."""
    tmp = dst_path.with_suffix(dst_path.suffix + ".tmp")
    with src_path.open("rb") as sf, tmp.open("wb") as tf:
        while True:
            chunk = sf.read(1 << 20)
            if not chunk:
                break
            tf.write(chunk)
        tf.flush()
        os.fsync(tf.fileno())
    os.replace(tmp, dst_path)
    fd = os.open(str(dst_path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_local_model(repo_id: str, filename: str,
                       cache_dir: str, local_model_path: Path) -> Path:
    """Model mevcutsa döndür; yoksa Hugging Face'ten indir ve kaydet."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub kurulu değil: pip install huggingface_hub"
        ) from exc

    if local_model_path.exists():
        log(f"[MODEL] Mevcut model kullanılıyor: {local_model_path}")
        return local_model_path

    local_model_path.parent.mkdir(parents=True, exist_ok=True)
    log("[MODEL] Hugging Face'ten indiriliyor (ilk kurulum)...")
    downloaded = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir=cache_dir)
    write_file_atomic(Path(downloaded), local_model_path)
    log(f"[MODEL] Kaydedildi: {local_model_path}")
    return local_model_path
