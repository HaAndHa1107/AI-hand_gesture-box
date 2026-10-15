import sys
import select
import os

RX_DEVICE = "/dev/lirc1"  # 如果沒反應，請換成 /dev/lirc1


def get_permanent_code():
    print("【永久密碼擷取工具 - 修正版】")
    print("請拿電視遙控器對準接收頭，『按一下』電源鍵...")

    recorded_bytes = []
    start_record = False

    with open(RX_DEVICE, "rb") as rx:
        while True:
            r, _, _ = select.select([rx], [], [], 1.5)
            if r:
                raw_data = rx.read(4)
                if len(raw_data) == 4:
                    if not start_record:
                        start_record = True
                    recorded_bytes.append(raw_data)
            else:
                if start_record:
                    break

    print("\n🎉 錄製成功！請複製下方這一整行陣列：\n")

    # 用標準 format 避開 f-string 的反斜線限制
    hex_list = []
    for packet in recorded_bytes:
        hex_str = "".join("\\x{:02x}".format(b) for b in packet)
        hex_list.append(f"b'{hex_str}'")

    print("TV_POWER_SIGNAL = [")
    print("    " + ",\n    ".join(hex_list))
    print("]")
    print("\n=============================================")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("請使用 'sudo python3 get_hex_code.py'")
        sys.exit(1)
    get_permanent_code()
