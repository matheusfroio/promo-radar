"""
vitrine.py
==========

Modulo utilitario para o bot Python adicionar produtos de afiliado
ao arquivo index.html da vitrine (GitHub Pages).

Uso basico:

    from vitrine import adicionar_produto

    adicionar_produto(
        titulo="Fone de Ouvido Bluetooth XYZ",
        link_afiliado="https://www.mercadolivre.com.br/sec/xxxxxxx",
        preco=89.90,
        preco_original=129.90,
        desconto=30,
        categoria="Eletrônicos",
        imagem_url="https://http2.mlstatic.com/exemplo.jpg",
    )
"""

import html
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

INDEX_PATH = Path(__file__).resolve().parent / "index.html"

MARCADOR_INICIO = "<!-- PRODUTOS_INICIO -->"
MARCADOR_FIM = "<!-- PRODUTOS_FIM -->"

MAX_PRODUTOS = 40

CATEGORIAS_VALIDAS = {
    "Eletrônicos", "Moda", "Casa", "Esporte", "Beleza", "Geral"
}

LOJAS_VALIDAS = {"Mercado Livre", "Shopee"}

# Mapeia o domain_id da categoria do Mercado Livre (automacao.py) para uma
# das categorias exibidas na vitrine.
CATEGORIA_ML_PARA_SITE = {
    # Moda
    "MLB-SNEAKERS": "Moda",
    "MLB-CLOTHING": "Moda",
    "MLB-WOMEN_CLOTHING": "Moda",
    "MLB-MEN_CLOTHING": "Moda",
    "MLB-KIDS_CLOTHING": "Moda",
    "MLB-UNDERWEAR_AND_SLEEPWEAR": "Moda",
    "MLB-HANDBAGS_AND_ACCESSORIES": "Moda",
    "MLB-SHOES": "Moda",
    "MLB-WOMEN_SHOES": "Moda",
    "MLB-MEN_SHOES": "Moda",
    "MLB-KIDS_SHOES": "Moda",
    "MLB-FASHION_ACCESSORIES": "Moda",
    "MLB-WATCHES": "Moda",
    "MLB-SUNGLASSES": "Moda",
    "MLB-JEWELRY": "Moda",
    # Beleza
    "MLB-PERFUMES_AND_FRAGRANCES": "Beleza",
    "MLB-PERFUMES": "Beleza",
    "MLB-MAKEUP": "Beleza",
    "MLB-SKIN_CARE": "Beleza",
    "MLB-HAIR_CARE": "Beleza",
    "MLB-PERSONAL_CARE": "Beleza",
    "MLB-HEALTH_AND_BEAUTY": "Beleza",
    # Esporte
    "MLB-SPORTS_AND_OUTDOORS": "Esporte",
    "MLB-CAMPING_AND_HIKING": "Esporte",
    "MLB-BIKES": "Esporte",
    "MLB-FITNESS_EQUIPMENT": "Esporte",
    # Casa
    "MLB-HOME_AND_GARDEN": "Casa",
    "MLB-FURNITURE": "Casa",
    "MLB-OFFICE_CHAIRS": "Casa",
    "MLB-BEDDING": "Casa",
    "MLB-KITCHEN": "Casa",
    "MLB-FOOD_STORAGE_CONTAINERS": "Casa",
    "MLB-TOOLS_AND_HOME_IMPROVEMENT": "Casa",
    "MLB-AIR_FRYERS": "Casa",
    "MLB-SMALL_APPLIANCES": "Casa",
    "MLB-LARGE_APPLIANCES": "Casa",
    # Eletrônicos
    "MLB-ELECTRONICS_ACCESSORIES": "Eletrônicos",
    "MLB-HEADPHONES": "Eletrônicos",
    "MLB-SPEAKERS": "Eletrônicos",
    "MLB-CAMERAS_AND_ACCESSORIES": "Eletrônicos",
    "MLB-VIDEO_GAMES": "Eletrônicos",
    "MLB-MUSICAL_INSTRUMENTS": "Eletrônicos",
    "MLB-CELL_PHONES_AND_SMARTPHONES": "Eletrônicos",
    "MLB-CELLPHONES": "Eletrônicos",
    "MLB-TABLETS_AND_ACCESSORIES": "Eletrônicos",
    "MLB-COMPUTERS": "Eletrônicos",
    "MLB-NOTEBOOKS": "Eletrônicos",
    "MLB-LAPTOPS_AND_ACCESSORIES": "Eletrônicos",
    "MLB-TELEVISIONS": "Eletrônicos",
    "MLB-PRINTERS": "Eletrônicos",
    "MLB-PROJECTORS": "Eletrônicos",
    "MLB-GAME_CONSOLES": "Eletrônicos",
    "MLB-SURVEILLANCE_CAMERAS": "Eletrônicos",
}


def mapear_categoria(domain_id: str) -> str:
    """Converte o domain_id do Mercado Livre para uma categoria da vitrine.

    Categorias nao mapeadas (ex: brinquedos, livros, pet, autopecas) caem em "Geral".
    """
    return CATEGORIA_ML_PARA_SITE.get(domain_id, "Geral")


# ---------------------------------------------------------------------------
# Funcoes internas
# ---------------------------------------------------------------------------

def _ler_index() -> str:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo index.html nao encontrado em: {INDEX_PATH}"
        )
    return INDEX_PATH.read_text(encoding="utf-8")


def _escapar(valor: str) -> str:
    """Escapa aspas e caracteres especiais para uso seguro em atributos HTML."""
    return html.escape(str(valor), quote=True)


def _montar_card(
    titulo: str,
    link_afiliado: str,
    preco: float,
    categoria: str,
    imagem_url: str,
    preco_original: float,
    desconto: int,
    loja: str,
) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()

    return (
        '  <div class="produto"\n'
        f'    data-titulo="{_escapar(titulo)}"\n'
        f'    data-link="{_escapar(link_afiliado)}"\n'
        f'    data-preco="{preco:.2f}"\n'
        f'    data-preco-original="{preco_original:.2f}"\n'
        f'    data-desconto="{int(desconto)}"\n'
        f'    data-categoria="{_escapar(categoria)}"\n'
        f'    data-imagem="{_escapar(imagem_url)}"\n'
        f'    data-loja="{_escapar(loja)}"\n'
        f'    data-timestamp="{timestamp}">\n'
        '  </div>\n'
    )


def _extrair_produtos_existentes(conteudo: str) -> list:
    """Retorna a lista de blocos <div class="produto" ...>...</div> existentes."""
    inicio = conteudo.find(MARCADOR_INICIO)
    fim = conteudo.find(MARCADOR_FIM)

    if inicio == -1 or fim == -1:
        raise ValueError(
            "Marcadores PRODUTOS_INICIO / PRODUTOS_FIM nao encontrados no index.html"
        )

    bloco = conteudo[inicio + len(MARCADOR_INICIO):fim]

    padrao = re.compile(
        r'<div class="produto".*?</div>',
        re.DOTALL,
    )
    return padrao.findall(bloco)


def _git_push(titulo: str) -> None:
    repo_dir = INDEX_PATH.parent
    comandos = [
        ["git", "add", "index.html"],
        ["git", "commit", "-m", f"produto: {titulo}"],
        ["git", "push"],
    ]

    for cmd in comandos:
        resultado = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if resultado.returncode != 0:
            # "nothing to commit" nao deve travar o fluxo
            if cmd[1] == "commit" and "nothing to commit" in resultado.stdout.lower():
                continue
            raise RuntimeError(
                f"Falha ao executar '{' '.join(cmd)}':\n"
                f"stdout: {resultado.stdout}\n"
                f"stderr: {resultado.stderr}"
            )


# ---------------------------------------------------------------------------
# Funcao principal
# ---------------------------------------------------------------------------

def adicionar_produto(
    titulo: str,
    link_afiliado: str,
    preco: float,
    categoria: str = "Geral",
    imagem_url: str = "",
    preco_original: float = 0,
    desconto: int = 0,
    loja: str = "Mercado Livre",
    auto_push: bool = True,
) -> bool:
    """
    Adiciona um novo produto na vitrine (index.html).

    Parametros:
        titulo: nome do produto exibido no card.
        link_afiliado: URL do link de afiliado (Mercado Livre ou Shopee).
        preco: preco atual do produto.
        categoria: uma das categorias suportadas (Eletrônicos, Moda, Casa,
                   Esporte, Beleza, Geral). Padrao: "Geral".
        imagem_url: URL da imagem do produto. Se vazio, o card mostra um
                    emoji de fallback baseado na categoria.
        preco_original: preco "de" (riscado). Se 0, nao exibe.
        desconto: percentual de desconto (inteiro). Se 0, nao exibe badge.
        loja: "Mercado Livre" ou "Shopee" — define o texto do botao de oferta.
              Padrao: "Mercado Livre".
        auto_push: se True, executa git add/commit/push automaticamente.

    Retorna:
        True em caso de sucesso.

    Lanca:
        FileNotFoundError, ValueError ou RuntimeError com mensagem clara
        em caso de falha.
    """

    if not titulo or not titulo.strip():
        raise ValueError("O titulo do produto nao pode ser vazio.")

    if not link_afiliado or not link_afiliado.strip():
        raise ValueError("O link de afiliado nao pode ser vazio.")

    if preco <= 0:
        raise ValueError("O preco deve ser maior que zero.")

    if categoria not in CATEGORIAS_VALIDAS:
        categoria = "Geral"

    if loja not in LOJAS_VALIDAS:
        loja = "Mercado Livre"

    conteudo = _ler_index()

    produtos_existentes = _extrair_produtos_existentes(conteudo)

    novo_card = _montar_card(
        titulo=titulo.strip(),
        link_afiliado=link_afiliado.strip(),
        preco=preco,
        categoria=categoria,
        imagem_url=imagem_url.strip(),
        preco_original=preco_original,
        desconto=desconto,
        loja=loja,
    )

    produtos_atualizados = [novo_card] + produtos_existentes
    produtos_atualizados = produtos_atualizados[:MAX_PRODUTOS]

    novo_bloco = "\n" + "".join(produtos_atualizados)

    inicio = conteudo.find(MARCADOR_INICIO) + len(MARCADOR_INICIO)
    fim = conteudo.find(MARCADOR_FIM)

    novo_conteudo = (
        conteudo[:inicio]
        + novo_bloco
        + conteudo[fim:]
    )

    try:
        INDEX_PATH.write_text(novo_conteudo, encoding="utf-8")
    except OSError as erro:
        raise RuntimeError(f"Falha ao escrever index.html: {erro}") from erro

    if auto_push:
        _git_push(titulo)

    return True


def remover_produto(numero: int = None, titulo_parcial: str = None, auto_push: bool = True) -> bool:
    """Remove um produto da vitrine pelo numero (posicao) ou trecho do titulo."""
    conteudo = _ler_index()
    produtos = _extrair_produtos_existentes(conteudo)

    if not produtos:
        print("Nenhum produto na vitrine.")
        return False

    if numero is not None:
        if numero < 1 or numero > len(produtos):
            raise ValueError(f"Numero invalido. Use de 1 a {len(produtos)}.")
        removido = produtos.pop(numero - 1)
    elif titulo_parcial:
        titulo_lower = titulo_parcial.lower()
        idx = None
        for i, p in enumerate(produtos):
            match = re.search(r'data-titulo="([^"]*)"', p)
            if match and titulo_lower in match.group(1).lower():
                idx = i
                break
        if idx is None:
            print(f"Nenhum produto encontrado com '{titulo_parcial}'.")
            return False
        removido = produtos.pop(idx)
    else:
        raise ValueError("Informe 'numero' ou 'titulo_parcial'.")

    match = re.search(r'data-titulo="([^"]*)"', removido)
    titulo_removido = match.group(1) if match else "desconhecido"

    novo_bloco = "\n" + "".join(produtos) if produtos else "\n"
    inicio = conteudo.find(MARCADOR_INICIO) + len(MARCADOR_INICIO)
    fim = conteudo.find(MARCADOR_FIM)
    novo_conteudo = conteudo[:inicio] + novo_bloco + conteudo[fim:]

    INDEX_PATH.write_text(novo_conteudo, encoding="utf-8")
    print(f"Removido: {titulo_removido}")

    if auto_push:
        _git_push(f"remover: {titulo_removido[:60]}")

    return True


def listar_produtos() -> list:
    """Lista todos os produtos da vitrine com numero, titulo e preco."""
    conteudo = _ler_index()
    produtos = _extrair_produtos_existentes(conteudo)
    lista = []
    for i, p in enumerate(produtos, 1):
        titulo = re.search(r'data-titulo="([^"]*)"', p)
        preco = re.search(r'data-preco="([^"]*)"', p)
        loja = re.search(r'data-loja="([^"]*)"', p)
        lista.append({
            "numero": i,
            "titulo": html.unescape(titulo.group(1)) if titulo else "?",
            "preco": float(preco.group(1)) if preco else 0,
            "loja": html.unescape(loja.group(1)) if loja else "?",
        })
    return lista


# ---------------------------------------------------------------------------
# Execucao direta — gerenciador interativo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    def _menu():
        print("\n===== GERENCIADOR DA VITRINE =====")
        print("1 - Listar produtos")
        print("2 - Remover produto por número")
        print("3 - Buscar e remover por nome")
        print("0 - Sair")
        return input("\nEscolha: ").strip()

    while True:
        opcao = _menu()

        if opcao == "0":
            print("Saindo.")
            break

        elif opcao == "1":
            itens = listar_produtos()
            if not itens:
                print("\nVitrine vazia.")
            else:
                print(f"\n{len(itens)} produto(s):\n")
                for item in itens:
                    print(f"  {item['numero']:>2}. [{item['loja']}] R${item['preco']:.2f} — {item['titulo'][:80]}")

        elif opcao == "2":
            itens = listar_produtos()
            if not itens:
                print("\nVitrine vazia.")
                continue
            print(f"\n{len(itens)} produto(s):\n")
            for item in itens:
                print(f"  {item['numero']:>2}. [{item['loja']}] R${item['preco']:.2f} — {item['titulo'][:80]}")
            num = input("\nNúmero do produto para remover (0 = cancelar): ").strip()
            if num == "0":
                continue
            try:
                remover_produto(numero=int(num))
            except Exception as e:
                print(f"Erro: {e}")

        elif opcao == "3":
            busca = input("Digite parte do nome do produto: ").strip()
            if not busca:
                continue
            try:
                remover_produto(titulo_parcial=busca)
            except Exception as e:
                print(f"Erro: {e}")

        else:
            print("Opção inválida.")
