#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  Canal Educação v4 — importa um dump de HML no Postgres LOCAL do Docker
#  e anonimiza logo em seguida. (Linux, macOS ou Git Bash no Windows)
#
#  Uso, na raiz do projeto:
#     bash scripts/dados_hml/importar_hml.sh scripts/dados_hml/hml_20261111_1030.dump
#     bash scripts/dados_hml/importar_hml.sh <arquivo> --manter-dump
#
#  ATENÇÃO: apaga e recria o banco local (POSTGRES_DB do .env).
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

ARQUIVO="${1:-}"
MANTER="${2:-}"
[ -n "$ARQUIVO" ] && [ -f "$ARQUIVO" ] || { echo "Uso: $0 scripts/dados_hml/<arquivo>.dump [--manter-dump]"; exit 1; }
case "$(cd "$(dirname "$ARQUIVO")" && pwd)" in
  */scripts/dados_hml) ;;
  *) echo "Coloque o dump dentro de scripts/dados_hml/ (é a pasta montada no container)."; exit 1 ;;
esac
[ -f .env ] || { echo "Rode na raiz do projeto (onde fica o .env)."; exit 1; }

set -a; . ./.env; set +a
U="${POSTGRES_USER:-assistente_professores}"
DB="${POSTGRES_DB:-postgres-prd}"   # mesmo padrão do docker-compose.yml
NOME="$(basename "$ARQUIVO")"

echo "[1/5] subindo o Postgres local"
docker compose up -d db
until docker compose exec -T db pg_isready -U "$U" -d "$DB" >/dev/null 2>&1; do sleep 2; done

echo "[2/5] parando a API e o worker (eles seguram conexões com o banco)"
docker compose stop api worker beat >/dev/null 2>&1 || true

echo "[3/5] recriando o banco $DB"
docker compose exec -T db psql -U "$U" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$DB\" WITH (FORCE);" -c "CREATE DATABASE \"$DB\";"
# O dump traz o próprio "CREATE SCHEMA public"; sem isto o pg_restore para no primeiro comando.
docker compose exec -T db psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE;"

echo "[4/5] restaurando $NOME"
docker compose exec -T db pg_restore -U "$U" -d "$DB" --no-owner --no-privileges --exit-on-error "/dados_hml/$NOME"

echo "[5/5] anonimizando (nomes, e-mails, senhas)"
docker compose exec -T -e PGOPTIONS="-c canal.permitir_anonimizar=sim" db \
  psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 -f /dados_hml/anonimizar.sql

if [ "$MANTER" != "--manter-dump" ]; then
  rm -f "$ARQUIVO"
  echo "Dump com dados reais apagado ($NOME)."
fi

echo
echo "Pronto. Suba a API (ela aplica as migrações da v4 sozinha):"
echo "  docker compose up -d api        # http://localhost:8000"
echo "Login: admin@teste.local  /  Teste@123   (os demais: <papel>001@teste.local)"
