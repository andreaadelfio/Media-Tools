"""Unit tests for Bird Audio Live service."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

from media_tools.services.audio_live_service import (
    LiveProcessState,
    build_live_command,
    live_status,
    start_live_process,
    stop_live_process,
    LIVE_PROCESS,
)


class TestBuildLiveCommand:
    """Test command building for Bird Audio Live."""

    def test_build_command_basic(self):
        """Test building a basic live command."""
        detections_dir = Path("/tmp/detections")
        cmd = build_live_command(
            detections_dir=detections_dir,
            backend="sounddevice",
            device_index=17,
            min_confidence=0.1,
            frame_length=512,
            slice_interval=300,
            disable_denoise=False,
            verbose=True,
        )
        
        assert "live" in cmd
        assert "--backend" in cmd
        assert "sounddevice" in cmd
        assert "--device-index" in cmd
        assert "17" in cmd
        assert "--min-confidence" in cmd
        assert "0.1" in cmd
        assert "--verbose" in cmd
        assert "--disable-denoise" not in cmd

    def test_build_command_with_denoise_disabled(self):
        """Test command with denoise disabled."""
        detections_dir = Path("/tmp/detections")
        cmd = build_live_command(
            detections_dir=detections_dir,
            backend="auto",
            device_index=0,
            min_confidence=0.5,
            frame_length=1024,
            slice_interval=600,
            disable_denoise=True,
            verbose=False,
        )
        
        assert "--disable-denoise" in cmd
        assert "--verbose" not in cmd
        assert "auto" in cmd

    def test_build_command_structure(self):
        """Test that command has correct structure."""
        detections_dir = Path("/tmp/test")
        cmd = build_live_command(
            detections_dir=detections_dir,
            backend="pvrecorder",
            device_index=1,
            min_confidence=0.7,
            frame_length=256,
            slice_interval=150,
            disable_denoise=False,
            verbose=True,
        )
        
        assert isinstance(cmd, list)
        assert len(cmd) > 10
        assert "live" in cmd
        assert "--detections-dir" in cmd
        assert str(detections_dir) in cmd
        assert "--frame-length" in cmd
        assert "256" in cmd
        assert "--slice-interval" in cmd
        assert "150" in cmd


class TestLiveProcessState:
    """Test LiveProcessState initialization."""

    def test_live_process_state_initial(self):
        """Test initial state of LIVE_PROCESS."""
        # Reset the global state
        LIVE_PROCESS.process = None
        LIVE_PROCESS.log_path = None
        LIVE_PROCESS.detections_dir = None
        LIVE_PROCESS.started_at = None
        LIVE_PROCESS.command_line = None
        LIVE_PROCESS.log_handle = None
        
        assert LIVE_PROCESS.process is None
        assert LIVE_PROCESS.log_path is None
        assert LIVE_PROCESS.detections_dir is None

    def test_live_process_state_dataclass(self):
        """Test creating a new LiveProcessState."""
        new_state = LiveProcessState()
        assert new_state.process is None
        assert new_state.log_path is None
        assert new_state.detections_dir is None
        assert new_state.started_at is None


class TestLiveStatus:
    """Test live_status function."""

    def setup_method(self):
        """Reset LIVE_PROCESS before each test."""
        LIVE_PROCESS.process = None
        LIVE_PROCESS.log_path = None
        LIVE_PROCESS.detections_dir = None
        LIVE_PROCESS.started_at = None
        LIVE_PROCESS.command_line = None

    def test_status_when_not_running(self):
        """Test status when no process is running."""
        status = live_status()
        
        assert isinstance(status, dict)
        assert status["running"] is False
        assert status["pid"] is None
        assert status["log_path"] is None
        assert status["started_at"] is None

    def test_status_when_running(self):
        """Test status when process is running."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.return_value = None  # Process is still running
        mock_process.pid = 12345
        
        LIVE_PROCESS.process = mock_process
        LIVE_PROCESS.log_path = Path("/tmp/bird.log")
        LIVE_PROCESS.started_at = "2026-04-07T10:30:00"
        LIVE_PROCESS.command_line = "python bird_audio_cli.py live"
        LIVE_PROCESS.detections_dir = Path("/tmp/detections")
        
        status = live_status()
        
        assert status["running"] is True
        assert status["pid"] == 12345
        assert status["log_path"] == "/tmp/bird.log"
        assert status["started_at"] == "2026-04-07T10:30:00"
        assert status["command_line"] == "python bird_audio_cli.py live"

    def test_status_when_process_terminated(self):
        """Test status when process has terminated."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.return_value = 0  # Process has terminated
        
        LIVE_PROCESS.process = mock_process
        LIVE_PROCESS.log_path = Path("/tmp/bird.log")
        
        status = live_status()
        
        assert status["running"] is False


class TestStartLiveProcess:
    """Test starting the live process."""

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
    def test_start_process_success(self, mock_popen, mock_cli_path):
        """Test successfully starting the live process."""
        mock_cli_path.exists.return_value = True
        # Create a proper mock Path
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        mock_process = MagicMock()
        mock_process.pid = 54321
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            result = start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=17,
                min_confidence=0.1,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
        
        assert result["message"] == "Bird Audio Live avviato."
        assert LIVE_PROCESS.process is not None
        assert LIVE_PROCESS.log_path is not None
        assert LIVE_PROCESS.detections_dir is not None
        assert LIVE_PROCESS.started_at is not None

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    def test_start_process_missing_cli(self, mock_cli_path):
        """Test starting when CLI is missing."""
        mock_cli_path.exists.return_value = False
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            with pytest.raises(FileNotFoundError):
                start_live_process(
                    detections_dir=detections_dir,
                    backend="sounddevice",
                    device_index=0,
                    min_confidence=0.1,
                    frame_length=512,
                    slice_interval=300,
                    disable_denoise=False,
                    verbose=True,
                )

    @patch('media_tools.services.audio_live_service.BIRD_AUDIO_CLI')
    @patch('subprocess.Popen')
    def test_start_process_already_running(self, mock_popen, mock_cli_path):
        """Test starting when process is already running."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        # Set up already running process
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 11111
        LIVE_PROCESS.process = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            result = start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=0,
                min_confidence=0.1,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
        
        assert result["message"] == "Bird Audio Live e' gia attivo."
        assert not mock_popen.called


class TestStopLiveProcess:
    """Test stopping the live process."""

    def setup_method(self):
        """Reset LIVE_PROCESS before each test."""
        LIVE_PROCESS.process = None
        LIVE_PROCESS.log_path = None
        LIVE_PROCESS.detections_dir = None
        LIVE_PROCESS.started_at = None
        LIVE_PROCESS.command_line = None
        LIVE_PROCESS.log_handle = None

    def test_stop_process_when_not_running(self):
        """Test stopping when no process is running."""
        result = stop_live_process()
        
        assert result["message"] == "Bird Audio Live non e' attivo."
        assert result["running"] is False

    def test_stop_process_when_running(self):
        """Test stopping when process is running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 99999
        
        mock_handle = MagicMock()
        
        LIVE_PROCESS.process = mock_process
        LIVE_PROCESS.log_handle = mock_handle
        LIVE_PROCESS.log_path = Path("/tmp/bird.log")
        
        result = stop_live_process()
        
        assert result["message"] == "Bird Audio Live fermato."
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()
        mock_handle.close.assert_called_once()

    def test_stop_process_timeout(self):
        """Test stopping process with timeout."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 99999
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", timeout=5),
            None,
        ]
        
        LIVE_PROCESS.process = mock_process
        LIVE_PROCESS.log_handle = None
        
        result = stop_live_process()
        
        assert result["message"] == "Bird Audio Live fermato."
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()


class TestBirdLiveIntegration:
    """Integration tests for bird live workflow."""

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
    def test_full_workflow(self, mock_popen, mock_cli_path):
        """Test complete workflow: status -> start -> status -> stop -> status."""
        mock_cli_path.exists.return_value = True
        mock_parent = MagicMock()
        mock_parent.parent = Path("/fake")
        mock_cli_path.parent = mock_parent
        
        # Initial status
        status = live_status()
        assert status["running"] is False
        
        # Start process
        mock_process = MagicMock()
        mock_process.pid = 11111
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        with tempfile.TemporaryDirectory() as tmpdir:
            detections_dir = Path(tmpdir)
            
            result = start_live_process(
                detections_dir=detections_dir,
                backend="sounddevice",
                device_index=17,
                min_confidence=0.1,
                frame_length=512,
                slice_interval=300,
                disable_denoise=False,
                verbose=True,
            )
            assert result["message"] == "Bird Audio Live avviato."
            
            # Status while running
            status = live_status()
            assert status["running"] is True
            assert status["pid"] == 11111
            
            # Stop process
            result = stop_live_process()
            assert result["message"] == "Bird Audio Live fermato."
            
            # Final status
            status = live_status()
            assert status["running"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
