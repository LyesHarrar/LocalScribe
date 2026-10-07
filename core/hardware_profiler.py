import platform
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
    """Tente de récupérer la VRAM disponible via PyTorch, sans crasher si absent."""
    try:
        import torch
        if torch.cuda.is_available():
            # torch.cuda.get_device_properties renvoie la mémoire en octets
            return torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        pass
    return None

def detect_hardware() -> HardwareProfile:
    """Détecte l'accélération matérielle et recommande un profil optimisé."""
    warnings = []
    device = "cpu"
    compute_type = "int8"
    recommended_model = "base"
    vram_gb = None

    # 1. Vérification CUDA
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            vram_gb = get_vram_gb()
            
            if vram_gb is not None:
                if vram_gb >= 8:
                    compute_type = "float16"
                    recommended_model = "large-v3"
                elif vram_gb >= 4:
                    compute_type = "int8_float16"
                    recommended_model = "medium"
                else:
                    compute_type = "int8"
                    recommended_model = "small"
            else:
                compute_type = "float16"
                recommended_model = "base"
    except ImportError:
        warnings.append("PyTorch n'est pas installé. La détection VRAM précise (CUDA) est désactivée.")

    # 2. Vérification MPS (Apple Silicon Mac)
    if device == "cpu" and platform.system() == "Darwin" and platform.machine() == "arm64":
        # Pour Mac Apple Silicon, CTranslate2 préfère 'cpu' (qui utilise Accelerate/NEON en interne)
        # Mais Faster-Whisper est souvent utilisé en 'cpu' ou avec torch 'mps'. 
        # CTranslate2 ne supporte pas MPS nativement comme "device", on utilise donc "cpu" + int8
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
