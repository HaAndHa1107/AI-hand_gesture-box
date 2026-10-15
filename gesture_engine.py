from utils import get_dist


def analyze_hand_gestures(lm, base):
    """
    大腦引擎：計算所有手指的角度與距離，將結果打包成字典回傳。
    """
    # 1. 基礎手指伸直判定
    is_index_up = get_dist(lm[8], lm[0]) > get_dist(lm[6], lm[0])
    is_middle_up = get_dist(lm[12], lm[0]) > get_dist(lm[10], lm[0])
    is_ring_up = get_dist(lm[16], lm[0]) > get_dist(lm[14], lm[0])
    is_pinky_up = get_dist(lm[20], lm[0]) > get_dist(lm[18], lm[0])

    is_thumb_up = get_dist(lm[4], lm[5]) > base * 0.6

    # 2. 關鍵距離量測
    dist_thumb_index = get_dist(lm[4], lm[8])

    # 3. 手勢判斷
    # OK 手勢：拇指食指相接，且中指明顯抬起
    is_ok = (dist_thumb_index < base * 0.3) and is_middle_up

    # 滑鼠左鍵點擊：
    # 食指彎曲（指尖到手腕距離縮短），拇指與食指分開保持距離（杜絕 OK 誤判），且並非比 OK
    index_finger_bent = get_dist(lm[8], lm[0]) < get_dist(lm[6], lm[0]) * 0.95
    is_mouse_left_click = index_finger_bent and (dist_thumb_index > base * 0.45) and not is_ok

    is_palm = (
        is_index_up and is_middle_up and is_ring_up and is_pinky_up and is_thumb_up
        and (get_dist(lm[8], lm[20]) > base * 1.0)
    )

    is_fist = (
        not is_index_up and not is_middle_up and not is_ring_up
        and not is_pinky_up and not is_thumb_up
    )

    is_together = get_dist(lm[8], lm[12]) < base * 0.4
    is_eraser = (
        is_index_up and is_middle_up and is_ring_up and is_pinky_up
        and (get_dist(lm[8], lm[20]) < base * 1.5)
    )
    is_backspace = is_pinky_up and not is_index_up and not is_middle_up and not is_ring_up
    is_three_up = is_index_up and is_middle_up and is_ring_up and not is_pinky_up

    is_mode_switch = (
        is_thumb_up and not is_index_up and not is_middle_up
        and not is_ring_up and not is_pinky_up
    )
    is_lock_sign = (
        is_thumb_up and is_pinky_up and not is_index_up
        and not is_middle_up and not is_ring_up
    )

    return {
        "index_up": is_index_up,
        "middle_up": is_middle_up,
        "together": is_together,
        "thumb_up": is_thumb_up,
        "ok": is_ok,
        "eraser": is_eraser,
        "backspace": is_backspace,
        "three_up": is_three_up,
        "mode_switch": is_mode_switch,
        "lock_sign": is_lock_sign,
        "palm": is_palm,
        "fist": is_fist,
        "mouse_click": is_mouse_left_click
    }
