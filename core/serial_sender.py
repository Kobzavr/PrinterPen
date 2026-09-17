"""
serial_sender.py — Sends G-code commands to 3D printer via USB Serial.

Implements Marlin handshake protocol: send line -> wait for "ok".
Supports pause, soft stop with safe pen lift and bed ejection.
"""
from __future__ import annotations
from typing import List, Optional, Callable
import threading
import time
import re

import serial
import serial.tools.list_ports


def _strip_comment(line: str) -> str:
    """
    Strips comments (';' and anything after) from G-code lines.
    Returns clean ASCII command without trailing spaces.
    Returns empty string if line has no active command.
    """
    idx = line.find(";")
    if idx >= 0:
        line = line[:idx]
    return line.strip()


def list_ports() -> List[str]:
    """Returns a list of available COM port identifiers."""
    ports = serial.tools.list_ports.comports()
    return [p.device for p in sorted(ports)]


def find_printer_port() -> Optional[str]:
    """
    Attempts to discover 3D printer COM port automatically.
    Searches by STM32 VID/PID or typical driver descriptions.
    """
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        if any(kw in desc for kw in ["stm32", "marlin", "usb serial", "3d printer"]):
            return p.device
        if p.vid == 0x0483:  # STMicroelectronics VID
            return p.device
    return None


class SerialSender:
    """
    Sends G-code to printer over Serial with 'ok' handshake.
    """

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
        self._paused = False
        self._stop_flag = False
        self._z_up_on_stop = 4.0
        self._feed_on_stop = 3000.0
        self._lock = threading.Lock()

    def connect(self, timeout: float = 5.0) -> bool:
        """Opens Serial connection. Returns True on success."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=timeout,
                write_timeout=timeout,
            )
            time.sleep(2.0)  # Wait for Marlin boot sequence
            self._serial.reset_input_buffer()
            return True
        except serial.SerialException as e:
            self._serial = None
            err_str = str(e)
            if "PermissionError" in err_str or "Отказано в доступе" in err_str or "Access is denied" in err_str:
                raise ConnectionError(
                    f"Port {self.port} is busy or access is denied (PermissionError).\n"
                    f"Another application (e.g. UltiMaker Cura, PrusaSlicer, Arduino IDE) is currently holding {self.port}.\n"
                    f"Please close Cura or other software connected to the printer, then try again."
                )
            raise ConnectionError(f"Could not connect to {self.port}: {e}")

    def disconnect(self):
        """Closes the serial connection safely."""
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception:
                pass
            finally:
                self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def send_gcode(
        self,
        lines: List[str],
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[bool], None]] = None,
    ):
        """Sends G-code lines in a background thread."""
        self._paused = False
        self._stop_flag = False

        thread = threading.Thread(
            target=self._send_thread,
            args=(lines, on_progress, on_log, on_finished),
            daemon=True,
        )
        thread.start()

    def pause(self):
        """Pauses execution."""
        self._paused = True

    def resume(self):
        """Resumes execution."""
        self._paused = False

    def stop(self, z_up: float = 4.0, feed: float = 3000.0):
        """
        Soft stop: sets stop flag.
        The current move completes, then pen lifts and bed ejects.
        M112 is avoided to prevent board freeze.
        """
        self._stop_flag = True
        self._z_up_on_stop = z_up
        self._feed_on_stop = feed

    def send_command(self, cmd: str, wait_ok: bool = True) -> str:
        """Sends a single G-code command and returns response."""
        if not self.is_connected:
            raise ConnectionError("No printer connected")

        clean = _strip_comment(cmd)
        if not clean:
            return "ok"

        with self._lock:
            line = clean + "\n"
            self._serial.write(line.encode("ascii"))
            self._serial.flush()

            if wait_ok:
                return self._wait_for_ok()
        return ""

    def _send_thread(
        self,
        lines: List[str],
        on_progress,
        on_log,
        on_finished,
    ):
        """Worker thread for serial execution."""
        commands = []
        for line in lines:
            clean = _strip_comment(line)
            if clean:
                commands.append(clean)

        total = len(commands)
        success = True

        try:
            for i, cmd in enumerate(commands):
                # Pause handling
                while self._paused and not self._stop_flag:
                    time.sleep(0.1)

                # Stop handling
                if self._stop_flag:
                    if on_log:
                        on_log("⏹ Stopping... lifting pen and parking bed")
                    try:
                        f = self._feed_on_stop
                        self.send_command(f"G0 Z{self._z_up_on_stop:.2f} F{f:.0f}", wait_ok=False)
                        self.send_command(f"G0 X0 F{f:.0f}", wait_ok=False)
                        self.send_command(f"G0 Y200 F{f:.0f}", wait_ok=False)
                    except Exception:
                        pass
                    if on_log:
                        on_log("⏹ Stopped by user.")
                    success = False
                    break

                # Send command
                try:
                    response = self.send_command(cmd, wait_ok=True)
                    if on_log:
                        on_log(f"[{i+1}/{total}] {cmd}  ->  {response.strip()}")
                    if on_progress:
                        on_progress(i + 1, total)
                except Exception as e:
                    if on_log:
                        on_log(f"❌ Error sending '{cmd}': {e}")
                    success = False
                    break

        except Exception as e:
            if on_log:
                on_log(f"❌ Critical error: {e}")
            success = False
        finally:
            if on_finished:
                on_finished(success)

    def _wait_for_ok(self, timeout: float = 30.0) -> str:
        """Waits for Marlin 'ok' handshake response."""
        if not self.is_connected:
            return ""

        deadline = time.time() + timeout
        buffer = ""

        while time.time() < deadline:
            if self._serial.in_waiting:
                chunk = self._serial.read(self._serial.in_waiting).decode("ascii", errors="ignore")
                buffer += chunk

                if re.search(r"\bok\b", buffer, re.IGNORECASE):
                    return buffer

                if "error" in buffer.lower():
                    return buffer
            else:
                time.sleep(0.001)

        return buffer
