/**
 * Integração "Planilhas Cursos Técnicos" ↔ Assistente de Professores.
 *
 * Para cada ABA (= disciplina), busca as aulas no Assistente (banco PRD) e
 * preenche as colunas:
 *   NOME ARQUIVO | LINK VÍDEO (VIMEO) | LINK VÍDEO (DRIVE) | LINK PDF
 *
 * O nome da ABA é usado como nome da disciplina (casamento normalizado no
 * servidor: ignora acento/maiúsculas/separadores).
 *
 * ── INSTALAÇÃO (uma vez por planilha) ─────────────────────────────────────
 *  1. Abra a planilha → menu Extensões → Apps Script.
 *  2. Apague o conteúdo padrão, cole TODO este arquivo e salve (💾).
 *  3. Engrenagem (Configurações do projeto) → "Propriedades do script" →
 *     "Adicionar propriedade":
 *        Nome:  X_API_KEY
 *        Valor: <a chave EXTERNAL_API_KEY do Assistente>
 *  4. Volte à planilha e recarregue a página (F5).
 *  5. Vai aparecer o menu "🔄 Assistente". Clique em "Atualizar todas as abas".
 *     (Na 1ª vez o Google pede autorização — aceite.)
 */

const ASSISTENTE_URL = 'https://assistentes.orossolucoes.com.br';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🔄 Assistente')
    .addItem('Atualizar todas as abas', 'atualizarTodasAsAbas')
    .addItem('Atualizar aba atual', 'atualizarAbaAtual')
    .addToUi();
}

function _apiKey_() {
  const k = PropertiesService.getScriptProperties().getProperty('X_API_KEY');
  if (!k) throw new Error('Configure X_API_KEY nas Propriedades do script (Configurações do projeto).');
  return k;
}

function _buscarDisciplina_(disciplina) {
  const url = ASSISTENTE_URL +
    '/api/v1/external/aulas-por-disciplina?disciplina=' + encodeURIComponent(disciplina);
  const resp = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: { 'X-API-Key': _apiKey_() },
    muteHttpExceptions: true
  });
  const code = resp.getResponseCode();
  if (code !== 200) {
    throw new Error('HTTP ' + code + ': ' + resp.getContentText().slice(0, 200));
  }
  return JSON.parse(resp.getContentText());
}

/** Preenche UMA aba. Retorna {casada, total}. */
function _preencherAba_(sheet) {
  const disciplina = sheet.getName().trim();
  const data = _buscarDisciplina_(disciplina);

  // Limpa as linhas de dados, preservando o cabeçalho (linha 1).
  const lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, 4).clearContent();
  }

  const linhas = (data && data.linhas) || [];
  if (linhas.length) {
    const values = linhas.map(function (l) {
      return [l.nome_arquivo || '', l.vimeo_url || '', l.drive_url || '', l.pdf_url || ''];
    });
    sheet.getRange(2, 1, values.length, 4).setValues(values);
  }
  return { casada: data ? data.disciplina_casada : null, total: linhas.length };
}

function atualizarTodasAsAbas() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const sheets = ss.getSheets();
  let totalAulas = 0;
  const semMatch = [];
  const erros = [];

  sheets.forEach(function (sheet) {
    try {
      const r = _preencherAba_(sheet);
      totalAulas += r.total;
      if (!r.casada) semMatch.push(sheet.getName());
    } catch (e) {
      erros.push(sheet.getName() + ': ' + e.message);
    }
  });

  let msg = sheets.length + ' aba(s) processada(s); ' + totalAulas + ' aula(s) escrita(s).';
  if (semMatch.length) msg += '\n\nDisciplinas NÃO encontradas no Assistente:\n- ' + semMatch.join('\n- ');
  if (erros.length) msg += '\n\nErros:\n- ' + erros.join('\n- ');
  ui.alert('Atualização concluída', msg, ui.ButtonSet.OK);
}

function atualizarAbaAtual() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const ui = SpreadsheetApp.getUi();
  try {
    const r = _preencherAba_(sheet);
    const head = r.casada ? ('Disciplina casada: ' + r.casada + '\n') : 'Disciplina NÃO encontrada no Assistente.\n';
    ui.alert('Aba "' + sheet.getName() + '"', head + r.total + ' aula(s) escrita(s).', ui.ButtonSet.OK);
  } catch (e) {
    ui.alert('Erro', e.message, ui.ButtonSet.OK);
  }
}
