# Banco de dados e migrações

## Um único banco para scanner e carteira

O módulo de carteira utiliza o banco já existente do Crypto Quant Monitor:

`data/crypto_market.db`

Ele **não cria um segundo banco** e não recria as tabelas do scanner. As tabelas
`candles`, `signals`, `scanner_runs`, `scanner_run_assets`, `history_audit` e
`signal_outcomes` permanecem sob responsabilidade do scanner. As tabelas da
carteira usam o prefixo `portfolio_`.

O caminho padrão é relativo à raiz do projeto. Também pode ser definido por
`CRYPTO_DB_PATH` ou informado com `--db` nos comandos de migração.

## Antes da primeira migração no Raspberry Pi

Pare temporariamente o agendador do scanner para reduzir concorrência durante
a manutenção e faça uma cópia do banco:

```bash
sudo systemctl stop crypto-monitor.timer
mkdir -p backups/database
cp data/crypto_market.db "backups/database/crypto_market_before_portfolio_$(date +%Y%m%d_%H%M%S).db"
```

A migração pode ser executada com o serviço parado. Em seguida:

```bash
source .venv/bin/activate
python -m portfolio.migrate
python -m portfolio.migrate --status
python -m unittest discover -s portfolio/tests -v
```

Verifique a integridade do banco:

```bash
python - <<'PY'
import sqlite3
con = sqlite3.connect('data/crypto_market.db')
print('integrity_check:', con.execute('PRAGMA integrity_check').fetchone()[0])
print('scanner_runs:', con.execute('SELECT COUNT(*) FROM scanner_runs').fetchone()[0])
print('portfolio tables:', con.execute("""
    SELECT name FROM sqlite_master
    WHERE type='table' AND name LIKE 'portfolio_%'
    ORDER BY name
""").fetchall())
con.close()
PY
```

Se estiver tudo correto, reative o timer:

```bash
sudo systemctl start crypto-monitor.timer
sudo systemctl status crypto-monitor.timer --no-pager
```

## Como as migrações funcionam

- `schema_migrations` registra a versão e a data de cada migração aplicada.
- Cada versão é aplicada uma única vez; executar o comando novamente é seguro.
- A migração inicial cria as tabelas `portfolio_*` que ainda não existirem.
- A migração seguinte garante os campos `invested_amount` e
  `net_liquidation_value` em `portfolio_positions`, sem apagar dados existentes.
- As migrações não executam `DROP TABLE`, não apagam linhas e não alteram o
  esquema das tabelas do scanner.
- O helper `portfolio.db` habilita chaves estrangeiras, WAL e `busy_timeout`.

Os testes usam bancos temporários e dados sintéticos. Eles não abrem nem alteram
o banco de produção ou a planilha pessoal da XP.

## Recuperação

Se uma migração falhar, não apague tabelas manualmente. Preserve o arquivo de
banco e o log do erro. A cópia criada antes da migração permite restaurar o
estado anterior, se necessário. Antes de restaurar, pare o scanner e copie
juntos o arquivo principal e, se existirem, os arquivos `-wal` e `-shm` após
encerrar todos os processos que usam o SQLite.
