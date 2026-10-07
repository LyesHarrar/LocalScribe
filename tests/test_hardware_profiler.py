import sys
import unittest
from unittest.mock import patch, MagicMock
from core.hardware_profiler import detect_hardware, HardwareProfile

class TestHardwareProfiler(unittest.TestCase):

    @patch("core.hardware_profiler.get_vram_gb")
    def test_cuda_high_vram(self, mock_get_vram):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        
        with patch.dict('sys.modules', {'torch': mock_torch}):
            mock_get_vram.return_value = 10.0 # 10 GB
            
            profile = detect_hardware()
            
            self.assertEqual(profile.device, "cuda")
            self.assertEqual(profile.compute_type, "float16")
            self.assertEqual(profile.recommended_model, "large-v3")
        
    @patch("core.hardware_profiler.get_vram_gb")
    def test_cuda_low_vram(self, mock_get_vram):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        
        with patch.dict('sys.modules', {'torch': mock_torch}):
            mock_get_vram.return_value = 2.0 # 2 GB
            
            profile = detect_hardware()
            
            self.assertEqual(profile.device, "cuda")
            self.assertEqual(profile.compute_type, "int8")
            self.assertEqual(profile.recommended_model, "small")

    @patch("core.hardware_profiler.platform.system")
    @patch("core.hardware_profiler.platform.machine")
    def test_mps_apple_silicon_fallback(self, mock_machine, mock_system):
        # On désactive cuda
        with patch.dict('sys.modules', {'torch': None}):
            mock_system.return_value = "Darwin"
            mock_machine.return_value = "arm64"
            
            profile = detect_hardware()
            
            self.assertEqual(profile.device, "cpu")
            self.assertEqual(profile.compute_type, "int8")
            self.assertEqual(profile.recommended_model, "small")

if __name__ == "__main__":
    unittest.main()
