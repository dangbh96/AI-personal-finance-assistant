"""Sinh 5 ảnh hoá đơn **tổng hợp** cho golden test Receipt OCR (Phase 13).

Cửa hàng, địa chỉ, số tiền đều là dữ liệu giả — không dùng ảnh có bản quyền hay dữ liệu cá nhân
thật. Ảnh đã sinh được commit cùng file expected `*.yaml`; chỉ cần chạy lại khi muốn đổi mẫu:

    (cd backend && python tests/ai_golden/receipts/generate_receipts.py)

Cần Pillow + font hệ thống có dấu tiếng Việt (mặc định font Windows: Courier New, Arial,
Consolas, Ink Free); đặt biến môi trường `RECEIPT_FONT_DIR` nếu font nằm chỗ khác.
"""

import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path(__file__).parent
FONT_DIR = Path(os.environ.get("RECEIPT_FONT_DIR", r"C:\Windows\Fonts"))
PAPER = (250, 248, 240)
DESK = (120, 110, 100)
INK = (30, 30, 30)
WIDTH = 760


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


class Receipt:
    """Vẽ hoá đơn in nhiệt (thermal) từ trên xuống."""

    def __init__(self, height: int, regular: str = "cour.ttf", bold: str = "courbd.ttf") -> None:
        self.image = Image.new("RGB", (WIDTH, height), PAPER)
        self.draw = ImageDraw.Draw(self.image)
        self.regular = font(regular, 26)
        self.bold = font(bold, 28)
        self.title = font(bold, 38)
        self.y = 40

    def center(self, text: str, f: ImageFont.FreeTypeFont | None = None, gap: int = 10) -> None:
        f = f or self.regular
        width = self.draw.textlength(text, font=f)
        self.draw.text(((WIDTH - width) / 2, self.y), text, font=f, fill=INK)
        self.y += int(f.size) + gap

    def left_right(self, left: str, right: str, f: ImageFont.FreeTypeFont | None = None) -> None:
        f = f or self.regular
        self.draw.text((40, self.y), left, font=f, fill=INK)
        width = self.draw.textlength(right, font=f)
        self.draw.text((WIDTH - 40 - width, self.y), right, font=f, fill=INK)
        self.y += int(f.size) + 10

    def text(self, text: str, f: ImageFont.FreeTypeFont | None = None) -> None:
        f = f or self.regular
        self.draw.text((40, self.y), text, font=f, fill=INK)
        self.y += int(f.size) + 10

    def rule(self) -> None:
        self.draw.line([(40, self.y + 14), (WIDTH - 40, self.y + 14)], fill=INK, width=2)
        self.y += 36

    def item(self, name: str, qty: int, price: int) -> None:
        self.text(name)
        self.left_right(f"   {qty} x {vnd(price)}", vnd(qty * price))

    def finish(self) -> Image.Image:
        return self.image.crop((0, 0, WIDTH, self.y + 40))


def as_photo(receipt: Image.Image, angle: float, seed: int) -> Image.Image:
    """Đặt hoá đơn lên nền bàn, xoay nhẹ, thêm nhiễu — giống ảnh chụp điện thoại."""
    rng = random.Random(seed)
    margin = 90
    rotated = receipt.rotate(angle, expand=True, fillcolor=DESK)
    photo = Image.new("RGB", (rotated.width + 2 * margin, rotated.height + 2 * margin), DESK)
    photo.paste(rotated, (margin, margin))
    pixels = photo.load()
    for _ in range(photo.width * photo.height // 40):
        x, y = rng.randrange(photo.width), rng.randrange(photo.height)
        r, g, b = pixels[x, y]
        d = rng.randint(-18, 18)
        pixels[x, y] = tuple(max(0, min(255, c + d)) for c in (r, g, b))
    return photo.filter(ImageFilter.GaussianBlur(0.6))


def supermarket() -> Image.Image:
    r = Receipt(1500)
    r.center("SIÊU THỊ XANH MART", r.title)
    r.center("12 Đường Số 7, P. An Phú, TP. Thủ Đức")
    r.center("ĐT: 028 0000 1234")
    r.center("HOÁ ĐƠN BÁN LẺ", r.bold, gap=20)
    r.text("Ngày: 05/10/2026   Giờ: 18:42")
    r.text("Số HĐ: XM-000318   Quầy: 03")
    r.rule()
    r.item("Gạo ST25 túi 5kg", 1, 185000)
    r.item("Sữa tươi không đường 1L", 2, 32000)
    r.item("Trứng gà hộp 10 quả", 1, 38000)
    r.item("Rau cải ngọt", 2, 15000)
    r.item("Dầu ăn 1L", 1, 52000)
    r.rule()
    r.left_right("Tạm tính:", vnd(369000))
    r.left_right("Giảm giá thành viên:", "-" + vnd(17000))
    r.left_right("TỔNG THANH TOÁN:", vnd(352000), r.bold)
    r.left_right("Tiền khách đưa:", vnd(500000))
    r.left_right("Tiền thối lại:", vnd(148000))
    r.rule()
    r.center("Cảm ơn quý khách - Hẹn gặp lại!")
    return as_photo(r.finish(), angle=1.5, seed=1)


def restaurant() -> Image.Image:
    r = Receipt(1500, regular="arial.ttf", bold="arialbd.ttf")
    r.center("NHÀ HÀNG PHỐ CỔ", r.title)
    r.center("45 Phố Hàng Giả, Quận Mẫu, Hà Nội")
    r.center("PHIẾU THANH TOÁN", r.bold, gap=20)
    r.text("Bàn: 08     Số khách: 4")
    r.text("Ngày: 12/10/2026  20:15")
    r.rule()
    r.item("Lẩu thái hải sản", 1, 320000)
    r.item("Gà nướng mật ong", 1, 185000)
    r.item("Rau muống xào tỏi", 1, 55000)
    r.item("Bia chai", 4, 25000)
    r.rule()
    r.left_right("Cộng tiền hàng:", vnd(660000))
    r.left_right("Phí phục vụ (5%):", vnd(33000))
    r.left_right("VAT (8%):", vnd(55440))
    r.left_right("TỔNG CỘNG:", vnd(748440), r.bold)
    r.rule()
    r.center("Xin cảm ơn và hẹn gặp lại!")
    return as_photo(r.finish(), angle=-2.0, seed=2)


def coffee_shop() -> Image.Image:
    r = Receipt(1100, regular="consola.ttf", bold="consolab.ttf")
    r.center("CÀ PHÊ MÂY", r.title)
    r.center("8 Ngõ Gió, Đà Lạt")
    r.text("18/10/2026 09:05      Bill #A1029")
    r.rule()
    r.item("Bạc xỉu", 1, 39000)
    r.item("Cà phê muối", 1, 45000)
    r.item("Bánh croissant", 1, 35000)
    r.rule()
    r.left_right("Thành tiền:", vnd(119000), r.bold)
    r.left_right("Tiền mặt:", vnd(200000))
    r.left_right("Trả lại:", vnd(81000))
    r.center("Wifi: maycafe / 12345678")
    return as_photo(r.finish(), angle=0.8, seed=3)


def blurry_photo() -> Image.Image:
    r = Receipt(1300)
    r.center("SIÊU THỊ HOA SEN", r.title)
    r.center("99 Đường Mẫu, Quận 1, TP. HCM")
    r.center("HOÁ ĐƠN BÁN LẺ", r.bold, gap=20)
    r.text("Ngày: 16/10/2026")
    r.rule()
    r.item("Nước giặt 3.8kg", 1, 189000)
    r.item("Mì ly", 6, 12000)
    r.item("Táo đỏ 1kg", 1, 79000)
    r.rule()
    r.left_right("TỔNG THANH TOÁN:", vnd(340000), r.bold)
    photo = as_photo(r.finish(), angle=3.0, seed=4)
    # Rung tay mạnh + lệch nét: chữ và số không còn đọc được.
    small = photo.resize((photo.width // 6, photo.height // 6))
    return small.resize(photo.size).filter(ImageFilter.GaussianBlur(9))


def handwritten() -> Image.Image:
    width, height = 820, 900
    image = Image.new("RGB", (width, height), (252, 250, 236))
    draw = ImageDraw.Draw(image)
    for y in range(110, height, 56):
        draw.line([(30, y), (width - 30, y)], fill=(170, 195, 225), width=2)
    # Ink Free thiếu vài glyph tiếng Việt dựng sẵn (ướ, ắ, ộ…) → dòng hàng viết không dấu,
    # giống hoá đơn viết tay thường gặp.
    hand = font("Inkfree.ttf", 40)
    ink = (25, 45, 120)
    lines = [
        ("Tạp hoá Cô Ba", 2),
        ("Hoá đơn - ngày 20/10/2026", 0),
        ("Nuoc mam 1 chai ...... 45.000", 0),
        ("Mì gói 10 gói ......... 50.000", 0),
        ("Duong 1kg .............. 25.000", 0),
        ("Tong cong: 120.000đ", 2),
        ("Cam on!", 0),
    ]
    rng = random.Random(5)
    y = 60
    for text, stroke in lines:
        draw.text(
            (60 + rng.randint(-8, 8), y + rng.randint(-4, 4)),
            text,
            font=hand,
            fill=ink,
            stroke_width=stroke // 2,
            stroke_fill=ink,
        )
        y += 104
    return as_photo(image, angle=-3.5, seed=6)


SAMPLES = {
    "supermarket.jpg": supermarket,
    "restaurant.jpg": restaurant,
    "coffee_shop.jpg": coffee_shop,
    "blurry_photo.jpg": blurry_photo,
    "handwritten.jpg": handwritten,
}


def main() -> None:
    for name, build in SAMPLES.items():
        path = OUT_DIR / name
        build().save(path, format="JPEG", quality=85)
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
