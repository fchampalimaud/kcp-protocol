# kcp-protocol

Python client for devices that use the KERN Communications Protocol (KCP), with current support focused on the Sauter FS2-20.

## Status

This project is in an early public release stage and currently targets a subset of KCP commands needed for the Sauter FS2-20 workflow.

## Features

- Serial communication over `pyserial`
- KCP frame parsing and command handling
- High-level `SauterFS220` device wrapper
- Immediate value reads
- Continuous streaming reads
- Device information and serial number queries
- Battery status query
- Zero command support

## Requirements

- Python 3.11 or newer
- A serial connection to a compatible KCP-enabled device
- For `SauterFS220`, a device that supports the required commands used during initialization and measurement

## Installation

Install from PyPI:

```bash
uv add kcp-protocol
# or
pip install kcp-protocol
```

## Quick Start

### Basic Usage

```python
from kcp_protocol import SauterFS220

# Initialize the device (replace with your serial port)
with SauterFS220(port="COM3") as device:
    # Device information
    print("Device Info:", device.get_device_information())

    # Serial number
    print("Serial Number:", device.get_serial_number())

    # Battery status
    print("Battery Status:", device.get_battery_status())

    # Read an immediate value
    value = device.read_value()
    print("Current value:", value)

    # Read a measurement
    measurement = device.read_measurement()
    print("Measurement:", measurement.value, measurement.unit)
```

### Streaming data

```python
from kcp_protocol import SauterFS220

with SauterFS220(port="COM3") as device:
    for value in device.stream_values(interval_ms=100):
        print(value)

        # or another stopping condition, e.g. based on user input or a timer
        if should_stop():
            device.stop_stream()

    # or in case you need a measurement stream:
    for measurement in device.stream_measurements(interval_ms=100):
        print(measurement.value, measurement.unit)

        if should_stop():
            device.stop_stream()
```

> [!NOTE]
> Stopping a stream does not close the device connection. You can continue to use the device for other commands after stopping a stream.
> 
> If you stop consuming the stream early, call `stop_stream()` explicitly so the device exits streaming mode cleanly.

### Advanced Transport Configuration

If you need to customize transport parameters (e.g. timeouts) or implement a custom transport, you can use `KCPSerialTransport` directly or subclass it.

```python
from kcp_protocol import KCPSerialTransport, SauterFS220

transport = KCPSerialTransport(
    "COM3",
    read_poll_timeout=0.1,
    write_timeout=1.0,
)

with SauterFS220(transport=transport) as device:
    print(device.read_value())
```

> [!NOTE]
> Use this advanced path only when you need custom transport behavior. For most use cases, the default `SauterFS220(port=...)` constructor is sufficient and the recommended usage.

## Public API

The main public entry points are:

- `SauterFS220` for the device-specific high-level interface
- `KCPSerialTransport` for serial transport access
- `KCPTransport` for custom or test transports

The main high-level methods on `SauterFS220` are:

- `read_value()`
- `read_measurement()`
- `stream_values(interval_ms: int | None = None)`
- `stream_measurements(interval_ms: int | None = None)`
- `stop_stream()`
- `get_device_information()`
- `get_serial_number()`
- `get_battery_status()`

## Example

A Windows interactive example is available in `examples/read_fs220.py`.

## Notes

- Supported parsed measurement units are currently `g` and `N`.
- `stop_stream()` is explicit so callers can stop streaming and continue using the same device connection.
- `get_battery_status()` currently returns either a parsed integer percentage or the raw line when parsing fails.

## Contributing

Contributions are welcome! Please open issues for bug reports or feature requests, and submit pull requests for any improvements or additions.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
