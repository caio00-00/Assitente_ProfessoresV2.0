# ════════════════════════════════════════════════════════════════════
#  Canal Educação v4 — importa um dump de HML no Postgres LOCAL do Docker
#  e anonimiza logo em seguida. (Windows / PowerShell)
#
#  Uso, na raiz do projeto:
#     .\scripts\dados_hml\importar_hml.ps1 -Arquivo .\scripts\dados_hml\hml_20261111_1030.dump
#     .\scripts\dados_hml\importar_hml.ps1 -Arquivo <arquivo> -ManterDump
#
#  Se o PowerShell bloquear o script:
#     powershell -ExecutionPolicy Bypass -File .\scripts\dados_hml\importar_hml.ps1 -Arquivo <arquivo>
#
#  ATENÇÃO: apaga e recria o banco local (POSTGRES_DB do .env).
# ════════════════════════════════════════════════════════════════════
param(
    [Parameter(Mandatory = $true)][string]$Arquivo,
    [switch]$ManterDump
)
# 'Continue' de propósito: no Windows PowerShell 5.1, 'Stop' transforma o progresso
# que o docker escreve no stderr em erro. Cada comando é conferido pelo código de saída.
$ErrorActionPreference = 'Continue'

function Passo($msg) { Write-Host $msg -ForegroundColor Cyan }
function Rodar {
    param([string[]]$Comando)
    & $Comando[0] $Comando[1..($Comando.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $($Comando -join ' ')" }
}

if (-not (Test-Path $Arquivo)) { throw "Arquivo não encontrado: $Arquivo" }
$pasta = (Resolve-Path (Split-Path $Arquivo -Parent)).Path
if (-not $pasta.Replace('\', '/').EndsWith('scripts/dados_hml')) {
    throw 'Coloque o dump dentro de scripts\dados_hml\ (é a pasta montada no container).'
}
if (-not (Test-Path '.env')) { throw 'Rode na raiz do projeto (onde fica o .env).' }

# Lê o .env (só as chaves que importam)
$envs = @{}
Get-Content .env | Where-Object { $_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$' } | ForEach-Object {
    $envs[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
}
$U  = if ($envs['POSTGRES_USER']) { $envs['POSTGRES_USER'] } else { 'assistente_professores' }
$DB = if ($envs['POSTGRES_DB'])   { $envs['POSTGRES_DB'] }   else { 'postgres-prd' }   # mesmo padrão do docker-compose.yml
$nome = Split-Path $Arquivo -Leaf

Passo '[1/5] subindo o Postgres local'
Rodar @('docker', 'compose', 'up', '-d', 'db')
do {
    Start-Sleep -Seconds 2
    docker compose exec -T db pg_isready -U $U -d $DB *> $null
} while ($LASTEXITCODE -ne 0)

Passo '[2/5] parando a API e o worker (eles seguram conexões com o banco)'
docker compose stop api worker beat *> $null

Passo "[3/5] recriando o banco $DB"
# O SQL vai pela entrada padrão: o PowerShell 5.1 estraga aspas em argumentos de programas externos.
$sqlRecriar = "DROP DATABASE IF EXISTS `"$DB`" WITH (FORCE);`nCREATE DATABASE `"$DB`";`n"
$sqlRecriar | docker compose exec -T db psql -U $U -d postgres -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) { throw "Não consegui recriar o banco $DB." }
# O dump traz o próprio "CREATE SCHEMA public"; sem isto o pg_restore para no primeiro comando.
"DROP SCHEMA public CASCADE;`n" | docker compose exec -T db psql -U $U -d $DB -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) { throw 'Não consegui limpar o schema public.' }

Passo "[4/5] restaurando $nome"
Rodar @('docker', 'compose', 'exec', '-T', 'db', 'pg_restore', '-U', $U, '-d', $DB,
        '--no-owner', '--no-privileges', '--exit-on-error', "/dados_hml/$nome")

Passo '[5/5] anonimizando (nomes, e-mails, senhas)'
Rodar @('docker', 'compose', 'exec', '-T', '-e', 'PGOPTIONS=-c canal.permitir_anonimizar=sim', 'db',
        'psql', '-U', $U, '-d', $DB, '-v', 'ON_ERROR_STOP=1', '-f', '/dados_hml/anonimizar.sql')

if (-not $ManterDump) {
    Remove-Item $Arquivo -Force
    Write-Host "Dump com dados reais apagado ($nome)."
}

Write-Host ''
Write-Host 'Pronto. Suba a API (ela aplica as migrações da v4 sozinha):' -ForegroundColor Green
Write-Host '  docker compose up -d api        # http://localhost:8000'
Write-Host 'Login: admin@teste.local  /  Teste@123   (os demais: <papel>001@teste.local)'
