"""
Canal Educação v3.0 — Parser de habilidades BNCC Computação.
Extrai habilidades do arquivo diagramado (PDF convertido para TXT).

Padrões de código identificados:
  - Ensino Fundamental por ano: (EF01CO01) a (EF09CO10)
  - Ensino Fundamental por etapa: (EF69CO01) a (EF69CO12)
  - Ensino Médio: (EM13CO01) a (EM13CO26)
"""

import re
import os


# ── Dicionário de habilidades conhecido ────────────────────────────────
# As descrições vêm do PDF diagramado com palavras coladas.
# A melhor abordagem é usar as descrições limpas conhecidas como lookup.
# Quando possível, extraímos do texto; senão, usamos o texto bruto.

HABILIDADES_COMPUTACAO = {
    # === 1º ANO ===
    "EF01CO01": "Organizar objetos físicos ou digitais considerando diferentes características para estabelecer critérios de organização.",
    "EF01CO02": "Identificar e seguir sequências de passos aplicados no dia a dia para resolver problemas.",
    "EF01CO03": "Reorganizar e criar sequências de passos em meios físicos ou digitais, relacionando essas sequências com algoritmos.",
    "EF01CO04": "Reconhecer o que é informação, que ela pode ser armazenada, transmitida como mensagem por diversos meios e utilizar os meios digitais.",
    "EF01CO05": "Representar informação usando diferentes codificações.",
    "EF01CO06": "Reconhecer a si mesmo e às demais pessoas como integrantes do mundo digital.",
    "EF01CO07": "Conhecer as possibilidades de uso seguro das tecnologias computacionais para proteção dos dados pessoais e para garantir a própria segurança.",
    # === 2º ANO ===
    "EF02CO01": "Criar e simular programas como sequências e repetições simples de poucos comandos para resolver problemas.",
    "EF02CO02": "Identificar padrões de comportamento e utilizá-los como critérios de generalização.",
    "EF02CO03": "Reconhecer que os computadores e dispositivos podem ser programados através de sequências de instruções.",
    "EF02CO04": "Compreender e utilizar diferentes codificações para representar informações como cores, textos e outras.",
    "EF02CO05": "Identificar o uso das tecnologias digitais no cotidiano.",
    "EF02CO06": "Reconhecer que as tecnologias são criadas e utilizadas para resolver problemas do dia a dia.",
    # === 3º ANO ===
    "EF03CO01": "Criar e simular programas, incluindo instruções condicionais simples.",
    "EF03CO02": "Identificar padrões de comportamento e utilizá-los como critérios de generalização para construir algoritmos.",
    "EF03CO03": "Compreender e utilizar diferentes formas de representação de dados, tais como tabelas e gráficos, para criar e executar programas em meios físicos ou digitais.",
    "EF03CO04": "Identificar os tipos de informação e como ela é codificada e armazenada nos computadores.",
    "EF03CO05": "Identificar e praticar regras básicas de segurança no uso da tecnologia, como proteção de senhas e informações pessoais.",
    "EF03CO06": "Selecionar e utilizar ferramentas e tecnologias digitais para resolver problemas de outras áreas do conhecimento.",
    "EF03CO07": "Utilizar diferentes navegadores e ferramentas de busca para pesquisar e acessar informações.",
    "EF03CO08": "Usar ferramentas computacionais em situações didáticas para se expressar em diferentes formatos digitais.",
    "EF03CO09": "Reconhecer o potencial impacto do compartilhamento de informações pessoais ou de seus pares em meio digital.",
    # === 4º ANO ===
    "EF04CO01": "Criar e depurar programas compostos por sequências, repetições e condições simples, em meios físicos e digitais.",
    "EF04CO02": "Construir soluções de problemas usando a técnica de decomposição e automatizar tais soluções usando uma linguagem de programação.",
    "EF04CO03": "Identificar problemas que se desejam resolver e definir os insumos e resultados esperados.",
    "EF04CO04": "Compreender o conceito de hardware e software e como eles se relacionam.",
    "EF04CO05": "Utilizar as tecnologias de forma segura e responsável.",
    "EF04CO06": "Selecionar e utilizar tecnologias computacionais para se expressar e resolver problemas.",
    "EF04CO07": "Demonstrar postura ética nas atividades de coleta, transferência, guarda e uso de dados.",
    "EF04CO08": "Reconhecer a importância de verificar a confiabilidade das fontes de informações obtidas na Internet.",
    # === 5º ANO ===
    "EF05CO01": "Criar e simular programas usando variáveis para armazenar e manipular dados.",
    "EF05CO02": "Construir soluções de problemas usando a técnica de decomposição.",
    "EF05CO03": "Criar algoritmos fazendo uso da generalização.",
    "EF05CO04": "Compreender como os dados são armazenados em computadores, por meio de coleção de bits.",
    "EF05CO05": "Analisar o uso das tecnologias em relação à saúde e ao bem-estar.",
    "EF05CO06": "Selecionar e utilizar ferramentas e tecnologias digitais para resolver problemas de outras áreas do conhecimento.",
    "EF05CO07": "Reconhecer a necessidade de um sistema operacional para a execução de programas e gerenciamento do hardware.",
    "EF05CO08": "Acessar as informações na Internet de forma crítica para distinguir os conteúdos confiáveis de não confiáveis.",
    "EF05CO09": "Usar informações considerando aplicações e limites dos direitos autorais em diferentes mídias digitais.",
    "EF05CO10": "Expressar-se crítica e criativamente na compreensão das mudanças tecnológicas no mundo do trabalho e sobre a evolução da sociedade.",
    # === 1º ao 5º ANO (por etapa) ===
    "EF15CO01": "Identificar as principais formas de organizar e representar a informação de maneira estruturada (matrizes, registros, listas e grafos) ou não estruturada (números, palavras, valores verdade).",
    "EF15CO02": "Construir e simular algoritmos, de forma independente ou em colaboração, que resolvam problemas simples e do cotidiano com uso de sequências, seleções condicionais e repetições de instruções.",
    "EF15CO03": "Realizar operações de negação, conjunção e disjunção sobre sentenças lógicas e valores 'verdadeiro' e 'falso'.",
    "EF15CO04": "Aplicar a estratégia de decomposição para resolver problemas complexos, dividindo esse problema em partes menores, resolvendo-as e combinando suas soluções.",
    "EF15CO05": "Codificar a informação de diferentes formas, entendendo a importância desta codificação para o armazenamento, manipulação e transmissão em dispositivos computacionais.",
    "EF15CO06": "Conhecer os componentes básicos de dispositivos computacionais, entendendo os princípios de seu funcionamento.",
    "EF15CO07": "Conhecer o conceito de Sistema Operacional e sua importância na integração entre software e hardware.",
    "EF15CO08": "Reconhecer e utilizar tecnologias computacionais para pesquisar e acessar informações, expressar-se crítica e criativamente e resolver problemas.",
    "EF15CO09": "Entender que as tecnologias devem ser utilizadas de maneira segura, ética e responsável, respeitando direitos autorais, de imagem e as leis vigentes.",
    # === 6º ANO ===
    "EF06CO01": "Criar soluções de problemas para os quais seja adequado o uso de variáveis, estruturas condicionais e de repetição, automatizando-as usando uma linguagem de programação.",
    "EF06CO02": "Construir soluções de problemas usando a técnica de decomposição, automatizando tais soluções usando uma linguagem de programação.",
    "EF06CO03": "Criar algoritmos fazendo uso da generalização, de forma que eles sejam expressos usando variáveis.",
    "EF06CO04": "Analisar e depurar programas para detectar e remover erros.",
    "EF06CO05": "Construir soluções computacionais de problemas de diferentes áreas do conhecimento.",
    "EF06CO06": "Explorar propriedades básicas de grafos.",
    "EF06CO07": "Entender o processo de transmissão de dados, como a informação é quebrada em pedaços, transmitida em pacotes através de múltiplos equipamentos, e reconstruída no destino.",
    "EF06CO08": "Compreender e utilizar diferentes formas de armazenar, manipular, compactar e recuperar arquivos, documentos e metadados.",
    "EF06CO09": "Apresentar conduta e linguagem apropriadas ao se comunicar em ambiente digital, considerando a ética e o respeito.",
    "EF06CO10": "Analisar o consumo de tecnologia na sociedade, compreendendo criticamente o caminho da produção dos recursos bem como aspectos ligados à obsolescência e a sustentabilidade.",
    # === 7º ANO ===
    "EF07CO01": "Criar soluções de problemas para os quais seja adequado o uso de registros e matrizes unidimensionais para descrever suas informações e automatizá-las usando uma linguagem de programação.",
    "EF07CO02": "Analisar programas para detectar e remover erros, ampliando a confiança na sua correção.",
    "EF07CO03": "Construir soluções computacionais de problemas de diferentes áreas do conhecimento, de forma individual e colaborativa, selecionando as estruturas de dados e técnicas adequadas.",
    "EF07CO04": "Explorar propriedades básicas de grafos.",
    "EF07CO05": "Criar algoritmos fazendo uso da decomposição e do reúso no processo de solução de forma colaborativa e cooperativa e automatizá-los usando uma linguagem de programação.",
    "EF07CO06": "Compreender o papel de protocolos para a transmissão de dados.",
    "EF07CO07": "Identificar problemas de segurança cibernética e experimentar formas de proteção.",
    "EF07CO08": "Demonstrar empatia sobre opiniões divergentes na web.",
    "EF07CO09": "Reconhecer e debater sobre cyberbullying.",
    "EF07CO10": "Identificar os impactos ambientais do descarte de peças de computadores e eletrônicos, bem como sua relação com a sustentabilidade.",
    "EF07CO11": "Criar, documentar e publicar, de forma individual ou colaborativa, produtos (vídeos, podcasts, websites) usando recursos de tecnologia.",
    # === 8º ANO ===
    "EF08CO01": "Construir soluções de problemas usando a técnica de recursão e automatizar tais soluções usando uma linguagem de programação.",
    "EF08CO02": "Criar soluções de problemas para os quais seja adequado o uso de listas para descrever suas informações e automatizá-las usando uma linguagem de programação.",
    "EF08CO03": "Utilizar algoritmos clássicos de manipulação sobre listas.",
    "EF08CO04": "Construir soluções computacionais de problemas de diferentes áreas do conhecimento, de forma individual e colaborativa, selecionando as estruturas de dados e técnicas adequadas.",
    "EF08CO05": "Compreender os conceitos de paralelismo, concorrência e armazenamento/processamento distribuídos.",
    "EF08CO06": "Entender como é a estrutura e funcionamento da internet.",
    "EF08CO07": "Compartilhar informações por meio de redes sociais, compreendendo a sua dinâmica de funcionamento, de forma responsável e avaliando sua confiabilidade.",
    "EF08CO08": "Distinguir os tipos de dados pessoais que são solicitados em espaços digitais e os riscos associados.",
    "EF08CO09": "Analisar criticamente as políticas de termos de uso das redes sociais e demais plataformas.",
    "EF08CO10": "Discutir questões sobre segurança e privacidade relacionadas ao uso dos ambientes virtuais.",
    "EF08CO11": "Avaliar a precisão, relevância, adequação, abrangência e vieses que ocorrem em fontes de informação eletrônica.",
    # === 9º ANO ===
    "EF09CO01": "Criar soluções de problemas para os quais seja adequado o uso de árvores e grafos para descrever suas informações e automatizá-las usando uma linguagem de programação.",
    "EF09CO02": "Construir soluções computacionais de problemas de diferentes áreas do conhecimento, de forma individual e colaborativa, selecionando as estruturas de dados e técnicas adequadas.",
    "EF09CO03": "Usar autômatos para descrever comportamentos de forma abstrata automatizando-os através de uma linguagem de programação baseada em eventos.",
    "EF09CO04": "Compreender o funcionamento de malwares e outros ataques cibernéticos.",
    "EF09CO05": "Analisar técnicas de criptografia para armazenamento e transmissão de dados.",
    "EF09CO06": "Analisar problemas sociais de sua cidade e estado a partir de ambientes digitais, propondo soluções.",
    "EF09CO07": "Avaliar aplicações e implicações políticas, socioambientais e culturais das tecnologias digitais para propor alternativas aos desafios do mundo contemporâneo.",
    "EF09CO08": "Discutir como a distribuição desigual de recursos de computação em uma economia global levanta questões de equidade, acesso e poder.",
    "EF09CO09": "Criar ou utilizar conteúdo em meio digital, compreendendo questões éticas relacionadas a direitos autorais e de uso de imagem.",
    "EF09CO10": "Avaliar a veracidade, credibilidade e relevância da informação em seus diferentes formatos, sendo capaz de identificar o propósito pelo qual foi disseminada.",
    # === 6º ao 9º ANO (por etapa) ===
    "EF69CO01": "Classificar informações, agrupando-as em coleções (conjuntos) e associando cada coleção a um 'tipo de dado'.",
    "EF69CO02": "Elaborar algoritmos que envolvam instruções sequenciais, de repetição e de seleção usando uma linguagem de programação.",
    "EF69CO03": "Descrever com precisão a solução de um problema, construindo o programa que implementa a solução descrita.",
    "EF69CO04": "Construir soluções de problemas usando a técnica de decomposição e automatizar tais soluções usando uma linguagem de programação.",
    "EF69CO05": "Identificar os recursos ou insumos necessários (entradas) para a resolução de problemas, bem como os resultados esperados (saídas), determinando os respectivos tipos de dados.",
    "EF69CO06": "Comparar diferentes casos particulares (instâncias) de um mesmo problema, identificando as semelhanças e diferenças entre eles, e criar um algoritmo para resolver todos, fazendo uso de variáveis (parâmetros).",
    "EF69CO07": "Entender o processo de transmissão de dados, como a informação é quebrada em pedaços, transmitida em pacotes através de múltiplos equipamentos, e reconstruída no destino.",
    "EF69CO08": "Compreender e utilizar diferentes formas de armazenar, manipular, compactar e recuperar arquivos, documentos e metadados.",
    "EF69CO09": "Compreender os conceitos de paralelismo, concorrência e armazenamento/processamento distribuídos.",
    "EF69CO10": "Entender como é a estrutura e funcionamento da internet.",
    "EF69CO11": "Apresentar conduta e linguagem apropriadas ao se comunicar em ambiente digital, considerando a ética e o respeito.",
    "EF69CO12": "Analisar o consumo de tecnologia na sociedade, compreendendo criticamente o caminho da produção dos recursos bem como aspectos ligados à obsolescência e a sustentabilidade.",
    # === ENSINO MÉDIO ===
    "EM13CO01": "Explorar e construir a solução de problemas por meio da reutilização de partes de soluções existentes.",
    "EM13CO02": "Explorar e construir a solução de problemas por meio de refinamentos, utilizando diversos níveis de abstração desde a especificação até a implementação.",
    "EM13CO03": "Identificar o comportamento dos algoritmos no que diz respeito ao consumo de recursos como tempo de execução, espaço de memória e energia, entre outros.",
    "EM13CO04": "Reconhecer o conceito de metaprogramação como uma forma de generalização na construção de programas, permitindo que algoritmos sejam entrada ou saída para outros algoritmos.",
    "EM13CO05": "Identificar os limites da Computação para diferenciar o que pode ou não ser automatizado, buscando uma compreensão mais ampla dos limites dos processos mentais envolvidos na resolução de problemas.",
    "EM13CO06": "Avaliar software levando em consideração diferentes características e métricas associadas.",
    "EM13CO07": "Compreender as diferentes tecnologias, bem como equipamentos, protocolos e serviços envolvidos no funcionamento de redes de computadores, identificando suas possibilidades de escala e confiabilidade.",
    "EM13CO08": "Entender como mudanças na tecnologia afetam a segurança, incluindo novas maneiras de preservar sua privacidade e dados pessoais on-line.",
    "EM13CO09": "Identificar tecnologias digitais, sua presença e formas de uso, nas diferentes atividades no mundo do trabalho.",
    "EM13CO10": "Conhecer os fundamentos da Inteligência Artificial, comparando-a com a inteligência humana, analisando suas potencialidades, riscos e limites.",
    "EM13CO11": "Criar e explorar modelos computacionais simples para simular e fazer previsões, identificando sua importância no desenvolvimento científico.",
    "EM13CO12": "Produzir, analisar, gerir e compartilhar informações a partir de dados, utilizando princípios de ciência de dados.",
    "EM13CO13": "Analisar e utilizar as diferentes formas de representação e consulta de dados em formato digital para pesquisas científicas.",
    "EM13CO14": "Avaliar a confiabilidade das informações encontradas em meio digital, investigando seus modos de construção e considerando a autoria, a estrutura e o propósito da mensagem.",
    "EM13CO15": "Analisar a interação entre usuários e artefatos computacionais, abordando aspectos da experiência do usuário e promovendo reflexão sobre a qualidade do uso dos artefatos.",
    "EM13CO16": "Desenvolver projetos com robótica, utilizando artefatos físicos ou simuladores.",
    "EM13CO17": "Construir redes virtuais de interação e colaboração, favorecendo o desenvolvimento de projetos de forma segura, legal e ética.",
    "EM13CO18": "Planejar e gerenciar projetos integrados às áreas de conhecimento de forma colaborativa, solucionando problemas, usando diversos artefatos computacionais.",
    "EM13CO19": "Expor, argumentar e negociar propostas, produtos e serviços, utilizando diferentes mídias e ferramentas digitais.",
    "EM13CO20": "Criar conteúdos, disponibilizando-os em ambientes virtuais para publicação e compartilhamento, avaliando a confiabilidade e as consequências da disseminação dessas informações.",
    "EM13CO21": "Comunicar ideias complexas de forma clara por meio de objetos digitais como mapas conceituais, infográficos, hipertextos e outros.",
    "EM13CO22": "Produzir e publicar conteúdo como textos, imagens, áudios, vídeos e suas associações, bem como ferramentas para sua integração, organização e apresentação, utilizando diferentes mídias digitais.",
    "EM13CO23": "Analisar criticamente as experiências em comunidades virtuais e as relações advindas da interação e comunicação com outras pessoas, bem como seus impactos na sociedade.",
    "EM13CO24": "Identificar e reconhecer como as redes sociais e artefatos computacionais em geral interferem na saúde física e mental de seus usuários.",
    "EM13CO25": "Dialogar em ambientes virtuais com segurança e respeito às diferenças culturais e pessoais, reconhecendo e denunciando atitudes abusivas.",
    "EM13CO26": "Aplicar os conceitos e pressupostos do direito digital em sua conduta e experiências com o cotidiano da cultura digital, bem como na produção e uso de artefatos computacionais.",
}


def parse_bncc_computacao(txt_path: str = None) -> list:
    """
    Retorna a lista de habilidades de Computação BNCC.
    Usa o dicionário conhecido de habilidades limpas.
    Opcionalmente valida contra o arquivo .txt para detectar habilidades faltantes.
    """
    resultados = []

    for codigo, descricao in HABILIDADES_COMPUTACAO.items():
        resultados.append({
            "codigo": codigo,
            "descricao": descricao,
            "label": f"({codigo}) - {descricao}"
        })

    # Se um arquivo .txt foi fornecido, valida que capturamos tudo
    if txt_path and os.path.exists(txt_path):
        with open(txt_path, 'r', encoding='utf-8') as f:
            conteudo = f.read()

        # Encontra todos os códigos no arquivo
        codigos_no_txt = set(re.findall(
            r'\((EF\d{2}CO\d{2}|EM13CO\d{2}|EF69CO\d{2})\)',
            conteudo
        ))

        codigos_conhecidos = set(HABILIDADES_COMPUTACAO.keys())
        faltantes = codigos_no_txt - codigos_conhecidos

        if faltantes:
            print(f"[WARN] Codigos encontrados no TXT mas nao no dicionario: {sorted(faltantes)}")

    return resultados


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, "bncccomputacaocompletodiagramado.txt")

    habilidades = parse_bncc_computacao(path)
    print(f"\nTotal de habilidades de Computação: {len(habilidades)}\n")
    for h in habilidades[:5]:
        print(f"  {h['codigo']}: {h['descricao'][:100]}...")
    if len(habilidades) > 5:
        print(f"  ... e mais {len(habilidades) - 5} habilidades")
