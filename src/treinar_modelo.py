"""Compara dois modelos e salva o melhor pipeline de classificação."""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "saida"
ARQUIVO_PREPARADO = SAIDA / "sensores_preparados.csv"


ROTULOS = {
    0: "Normal",
    1: "Desgaste de ferramenta",
    2: "Falha de refrigeração",
    3: "Desalinhamento ou trinca",
}


def treinar():
    SAIDA.mkdir(exist_ok=True)
    if not ARQUIVO_PREPARADO.exists():
        raise FileNotFoundError(
            "Execute o notebook notebooks/tratamento_dados.ipynb antes de treinar o modelo."
        )
    dados = pd.read_csv(ARQUIVO_PREPARADO, parse_dates=["timestamp"])
    alvo = "tipo_falha"
    categoricas = ["id_celula", "liga_metalica"]
    ignorar = ["timestamp", alvo]
    colunas = [c for c in dados.columns if c not in ignorar]
    numericas = [c for c in colunas if c not in categoricas]

    pre_processamento = ColumnTransformer([
        ("numericas", Pipeline([
            ("preencher", SimpleImputer(strategy="median")),
            ("escala", StandardScaler()),
        ]), numericas),
        ("categoricas", Pipeline([
            ("preencher", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), categoricas),
    ])

    # O corte é cronológico: 70% iniciais para treino e 30% finais para teste.
    corte = int(len(dados) * 0.70)
    treino, teste = dados.iloc[:corte], dados.iloc[corte:]
    modelos = {
        "Random Forest": RandomForestClassifier(
            n_estimators=160, class_weight="balanced", min_samples_leaf=2,
            random_state=42, n_jobs=-1,
        ),
        "Extra Trees": ExtraTreesClassifier(
            n_estimators=160, class_weight="balanced", min_samples_leaf=2,
            random_state=42, n_jobs=-1,
        ),
    }

    resultados = {}
    melhor = None
    melhor_recall = -1
    for nome, classificador in modelos.items():
        pipeline = Pipeline([
            ("preparacao", pre_processamento),
            ("modelo", classificador),
        ])
        pipeline.fit(treino[colunas], treino[alvo])
        previsto = pipeline.predict(teste[colunas])
        recall = recall_score(teste[alvo], previsto, labels=[1, 2, 3], average="macro", zero_division=0)
        resultados[nome] = {
            "recall_macro_falhas": round(float(recall), 4),
            "matriz_confusao": confusion_matrix(teste[alvo], previsto, labels=[0, 1, 2, 3]).tolist(),
            "relatorio": classification_report(
                teste[alvo], previsto, labels=[0, 1, 2, 3],
                target_names=[ROTULOS[i] for i in range(4)], output_dict=True, zero_division=0,
            ),
        }
        nomes = pipeline.named_steps["preparacao"].get_feature_names_out()
        pesos = pipeline.named_steps["modelo"].feature_importances_
        ordem = pesos.argsort()[::-1][:10]
        resultados[nome]["atributos_mais_relevantes"] = [
            {"atributo": str(nomes[i]), "importancia": round(float(pesos[i]), 4)} for i in ordem
        ]
        if recall > melhor_recall:
            melhor, melhor_recall = pipeline, recall

    resultados["modelo_escolhido"] = max(
        modelos, key=lambda nome: resultados[nome]["recall_macro_falhas"]
    )
    joblib.dump({"pipeline": melhor, "colunas": colunas}, SAIDA / "modelo_vulcantech.joblib")

    # Cenário didático de OEE: as colunas não medem produção/tempo real.
    # Risco de parada reduz disponibilidade; risco de refrigeração reduz qualidade.
    linha = teste[colunas].copy()
    risco = melhor.predict(linha)
    disponibilidade = 0.90 - (risco == 1).mean() * 0.10 - (risco == 3).mean() * 0.05
    qualidade = 0.96 - (risco == 2).mean() * 0.08
    desempenho = 0.95
    resultados["oee_simulado"] = {
        "disponibilidade": round(float(disponibilidade), 4),
        "desempenho": desempenho,
        "qualidade": round(float(qualidade), 4),
        "oee": round(float(disponibilidade * desempenho * qualidade), 4),
        "observacao": "Estimativa didática: o CSV não contém tempos produtivos, ciclos ou refugo real.",
    }
    metricas_json = json.dumps(resultados, ensure_ascii=False, indent=2)
    (SAIDA / "metricas_modelo.json").write_text(metricas_json, encoding="utf-8")
    pasta_site = RAIZ / "site" / "data"
    pasta_site.mkdir(parents=True, exist_ok=True)
    (pasta_site / "metricas_modelo.json").write_text(metricas_json, encoding="utf-8")
    print(f"Modelo escolhido: {resultados['modelo_escolhido']}")
    print(f"Recall macro das falhas: {melhor_recall:.1%}")
    print(f"Métricas: {SAIDA / 'metricas_modelo.json'}")


if __name__ == "__main__":
    treinar()
