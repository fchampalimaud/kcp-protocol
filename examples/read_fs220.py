import msvcrt
from kcp_protocol import SauterFS220


def main() -> None:

    with SauterFS220(port="COM3", stream_interval_ms=100) as device:
        try:
            for raw in device.stream_immediate_value_raw():
                print(raw)

                if msvcrt.kbhit():
                    _key = msvcrt.getch()
                    if _key.lower() == b"q":
                        print("\nStopping stream...")
                        device.stop_stream()
        except KeyboardInterrupt:
            print("\nStopping stream...")
            device.stop_stream()

        dev_info = device.get_device_information()
        print("Device information:")
        print(f"{dev_info}")


if __name__ == "__main__":
    main()
