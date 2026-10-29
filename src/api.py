"""API REST simples para inferência e inspeção visual de demonstração."""

from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from inspecao_solda import analisar_cordao, analisar_termica
from treinar_modelo import ROTULOS


RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_MODELO = RAIZ / "saida" / "modelo_vulcantech.joblib"
app = FastAPI(title="VulcanTech Smart Metals", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class LeituraSensor(BaseModel):
    id_celula: str
    liga_metalica: str
    temperatura_fuso_c: float
    vibracao_triaxial_rms_mms: float
    torque_fuso_nm: float
    vazao_refrigerante_lmin: float
    corrente_estator_amp: float
    pressao_hidraulica_bar: float
    nivel_ruido_db: float


@app.get("/")
async def inicio():
    return {"servico": "VulcanTech Smart Metals", "docs": "/docs"}


@app.post("/prever")
async def prever(leitura: LeituraSensor):
    if not ARQUIVO_MODELO.exists():
        raise HTTPException(status_code=503, detail="Execute primeiro: python src/treinar_modelo.py")
    salvo = joblib.load(ARQUIVO_MODELO)
    linha = pd.DataFrame([leitura.model_dump()])
    for coluna in ["temperatura_fuso_c", "vibracao_triaxial_rms_mms", "torque_fuso_nm", "vazao_refrigerante_lmin"]:
        for janela in ["30m", "2h"]:
            linha[f"{coluna}_media_{janela}"] = linha[coluna]
            linha[f"{coluna}_desvio_{janela}"] = 0
    linha["iem"] = linha["torque_fuso_nm"] * linha["vibracao_triaxial_rms_mms"] / (linha["vazao_refrigerante_lmin"] + 1)
    for coluna in ["temperatura_fuso_c", "vibracao_triaxial_rms_mms", "torque_fuso_nm", "vazao_refrigerante_lmin"]:
        linha[f"{coluna}_relativo_liga"] = 1.0
    classe = int(salvo["pipeline"].predict(linha[salvo["colunas"]])[0])
    return {
        "classe": classe,
        "diagnostico": ROTULOS[classe],
        "acao_sugerida": {
            0: "Manter monitoramento normal.",
            1: "Inspecionar ferramenta e avaliar parada preventiva.",
            2: "Verificar vazão do fluido de refrigeração.",
            3: "Verificar alinhamento da matriz e risco de trinca.",
        }[classe],
    }


@app.post("/inspecionar-solda")
async def inspecionar_solda(imagem: UploadFile = File(...)):
    conteudo = await _ler_imagem(imagem)
    try:
        return analisar_cordao(conteudo)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.post("/inspecionar-termica")
async def inspecionar_termica(
    imagem: UploadFile = File(...),
    brilho_minimo: int = Query(205, ge=120, le=250),
):
    conteudo = await _ler_imagem(imagem)
    try:
        return analisar_termica(conteudo, brilho_minimo)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


async def _ler_imagem(imagem: UploadFile):
    if imagem.content_type and not imagem.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Envie um arquivo de imagem.")
    conteudo = await imagem.read(12 * 1024 * 1024 + 1)
    if len(conteudo) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="A imagem deve ter no máximo 12 MB.")
    if not conteudo:
        raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")
    return conteudo
