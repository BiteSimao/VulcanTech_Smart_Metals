"""Painel leve de leitura das métricas geradas pelo treinamento."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st


RAIZ = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="VulcanTech | Monitoramento", layout="wide")
st.title("VulcanTech Smart Metals")
st.caption("Monitoramento de sensores, classificação de falhas e qualidade de solda")

metricas = RAIZ / "saida" / "metricas_modelo.json"
if not metricas.exists():
    st.info("Treine os modelos para exibir as métricas: python src/treinar_modelo.py")
else:
    dados = json.loads(metricas.read_text(encoding="utf-8"))
    oee = dados["oee_simulado"]
    colunas = st.columns(4)
    colunas[0].metric("Modelo", dados["modelo_escolhido"])
    colunas[1].metric("OEE estimado", f"{oee['oee']:.1%}")
    colunas[2].metric("Disponibilidade", f"{oee['disponibilidade']:.1%}")
    colunas[3].metric("Qualidade", f"{oee['qualidade']:.1%}")
    st.caption(oee["observacao"])

    escolhas = [k for k in dados if k in ("Random Forest", "Extra Trees")]
    escolhido = st.selectbox("Modelo avaliado", escolhas, index=escolhas.index(dados["modelo_escolhido"]))
    relatorio = dados[escolhido]["relatorio"]
    tabela = pd.DataFrame({
        "Classe": [nome for nome in relatorio if isinstance(relatorio[nome], dict)],
        "Precisão": [relatorio[nome]["precision"] for nome in relatorio if isinstance(relatorio[nome], dict)],
        "Recall": [relatorio[nome]["recall"] for nome in relatorio if isinstance(relatorio[nome], dict)],
        "F1": [relatorio[nome]["f1-score"] for nome in relatorio if isinstance(relatorio[nome], dict)],
    })
    st.subheader("Desempenho por classe")
    st.dataframe(tabela, hide_index=True, use_container_width=True)

    esquerda, direita = st.columns(2)
    with esquerda:
        st.subheader("Matriz de confusão")
        classes = ["Normal", "Desgaste", "Refrigeração", "Desalinhamento/trinca"]
        matriz = pd.DataFrame(dados[escolhido]["matriz_confusao"], index=classes, columns=classes)
        st.dataframe(matriz, use_container_width=True)
        st.caption("Linhas: classe real. Colunas: classe prevista.")
    with direita:
        st.subheader("Atributos mais relevantes")
        importancia = pd.DataFrame(dados[escolhido]["atributos_mais_relevantes"])
        importancia = importancia.set_index("atributo")
        st.bar_chart(importancia)

st.subheader("Inspeção visual demonstrativa")
a, b = st.columns(2)
a.image(str(RAIZ / "imagens" / "cordao_solda_demo.png"), caption="Cordão sintético para análise de contornos")
b.image(str(RAIZ / "imagens" / "termica_haz_demo.png"), caption="Mapa térmico sintético para análise HAZ")
st.caption("As imagens são sintéticas. A inspeção real exige fotos calibradas, escala e validação industrial.")

preparados = RAIZ / "saida" / "sensores_preparados.csv"
if preparados.exists():
    st.subheader("Exploração dos sensores")
    sensores = pd.read_csv(preparados, parse_dates=["timestamp"])
    celula = st.selectbox("Célula", sorted(sensores["id_celula"].unique()))
    sinal = st.selectbox("Sinal", [
        "temperatura_fuso_c", "vibracao_triaxial_rms_mms", "torque_fuso_nm",
        "vazao_refrigerante_lmin", "corrente_estator_amp", "pressao_hidraulica_bar",
    ])
    serie = sensores[sensores["id_celula"] == celula].set_index("timestamp")[[sinal]].resample("1h").mean()
    st.line_chart(serie)
    st.caption("Médias horárias para facilitar a leitura; os dados originais são amostrados a cada cinco minutos.")
