import platform
import subprocess
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class HardwareProfile:
    device: str
    compute_type: str
    recommended_model: str
    vram_gb: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

def get_vram_gb() -> Optional[float]:
    """
    Récupère la VRAM disponible sans dépendance obligatoire à PyTorch.
    1. Tente via nvidia-smi (rapide, standard sur Windows & Linux)
    2. Tente via torch si présent
    """
    # 1. Tentative via nvidia-smi
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2
        )
        first_line = res.stdout.strip().splitlines()[0]
        return round(float(first_line) / 1024, 1)
    except Exception:
        pass

    # 2. Tentative via PyTorch
    try:
        import torch
        if torch.cuda.is_available():
            mem_bytes = torch.cuda.get_device_properties(0).total_memory
            return round(mem_bytes / (1024 ** 3), 1)
    except Exception:
        pass

    return None

def is_cuda_available() -> bool:
    """Vérifie si CUDA est disponible pour CTranslate2 ou Torch."""
    # 1. Vérification directe via CTranslate2 (notre moteur réel)
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return True
    except Exception:
        pass

    # 2. Vérification alternative via Torch
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass

    return False

def detect_hardware() -> HardwareProfile:
    """Détecte l'accélération matérielle et recommande un profil optimisé."""
    warnings = []
    device = "cpu"
    compute_type = "int8"
    recommended_model = "base"
    vram_gb = None

    # 1. Vérification CUDA
    if is_cuda_available():
        device = "cuda"
        vram_gb = get_vram_gb()

        if vram_gb is not None:
            if vram_gb >= 8:
                compute_type = "float16"
                recommended_model = "large-v3"
            elif vram_gb >= 5.5: # Ex: RTX 3060 6GB
                compute_type = "float16"
                recommended_model = "medium"
            elif vram_gb >= 4:
                compute_type = "int8_float16"
                recommended_model = "medium"
            else:
                compute_type = "int8"
                recommended_model = "small"
        else:
            compute_type = "float16"
            recommended_model = "small"

    # 2. Vérification Apple Silicon Mac (ARM64)
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        device = "cpu"
        compute_type = "int8"
        recommended_model = "small"

    return HardwareProfile(
        device=device,
        compute_type=compute_type,
        recommended_model=recommended_model,
        vram_gb=vram_gb,
        warnings=warnings
    )
