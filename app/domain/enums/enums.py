"""
Canal Educação v3.0 — Domain Enums.
Todos os Enumeradores do domínio conforme especificação técnica v3.0.
Atualizado com valores completos do RequisitosAdicionais.

v3.1: adiciona fluxo de validação de relatórios por Coordenação
(RASCUNHO -> AGUARDANDO_VALIDACAO -> VALIDADO) e o papel COORDENADOR.
"""

from enum import Enum


class TurnoEnum(str, Enum):
    MANHA = "Manhã"
    TARDE = "Tarde"
    NOITE = "Noite"
    FDS_MANHA = "FDS manhã"
    FDS_TARDE = "FDS tarde"
    FDS_NOITE = "FDS noite"
    OUTRO = "Outro"


class EstudioEnum(str, Enum):
    ESTUDIO_01 = "Estúdio 01"
    ESTUDIO_02 = "Estúdio 02"
    ESTUDIO_03 = "Estúdio 03"
    ESTUDIO_04 = "Estúdio 04"
    ESTUDIO_05 = "Estúdio 05"
    ESTUDIO_06 = "Estúdio 06"
    ESTUDIO_07 = "Estúdio 07"
    ESTUDIO_08 = "Estúdio 08"
    ESTUDIO_09 = "Estúdio 09"
    EXTERNO = "Externo"


class StatusReportEnum(str, Enum):
    """
    Fluxo de validação de relatórios (v3.1):

        RASCUNHO -> AGUARDANDO_VALIDACAO -> VALIDADO
                          ^                     |
                          |___(correção)________|

    Quando a Coordenação envia um relatório para correção, ele volta para
    RASCUNHO com a flag Report.precisa_correcao = True e o texto em
    Report.observacao_coordenacao (ver model Report).

    FINALIZADO é mantido apenas por compatibilidade com relatórios já
    gravados no banco antes desta versão — não usar em código novo.
    """
    RASCUNHO = "RASCUNHO"
    AGUARDANDO_VALIDACAO = "AGUARDANDO_VALIDACAO"
    VALIDADO = "VALIDADO"
    CANCELADO = "CANCELADO"
    FINALIZADO = "FINALIZADO"  # legado — substituído por AGUARDANDO_VALIDACAO/VALIDADO


class TipoAulaEnum(str, Enum):
    MANUTENCAO_ESTUDIO = "Manutenção de estúdio"
    PLANEJAMENTO_PEDAGOGICO = "Planejamento Pedagógico"
    VIDEOCONFERENCIA = "Videoconferência"
    GRAVACAO_ESTUDIO = "Gravação estúdio"
    UAPI = "UAPI"
    TRANSMISSAO_AO_VIVO = "Transmissão ao vivo"
    GRAVACAO_EXTERNA = "Gravação externa"


class InteracaoEnum(str, Enum):
    NAO = "Não"
    CHAT = "Chat"
    VIDEOCONFERENCIA = "Videoconferência"
    CHAT_E_VIDEO = "Chat e vídeo"
    OUTRAS = "Outras"


class AtividadePraticaEnum(str, Enum):
    EXERCICIO_TEORICO = "Exercício teórico"
    EXERCICIO_PRATICO = "Exercício prático"
    DINAMICA = "Dinâmica"
    DEBATES = "Debates"


class RecursoEnum(str, Enum):
    VIDEO = "vídeo"
    CHROMA_KEY = "chroma key"
    ANIMACAO = "animação"
    ALPHA = "alpha"
    INTERNET = "Internet"
    OUTRO = "Outro"


class ProblemaMaterialEnum(str, Enum):
    NAO = "Não"
    ATRASO_ENTREGA = "Atraso na entrega"
    ALTERACAO = "Alteração"
    NAO_ENTREGUE = "Não entregue"
    PROBLEMAS_TECNICOS = "Problemas técnicos"
    OUTROS = "Outros"


class UserRoleEnum(str, Enum):
    ADMIN = "admin"
    GESTOR = "gestor"
    COORDENADOR = "coordenador"  # v3.1 — valida/corrige relatórios de cada série
    AUDITOR = "auditor"
    ASSISTENTE = "assistente"
    DIRETOR_IMAGEM = "diretor_imagem"  # v3.2 — preenche o Relatório do Diretor de Imagem
    DIRETOR_CHEFE = "diretor_chefe"    # v3.2 — administra perguntas/checklist e vê todos os relatórios de imagem


# ─── v3.2 — Relatório do Diretor de Imagem ────────────────────────────

# Papéis que podem administrar perguntas extras / checklist e ver todos os
# relatórios de imagem (não só os próprios).
PAPEIS_DIRETOR_CHEFE = ("admin", "gestor", "diretor_chefe")

# Todos os papéis que podem acessar a tela de Relatório do Diretor de Imagem.
PAPEIS_DIRETOR_IMAGEM = ("admin", "gestor", "diretor_chefe", "diretor_imagem")


class ImageReportStatusEnum(str, Enum):
    """
    Fluxo do Relatório do Diretor de Imagem (v3.2 — mesma lógica do Relatório de Aula):

        RASCUNHO -> AGUARDANDO_VALIDACAO -> VALIDADO
                          ^                     |
                          |___(correção)________|
    """
    RASCUNHO = "RASCUNHO"
    AGUARDANDO_VALIDACAO = "AGUARDANDO_VALIDACAO"
    VALIDADO = "VALIDADO"
    CANCELADO = "CANCELADO"


class TransmissaoTipoEnum(str, Enum):
    TRANSMISSAO = "Transmissão"
    GRAVADA = "Aula gravada"


class SimNaoEnum(str, Enum):
    SIM = "Sim"
    NAO = "Não"


class PerguntaTipoEnum(str, Enum):
    """Tipo de resposta de uma pergunta extra cadastrada pelo Diretor-Chefe."""
    SIM_NAO = "sim_nao"
    TEXTO = "texto"


class PerguntaNivelEnum(str, Enum):
    """Em que nível a pergunta extra aparece no formulário."""
    POR_AULA = "por_aula"          # repete dentro de cada bloco "AULA 0X"
    POR_RELATORIO = "por_relatorio"  # aparece uma única vez no relatório


class RegularEnum(str, Enum):
    SIM = "Sim"
    NAO = "Não"


class CanalUtilizadoEnum(str, Enum):
    CANAL_1 = "Canal SEDUC PI 1"
    CANAL_2 = "Canal SEDUC PI 2"
    CANAL_3 = "Canal SEDUC PI 3"
    CANAL_4 = "Canal SEDUC PI 4"
    CANAL_5 = "Canal SEDUC PI 5"
    CANAL_6 = "Canal SEDUC PI 6"
    CANAL_7 = "Canal SEDUC PI 7"
    CANAL_8 = "Canal SEDUC PI 8"
    CANAL_9 = "Canal SEDUC PI 9"


class HorarioAulaEnum(str, Enum):
    H1 = "1º Horário"
    H2 = "2º Horário"
    H3 = "3º Horário"
    H4 = "4º Horário"
    H5 = "5º Horário"
    H6 = "6º Horário"
    H7 = "7º Horário"
    H8 = "8º Horário"


class AuditActionEnum(str, Enum):
    """Ações rastreáveis no log de auditoria (§5.4)."""
    USER_INVITED = "USER_INVITED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_ACTIVATED = "USER_ACTIVATED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    REPORT_FINALIZED = "REPORT_FINALIZED"
    REPORT_CANCELLED = "REPORT_CANCELLED"
    REPORT_VALIDATED = "REPORT_VALIDATED"                  # v3.1
    REPORT_CORRECTION_REQUESTED = "REPORT_CORRECTION_REQUESTED"  # v3.1
    IMAGE_REPORT_FINALIZED = "IMAGE_REPORT_FINALIZED"       # v3.2
    IMAGE_REPORT_CANCELLED = "IMAGE_REPORT_CANCELLED"       # v3.2
    IMAGE_REPORT_VALIDATED = "IMAGE_REPORT_VALIDATED"       # v3.2
    IMAGE_REPORT_CORRECTION_REQUESTED = "IMAGE_REPORT_CORRECTION_REQUESTED"  # v3.2
    IMAGE_QUESTION_CREATED = "IMAGE_QUESTION_CREATED"       # v3.2
    IMAGE_QUESTION_UPDATED = "IMAGE_QUESTION_UPDATED"       # v3.2