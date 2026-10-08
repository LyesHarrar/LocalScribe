import unittest
from unittest.mock import patch, MagicMock
from core.hardware_profiler import detect_hardware, HardwareProfile

class TestHardwareProfiler(unittest.TestCase):

    @patch("core.hardware_profiler.get_vram_gb")
    @patch("core.hardware_profiler.is_cuda_available")
    def test_cuda_high_vram(self, mock_is_cuda, mock_get_vram):
        mock_is_cuda.return_value = True
        mock_get_vram.return_value = 10.0 # 10 GB
        
        profile = detect_hardware()
        
        self.assertEqual(profile.device, "cuda")
        self.assertEqual(profile.compute_type, "float16")
        self.assertEqual(profile.recommended_model, "large-v3")

    @patch("core.hardware_profiler.get_vram_gb")
    @patch("core.hardware_profiler.is_cuda_available")
    def test_cuda_mid_vram(self, mock_is_cuda, mock_get_vram):
        mock_is_cuda.return_value = True
        mock_get_vram.return_value = 6.0 # RTX 3060 (6 GB)
        
        profile = detect_hardware()
        
        self.assertEqual(profile.device, "cuda")
        self.assertEqual(profile.compute_type, "float16")
        self.assertEqual(profile.recommended_model, "medium")
        
    @patch("core.hardware_profiler.get_vram_gb")
    @patch("core.hardware_profiler.is_cuda_available")
    def test_cuda_low_vram(self, mock_is_cuda, mock_get_vram):
        mock_is_cuda.return_value = True
        mock_get_vram.return_value = 2.0 # 2 GB
        
        profile = detect_hardware()
        
        self.assertEqual(profile.device, "cuda")
        self.assertEqual(profile.compute_type, "int8")
        self.assertEqual(profile.recommended_model, "small")

    @patch("core.hardware_profiler.is_cuda_available")
    @patch("core.hardware_profiler.platform.system")
    @patch("core.hardware_profiler.platform.machine")
    def test_mps_apple_silicon_fallback(self, mock_machine, mock_system, mock_is_cuda):
        mock_is_cuda.return_value = False
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"
        
        profile = detect_hardware()
        self.assertEqual(profile.device, "cpu")
        self.assertEqual(profile.compute_type, "int8")
        self.assertEqual(profile.recommended_model, "small")
    @patch("core.hardware_profiler.get_vram_gb")
    @patch("core.hardware_profiler.is_cuda_available")
    @patch("core.hardware_profiler.platform.system")
    def test_cuda_missing_cublas_fallback(self, mock_system, mock_is_cuda, mock_get_vram):
        mock_system.return_value = "Windows"
        mock_is_cuda.return_value = False
        mock_get_vram.return_value = 6.0

        with patch("ctranslate2.get_cuda_device_count", return_value=1):
            profile = detect_hardware()
            self.assertEqual(profile.device, "cpu")
            self.assertEqual(profile.compute_type, "int8")
            self.assertEqual(profile.recommended_model, "base")
            self.assertTrue(any("cuBLAS" in w for w in profile.warnings))

    def test_configure_cuda_paths_non_windows(self):
        from core.hardware_profiler import configure_cuda_paths
        import core.hardware_profiler as hp
        with patch("sys.platform", "darwin"):
            orig_configured = hp._CUDA_CONFIGURED
            try:
                hp._CUDA_CONFIGURED = False
                res = configure_cuda_paths()
                self.assertEqual(res, [])
            finally:
                hp._CUDA_CONFIGURED = orig_configured

    def test_configure_cuda_paths_idempotent(self):
        from core.hardware_profiler import configure_cuda_paths
        import core.hardware_profiler as hp
        orig_configured = hp._CUDA_CONFIGURED
        try:
            hp._CUDA_CONFIGURED = True
            res = configure_cuda_paths()
            self.assertEqual(res, [])
        finally:
            hp._CUDA_CONFIGURED = orig_configured


if __name__ == "__main__":
    unittest.main()
