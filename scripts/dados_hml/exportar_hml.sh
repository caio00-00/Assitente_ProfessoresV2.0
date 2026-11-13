#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  Canal Educação v4 — exporta o banco de HML (roda NO SERVIDOR do Dokploy)
#
#  Uso (no servidor, via SSH):
#     bash exportar_hml.sh                 # lista os containers Postgres
#     bash exportar_hml.sh <container>     # gera /tmp/hml_AAAAMMDD_HHMM.dump
#
#  Só LÊ o banco (pg_dump). Usuário, senha e nome do banco vêm das
#  variáveis do próprio container, então nenhuma senha aparece aqui.
#  O arquivo gerado tem dados reais: baixe, importe e apague.
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

CONTAINER="${1:-}"
if [ -z "$CONTAINER" ]; then
  echo "Informe o container do Postgres de HML. Candidatos:"
  docker ps --format '  {{.Names}}\t{{.Image}}' | grep -i postgres || echo "  (nenhum container com imagem postgres rodando)"
  exit 1
fi

SAIDA="/tmp/hml_$(date +%Y%m%d_%H%M).dump"
echo "[exportar] lendo $CONTAINER ..."
docker exec "$CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "${POSTGRES_DB:-$POSTGRES_USER}" \
    --format=custom --schema=public --no-owner --no-privileges' > "$SAIDA"
chmod 600 "$SAIDA"

VERSAO=$(docker exec "$CONTAINER" sh -c 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-$POSTGRES_USER}" -Atc "show server_version"' | cut -d. -f1)
echo "[exportar] pronto: $SAIDA ($(du -h "$SAIDA" | cut -f1))"
echo "[exportar] versão do Postgres de HML: $VERSAO  →  no .env local use POSTGRES_VERSION=$VERSAO"
echo
echo "No seu computador:"
echo "  scp <usuario>@<servidor>:$SAIDA scripts/dados_hml/"
echo "Depois de baixar, apague daqui:  rm $SAIDA"
