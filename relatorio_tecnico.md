# Parecer técnico - VulcanTech Smart Metals

## Solução

O fluxo parte do CSV de sensores em intervalos de cinco minutos. As leituras fora dos limites físicos são tratadas como ausentes, ruídos adicionais são verificados por Z-score dentro de cada liga e lacunas são interpoladas temporalmente dentro da célula. A preparação calcula estatísticas móveis de 30 minutos e duas horas, normaliza sinais pela liga e deriva o Índice de Esforço Mecânico (IEM).

Dois modelos de árvores com ponderação de classes são comparados com corte temporal de 70% para treino e 30% para teste. O relatório gerado em `saida/metricas_modelo.json` registra recall por falha, matriz de confusão, métricas por classe e o modelo escolhido. O critério de aceitação proposto é recall de pelo menos 90% em cada falha crítica, medido em dados representativos e separados no tempo. Se não atingir esse valor, a previsão não deve acionar uma intervenção automática.

## OEE e visão computacional

O CSV não informa tempo planejado, paradas, ciclo ideal, produção total ou refugo real. Portanto, o OEE do painel é uma simulação ilustrativa: o risco de parada afeta disponibilidade e o risco de refrigeração afeta qualidade. Para uso operacional, esses componentes precisam vir do MES/CLP e do apontamento de qualidade.

A inspeção usa nitidez, escala de cinza, Canny e contornos para a geometria do cordão; usa morfologia black-hat para destacar possíveis poros. Para a HAZ, converte a imagem térmica recebida para HSV e segmenta regiões quentes com um limiar ajustável. As imagens exibidas são as referências fornecidas para o projeto. O detector de poros é heurístico e pode destacar marcas da superfície como candidatos; a imagem térmica em paleta de cores não permite medir °C sem calibração radiométrica. Uma implantação real precisa de câmera calibrada, iluminação controlada, resolução e limites definidos por processo, conjunto rotulado por especialistas e validação de falsos positivos e negativos.

## Segurança, privacidade e governança

- **LGPD:** dados de máquina não identificam necessariamente pessoas, mas registros associados a operadores, turnos ou produtividade podem se tornar dados pessoais. Minimizar esses campos, restringir acesso, definir retenção e registrar a finalidade.
- **Cibersegurança OT/IT:** manter inferência em rede segregada, autenticação e autorização na API, TLS entre zonas, logs sem segredos, imagens e modelos versionados, atualização assinada e controle de acesso. O protótipo não escreve em CLP; comandos de parada precisam de intertravamentos e validação do responsável de segurança funcional.
- **EU AI Act:** classificar o uso pretendido com apoio jurídico e de conformidade antes da implantação. Uma ferramenta de manutenção fabril não é automaticamente de alto risco; o contexto, o uso e o efeito sobre pessoas e segurança são determinantes. Documentar finalidade, supervisão humana, desempenho, limitações e alterações do modelo.
- **MLOps:** guardar versão do modelo e métricas, monitorar distribuição das ligas e sensores, acompanhar recall das falhas e revalidar após mudanças de ferramenta, processo ou material. A resposta da API deve ser tratada como apoio à decisão.

## Sustentabilidade e conclusão

A detecção antecipada pode reduzir refugo, retrabalho, troca prematura de ferramenta e consumo de fluido. Esses ganhos devem ser medidos com linha de base de peças refugadas, energia por peça, fluido consumido e paradas não planejadas. O protótipo entrega os blocos técnicos e torna suas limitações explícitas; a passagem para produção depende de validação em dados reais, critérios de segurança e confirmação de recall por classe.
