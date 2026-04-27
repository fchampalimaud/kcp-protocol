from collections.abc import Generator
from kcp_protocol.device import (
    KCPDevice,
    KCPTransport,
    KCPUnexpectedReply,
)
from kcp_protocol.transport import KCPSerialTransport, KCPTimeoutError


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

    def open(self) -> None:
        super().open()
        self.initialize()

    def initialize(self) -> None:
        self.refresh_supported_commands()
        self.require_support(*self.REQUIRED_COMMANDS)

    @staticmethod
    def _is_immediate_value_raw_line(raw: str) -> bool:
        parts = raw.split()
        return len(parts) >= 4 and parts[0] == "S"

    def read_immediate_value_raw(self) -> str:
        self.require_support("SI")
        raw = self._request_raw_line("SI")
        if not self._is_immediate_value_raw_line(raw):
            raise KCPUnexpectedReply(f"Invalid SI reply: {raw!r}")
        return raw

    def stream_immediate_value_raw(
        self,
        interval_ms: int | None = None,
    ) -> Generator[str, None, None]:
        self.require_support("SIR", "@")

        if interval_ms is not None and interval_ms <= 0:
            raise ValueError("interval_ms must be a positive integer")

        if interval_ms is None:
            self._send_no_reply("SIR")
        else:
            self._send_no_reply("SIR", interval_ms)

        read_timeout = self._sir_read_timeout(interval_ms)

        try:
            while True:
                raw = self._read_raw_line(timeout=read_timeout)
                if not self._is_immediate_value_raw_line(raw):
                    raise KCPUnexpectedReply(f"Invalid SIR reply: {raw!r}")
                yield raw
        finally:
            self._send_no_reply("@")
            self._drain_sir_shutdown()

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

            if self._is_immediate_value_raw_line(raw):
                continue

            return

    def zero_immediately(self) -> None:
        self.require_support("ZI")
        self._send_no_reply("ZI")
