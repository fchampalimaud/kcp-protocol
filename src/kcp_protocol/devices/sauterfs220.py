from collections.abc import Generator
from dataclasses import dataclass
from typing import Literal

from kcp_protocol.device import (
    KCPDevice,
    KCPTransport,
    KCPUnexpectedReply,
)
from kcp_protocol.transport import KCPSerialTransport, KCPTimeoutError


@dataclass(frozen=True)
class Measurement:
    value: float
    unit: Literal["g", "N"]


class SauterFS220(KCPDevice):
    REQUIRED_COMMANDS = frozenset(
        {"I0", "I2", "I4", "I5", "SI", "SIR", "ZI", "@", "IBBS"}
    )

    def __init__(
        self,
        port: str | None = None,
        *,
        transport: KCPTransport | None = None,
    ) -> None:
        if (port is None) == (transport is None):
            raise ValueError("Specify exactly one of port or transport")

        if port is not None:
            super().__init__(KCPSerialTransport(port))
        elif transport is not None:
            super().__init__(transport)

        self._sir_active = False

    def open(self) -> None:
        super().open()
        self.initialize()

    def close(self) -> None:
        try:
            self.stop_stream()
        finally:
            super().close()

    def initialize(self) -> None:
        self.refresh_supported_commands()
        self.require_support(*self.REQUIRED_COMMANDS)

    @staticmethod
    def _parse_measurement(raw: str) -> Measurement:
        parts = raw.split()
        if len(parts) < 4 or parts[0] != "S":
            raise KCPUnexpectedReply(f"Invalid measurement reply: {raw!r}")

        unit = parts[-1]
        if unit not in {"g", "N"}:
            raise KCPUnexpectedReply(f"Unsupported measurement unit: {raw!r}")

        value_text = parts[-2]
        if len(parts) >= 5 and parts[-3] in {"+", "-"}:
            value_text = parts[-3] + value_text

        try:
            value = float(value_text)
        except ValueError as exc:
            raise KCPUnexpectedReply(f"Invalid measurement value: {raw!r}") from exc

        return Measurement(value=value, unit=unit)

    def read_value(self) -> float:
        return self.read_measurement().value

    def read_measurement(self) -> Measurement:
        self.require_support("SI")
        raw = self._request_raw_line("SI")
        return self._parse_measurement(raw)

    def stream_values(
        self,
        *,
        interval_ms: int | None = None,
    ) -> Generator[float, None, None]:
        for measurement in self.stream_measurements(interval_ms=interval_ms):
            yield measurement.value

    def stream_measurements(
        self,
        *,
        interval_ms: int | None = None,
    ) -> Generator[Measurement, None, None]:
        self._start_sir(interval_ms)

        try:
            while self._sir_active:
                raw = self._read_raw_line(timeout=self._sir_read_timeout(interval_ms))
                yield self._parse_measurement(raw)
        finally:
            self.stop_stream()

    def stop_stream(self) -> None:
        if not self._sir_active:
            return

        self._sir_active = False
        self._send_no_reply("@")
        self._drain_sir_shutdown()

    def _start_sir(self, interval_ms: int | None) -> None:
        if self._sir_active:
            raise RuntimeError("SIR stream is already active")

        self.require_support("SIR", "@")

        if interval_ms is None:
            self._send_no_reply("SIR")
        else:
            self._send_no_reply("SIR", interval_ms)

        self._sir_active = True

    @staticmethod
    def _sir_read_timeout(interval_ms: int | None) -> float:
        if interval_ms is None:
            return 2.0
        return max(2.0, interval_ms / 1000.0 + 1.0)

    def _drain_sir_shutdown(self) -> None:
        while True:
            try:
                raw = self._read_raw_line(timeout=0.2)
            except KCPTimeoutError:
                return

            if raw.split()[:1] == ["S"]:
                continue

            return

    def zero_immediately(self) -> None:
        self.require_support("ZI")
        self._send_no_reply("ZI")

    def get_battery_status(self) -> int | str:
        self.require_support("IBBS")
        raw_line = self._request_raw_line("IBBS")
        parts = raw_line.split()
        # return 3rd part, which is the battery status text as an integer
        # if not 5 parts or the 3rd part is not an integer, return the whole raw line for debugging
        if len(parts) != 5:
            return raw_line
        try:
            return int(parts[2])
        except ValueError:
            return raw_line
