# Importação da carteira XP

## Objetivo

O módulo permite ler uma planilha de posição detalhada da XP, validar
os dados financeiros e persistir posições, proventos e snapshots em
um banco SQLite.

A importação é realizada separadamente do scanner de criptomoedas.
Os dados da carteira não são enviados ao ThingsBoard.

## Arquivo esperado

A planilha deve conter:

- Aba `Sua carteira`.
- Cabeçalho com conta e data na célula `F1` (pode estar mesclada com `G1`).

Caminho padrão:

```text
imports/xp/PosicaoDetalhada.xlsx
```

A pasta `imports/xp/` é ignorada pelo Git. Não versione a planilha
real nem inclua dados pessoais em pacotes compartilhados.

## Prévia e validação

Ative o ambiente virtual:

```bash
source .venv/bin/activate
```

Execute:

```bash
python -m portfolio.imports.xp
```

Para indicar outro arquivo:

```bash
python -m portfolio.imports.xp --file /caminho/PosicaoDetalhada.xlsx
```

O parser apresenta:

- Conta e data do relatório.
- Posições e valores.
- Proventos provisionados.
- Subtotais por grupo.
- Total patrimonial informado pela XP.

O processo verifica a consistência dos registros e dos totais.
Se alguma conferência falhar, a importação é bloqueada.

A prévia não grava dados no SQLite.

## Banco de dados e migrações

O módulo de carteira utiliza o mesmo banco SQLite do projeto.

Banco padrão:

```text
data/crypto_market.db
```

É possível indicar outro banco pela variável de ambiente:

```bash
export CRYPTO_DB_PATH=/caminho/crypto_market.db
```

Para consultar o estado das migrações:

```bash
python -m portfolio.migrate --status
```

Para aplicar migrações:

```bash
python -m portfolio.migrate
```

As migrações são versionadas e idempotentes. As tabelas existentes
do scanner são preservadas.

## Persistência da importação

A persistência é implementada em:

```text
portfolio/imports/xp_persistence.py
```

A função principal é:

```python
from portfolio.imports.xp import parse_workbook
from portfolio.imports.xp_persistence import import_xp_data

data = parse_workbook("imports/xp/PosicaoDetalhada.xlsx")
result = import_xp_data(data)

print(result)
```

A importação:

1. Verifica se as validações do parser foram aprovadas.
2. Restringe a conta XP autorizada.
3. Identifica o arquivo pelo SHA-256.
4. Impede a reimportação do mesmo arquivo.
5. Impede dois snapshots da mesma conta, data e moeda.
6. Cadastra ativos e posições.
7. Registra proventos provisionados.
8. Cria um snapshot patrimonial.
9. Confirma todas as gravações em uma única transação.

Se ocorrer uma falha, a transação inteira é revertida.

**Atenção:** a função `import_xp_data` grava no banco indicado. Antes de
utilizá-la na base de produção, faça backup e confira o arquivo e a conta.

## Deduplicação de proventos

Os proventos possuem uma chave única calculada com:

- Conta.
- Ativo.
- Tipo de evento.
- Quantidade de referência.
- Valor bruto e líquido.
- Data prevista de pagamento.
- Ocorrência do registro no arquivo.

A chave permite reconhecer eventos repetidos entre snapshots diferentes.

O mesmo arquivo é bloqueado pelo SHA-256. Um arquivo diferente para
a mesma data de snapshot também é bloqueado.

A deduplicação foi testada com cenários de snapshots distintos,
pagamentos em datas diferentes e ocorrências idênticas no mesmo arquivo.

## Estrutura das tabelas da carteira

| Tabela | Finalidade |
|---|---|
| `portfolio_accounts` | Contas de investimento |
| `portfolio_assets` | Cadastro de ativos |
| `portfolio_imports` | Histórico de importações |
| `portfolio_positions` | Posições por snapshot |
| `portfolio_income` | Dividendos, JCP e rendimentos |
| `portfolio_transactions` | Movimentações |
| `portfolio_snapshots` | Consolidação patrimonial |

## Testes automatizados

Execute todos os testes:

```bash
python -m unittest discover -s portfolio/tests -v
```

Os testes utilizam bancos SQLite temporários. Não precisam gravar
na base de produção.

A suíte cobre:

- Conexão e configuração SQLite.
- Migrações e preservação das tabelas do scanner.
- Leitura e validação da planilha.
- Importação de posições e proventos.
- Reimportação e deduplicação.
- Rejeição de conta não autorizada.
- Rollback após falhas.

## Cuidados

- Não versione planilhas reais da XP.
- Não envie dados pessoais para o Git.
- Faça backup antes de importar na base de produção.
- Não execute testes diretamente no banco de produção.
- Confira os totais e a integridade SQLite após qualquer importação.
