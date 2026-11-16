# Importação da posição XP

## Arquivo esperado

O leitor foi desenvolvido para a planilha XP com a aba `Sua carteira` e o
cabeçalho que contém conta e data na célula `F1` (no relatório, `F1:G1` pode
estar mesclada). O arquivo pessoal deve ficar localmente em
`imports/xp/PosicaoDetalhada.xlsx`.

A pasta `imports/xp/` é ignorada pelo Git. Não versione a planilha real nem
inclua-a em ZIPs compartilhados.

## Executar prévia

```bash
python -m portfolio.imports.xp
```

Ou indique outro caminho:

```bash
python -m portfolio.imports.xp --file /caminho/PosicaoDetalhada.xlsx
```

O programa apresenta posições, preço médio, valor de mercado e proventos
provisionados. Também compara as quantidades e os totais extraídos com os
subtotais e o patrimônio informado pela XP. Se alguma conferência falhar, o
processo termina com código diferente de zero.

**Esta versão não grava nada no SQLite.** A saída `Nenhum dado foi gravado no
banco de dados` é intencional. A importação persistente só deve ser habilitada
após a validação do mapeamento e da regra de deduplicação.

## Testes sem dados pessoais

O teste automatizado cria uma planilha sintética em diretório temporário e
verifica o cabeçalho, os 17 registros de posição, os 10 proventos e as somas.
Ele não depende do arquivo real da conta.
