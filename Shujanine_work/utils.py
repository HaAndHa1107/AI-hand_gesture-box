import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def get_dist(p1, p2):
    """計算兩點之間的距離"""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def draw_chinese_text(frame, text, position, font_path="wqy-zenhei.ttc", font_size=40, color=(255, 255, 0)):
    """使用 PIL 在 OpenCV 畫面上繪製支援中文的文字"""
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)

    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        font = ImageFont.load_default()

    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.asarray(img_pil), cv2.COLOR_RGB2BGR)
