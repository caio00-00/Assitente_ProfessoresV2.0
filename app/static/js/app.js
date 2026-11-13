/**
 * Canal Educação v3.0 — App JavaScript
 * Authentication, user profile, toast notifications, utilities.
 */

// ─── Theme Management ──────────────────────────────────────────────

// ─── Ícones (sprite SVG em templates/_icones.html) ──────────────────

/** HTML de um ícone do sprite. Ex.: icone('ok'), icone('alerta', 'ico-lg') */
function icone(nome, classe = '') {
    return `<svg class="ico ${classe}" aria-hidden="true"><use href="#i-${nome}"/></svg>`;
}

/** Nome de cada papel como aparece para as pessoas. */
const NOMES_PAPEIS = {
    admin: 'Administrador', gestor: 'Gestor', coordenador: 'Coordenação', coordenadora: 'Coordenação',
    auditor: 'Auditoria', assistente: 'Assistente de aula',
    diretor_imagem: 'Diretor de imagem', diretor_chefe: 'Diretor-chefe',
};
function nomeDoPapel(papel) {
    if (!papel) return '';
    return NOMES_PAPEIS[papel.toLowerCase()] || (papel.charAt(0).toUpperCase() + papel.slice(1));
}
function iniciais(nome) {
    const partes = String(nome || '').trim().split(/\s+/).filter(Boolean);
    if (!partes.length) return '?';
    return ((partes[0][0] || '') + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase();
}

function updateThemeUI(theme) {
    // O ícone mostra para qual tema o clique leva
    const icon = document.getElementById('theme-icon');
    const text = document.getElementById('theme-text');
    if (theme === 'light') {
        if (icon) icon.setAttribute('href', '#i-lua');
        if (text) text.textContent = 'Tema escuro';
        document.body.classList.add('light-mode');
    } else {
        if (icon) icon.setAttribute('href', '#i-sol');
        if (text) text.textContent = 'Tema claro';
        document.body.classList.remove('light-mode');
    }
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-mode');
    const theme = isLight ? 'light' : 'dark';
    
    // Update UI
    updateThemeUI(theme);
    
    // Save to API
    apiPatch('/api/v1/auth/me/theme', { theme_preference: theme })
        .then(user => {
            if (user) {
                localStorage.setItem('user', JSON.stringify(user));
            }
        })
        .catch(e => console.error('Failed to save theme preference:', e));
}

// ─── Auth Helpers ───────────────────────────────────────────────────

function getToken() {
    return localStorage.getItem('access_token');
}

function getUser() {
    const u = localStorage.getItem('user');
    return u ? JSON.parse(u) : null;
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/';
}

/** Redireciona diretor_imagem / diretor_chefe fora de páginas de relatório de aula. */
function guardClassReportPages() {
    const user = getUser();
    if (!user || !['diretor_imagem', 'diretor_chefe'].includes(user.role)) return;

    const path = window.location.pathname;
    const blocked = ['/dashboard', '/report', '/live-monitor'];
    if (user.role === 'diretor_imagem') {
        blocked.push('/reports-audit');
    }
    if (blocked.some((p) => path === p || path.startsWith(`${p}/`))) {
        window.location.replace('/diretor-imagem/historico');
    }
}

/** Aplica restrições de menu para diretor_imagem / diretor_chefe. */
function applyNavForRole(user) {
    if (!user || !user.role) return;

    const papeisDiretorImagem = ['admin', 'gestor', 'diretor_chefe', 'diretor_imagem'];
    const papeisDiretorChefe = ['admin', 'gestor', 'diretor_chefe'];
    const isDiretorImagem = user.role === 'diretor_imagem';
    const isDiretorChefe = user.role === 'diretor_chefe';
    const isDiretorFluxo = isDiretorImagem || isDiretorChefe;

    const adminNav = document.getElementById('nav-admin');
    if (adminNav) {
        adminNav.style.display = papeisDiretorChefe.includes(user.role) ? 'flex' : 'none';
    }

    const cadastrosNav = document.getElementById('nav-cadastros');
    if (cadastrosNav) {
        cadastrosNav.style.display = ['admin', 'gestor'].includes(user.role) ? 'flex' : 'none';
    }

    const configNav = document.getElementById('nav-configuracoes');
    if (configNav) {
        configNav.style.display = ['admin', 'gestor'].includes(user.role) ? 'flex' : 'none';
    }

    // "Nova Aula" saiu: relatório só a partir da Grade Horária (gestão de grade pelo diretor-chefe)

    const diretorImagemHistNav = document.getElementById('nav-diretor-imagem-historico');
    if (diretorImagemHistNav) {
        diretorImagemHistNav.style.display = papeisDiretorImagem.includes(user.role) ? 'flex' : 'none';
    }

    const agendaEstudiosNav = document.getElementById('nav-agenda-estudios');
    if (agendaEstudiosNav) {
        // Admin e Diretor-Chefe editam; pedagógico, auditoria e diretores de imagem só consultam
        const papeisAgenda = ['admin', 'diretor_chefe', 'gestor', 'coordenador', 'auditor'];
        agendaEstudiosNav.style.display = papeisAgenda.includes(user.role) ? 'flex' : 'none';
    }

    // v4: títulos de seção do menu aparecem só quando há algum item visível nelas
    const secaoImagem = document.getElementById('nav-secao-imagem');
    if (secaoImagem) secaoImagem.style.display = papeisDiretorImagem.includes(user.role) ? 'block' : 'none';
    const secaoGestao = document.getElementById('nav-secao-gestao');
    if (secaoGestao) secaoGestao.style.display = papeisDiretorChefe.includes(user.role) ? 'block' : 'none';

    const diretorImagemPerguntasNav = document.getElementById('nav-diretor-imagem-perguntas');
    if (diretorImagemPerguntasNav) {
        diretorImagemPerguntasNav.style.display = papeisDiretorChefe.includes(user.role) ? 'flex' : 'none';
    }

    if (isDiretorFluxo) {
        ['nav-dashboard', 'nav-live-monitor'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
        const gradeNav = document.getElementById('nav-grade');
        if (gradeNav) {
            gradeNav.style.display = 'flex';
            // Diretor de imagem: grade por estúdio (onde está escalado), não por turma
            if (isDiretorImagem) {
                gradeNav.href = '/diretor-imagem/grade';
                const texto = gradeNav.querySelector('.nav-texto');
                if (texto) texto.textContent = 'Minha escala';
                if (window.location.pathname === '/diretor-imagem/grade') gradeNav.classList.add('active');
            }
        }
        const auditNav = document.getElementById('nav-reports-audit');
        if (auditNav) {
            auditNav.style.display = isDiretorChefe ? 'flex' : 'none';
        }
        guardClassReportPages();
    }
}

async function loadUserProfile() {
    const token = getToken();
    if (!token) return;

    try {
        const res = await fetch('/api/v1/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!res.ok) {
            logout();
            return;
        }

        const user = await res.json();
        localStorage.setItem('user', JSON.stringify(user));

        const nameEl = document.getElementById('user-name');
        const roleEl = document.getElementById('user-role');
        if (nameEl) nameEl.textContent = user.full_name;
        if (roleEl) roleEl.textContent = nomeDoPapel(user.role);
        const avatarEl = document.getElementById('user-avatar');
        if (avatarEl) avatarEl.textContent = iniciais(user.full_name);

        applyNavForRole(user);

        // Apply theme from user profile
        updateThemeUI(user.theme_preference);
    } catch (e) {
        console.error('Failed to load profile:', e);
    }
}

// ─── Rótulo de turma sem ambiguidade ───────────────────────────────

/**
 * Rótulos únicos para listas de turmas (filtros, selects).
 * Normal: "EM 1 TI (INTEGRAL)". Quando duas turmas ficariam com o mesmo
 * rótulo (ex.: "EJA V QP" e "EJA V QP ADM", ambas "EJA V (NOITE)"), acrescenta
 * a série/módulo; se ainda repetir, o nome completo da turma.
 * Retorna { id: rótulo }.
 */
function rotulosDeTurmas(turmas) {
    const lista = turmas || [];
    const nomeCurto = t => (t.nomenclatura_padrao || t.nome || '').trim();
    const turno = t => (t.turno ? ` (${t.turno})` : '');
    const contar = fn => lista.reduce((acc, t) => { const k = fn(t).toLowerCase(); acc[k] = (acc[k] || 0) + 1; return acc; }, {});
    const nivel1 = t => `${nomeCurto(t)}${turno(t)}`;
    const c1 = contar(nivel1);
    const nivel2 = t => {
        if (c1[nivel1(t).toLowerCase()] < 2) return nivel1(t);
        const serie = (t.serie_modulo || '').trim();
        return serie && serie.toLowerCase() !== nomeCurto(t).toLowerCase()
            ? `${nomeCurto(t)} — ${serie}${turno(t)}` : nivel1(t);
    };
    const c2 = contar(nivel2);
    const saida = {};
    lista.forEach(t => {
        let rotulo = nivel2(t);
        if (c2[rotulo.toLowerCase()] > 1 && t.nome && t.nome.trim().toLowerCase() !== nomeCurto(t).toLowerCase()) {
            rotulo = `${rotulo} · ${t.nome.trim()}`;
        }
        saida[t.id] = rotulo;
    });
    return saida;
}

// ─── Toast Notifications ────────────────────────────────────────────

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.display = 'flex';
    toast.style.justifyContent = 'space-between';
    toast.style.alignItems = message.includes('\n') ? 'flex-start' : 'center';
    toast.style.gap = '12px';
    toast.style.cursor = 'pointer';

    const textSpan = document.createElement('span');
    textSpan.textContent = message;
    textSpan.style.whiteSpace = 'pre-line';
    textSpan.style.flex = '1';
    toast.appendChild(textSpan);

    const closeBtn = document.createElement('span');
    closeBtn.textContent = '✕';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.style.fontSize = '0.9rem';
    closeBtn.style.opacity = '0.7';
    toast.appendChild(closeBtn);

    const dismiss = () => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    };

    toast.onclick = dismiss;
    container.appendChild(toast);
    // some sozinho: duração reduzida (sucesso/info: 2s, erro/aviso: 2.8s); passar o mouse segura o alerta
    const tempo = (type === 'error' || type === 'warning') ? 2800 : 2000;
    let timer = setTimeout(dismiss, tempo);
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', () => { timer = setTimeout(dismiss, 1000); });
}

// ─── API Helpers ────────────────────────────────────────────────────

function formatApiDetail(detail) {
    if (!detail) return 'Erro na requisição.';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        const msgs = detail.map((e) => {
            const loc = (e.loc || []).slice(1).join(' › ') || 'campo';
            return `${loc}: ${e.msg}`;
        });
        return msgs.length === 1 ? msgs[0] : 'Corrija os seguintes campos:\n• ' + msgs.join('\n• ');
    }
    return String(detail);
}

async function apiGet(url) {
    const token = getToken();
    const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.status === 401) { logout(); return null; }
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

async function apiPost(url, body) {
    const token = getToken();
    const res = await fetch(url, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
    });
    if (res.status === 401) { logout(); return null; }
    if (!res.ok) {
        const data = await res.json();
        throw new Error(formatApiDetail(data.detail) || `API error: ${res.status}`);
    }
    return res.json();
}

async function apiPatch(url, body = {}) {
    const token = getToken();
    const res = await fetch(url, {
        method: 'PATCH',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
    });
    if (res.status === 401) { logout(); return null; }
    if (!res.ok) {
        const data = await res.json();
        throw new Error(formatApiDetail(data.detail) || `API error: ${res.status}`);
    }
    return res.json();
}

// ─── Horário de slot (Grade / IDR) ─────────────────────────────────

const IDR_HORARIO_MAP = {
    TI: {
        '1º Horário': ['07:30', '08:30'],
        '2º Horário': ['08:30', '09:30'],
        '3º Horário': ['09:50', '10:50'],
        '4º Horário': ['10:50', '11:50'],
        '5º Horário': ['12:50', '13:50'],
        '6º Horário': ['13:50', '14:50'],
        '7º Horário': ['15:10', '16:10'],
        '8º Horário': ['16:10', '17:10'],
    },
    MANHA: {
        '1º Horário': ['07:00', '08:00'],
        '2º Horário': ['08:00', '09:00'],
        '3º Horário': ['09:00', '10:00'],
        '4º Horário': ['10:20', '11:20'],
        '5º Horário': ['11:20', '12:20'],
    },
    TARDE: {
        '1º Horário': ['13:00', '14:00'],
        '2º Horário': ['14:00', '15:00'],
        '3º Horário': ['15:00', '16:00'],
        '4º Horário': ['16:20', '17:20'],
        '5º Horário': ['17:20', '18:20'],
    },
    NOITE_EM: {
        '1º Horário': ['18:30', '19:15'],
        '2º Horário': ['19:15', '20:00'],
        '3º Horário': ['20:00', '20:45'],
        '4º Horário': ['20:45', '21:30'],
        '5º Horário': ['21:30', '22:15'],
    },
    EJA: {
        '1º Horário': ['18:00', '19:00'],
        '2º Horário': ['19:00', '20:00'],
        '3º Horário': ['20:00', '21:00'],
        '4º Horário': ['21:00', '22:00'],
    },
};

const IDR_DEFAULT_HORARIOS = [
    '1º Horário', '2º Horário', '3º Horário', '4º Horário',
    '5º Horário', '6º Horário', '7º Horário', '8º Horário',
];

function isTiNomenclaturaHorario(nomenclatura) {
    // 'EM 1 TI' → true; 'EM 1 TIM' (manhã) → false
    return /(^|[\s-])TI($|[\s-])/.test(String(nomenclatura || '').toUpperCase());
}

function getTipoTurmaFromNomenclaturaHorario(nomenclatura) {
    const n = String(nomenclatura || '').toUpperCase();
    if (n.includes('EJA')) return 'EJA';
    if (isTiNomenclaturaHorario(n)) return 'TI';
    if (n.includes('MANHA') || n.includes('MANHÃ')) return 'MANHA';
    if (n.includes('TARDE')) return 'TARDE';
    if (n.includes('NOITE')) return 'NOITE_EM';
    return 'NOITE_EM';
}

function getTipoPorTurnoHorario(turno, nomenclatura) {
    const t = String(turno || '').toUpperCase();
    const n = String(nomenclatura || '').toUpperCase();
    if (t.includes('INTEGRAL') || isTiNomenclaturaHorario(n)) return 'TI';
    if (t.includes('MANHÃ') || t.includes('MANHA')) return 'MANHA';
    if (t.includes('TARDE')) return 'TARDE';
    if (t.includes('NOITE')) return (n.includes('EJA') ? 'EJA' : 'NOITE_EM');
    return getTipoTurmaFromNomenclaturaHorario(nomenclatura);
}

function faixaFromOrdinalHorario(tipo, ordinal) {
    const slot = IDR_HORARIO_MAP[tipo] && IDR_HORARIO_MAP[tipo][ordinal];
    return slot ? `${slot[0]} às ${slot[1]}` : null;
}

function horariosOrdinaisForTipoHorario(tipo) {
    if (!tipo || !IDR_HORARIO_MAP[tipo]) return IDR_DEFAULT_HORARIOS.slice();
    return Object.keys(IDR_HORARIO_MAP[tipo]);
}

function _turnoKeyHorario(turno) {
    const t = String(turno || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
    if (t.includes('MANHA')) return 'MANHA';
    if (t.includes('TARDE')) return 'TARDE';
    if (t.includes('NOITE')) return 'NOITE';
    return '';
}

function _turnoDoInicioHorario(hhmm) {
    const [h, m] = String(hhmm || '00:00').split(':').map(Number);
    const min = h * 60 + m;
    if (min < 12 * 60 + 30) return 'MANHA';
    if (min < 18 * 60) return 'TARDE';
    return 'NOITE';
}

/**
 * Horários padrão (sem grade) do turno, com numeração da modalidade:
 * TI é contínuo (tarde = 5º–8º); regular/técnico/EJA reiniciam no 1º.
 * Sem tipo (turma não escolhida), usa a tabela do próprio turno.
 */
function horariosPadraoDoTurno(tipo, turno) {
    const turnoKey = _turnoKeyHorario(turno);
    let t = tipo;
    if (!t) {
        if (turnoKey === 'MANHA') t = 'MANHA';
        else if (turnoKey === 'TARDE') t = 'TARDE';
        else if (turnoKey === 'NOITE') t = 'NOITE_EM';
    }
    if (!t || !IDR_HORARIO_MAP[t]) {
        return IDR_DEFAULT_HORARIOS.map(o => ({ value: o, inicio: null, fim: null, faixa: null }));
    }
    let itens = Object.entries(IDR_HORARIO_MAP[t]).map(([ord, [ini, fim]]) => ({
        value: ord, inicio: ini, fim, faixa: `${ini} às ${fim}`,
    }));
    if (t === 'TI' && turnoKey) {
        const doTurno = itens.filter(o => _turnoDoInicioHorario(o.inicio) === turnoKey);
        if (doTurno.length) itens = doTurno;
    }
    return itens;
}

function normalizeHorarioAulaValor(valor, tipo) {
    const v = String(valor || '').trim();
    if (!v) return '';
    if (v.toLowerCase() === 'gravação') return 'GRAVAÇÃO';

    const ordinals = horariosOrdinaisForTipoHorario(tipo);
    const ordinalMatch = ordinals.find(o => o.toLowerCase() === v.toLowerCase());
    if (ordinalMatch) return ordinalMatch;

    if (v.includes('às') && tipo) {
        const norm = v.replace(/\s+/g, ' ').trim();
        for (const ord of ordinals) {
            if (faixaFromOrdinalHorario(tipo, ord) === norm) return ord;
        }
    }
    return v;
}

function _formatTimeShort(t) {
    if (!t) return null;
    return String(t).substring(0, 5);
}

function resolveHorarioSlotTimes(horario_aula, turno, turma_nome, start_time, end_time) {
    const stApi = _formatTimeShort(start_time);
    const etApi = _formatTimeShort(end_time);
    if (stApi && etApi) {
        return { inicio: stApi, fim: etApi, faixa: `${stApi} às ${etApi}` };
    }

    const v = String(horario_aula || '').trim();
    if (!v) return { inicio: null, fim: null, faixa: '—' };
    if (v.toLowerCase() === 'gravação') return { inicio: null, fim: null, faixa: 'GRAVAÇÃO' };

    if (v.includes('às')) {
        const parts = v.split('às').map(s => s.trim());
        const inicio = parts[0] ? parts[0].substring(0, 5) : null;
        const fim = parts[1] ? parts[1].substring(0, 5) : null;
        return { inicio, fim, faixa: v };
    }

    const tipo = getTipoPorTurnoHorario(turno, turma_nome);
    const slot = IDR_HORARIO_MAP[tipo] && IDR_HORARIO_MAP[tipo][v];
    if (slot) {
        return { inicio: slot[0], fim: slot[1], faixa: `${slot[0]} às ${slot[1]}` };
    }
    return { inicio: null, fim: null, faixa: v };
}

function resolveHorarioFaixa(horario_aula, turno, turma_nome, start_time, end_time) {
    return resolveHorarioSlotTimes(horario_aula, turno, turma_nome, start_time, end_time).faixa;
}

// ─── Initialization ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const user = getUser();
    if (user && user.theme_preference) {
        updateThemeUI(user.theme_preference);
    }
    if (user) {
        applyNavForRole(user);
    }
    loadUserProfile();
});
