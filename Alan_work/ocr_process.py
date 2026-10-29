import os
import cv2
import numpy as np


def ocr_worker(input_queue, output_queue):
    print(">>> [子進程] 🚀 啟動純微軟 ONNX Runtime 旗艦引擎...")
    
    # 模型與字典相對於本檔案，避免從其他工作目錄啟動時找不到資源。
    from pathlib import Path
    model_dir = Path(__file__).resolve().parent / "models"
    dict_path = model_dir / "ppocr_keys_v1.txt"
    onnx_path = model_dir / "ch_PP-OCRv4_rec_infer.onnx"
    onnx_ready = False
    char_list = []
    rec_session = None
    if dict_path.is_file() and onnx_path.is_file():
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            with dict_path.open("r", encoding="utf-8") as f:
                char_list = ["blank"] + [line.strip() for line in f] + [" "]
            rec_session = ort.InferenceSession(str(onnx_path), opts, providers=["CPUExecutionProvider"])
            onnx_ready = True
        except Exception as exc:
            print(">>> [OCR] ONNX 載入失敗，改用 Tesseract 備援:", exc)
    else:
        print(">>> [OCR] 模型或字典不存在，改用 Tesseract 備援")

    while True:
        data = input_queue.get()
        if data == b"EXIT" or data == "EXIT":
            break
        try:
            np_arr = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                output_queue.put("ERROR")
                continue

            detected_text = ""

            if onnx_ready:
                try:
                    h, w, _ = img.shape
                    target_h = 48
                    target_w = int(w * (target_h / h))
                    img_resized = cv2.resize(img, (target_w, target_h))
                    
                    img_data = img_resized.astype('float32') / 255.0
                    img_data = np.transpose(img_data, (2, 0, 1))
                    img_data = np.expand_dims(img_data, axis=0)

                    rec_inputs = {rec_session.get_inputs()[0].name: img_data}
                    preds = rec_session.run(None, rec_inputs)[0]
                    preds_idx = np.argmax(preds, axis=2)[0]
                    
                    last_idx = 0
                    for idx in preds_idx:
                        if idx > 0 and idx != last_idx and idx < len(char_list):
                            detected_text += char_list[idx]
                        last_idx = idx
                except Exception:
                    pass

            if not detected_text.strip():
                try:
                    import pytesseract
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    detected_text = pytesseract.image_to_string(gray, lang='chi_tra+eng', config='--psm 7').strip()
                except:
                    detected_text = ""

            output_queue.put(detected_text.strip().replace(" ", "").replace("\n", ""))

        except Exception:
            output_queue.put("ERROR")