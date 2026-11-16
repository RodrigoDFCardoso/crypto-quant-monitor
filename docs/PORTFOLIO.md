# Módulo de carteira

## Escopo atual

O módulo amplia o Crypto Quant Monitor sem substituir o scanner de mercado.
Nesta etapa estão disponíveis o esquema SQLite, a camada de conexão, as
migrações versionadas e o leitor de planilha XP em modo de prévia (dry-run).
Ainda não há execução de ordens nem gravação das posições/proventos importados.

## Modelo de dados

| Tabela | Finalidade |
|---|---|
| `portfolio_accounts` | Contas e corretoras (XP, Binance etc.) |
| `portfolio_assets` | Cadastro de ações, BDRs, FIIs, fundos e criptoativos |
| `portfolio_imports` | Auditoria de arquivos e processos de importação |
| `portfolio_positions` | Fotografias de posição por conta e data |
| `portfolio_transactions` | Compras, vendas, taxas, transferências e ajustes |
| `portfolio_income` | Dividendos, JCP e rendimentos, com estado pendente/recebido/cancelado |
| `portfolio_snapshots` | Consolidações patrimoniais históricas |

A posição inicial da XP é uma fotografia da carteira na data do relatório. Ela
não deve ser convertida artificialmente em compras históricas. O preço médio
informado pela corretora é uma referência da fotografia.

## Moedas e mercados

- Binance Spot: ativos cotados em USDT.
- XP/B3: ativos cotados em BRL.
- Consolidação patrimonial: BRL, com conversão cambial explícita quando houver
  ativos em outra moeda.
- Contas são separadas por corretora/mercado para evitar misturar saldos.

## Cuidados contábeis

- Proventos provisionados e recebidos são estados distintos; não somar ambos.
- Rendimentos, dividendos e JCP não são vendas de ativos.
- Não contar USDT simultaneamente como saldo e como parte do valor de uma
  operação. O razão de transações deverá representar corretamente os fluxos.
- Taxas pagas no ativo-base, na moeda de cotação ou em terceiro ativo exigem
  tratamento específico; não devem ser descartadas silenciosamente.
- O custo médio ponderado será usado para acompanhamento de criptoativos, mas
  isso, por si só, não constitui apuração fiscal completa.

## Importador XP

O importador atual lê `imports/xp/PosicaoDetalhada.xlsx`, extrai posições e
proventos e compara os totais do arquivo. A execução é somente leitura:

```bash
python -m portfolio.imports.xp
```

Para outro arquivo:

```bash
python -m portfolio.imports.xp --file /caminho/PosicaoDetalhada.xlsx
```

A importação persistente será uma etapa separada, com prévia, validação,
confirmação explícita, hash do arquivo e deduplicação por linha/evento.

## Testes

```bash
python -m unittest discover -s portfolio/tests -v
```

Todos os testes criam arquivos temporários e planilhas sintéticas.
