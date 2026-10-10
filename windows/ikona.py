from PIL import Image, ImageDraw
im = Image.new("RGBA", (256, 256), (27, 94, 32, 255))
d = ImageDraw.Draw(im)
d.rounded_rectangle((36, 80, 220, 176), 10, fill="white")
for cx in (96, 160):
    d.ellipse((cx - 28, 100, cx + 28, 156), fill=(118, 185, 0))
d.rectangle((52, 176, 160, 194), fill="white")
im.save("windows/ikona.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
