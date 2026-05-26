import click
import serial
from wand.image import Image
from wand.font import Font
import PIL.Image
import image_helper


@click.command()
@click.argument("text")
@click.option(
    "--font",
    default="/usr/share/fonts/TTF/DejaVuSans.ttf",
    help="Path to TTF font file",
)
@click.option(
    "--preview", is_flag=True, default=False, help="Generate image only, do not print"
)
@click.option(
    "--label-width-mm", type=float, default=40, help="Label width in millimeters."
)
@click.option(
    "--label-height-mm", type=float, default=12, help="Label height in millimeters."
)
@click.option(
    "--duplicate",
    is_flag=True,
    default=False,
    help="Print the text twice on the label (for cable labels).",
)
@click.option(
    "--scale",
    type=float,
    default=1.0,
    help="Scale the text size (1.0 = fill the label).",
)
@click.option("--device", default="/dev/rfcomm1", help="The serial device to print to.")
def main(
    text, font, preview, label_width_mm, label_height_mm, duplicate, scale, device
):
    image = generate_image(
        text, font, label_width_mm, label_height_mm, duplicate, scale
    )

    if preview:
        filename = "temp.png"
        image.save(filename)
        print(f"Preview saved to {filename}")
        return

    port = serial.Serial(device, timeout=10)
    header(port)
    print_image(port, image)


def header(port):
    # printer initialization sniffed from Android app "Print Master"
    packets = [
        "1f1138",
        "1f11121f1113",
        "1f1109",
        "1f1111",
        "1f1119",
        "1f1107",
        "1f110a1f110202",
    ]

    for packet in packets:
        port.write(bytes.fromhex(packet))
        port.flush()


def generate_image(text, font_path, label_width_mm, label_height_mm, duplicate, scale):
    # Phomemo D30 has a resolution of 203 DPI, which is approximately 8 pixels/mm.
    dpmm = 8
    img_height_px = int(label_height_mm * dpmm)
    img_width_px = int(label_width_mm * dpmm)

    # Create the font object once.
    font = Font(font_path, size=int(img_height_px * scale))

    def _create_text_image(width, height, text, font):
        with Image(width=width, height=height) as img:
            img.background_color = "white"
            img.font = font
            img.gravity = "center"
            img.caption(text)
            img.extent(width=width, height=height)
            return img.clone()

    if duplicate:
        # For duplicate mode, we create a text block half the width
        content_width = img_width_px // 2
        text_block = _create_text_image(content_width, img_height_px, text, font)

        # We then composite this text block twice onto the full-width canvas
        with Image(
            width=img_width_px, height=img_height_px, background="white"
        ) as canvas:
            canvas.composite(text_block, left=0, top=0)
            canvas.composite(text_block, left=content_width, top=0)
            canvas.rotate(270)
            # Convert to PIL Image
            return PIL.Image.frombytes(
                "RGB", canvas.size, canvas.make_blob("RGB")
            ).convert("L")
    else:
        # For normal mode, we just create the image
        img = _create_text_image(img_width_px, img_height_px, text, font)
        img.rotate(270)
        # Convert to PIL Image
        return PIL.Image.frombytes("RGB", img.size, img.make_blob("RGB")).convert("L")


def print_image(port, image):
    width = 96

    processed_image = image_helper.preprocess_image(image, width)

    # Calculate height in little-endian hex for header
    height_bytes = processed_image.height.to_bytes(2, "little").hex()
    output = f"1f1124001b401d7630000c00{height_bytes}"

    # adapted from https://github.com/theacodes/phomemo_m02s/blob/main/phomemo_m02s/printer.py
    for chunk in image_helper.split_image(processed_image):
        output = bytearray.fromhex(output)

        bits = image_helper.image_to_bits(chunk)
        for line in bits:
            for byte_num in range(width // 8):
                byte = 0
                for bit in range(8):
                    pixel = line[byte_num * 8 + bit]
                    byte |= (pixel & 0x01) << (7 - bit)
                output.append(byte)

        port.write(output)
        port.flush()

        output = ""


if __name__ == "__main__":
    main()
