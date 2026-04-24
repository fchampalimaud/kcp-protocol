from __future__ import annotations

import serial


class KCPProtocolError(RuntimeError):
    pass


class KCPTransport:
    def __init__(self, port: str):
        self._port = port

        self._ser: serial.Serial | None = None

    def open(self) -> None:
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(
            port=self._port,
            baudrate=115200,
            timeout=0.5,
            write_timeout=0.5,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self) -> "KCPTransport":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def query_line(self, command: str) -> str:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port is not open")

        payload = command.rstrip("\r\n").encode("ascii") + b"\r\n"
        self._ser.reset_input_buffer()
        self._ser.write(payload)
        self._ser.flush()

        raw = self._ser.read_until(b"\n")
        if not raw:
            raise TimeoutError(f"No response for command {command!r}")

        try:
            return raw.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise KCPProtocolError("Device returned non-ASCII data") from exc
