from __future__ import annotations
import time

from typing import Self

import serial


class KCPTransportError(RuntimeError):
    pass


class KCPTimeoutError(KCPTransportError):
    pass


class KCPEncodingError(KCPTransportError):
    pass


class KCPSerialTransport:
    def __init__(self, port: str):
        self._port = port
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        if self._ser and self._ser.is_open:
            return

        self._ser = serial.Serial(
            port=self._port,
            baudrate=115200,
            timeout=1,
            write_timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send(self, command_line: str) -> None:
        ser = self._require_open_serial()
        payload = self._encode_command(command_line)

        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()

    def read_line(self, timeout: float | None = None) -> str:
        line = self._read_optional_line(timeout=timeout)
        if line is None:
            raise KCPTimeoutError("Timed out waiting for device response")
        return line

    def _read_required_line(self, timeout: float | None = None) -> str:
        line = self._read_optional_line(timeout=timeout)
        if line is None:
            raise KCPTimeoutError("Timed out waiting for device response")
        return line

    def _read_optional_line(self, timeout: float | None = None) -> str | None:
        ser = self._require_open_serial()
        deadline = None if timeout is None else time.monotonic() + timeout
        raw = bytearray()

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                if raw:
                    raise KCPTimeoutError("Timed out waiting for line terminator")
                return None

            chunk = ser.read_until(b"\n")
            if chunk:
                raw.extend(chunk)
                if raw.endswith(b"\n"):
                    break
                continue

            if raw:
                raise KCPTimeoutError("Timed out waiting for line terminator")
            if deadline is None:
                return None

        try:
            text = raw.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise KCPEncodingError("Device returned non-ASCII data") from exc

        return text.rstrip("\r\n")

    def request_line(self, command_line: str) -> str:
        ser = self._require_open_serial()
        payload = self._encode_command(command_line)

        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()

        return self._read_required_line()

    def request_lines(self, command_line: str) -> list[str]:
        ser = self._require_open_serial()
        payload = self._encode_command(command_line)

        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()

        lines = [self._read_required_line(timeout=2.0)]

        while True:
            line = self._read_optional_line(timeout=0.1)
            if line is None:
                return lines
            lines.append(line)

    def _require_open_serial(self) -> serial.Serial:
        if self._ser is None or not self._ser.is_open:
            raise KCPTransportError("Serial port is not open")
        return self._ser

    @staticmethod
    def _encode_command(command_line: str) -> bytes:
        text = command_line.rstrip("\r\n")
        try:
            return text.encode("ascii", errors="strict") + b"\r\n"
        except UnicodeEncodeError as exc:
            raise KCPEncodingError(
                f"Command contains non-ASCII data: {command_line!r}"
            ) from exc
