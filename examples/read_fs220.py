import time
from contextlib import closing

from kcp_protocol import SauterFS220


def main() -> None:

    with (
        SauterFS220(port="COM3") as device,
        closing(device.stream_immediate_value_raw(interval_ms=1000)) as stream,
    ):
        try:
            for raw in stream:
                print(raw)
        except KeyboardInterrupt:
            print("\nStopping.")


if __name__ == "__main__":
    main()
