"""主選單按鈕與繪圖。"""
import cv2
from config import COLOR_YELLOW

class InteractiveTile:
    """主選單按鈕"""

    def __init__(
        self, title, x1, y1, x2, y2,
        color, hover_color, url
    ):
        self.title = title
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self.hover_color = hover_color
        self.url = url

        self.is_hovered = False
        self.is_clicked = False
        self.hover_start_time = None

    def update_state(self, cx, cy, now):
        inside = (
            cx is not None
            and cy is not None
            and self.x1 <= cx <= self.x2
            and self.y1 <= cy <= self.y2
        )

        if inside:
            if not self.is_hovered:
                self.is_hovered = True
                self.hover_start_time = now
        else:
            self.is_hovered = False
            self.hover_start_time = None
            self.is_clicked = False

        return self.is_hovered

    def draw(self, img, now):
        if self.is_clicked:
            cur_color = (0, 200, 0)
        elif self.is_hovered:
            cur_color = self.hover_color
        else:
            cur_color = self.color

        cv2.rectangle(
            img,
            (self.x1, self.y1),
            (self.x2, self.y2),
            cur_color,
            -1
        )

        if self.is_hovered or self.is_clicked:
            cv2.rectangle(
                img,
                (self.x1 - 4, self.y1 - 4),
                (self.x2 + 4, self.y2 + 4),
                (255, 255, 255),
                5
            )

            if self.hover_start_time:
                progress = min(
                    1.0,
                    (now - self.hover_start_time) / 1.0
                )
                bar_w = int(
                    (self.x2 - self.x1) * progress
                )

                cv2.rectangle(
                    img,
                    (self.x1, self.y2 - 6),
                    (self.x1 + bar_w, self.y2),
                    (0, 255, 0),
                    -1
                )

        # 按鈕文字延後到螢幕原生解析度繪製，避免放大模糊。


def draw_menu_text_hd(image, tiles, source_w, source_h):
    """主選單文字在目前桌面輸出解析度上重新繪製。"""
    sx = image.shape[1] / source_w
    sy = image.shape[0] / source_h
    scale = min(sx, sy)
    thickness = max(2, round(2 * scale))

    cv2.putText(image, "TV LAUNCHER",
                (round(40 * sx), round(50 * sy)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8 * scale,
                (200, 200, 200), thickness, cv2.LINE_AA)

    for tile in tiles:
        label = "LOADING..." if tile.is_clicked else tile.title
        cv2.putText(image, label,
                    (round((tile.x1 + 18) * sx),
                     round((tile.y1 + (tile.y2 - tile.y1) / 2 + 10) * sy)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75 * scale,
                    (255, 255, 255), thickness, cv2.LINE_AA)

    cv2.putText(image, "Hover or Pinch to Select",
                (round(40 * sx), round(320 * sy)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6 * scale,
                COLOR_YELLOW, thickness, cv2.LINE_AA)



