import Jetson.GPIO as GPIO
import time

# 定義腳位 (對照你接在 A1 的 Pin 33)
#
IR_RECEIVER_PIN = 33

def setup():
    # 使用實體針腳編號模式
    GPIO.setmode(GPIO.BOARD)
    # 設定為輸入模式
    GPIO.setup(IR_RECEIVER_PIN, GPIO.IN)
    print("紅外線接收測試開始... 請對著接收頭按遙控器")

def loop():
    last_state = GPIO.input(IR_RECEIVER_PIN)
    try:
        while True:
            current_state = GPIO.input(IR_RECEIVER_PIN)
            # 當電位發生改變時（代表收到紅外線脈衝）
            if current_state != last_state:
                print(f"偵測到訊號變化！時間: {time.time()}")
                last_state = current_state
            time.sleep(0.0001) # 微小延遲避免過度佔用 CPU
    except KeyboardInterrupt:
        print("停止測試")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    setup()
    loop()
