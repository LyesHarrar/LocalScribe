import os
import sys
import platform
import subprocess
import pathlib
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger("LocalScribe.Hardware")

_CUDA_CONFIGURED = False
_DLL_HANDLES = []


def configure_cuda_paths() -> List[str]:
    """
    Configure automatiquement l'accès aux bibliothèques dynamiques NVIDIA (cuBLAS, cuDNN, CUDA)
    sous Windows pour CTranslate2 et PyTorch.
    Résout les DLLs dans les packages Python (nvidia/*), le dossier de l'application ou le système,
    permettant l'accélération GPU sans configuration manuelle de variables d'environnement.
    """
    global _CUDA_CONFIGURED
    if _CUDA_CONFIGURED:
        return []

    added = []
    if sys.platform != "win32":
        _CUDA_CONFIGURED = True
        return added

    # Répertoires de base où chercher les bibliothèques NVIDIA
    candidate_bases = [pathlib.Path(p) for p in sys.path if p]

    # Chemins relatifs projet LocalScribe (mode standard et portable)
    try:
        project_root = pathlib.Path(__file__).resolve().parent.parent
        candidate_bases.extend([
            project_root / "python" / "Lib" / "site-packages",
            project_root / "bin",
            project_root,
        ])
    except Exception:
        pass

    # Variables d'environnement standard CUDA Toolkit (si présent)
    for env_var in ("CUDA_PATH", "CUDA_PATH_V12_0", "CUDA_PATH_V11_8"):
        val = os.environ.get(env_var)
        if val:
            candidate_bases.append(pathlib.Path(val) / "bin")

    seen = set()
    for base in candidate_bases:
        if not base.exists():
            continue

        search_dirs = []
        # Packages pip 'nvidia-*' (ex: nvidia/cublas/bin, nvidia/cudnn/bin, etc.)
        nvidia_dir = base / "nvidia" if base.name != "nvidia" else base
        if nvidia_dir.is_dir():
            for bin_dir in nvidia_dir.glob("*/bin"):
                if bin_dir.is_dir():
                    search_dirs.append(bin_dir)
        elif base.is_dir():
            # Si le dossier contient directement des DLLs cublas
            if any(base.glob("cublas64_*.dll")):
                search_dirs.append(base)

        for d in search_dirs:
            try:
                d_resolved = d.resolve()
                d_str = str(d_resolved)
            except Exception:
                d_str = str(d)

            if d_str not in seen:
                seen.add(d_str)
                # 1. Enregistrement auprès du chargeur de DLL Windows (Python 3.8+)
                if hasattr(os, "add_dll_directory"):
                    try:
                        handle = os.add_dll_directory(d_str)
                        _DLL_HANDLES.append(handle)
                    except Exception:
                        pass
                # 2. Ajout au PATH du processus pour les bibliothèques C++ natives
                current_path_parts = os.environ.get("PATH", "").split(os.pathsep)
                if d_str not in current_path_parts:
                    os.environ["PATH"] = d_str + os.pathsep + os.environ.get("PATH", "")
                added.append(d_str)

    _CUDA_CONFIGURED = True
    if added:
        logger.info(f"Chemins DLL NVIDIA configurés avec succès : {len(added)} répertoires ajoutés.")
    return added


# Initialisation anticipée dès l'import du module
configure_cuda_paths()


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
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
            creationflags=creation_flags
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
    """Vérifie si CUDA est réellement opérationnel pour CTranslate2 ou Torch."""
    configure_cuda_paths()
    # 1. Vérification directe via CTranslate2 (notre moteur réel)
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            # Sur Windows, CTranslate2 nécessite impérativement les DLLs NVIDIA cuBLAS
            if sys.platform == "win32":
                import ctypes
                found = False
                for dll_name in ("cublas64_12.dll", "cublas64_11.dll"):
                    try:
                        ctypes.CDLL(dll_name)
                        found = True
                        break
                    except Exception:
                        pass
                if not found:
                    return False
            return True
    except Exception:
        pass

    # 2. Vérification alternative via Torch
    try:
        import torch
        if torch.cuda.is_available():
            if sys.platform == "win32":
                try:
                    torch.zeros(1, device="cuda")
                    return True
                except Exception:
                    return False
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
    has_nvidia_device = False
    try:
        import ctranslate2
        has_nvidia_device = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass

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

    elif has_nvidia_device:
        vram_gb = get_vram_gb()
        warnings.append(
            "GPU NVIDIA détecté, mais bibliothèques cuBLAS (cublas64_12.dll) absentes de Windows. "
            "Bascule automatique sur CPU multithreadé optimisé (int8)."
        )

    return HardwareProfile(
        device=device,
        compute_type=compute_type,
        recommended_model=recommended_model,
        vram_gb=vram_gb,
        warnings=warnings
    )
