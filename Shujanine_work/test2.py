import Jetson.GPIO as GPIO
import time

# 腳位定義 (Pin 32 發射, Pin 33 接收)
TX_PIN = 32
RX_PIN = 33


def soft_pwm_38khz(duration_seconds):
    """
    手動切換 GPIO 產生約 38kHz 的方波
    38kHz 的週期約為 26 微秒 (13us High, 13us Low)
    """
    start_time = time.time()
    while (time.time() - start_time) < duration_seconds:
        GPIO.output(TX_PIN, GPIO.HIGH)
        time.sleep(0.000013)  # 13 微秒
        GPIO.output(TX_PIN, GPIO.LOW)
        time.sleep(0.000013)  # 13 微秒


def test_ir_pair():
    # 忽略載板不相符的警告
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)

    GPIO.setup(RX_PIN, GPIO.IN)
    GPIO.setup(TX_PIN, GPIO.OUT, initial=GPIO.LOW)

    print("--- 啟動軟體模擬 38kHz 對接測試 ---")
    print("請確保發射器與接收器互對...")

    try:
        while True:
            print("正在發射 38kHz 訊號...", end=" ", flush=True)
            # 發射 0.2 秒的模擬載波
            soft_pwm_38khz(0.2)

            # 讀取接收器（低電位代表收到訊號）
            if GPIO.input(RX_PIN) == GPIO.LOW:
                print(">>> [成功] 偵測到訊號！")
            else:
                print(">>> [失敗] 未收到。")

            time.sleep(1)  # 間隔一秒再測

    except KeyboardInterrupt:
        print("\n測試停止")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    test_ir_pair()
