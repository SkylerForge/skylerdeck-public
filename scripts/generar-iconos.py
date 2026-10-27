"""Draws the app icons (green rounded square with an «S» in Aldrich) into static/iconos/.

Needs Pillow, which the panel itself does not use: run it from any environment that has it.
    python scripts/generar-iconos.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "static" / "iconos"
FUENTE = RAIZ / "static" / "fonts" / "aldrich-latin.woff2"
FONDO = (14, 17, 12)  # --fondo
VERDE = (158, 255, 106)  # --nvg


def icono(lado: int, margen: float, redondeo: float, fondo_lleno: bool) -> Image.Image:
    escala = 4  # draw big, then shrink: smooth edges
    grande = lado * escala
    img = Image.new("RGBA", (grande, grande), FONDO + (255,) if fondo_lleno else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = int(grande * margen)
    d.rounded_rectangle((m, m, grande - m, grande - m), radius=int((grande - 2 * m) * redondeo), fill=VERDE)
    fuente = ImageFont.truetype(str(FUENTE), int((grande - 2 * m) * 0.62))
    caja = d.textbbox((0, 0), "S", font=fuente)
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    d.text(((grande - ancho) / 2 - caja[0], (grande - alto) / 2 - caja[1]), "S", font=fuente, fill=FONDO)
    return img.resize((lado, lado), Image.LANCZOS)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    icono(192, 0.0, 0.22, False).save(SALIDA / "icono-192.png")
    icono(512, 0.0, 0.22, False).save(SALIDA / "icono-512.png")
    # Maskable: the system crops it into its own shape, so the mark keeps to the safe centre.
    icono(512, 0.12, 0.22, True).save(SALIDA / "icono-maskable-512.png")
    # iOS draws its own rounded corners and wants no transparency.
    icono(180, 0.0, 0.0, True).convert("RGB").save(SALIDA / "apple-touch-icon.png")
    icono(64, 0.0, 0.22, False).save(SALIDA / "favicon.png")
    print("Iconos en", SALIDA)


if __name__ == "__main__":
    main()
