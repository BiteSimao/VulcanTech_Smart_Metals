"""Análise visual demonstrativa de solda e imagem térmica com OpenCV."""

import base64
from pathlib import Path

import cv2
import numpy as np


MAX_DIMENSAO = 1600
VERSAO_CRITERIOS = "conservadora-2"
PASTA_REFERENCIAS = Path(__file__).resolve().parents[1] / "imagens"


def _decodificar(conteudo):
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ValueError("O arquivo não parece ser uma imagem válida.")
    altura, largura = imagem.shape[:2]
    if min(altura, largura) < 16:
        raise ValueError("A imagem precisa ter pelo menos 16 pixels em cada lado.")
    escala = min(1.0, MAX_DIMENSAO / max(altura, largura))
    if escala < 1:
        imagem = cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return imagem


def _imagem_base64(imagem):
    ok, buffer = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Não foi possível gerar a imagem de análise.")
    return "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii")


def _medir_cordao(imagem):
    altura, largura = imagem.shape[:2]
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    suavizada = cv2.GaussianBlur(cinza, (0, 0), 1.1)
    nitida = cv2.addWeighted(cinza, 1.7, suavizada, -0.7, 0)
    gradiente_y = np.abs(cv2.Sobel(nitida, cv2.CV_32F, 0, 1, ksize=3))

    # Para este exemplo, o cordão é aproximadamente horizontal.
    perfil_completo = gradiente_y.mean(axis=1)
    perfil = perfil_completo.copy()
    janela = max(5, int(altura * 0.06))
    perfil = np.convolve(perfil, np.ones(janela) / janela, mode="same")
    centro_y = int(np.argmax(perfil))
    base_perfil = float(np.percentile(perfil, 50))
    pico_perfil = float(perfil[centro_y])
    snr_cordao = pico_perfil / max(base_perfil, 1e-6)
    nivel_meia_altura = base_perfil + 0.35 * max(0.0, pico_perfil - base_perfil)
    acima = np.flatnonzero(perfil >= nivel_meia_altura)
    mesma_faixa = acima[np.abs(acima - centro_y) <= max(2, altura // 8)]
    largura_faixa = int(mesma_faixa[-1] - mesma_faixa[0] + 1) if len(mesma_faixa) else 0
    banda = max(16, int(altura * 0.24))
    y0, y1 = max(0, centro_y - banda // 2), min(altura, centro_y + banda // 2)
    recorte = nitida[y0:y1, :]

    bordas = cv2.Canny(recorte, 45, 130)
    contornos, _ = cv2.findContours(bordas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contornos = [c for c in contornos if cv2.contourArea(c) >= max(3, largura * altura * 0.000015)]

    # Black-hat na imagem original realça cavidades escuras sem suavizar os poros.
    recorte_original = cinza[y0:y1, :]
    tamanho = max(7, int(min(largura, altura) * 0.06) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tamanho, tamanho))
    blackhat = cv2.morphologyEx(recorte_original, cv2.MORPH_BLACKHAT, kernel)
    limiar = 45
    _, mascara = cv2.threshold(blackhat, limiar, 255, cv2.THRESH_BINARY)
    candidatos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    poros = []
    area_minima = max(8, largura * altura * 0.00004)
    area_maxima = max(area_minima + 1, largura * altura * 0.002)
    for contorno in candidatos:
        area = cv2.contourArea(contorno)
        perimetro = cv2.arcLength(contorno, True)
        circularidade = 4 * np.pi * area / (perimetro * perimetro) if perimetro else 0
        if area_minima <= area <= area_maxima and circularidade >= 0.45:
            momentos = cv2.moments(contorno)
            if momentos["m00"]:
                poros.append((int(momentos["m10"] / momentos["m00"]), int(momentos["m01"] / momentos["m00"]) + y0))

    # Continuidade é uma medida relativa do gradiente ao longo da faixa detectada.
    energia_coluna = gradiente_y[max(0, centro_y - 3):min(altura, centro_y + 4), :].max(axis=0)
    referencia = float(np.percentile(energia_coluna, 70)) if energia_coluna.size else 0
    presentes = energia_coluna >= max(8.0, referencia * 0.22)
    continuidade = round(float(presentes.mean() * 100), 1) if presentes.size else 0.0
    energia_vertical = float(gradiente_y[y0:y1, :].mean())
    energia_horizontal = float(np.abs(cv2.Sobel(nitida[y0:y1, :], cv2.CV_32F, 1, 0, ksize=3)).mean())
    orientacao_horizontal = energia_vertical / max(energia_vertical + energia_horizontal, 1e-6)
    nitidez = float(cv2.Laplacian(cinza, cv2.CV_64F).var())
    densidade_bordas = cv2.countNonZero(bordas) / max(1, bordas.size) * 100

    # Perfil normalizado ajuda a rejeitar linhas, chapas e cordões com geometria diferente.
    meio = max(8, int(altura * 0.12))
    perfil_local = perfil_completo[max(0, centro_y - meio):min(altura, centro_y + meio + 1)]
    amostras = np.interp(np.linspace(0, max(0, len(perfil_local) - 1), 64), np.arange(len(perfil_local)), perfil_local)
    amostras = np.maximum(amostras - np.percentile(amostras, 20), 0)
    perfil_normalizado = amostras / max(float(np.linalg.norm(amostras)), 1e-6)

    sobreposicao = imagem.copy()
    cv2.rectangle(sobreposicao, (0, y0), (largura - 1, y1), (40, 180, 255), 2)
    cv2.drawContours(sobreposicao[y0:y1, :], contornos, -1, (50, 220, 100), 1)
    for x, y in poros:
        cv2.circle(sobreposicao, (x, y), max(5, int(min(largura, altura) * 0.025)), (40, 50, 255), 2)

    return {
        "tipo": "cordao",
        "largura_px": largura,
        "altura_px": altura,
        "contornos_detectados": len(contornos),
        "candidatos_por_porosidade": len(poros),
        "continuidade_estimada_percentual": continuidade,
        "faixa_inspecionada_y_px": [y0, y1],
        "snr_faixa": round(float(snr_cordao), 2),
        "largura_faixa_px": largura_faixa,
        "orientacao_horizontal": round(float(orientacao_horizontal), 3),
        "nitidez_laplaciana": round(nitidez, 1),
        "densidade_bordas_percentual": round(float(densidade_bordas), 2),
        "_perfil_normalizado": perfil_normalizado,
        "_sobreposicao": sobreposicao,
    }


def analisar_cordao(conteudo):
    """Compara a imagem enviada com a referência interna e decide a triagem."""
    medida = _medir_cordao(_decodificar(conteudo))
    arquivo_referencia = PASTA_REFERENCIAS / "cordao_solda_referencia.png"
    referencia = _medir_cordao(_decodificar(arquivo_referencia.read_bytes()))
    area = medida["largura_px"] * medida["altura_px"]
    area_referencia = referencia["largura_px"] * referencia["altura_px"]
    densidade = medida["candidatos_por_porosidade"] / area * 1_000_000
    densidade_referencia = referencia["candidatos_por_porosidade"] / area_referencia * 1_000_000
    similaridade_perfil = float(np.dot(medida["_perfil_normalizado"], referencia["_perfil_normalizado"]))
    razao_faixa = medida["largura_faixa_px"] / max(1, referencia["largura_faixa_px"])
    razao_bordas = medida["densidade_bordas_percentual"] / max(0.1, referencia["densidade_bordas_percentual"])
    razao_nitidez = medida["nitidez_laplaciana"] / max(1.0, referencia["nitidez_laplaciana"])
    limite_continuidade = max(90.0, referencia["continuidade_estimada_percentual"] - 5.0)
    limite_porosos = densidade_referencia + 8.0

    motivos = []
    if medida["snr_faixa"] < max(2.0, referencia["snr_faixa"] * 0.7):
        motivos.append("Cordão não foi localizado com contraste suficiente.")
    if medida["continuidade_estimada_percentual"] < limite_continuidade:
        motivos.append("A faixa do cordão apresenta possíveis interrupções.")
    if not 0.65 <= razao_faixa <= 1.5:
        motivos.append("A largura detectada difere da referência.")
    if medida["orientacao_horizontal"] < max(0.35, referencia["orientacao_horizontal"] * 0.72):
        motivos.append("A geometria não corresponde ao cordão horizontal de referência.")
    if not 0.55 <= razao_bordas <= 1.7:
        motivos.append("O padrão de bordas difere da textura de referência.")
    if razao_nitidez < 0.45:
        motivos.append("Imagem desfocada; envie uma captura mais nítida.")
    if similaridade_perfil < 0.88:
        motivos.append("O perfil do cordão difere da referência interna.")
    if densidade > limite_porosos:
        motivos.append("Foram detectados candidatos a porosidade acima do limite.")
    aprovada = not motivos
    medida["aprovado"] = bool(aprovada)
    medida["versao_criterios"] = VERSAO_CRITERIOS
    medida["resultado"] = "Aprovado na triagem" if aprovada else "Reprovado na triagem"
    medida["motivos_reprovacao"] = motivos
    medida["criterios"] = {
        "continuidade_minima_percentual": round(limite_continuidade, 1),
        "candidatos_porosos_por_milhao_px_maximo": round(limite_porosos, 2),
        "densidade_detectada_por_milhao_px": round(densidade, 2),
        "similaridade_minima_perfil": 0.88,
        "similaridade_perfil": round(similaridade_perfil, 3),
        "razao_largura_faixa": round(razao_faixa, 3),
        "razao_densidade_bordas": round(razao_bordas, 3),
        "razao_nitidez": round(razao_nitidez, 3),
    }
    medida["referencia_interna"] = "cordao_solda_referencia.png"
    medida["observacao"] = "Triagem heurística comparada à referência interna; confirme a decisão com inspeção qualificada."
    medida["imagem_anotada"] = _imagem_base64(medida.pop("_sobreposicao"))
    medida.pop("_perfil_normalizado", None)
    return medida


def _medir_termica(imagem, brilho_minimo=205):
    altura, largura = imagem.shape[:2]
    hsv = cv2.cvtColor(imagem, cv2.COLOR_BGR2HSV)
    matiz, saturacao, brilho = cv2.split(hsv)

    # Cores quentes do mapa (vermelho/amarelo) mais os pontos quase brancos.
    cores_quentes = ((matiz <= 38) | (matiz >= 170)) & (saturacao >= 65) & (brilho >= 125)
    pontos_brancos = (saturacao < 55) & (brilho >= int(brilho_minimo))
    mascara = np.uint8(cores_quentes | pontos_brancos) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # A legenda de escala da referência ocupa o canto inferior esquerdo.
    legenda_y, legenda_x = int(altura * 0.80), int(largura * 0.10)
    mascara[legenda_y:, :legenda_x] = 0

    total, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(mascara, 8)
    area_minima = max(25, int(largura * altura * 0.0001))
    mascara_area = np.zeros_like(mascara)
    regioes = 0
    maior_indice = 0
    maior_area = 0
    for indice in range(1, total):
        area = int(estatisticas[indice, cv2.CC_STAT_AREA])
        if area >= area_minima:
            mascara_area[rotulos == indice] = 255
            regioes += 1
            if area > maior_area:
                maior_area = area
                maior_indice = indice
    area_quente = int(cv2.countNonZero(mascara_area))
    cobertura = round(area_quente / (largura * altura) * 100, 2)
    if maior_indice:
        x, y, largura_principal, altura_principal, _ = estatisticas[maior_indice]
        extensao_horizontal = largura_principal / largura
        altura_relativa = altura_principal / altura
        centro_vertical = (y + altura_principal / 2) / altura
    else:
        extensao_horizontal = altura_relativa = centro_vertical = 0.0

    contornos, _ = cv2.findContours(mascara_area, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sobreposicao = imagem.copy()
    cor = np.zeros_like(imagem)
    cor[:, :] = (0, 80, 255)
    zona_colorida = cv2.bitwise_and(cor, cor, mask=mascara_area)
    sobreposicao = cv2.addWeighted(sobreposicao, 0.72, zona_colorida, 0.65, 0)
    cv2.drawContours(sobreposicao, contornos, -1, (0, 255, 255), 2)

    return {
        "tipo": "termica_haz",
        "largura_px": largura,
        "altura_px": altura,
        "brilho_minimo_hsv": int(brilho_minimo),
        "area_quente_px": area_quente,
        "cobertura_quente_percentual": cobertura,
        "regioes_quentes": regioes,
        "pico_relativo_hsv_v": int(np.max(brilho[mascara_area > 0])) if area_quente else 0,
        "extensao_horizontal_percentual": round(float(extensao_horizontal * 100), 1),
        "altura_faixa_percentual": round(float(altura_relativa * 100), 1),
        "centro_vertical_percentual": round(float(centro_vertical * 100), 1),
        "_componente_principal": (int(x), int(y), int(largura_principal), int(altura_principal)) if maior_indice else None,
        "_sobreposicao": sobreposicao,
    }


def analisar_termica(conteudo, brilho_minimo=205):
    """Compara a zona quente com a referência térmica interna."""
    medida = _medir_termica(_decodificar(conteudo), brilho_minimo)
    arquivo_referencia = PASTA_REFERENCIAS / "termica_haz_referencia.png"
    referencia = _medir_termica(_decodificar(arquivo_referencia.read_bytes()), brilho_minimo)
    cobertura_ref = referencia["cobertura_quente_percentual"]
    minimo = cobertura_ref * 0.85
    maximo = cobertura_ref * 1.15
    principal_ref = referencia["_componente_principal"]
    principal = medida["_componente_principal"]
    motivos = []
    if not principal or not principal_ref:
        motivos.append("Não foi detectada uma faixa térmica contínua.")
    else:
        largura_ref = principal_ref[2] / referencia["largura_px"]
        largura_atual = principal[2] / medida["largura_px"]
        centro_ref = (principal_ref[1] + principal_ref[3] / 2) / referencia["altura_px"]
        centro_atual = (principal[1] + principal[3] / 2) / medida["altura_px"]
        altura_ref = principal_ref[3] / referencia["altura_px"]
        altura_atual = principal[3] / medida["altura_px"]
        if largura_atual < largura_ref - 0.08:
            motivos.append("A zona quente não forma um cordão suficientemente contínuo.")
        if abs(centro_atual - centro_ref) > 0.08:
            motivos.append("A posição da faixa térmica difere da referência.")
        if not 0.65 <= altura_atual / max(altura_ref, 1e-6) <= 1.45:
            motivos.append("A largura térmica difere do perfil de referência.")
    if not minimo <= medida["cobertura_quente_percentual"] <= maximo:
        motivos.append("A área quente está fora da faixa comparada à referência.")
    if medida["regioes_quentes"] > referencia["regioes_quentes"] + 2:
        motivos.append("A imagem contém pontos quentes isolados além do padrão de referência.")
    aprovada = not motivos
    medida["aprovado"] = bool(aprovada)
    medida["versao_criterios"] = VERSAO_CRITERIOS
    medida["resultado"] = "Aprovado na triagem" if aprovada else "Reprovado na triagem"
    medida["motivos_reprovacao"] = motivos
    medida["criterios"] = {
        "cobertura_minima_percentual": round(minimo, 2),
        "cobertura_maxima_percentual": round(maximo, 2),
        "cobertura_referencia_percentual": cobertura_ref,
        "tolerancia_cobertura_percentual": 15,
    }
    medida["referencia_interna"] = "termica_haz_referencia.png"
    medida["observacao"] = "Triagem por cor/brilho comparada à referência; não mede temperatura real em °C."
    medida["imagem_anotada"] = _imagem_base64(medida.pop("_sobreposicao"))
    medida.pop("_componente_principal", None)
    return medida
