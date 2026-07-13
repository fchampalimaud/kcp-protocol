from __future__ import annotations

from dataclasses import dataclass
import shlex
from typing import Protocol, Self


class KCPTransport(Protocol):
    # send a command
    def send(self, command_line: str) -> None: ...
    # request a single line
    def request_line(self, command_line: str) -> str: ...
    # for SIR and similar multi-line commands, which return a block of lines
    def request_lines(self, command_line: str) -> list[str]: ...
    # These are used for the context manager in KCPDevice
    def open(self) -> None: ...
    def close(self) -> None: ...
    # This will be used for the SIR streaming command, which requires a special cancel sequence.
    # The transport must allow reading lines directly in this mode.
    def read_line(self, timeout: float | None = None) -> str: ...


class KCPProtocolError(RuntimeError):
    pass


class KCPSyntaxError(KCPProtocolError):
    pass


class KCPLogicalError(KCPProtocolError):
    pass


class KCPBusyError(KCPProtocolError):
    pass


class KCPUnexpectedReply(KCPProtocolError):
    pass


@dataclass(frozen=True)
class KCPFrame:
    command: str
    code: str
    fields: tuple[str, ...]
    raw: str

    @property
    def is_terminal(self) -> bool:
        return self.code in {"A", "I", "L"}

    @property
    def is_intermediate(self) -> bool:
        return self.code == "B"

    @property
    def is_error(self) -> bool:
        return self.code in {"I", "L"}


@dataclass(frozen=True)
class KCPImplementedCommand:
    level: int
    name: str


@dataclass(frozen=True)
class KCPVersionInfo:
    levels: str
    versions: tuple[str, ...]


def parse_kcp_line(raw: str) -> KCPFrame:
    text = raw.rstrip("\r\n")
    if text == "ES":
        raise KCPSyntaxError("Erroneous syntax or unknown command")

    parts = shlex.split(text)
    if len(parts) < 2:
        raise KCPUnexpectedReply(f"Malformed KCP reply: {text!r}")

    return KCPFrame(
        command=parts[0],
        code=parts[1],
        fields=tuple(parts[2:]),
        raw=text,
    )


def quote_arg(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(ch.isspace() for ch in text) or '"' in text:
        return '"' + text.replace('"', '\\"') + '"'
    return text


class KCPDevice:
    """
    Generic KCP level-0 device interface.

    This class exposes protocol-level primitives plus the universal
    Device-category commands from the KCP manual.
    """

    def __init__(self, transport: KCPTransport):
        self._transport = transport
        self._implemented_commands: dict[str, KCPImplementedCommand] = {}
        self._categories: tuple[str, ...] = ()
        self._versions: KCPVersionInfo | None = None

    def open(self) -> None:
        self._transport.open()

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _raise_for_error(frame: KCPFrame) -> KCPFrame:
        if frame.code == "L":
            raise KCPLogicalError(frame.raw)
        if frame.code == "I":
            raise KCPBusyError(frame.raw)
        return frame

    @staticmethod
    def _format(command: str, *args: object) -> str:
        parts = [command]
        parts.extend(quote_arg(arg) for arg in args)
        return " ".join(parts)

    def _read_frame(self) -> KCPFrame:
        frame = parse_kcp_line(self._transport.read_line())
        return self._raise_for_error(frame)

    def _request_raw_line(self, command: str, *args: object) -> str:
        return self._transport.request_line(self._format(command, *args))

    def _read_raw_line(self, timeout: float | None = None) -> str:
        return self._transport.read_line(timeout=timeout)

    def _request_single(self, command: str, *args: object) -> KCPFrame:
        raw = self._transport.request_line(self._format(command, *args))
        frame = parse_kcp_line(raw)
        return self._raise_for_error(frame)

    def _request_list(self, command: str, *args: object) -> list[KCPFrame]:
        raw_lines = self._transport.request_lines(self._format(command, *args))
        frames = [parse_kcp_line(line) for line in raw_lines]
        if not frames:
            raise KCPUnexpectedReply(f"{command} returned no data")

        for frame in frames:
            if frame.command != command:
                raise KCPUnexpectedReply(
                    f"{command} returned foreign line: {frame.raw!r}"
                )
            if frame.code not in {"A", "B", "I", "L"}:
                raise KCPUnexpectedReply(
                    f"{command} returned unexpected continuation code: {frame.raw!r}"
                )

        last = frames[-1]
        if last.code == "L":
            raise KCPLogicalError(last.raw)
        if last.code == "I":
            raise KCPBusyError(last.raw)
        if last.code != "A":
            raise KCPUnexpectedReply(f"{command} did not terminate with final A frame")

        return frames

    def _send_no_reply(self, command: str, *args: object) -> None:
        self._transport.send(self._format(command, *args))

    def supports(self, command: str) -> bool:
        return command in self._implemented_commands

    def require_support(self, *commands: str) -> None:
        missing = [
            command for command in commands if command not in self._implemented_commands
        ]
        if missing:
            raise NotImplementedError(
                f"Device does not advertise support for: {', '.join(missing)}"
            )

    def refresh_supported_commands(self) -> tuple[KCPImplementedCommand, ...]:
        frames = self._request_list("I0")
        commands: list[KCPImplementedCommand] = []

        for frame in frames:
            if len(frame.fields) != 2:
                raise KCPUnexpectedReply(f"Invalid I0 frame: {frame.raw!r}")
            level_text, command_name = frame.fields
            commands.append(
                KCPImplementedCommand(level=int(level_text), name=command_name)
            )

        self._implemented_commands = {item.name: item for item in commands}
        return tuple(commands)

    def refresh_categories(self) -> tuple[str, ...]:
        frames = self._request_list("KCPC")
        categories: list[str] = []

        for frame in frames:
            if len(frame.fields) != 1:
                raise KCPUnexpectedReply(f"Invalid KCPC frame: {frame.raw!r}")
            categories.append(frame.fields[0])

        self._categories = tuple(categories)
        return self._categories

    def refresh_versions(self) -> KCPVersionInfo:
        frame = self._request_single("I1")
        if frame.command != "I1" or frame.code != "A" or len(frame.fields) < 2:
            raise KCPUnexpectedReply(f"Invalid I1 frame: {frame.raw!r}")

        self._versions = KCPVersionInfo(
            levels=frame.fields[0],
            versions=tuple(frame.fields[1:]),
        )
        return self._versions

    def cancel(self) -> str:
        """
        Reset volatile device state. According to the KCP manual, the reply might be
        an unsolicited-style I4 line containing the serial number.
        """
        frame = self._request_single("@")
        if frame.command != "I4" or frame.code != "A" or len(frame.fields) != 1:
            raise KCPUnexpectedReply(f"Invalid @ reply: {frame.raw!r}")
        return frame.fields[0]

    def get_device_information(self) -> str:
        """
        I2 is intentionally exposed as an opaque string because the manual states so.
        """
        frame = self._request_single("I2")
        if (
            frame.command not in {"I2", "IBMT"}
            or frame.code != "A"
            or len(frame.fields) != 1
        ):
            raise KCPUnexpectedReply(f"Invalid I2/IBMT reply: {frame.raw!r}")
        return frame.fields[0]

    def get_software_version_fields(self) -> tuple[str, ...]:
        frame = self._request_single("I3")
        if frame.command != "I3" or frame.code != "A" or not frame.fields:
            raise KCPUnexpectedReply(f"Invalid I3 reply: {frame.raw!r}")
        return frame.fields

    def get_serial_number(self) -> str:
        frame = self._request_single("I4")
        if (
            frame.command not in {"I4", "IBIS"}
            or frame.code != "A"
            or len(frame.fields) != 1
        ):
            raise KCPUnexpectedReply(f"Invalid I4/IBIS reply: {frame.raw!r}")
        return frame.fields[0]

    def get_software_identification_fields(self) -> tuple[str, ...]:
        frame = self._request_single("I5")
        if frame.command != "I5" or frame.code != "A" or not frame.fields:
            raise KCPUnexpectedReply(f"Invalid I5 reply: {frame.raw!r}")
        return frame.fields
