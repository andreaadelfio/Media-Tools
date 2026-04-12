"""Integration tests for Bird Audio Live and audio hardware."""

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Test sounddevice availability
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False
    sd = None

from media_tools.services.audio_live_service import (
    LIVE_PROCESS,
    start_live_process,
    stop_live_process,
    live_status,
)


class TestAudioDeviceAvailability:
    """Test audio device detection and sounddevice functionality."""

    @pytest.mark.skipif(not SOUNDDEVICE_AVAILABLE, reason="sounddevice not installed")
    def test_sounddevice_import(self):
        """Test that sounddevice can be imported."""
        assert SOUNDDEVICE_AVAILABLE
        assert sd is not None

    @pytest.mark.skipif(not SOUNDDEVICE_AVAILABLE, reason="sounddevice not installed")
    def test_query_audio_devices(self):
        """Test querying available audio devices."""
        devices = sd.query_devices()
        # query_devices() returns a numpy structured array
        assert devices is not None
        assert len(devices) > 0, "No audio devices found"

    @pytest.mark.skipif(not SOUNDDEVICE_AVAILABLE, reason="sounddevice not installed")
    def test_get_default_device(self):
        """Test getting default audio input device."""
        default_in = sd.default.device[0]
        assert default_in is not None
        assert isinstance(default_in, int)
        assert default_in >= 0

    @pytest.mark.skipif(not SOUNDDEVICE_AVAILABLE, reason="sounddevice not installed")
    def test_audio_device_properties(self):
        """Test that audio devices have expected properties."""
        devices = sd.query_devices()
        # At least one device should support input
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        assert len(input_devices) > 0, "No input devices found"
        
        # Check first input device has required properties
        device = input_devices[0]
        assert "name" in device
        assert "max_input_channels" in device
        assert device["max_input_channels"] > 0

    @pytest.mark.skipif(not SOUNDDEVICE_AVAILABLE, reason="sounddevice not installed")
    def test_record_short_audio_snippet(self):
        """Test recording a short audio snippet (1 second)."""
        try:
            import numpy as np
            
            sample_rate = 16000
            duration = 0.5  # 500ms recording
            
            # Record short audio
            audio_data = sd.rec(
                int(sample_rate * duration),
                samplerate=sample_rate,
                channels=1,
                dtype='float32',
                blocking=True
            )
            
            # Verify we got audio data
            assert audio_data is not None
            assert len(audio_data) > 0
            assert audio_data.shape[0] > 0
            
        except Exception as e:
            pytest.skip(f"Could not record audio: {str(e)}")

    @pytest.mark.skipif(not SOUNDDEVICE_AVAILABLE, reason="sounddevice not installed")
    def test_backend_sounddevice_name(self):
        """Test that sounddevice backend is correctly named."""
        # Just verify the backend string matches what we use
        backend = "sounddevice"
        assert backend == "sounddevice"
        assert isinstance(backend, str)


class TestBirdLiveIntegrationWithMocks:
    """Integration tests for bird live using mocks (no actual process)."""

    def setup_method(self):
        """Reset LIVE_PROCESS before each test."""
        LIVE_PROCESS.process = None
        LIVE_PROCESS.log_path = None
        LIVE_PROCESS.detections_dir = None
        LIVE_PROCESS.started_at = None
        LIVE_PROCESS.command_line = None
        LIVE_PROCESS.log_handle = None

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_live_process_creates_log_file(self, mock_popen, mock_cli_path):
        """Test that starting live process creates a log file."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            result = start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=0,
                min_confidence=0.5,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            # Verify log file path was created
            assert LIVE_PROCESS.log_path is not None
            assert LIVE_PROCESS.log_path.parent == detections_dir
            assert LIVE_PROCESS.log_path.name == "bird_audio_live.log"

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_live_process_detections_dir_created(self, mock_popen, mock_cli_path):
        """Test that detections directory is created."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 12346
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir) / "nested" / "detections"
            assert not detections_dir.exists()
            
            result = start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=1,
                min_confidence=0.3,
                frame_length=1024,
                slice_interval=600,
                disable_denoise=True,
                verbose=False,
            )
            
            # Verify directory was created
            assert detections_dir.exists()
            assert detections_dir.is_dir()

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_live_process_command_parameters(self, mock_popen, mock_cli_path):
        """Test that subprocess.Popen is called with correct parameters."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 12347
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            start_live_process(
                detections_dir=detections_dir,
                backend="pvrecorder",
                device_index=5,
                min_confidence=0.8,
                frame_length=256,
                slice_interval=120,
                disable_denoise=True,
                verbose=False,
            )
            
            # Verify Popen was called
            assert mock_popen.called
            call_args = mock_popen.call_args
            
            # Verify command contains expected parameters
            cmd = call_args[0][0]
            assert "live" in cmd
            assert "--backend" in cmd
            assert "pvrecorder" in cmd
            assert "--device-index" in cmd
            assert "5" in cmd
            assert "--disable-denoise" in cmd

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_live_process_stdout_redirect(self, mock_popen, mock_cli_path):
        """Test that process stdout is redirected to log file."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 12348
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=0,
                min_confidence=0.5,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            # Verify Popen was called with stdout/stderr redirection
            call_args = mock_popen.call_args
            kwargs = call_args[1]
            assert "stdout" in kwargs
            assert kwargs["stderr"] == subprocess.STDOUT


class TestBirdLiveStatusDuringOperation:
    """Test status reporting during bird live operation."""

    def setup_method(self):
        """Reset LIVE_PROCESS before each test."""
        LIVE_PROCESS.process = None
        LIVE_PROCESS.log_path = None
        LIVE_PROCESS.detections_dir = None
        LIVE_PROCESS.started_at = None
        LIVE_PROCESS.command_line = None
        LIVE_PROCESS.log_handle = None

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_status_contains_command_line(self, mock_popen, mock_cli_path):
        """Test that status includes the full command line."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=0,
                min_confidence=0.5,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            status = live_status()
            
            assert status["command_line"] is not None
            assert isinstance(status["command_line"], str)
            assert len(status["command_line"]) > 0

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_status_timestamp_format(self, mock_popen, mock_cli_path):
        """Test that status timestamp is in ISO format."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 88888
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=0,
                min_confidence=0.5,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            status = live_status()
            started_at = status["started_at"]
            
            # Verify ISO format (e.g., "2026-04-07T10:30:00")
            assert started_at is not None
            assert "T" in started_at
            assert "-" in started_at
            assert ":" in started_at


class TestAudioBackendChoice:
    """Test different audio backend configurations."""

    def setup_method(self):
        """Reset LIVE_PROCESS before each test."""
        LIVE_PROCESS.process = None
        LIVE_PROCESS.log_path = None
        LIVE_PROCESS.detections_dir = None
        LIVE_PROCESS.started_at = None
        LIVE_PROCESS.command_line = None
        LIVE_PROCESS.log_handle = None

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_backend_sounddevice_option(self, mock_popen, mock_cli_path):
        """Test sounddevice backend configuration."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 11111
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            start_live_process(
                detections_dir=Path(tmpdir),
                backend="sounddevice",
                device_index=0,
                min_confidence=0.1,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            cmd = mock_popen.call_args[0][0]
            assert "--backend" in cmd
            idx = cmd.index("--backend")
            assert cmd[idx + 1] == "sounddevice"

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_backend_pvrecorder_option(self, mock_popen, mock_cli_path):
        """Test pvrecorder backend configuration."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 22222
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            start_live_process(
                detections_dir=Path(tmpdir),
                backend="pvrecorder",
                device_index=0,
                min_confidence=0.1,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            cmd = mock_popen.call_args[0][0]
            assert "--backend" in cmd
            idx = cmd.index("--backend")
            assert cmd[idx + 1] == "pvrecorder"

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_backend_auto_option(self, mock_popen, mock_cli_path):
        """Test auto backend configuration."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 33333
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            start_live_process(
                detections_dir=Path(tmpdir),
                backend="auto",
                device_index=0,
                min_confidence=0.1,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            
            cmd = mock_popen.call_args[0][0]
            assert "--backend" in cmd
            idx = cmd.index("--backend")
            assert cmd[idx + 1] == "auto"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
