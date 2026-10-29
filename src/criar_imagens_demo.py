"""Cria amostras visuais sintéticas, em alta resolução, para testar o fluxo CV."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


PASTA = Path(__file__).resolve().parents[1] / "imagens"
LARGURA, ALTURA = 1600, 900


def criar_fundo_metal(seed=14):
    rng = np.random.default_rng(seed)
    ruido = rng.normal(0, 5, (ALTURA, LARGURA, 1))
    y = np.linspace(0.82, 0.48, ALTURA)[:, None, None]
    base = np.broadcast_to(np.array([48, 62, 75]), (ALTURA, LARGURA, 3)).astype(float)
    base = base * y + ruido
    return Image.fromarray(np.uint8(np.clip(base, 0, 255)), "RGB")


def criar_cordao():
    imagem = criar_fundo_metal()
    luz = Image.new("RGBA", imagem.size)
    d = ImageDraw.Draw(luz)
    # Brilho amplo e depois núcleo do cordão para uma amostra macro legível.
    d.line([(160, 500), (360, 450), (600, 480), (850, 430), (1120, 465), (1450, 410)], fill=(255, 105, 28, 115), width=100, joint="curve")
    luz = luz.filter(ImageFilter.GaussianBlur(45))
    imagem = Image.alpha_composite(imagem.convert("RGBA"), luz)
    d = ImageDraw.Draw(imagem)
    pontos = [(160, 500), (360, 450), (600, 480), (850, 430), (1120, 465), (1450, 410)]
    d.line(pontos, fill=(255, 117, 43, 245), width=34, joint="curve")
    d.line([(x, y - 7) for x, y in pontos], fill=(255, 222, 169, 240), width=7, joint="curve")
    # Marcas pequenas ilustram descontinuidades para o processamento Canny.
    for x, y in [(550, 477), (1000, 454), (1285, 440)]:
        d.ellipse((x - 8, y - 12, x + 8, y + 12), fill=(22, 28, 33, 245))
    imagem.convert("RGB").save(PASTA / "cordao_solda_demo.png", optimize=True)


def criar_termica():
    yy, xx = np.mgrid[0:ALTURA, 0:LARGURA]
    base = 28 + 17 * np.exp(-((yy - 445) / 160) ** 2)
    pontos = [(160, 500), (360, 450), (600, 480), (850, 430), (1120, 465), (1450, 410)]
    for x, y in pontos:
        base += 205 * np.exp(-(((xx - x) / 150) ** 2 + ((yy - y) / 85) ** 2))
    base += np.random.default_rng(8).normal(0, 2, base.shape)
    t = np.uint8(np.clip(base, 0, 255))
    # Mapa térmico semelhante a ferro -> vermelho -> amarelo -> branco.
    stops = np.array([[8, 12, 38], [60, 16, 112], [180, 25, 48], [255, 118, 18], [255, 235, 120], [255, 255, 244]])
    idx = t.astype(float) / 255 * (len(stops) - 1)
    low = np.floor(idx).astype(int)
    high = np.minimum(low + 1, len(stops) - 1)
    frac = (idx - low)[..., None]
    rgb = stops[low] * (1 - frac) + stops[high] * frac
    Image.fromarray(np.uint8(rgb), "RGB").save(PASTA / "termica_haz_demo.png", optimize=True)


if __name__ == "__main__":
    PASTA.mkdir(exist_ok=True)
    criar_cordao()
    criar_termica()
    print(f"Imagens demonstrativas criadas em {PASTA}")
