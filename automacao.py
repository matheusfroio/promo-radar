"""
╔══════════════════════════════════════════════════════════╗
║          FROIO AUTOMAÇÃO - Afiliados Mercado Livre       ║
║  Busca produtos, gera posts com IA e posta no Facebook   ║
╚══════════════════════════════════════════════════════════╝

Requisitos:
    pip install requests pillow openai schedule facebook-sdk python-dotenv

Como usar:
    1. Preencha o arquivo config.env com suas credenciais
    2. Execute: python automacao.py
"""

import os
import re
import sys
import time
import json
import logging
import subprocess
import requests
import schedule
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO
from openai import OpenAI
from vitrine import adicionar_produto, mapear_categoria

# ─── Configuração de logs ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("froio_automacao.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── Lock de instância única ────────────────────────────────────────
LOCK_FILE = Path("automacao.pid")

def adquirir_lock():
    """Garante que apenas uma instância do agendador rode por vez.
    Retorna True se pode prosseguir, False se outra instância já está ativa."""
    meu_pid = os.getpid()

    if LOCK_FILE.exists():
        try:
            pid_antigo = int(LOCK_FILE.read_text().strip())
            if pid_antigo != meu_pid:
                resultado = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid_antigo}", "/NH"],
                    capture_output=True, text=True
                )
                if str(pid_antigo) in resultado.stdout:
                    log.warning(f"Instância duplicada detectada (PID {pid_antigo} já rodando). Encerrando esta instância (PID {meu_pid}).")
                    return False
        except Exception:
            pass  # lock corrompido — sobrescreve

    LOCK_FILE.write_text(str(meu_pid))
    log.info(f"Lock adquirido (PID {meu_pid}).")
    return True

def liberar_lock():
    """Remove o arquivo de lock ao encerrar."""
    try:
        if LOCK_FILE.exists():
            pid = int(LOCK_FILE.read_text().strip())
            if pid == os.getpid():
                LOCK_FILE.unlink()
    except Exception:
        pass


# ─── Carregar configurações ─────────────────────────────────────────
load_dotenv("config.env")

ML_AFILIADO_TAG  = os.getenv("ML_AFILIADO_TAG", "matheusfroio")
ML_AFILIADO_ID   = os.getenv("ML_AFILIADO_ID", "65970241")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
FB_PAGE_TOKEN    = os.getenv("FB_PAGE_TOKEN")
FB_PAGE_ID       = os.getenv("FB_PAGE_ID")

INSTAGRAM_PAUSADO   = False # pausa toda publicação no Instagram (posts novos e fila de backlog)

MIN_DESCONTO        = 15   # % mínimo de desconto do produto (critério normal)
MIN_DESCONTO_FALLBACK = 5  # % mínimo de desconto no fallback (quando não há produto novo)
MAX_PRECO           = 2000 # preço máximo em R$
MIN_VENDAS          = 1000 # vendas mínimas confirmadas
MIN_COMISSAO        = 10   # % mínimo de comissão de afiliado por categoria
POSTS_POR_DIA       = 5    # quantos posts publicar por dia

# Categorias com foco prioritário em todos os posts (academia + beleza — maior comissão)
CATEGORIAS_PREFERIDAS = {
    "MLB-FITNESS_EQUIPMENT",
    "MLB-SPORTS_AND_OUTDOORS",
    "MLB-CAMPING_AND_HIKING",
    "MLB-BIKES",
    "MLB-MAKEUP",
    "MLB-SKIN_CARE",
    "MLB-HAIR_CARE",
    "MLB-PERSONAL_CARE",
    "MLB-HEALTH_AND_BEAUTY",
    "MLB-PERFUMES_AND_FRAGRANCES",
    "MLB-PERFUMES",
}

# Categorias de alimentos e bebidas (domain_id do ML) — sem comissão de afiliado
CATEGORIAS_BLOQUEADAS = {
    "MLB-BEVERAGES", "MLB-FOOD", "MLB-FOOD_BEVERAGES",
    "MLB-WATER_AND_DRINKS", "MLB-MEATS", "MLB-BREADS_AND_BAKERY",
    "MLB-CONDIMENTS_AND_SAUCES", "MLB-DAIRY_AND_EGGS",
    "MLB-FRUITS_AND_VEGETABLES", "MLB-SNACKS", "MLB-COFFEE_AND_TEA",
    "MLB-HEALTH_DRINKS", "MLB-WINE_SPIRITS", "MLB-BEER_AND_CIDER",
}

# Tabela de comissão por domain_id (fonte: ML Afiliados — taxas base por categoria)
# Categorias não listadas recebem 0% (sem comissão de afiliado)
COMISSAO_POR_CATEGORIA = {
    # Alta comissão (≥10%)
    "MLB-SNEAKERS":                    15,
    "MLB-CLOTHING":                    15,
    "MLB-WOMEN_CLOTHING":              15,
    "MLB-MEN_CLOTHING":                15,
    "MLB-KIDS_CLOTHING":               15,
    "MLB-UNDERWEAR_AND_SLEEPWEAR":     15,
    "MLB-HANDBAGS_AND_ACCESSORIES":    15,
    "MLB-SHOES":                       15,
    "MLB-WOMEN_SHOES":                 15,
    "MLB-MEN_SHOES":                   15,
    "MLB-KIDS_SHOES":                  15,
    "MLB-FASHION_ACCESSORIES":         12,
    "MLB-WATCHES":                     12,
    "MLB-SUNGLASSES":                  12,
    "MLB-JEWELRY":                     12,
    "MLB-PERFUMES_AND_FRAGRANCES":     12,
    "MLB-PERFUMES":                    12,
    "MLB-MAKEUP":                      12,
    "MLB-SKIN_CARE":                   12,
    "MLB-HAIR_CARE":                   12,
    "MLB-PERSONAL_CARE":               12,
    "MLB-HEALTH_AND_BEAUTY":           12,
    "MLB-SPORTS_AND_OUTDOORS":         10,
    "MLB-CAMPING_AND_HIKING":          10,
    "MLB-BIKES":                       10,
    "MLB-FITNESS_EQUIPMENT":           10,
    "MLB-BABY_AND_KIDS":               10,
    "MLB-TOYS_AND_GAMES":              10,
    "MLB-BOOKS":                       10,
    "MLB-STATIONERY":                  10,
    "MLB-PET_SUPPLIES":                10,
    "MLB-HOME_AND_GARDEN":             10,
    "MLB-FURNITURE":                   10,
    "MLB-OFFICE_CHAIRS":               10,
    "MLB-BEDDING":                     10,
    "MLB-KITCHEN":                     10,
    "MLB-FOOD_STORAGE_CONTAINERS":     10,
    "MLB-TOOLS_AND_HOME_IMPROVEMENT":  10,
    "MLB-AIR_FRYERS":                  10,
    "MLB-SMALL_APPLIANCES":            10,
    # Média comissão (5–9%) — abaixo do mínimo de 10%
    "MLB-ELECTRONICS_ACCESSORIES":      8,
    "MLB-HEADPHONES":                   8,
    "MLB-SPEAKERS":                     8,
    "MLB-CAMERAS_AND_ACCESSORIES":      7,
    "MLB-VIDEO_GAMES":                  7,
    "MLB-MUSICAL_INSTRUMENTS":          7,
    "MLB-AUTO_PARTS":                   6,
    "MLB-TIRES_AND_WHEELS":             6,
    # Baixa comissão (<5%) — sem programa de afiliados
    "MLB-CELL_PHONES_AND_SMARTPHONES":  3,
    "MLB-CELLPHONES":                   3,
    "MLB-TABLETS_AND_ACCESSORIES":      3,
    "MLB-COMPUTERS":                    3,
    "MLB-NOTEBOOKS":                    3,
    "MLB-LAPTOPS_AND_ACCESSORIES":      3,
    "MLB-TELEVISIONS":                  3,
    "MLB-LARGE_APPLIANCES":             3,
    "MLB-PRINTERS":                     3,
    "MLB-PROJECTORS":                   3,
    "MLB-GAME_CONSOLES":                3,
    "MLB-SURVEILLANCE_CAMERAS":         3,
}

# Padrão do link de afiliado, usado para remover o link da legenda do Instagram
# (no Instagram o link vai no comentário fixado, não na legenda)
LINK_AFILIADO_PATTERN = re.compile(r'https://www\.mercadolivre\.com\.br/p/MLB\d+\?matt_tool=\d+&matt_word=\w+')

TEXTO_LINK_COMENTARIO = "\n\n👉 Link na bio."

# Palavras no nome do produto que indicam alimento/bebida
PALAVRAS_BLOQUEADAS = {
    "café", "cafe", "cerveja", "vinho", "suco", "refrigerante", "whey",
    "proteína", "proteina", "suplemento", "vitamina", "leite", "iogurte",
    "chocolate", "biscoito", "barra de cereal", "granola", "óleo", "oleo",
    "azeite", "arroz", "feijão", "feijao", "macarrão", "macarrao",
    "farinha", "tempero", "molho", "ketchup", "mostarda", "bebida",
}


# ════════════════════════════════════════════════════════════════════
#  VERIFICAÇÃO DE VALIDADE DO TOKEN DO FACEBOOK
# ════════════════════════════════════════════════════════════════════

def verificar_token_facebook():
    """Verifica quantos dias faltam para o token expirar e avisa no log."""
    try:
        resp = requests.get(
            "https://graph.facebook.com/debug_token",
            params={
                "input_token":  FB_PAGE_TOKEN,
                "access_token": FB_PAGE_TOKEN,
            },
            timeout=10
        )
        dados = resp.json().get("data", {})
        expira_em = dados.get("expires_at", 0)

        if expira_em == 0:
            log.info("Token do Facebook: sem expiração definida (pode ser permanente).")
            return

        dias_restantes = (expira_em - time.time()) / 86400

        if dias_restantes <= 0:
            log.error("=" * 55)
            log.error("TOKEN DO FACEBOOK EXPIRADO!")
            log.error("Siga o passo a passo abaixo para renovar:")
            log.error("1. Acesse: developers.facebook.com/tools/explorer")
            log.error("2. Selecione 'Promo Radar' em App da Meta")
            log.error("3. Clique em 'Generate Access Token' e autorize")
            log.error("4. No dropdown 'Token do usuario', selecione 'Promo Radar'")
            log.error("5. Copie o token e envie para o Claude atualizar")
            log.error("=" * 55)
        elif dias_restantes <= 15:
            log.warning("=" * 55)
            log.warning(f"ATENCAO: Token do Facebook expira em {int(dias_restantes)} dias!")
            log.warning("Renove seguindo o passo a passo:")
            log.warning("1. Acesse: developers.facebook.com/tools/explorer")
            log.warning("2. Selecione 'Promo Radar' em App da Meta")
            log.warning("3. Clique em 'Generate Access Token' e autorize")
            log.warning("4. No dropdown 'Token do usuario', selecione 'Promo Radar'")
            log.warning("5. Copie o token e envie para o Claude atualizar")
            log.warning("=" * 55)
        else:
            log.info(f"Token do Facebook OK — expira em {int(dias_restantes)} dias.")

    except Exception as e:
        log.warning(f"Nao foi possivel verificar o token do Facebook: {e}")


# ════════════════════════════════════════════════════════════════════
#  1. MERCADO LIVRE — Token OAuth
# ════════════════════════════════════════════════════════════════════

_ml_token = None
_ml_token_expira = 0

def obter_token_ml():
    global _ml_token, _ml_token_expira
    if _ml_token and time.time() < _ml_token_expira:
        return _ml_token

    esperas = [2 * 60, 4 * 60]  # retry: aguarda 2 min, depois 4 min
    ultimo_erro = None
    for tentativa in range(1, 4):
        try:
            resp = requests.post(
                "https://api.mercadolibre.com/oauth/token",
                data={"grant_type": "client_credentials",
                      "client_id": os.getenv("ML_CLIENT_ID"),
                      "client_secret": os.getenv("ML_CLIENT_SECRET"),
                      "scope": "read"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15
            )
            resp.raise_for_status()
            dados = resp.json()
            _ml_token = dados["access_token"]
            _ml_token_expira = time.time() + dados.get("expires_in", 21600) - 300
            if tentativa > 1:
                log.info(f"Token ML obtido na tentativa {tentativa}/3.")
            return _ml_token
        except Exception as e:
            ultimo_erro = e
            if tentativa < 3:
                espera = esperas[tentativa - 1]
                log.warning(f"Erro ao obter token ML (tentativa {tentativa}/3): {e}. Aguardando {espera // 60} min antes de tentar novamente...")
                time.sleep(espera)

    raise Exception(f"Falha ao obter token ML após 3 tentativas: {ultimo_erro}")


# ════════════════════════════════════════════════════════════════════
#  2. BUSCAR OFERTAS DO MERCADO LIVRE via página de Ofertas
# ════════════════════════════════════════════════════════════════════

BADGE_PRIORIDADE = [
    "oferta_do_dia",     # prioridade 1
    "oferta_relampago",  # prioridade 2
    "oferta_imperdivel", # prioridade 3
    "mais_vendido",      # prioridade 4
]

BADGE_PATTERNS = {
    "oferta_do_dia":     r'oferta.{0,10}dia',
    "oferta_relampago":  r'oferta.{0,10}rel[aâ]mpago',
    "oferta_imperdivel": r'oferta.{0,10}imperd[ií]vel',
    "mais_vendido":      r'mais.?vendido',
}

BADGE_LABELS = {
    "oferta_do_dia":     "Oferta do Dia",
    "oferta_relampago":  "Oferta Relâmpago",
    "oferta_imperdivel": "Oferta Imperdível",
    "mais_vendido":      "Mais Vendido",
}


def buscar_catalog_ids_ofertas():
    """Extrai IDs de catálogo da página de ofertas do ML e detecta badges por prioridade."""
    resp = requests.get(
        "https://www.mercadolivre.com.br/ofertas",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
        timeout=15
    )
    resp.raise_for_status()
    html = resp.text

    # Posições de cada tipo de badge no HTML
    badge_pos = {
        badge: [m.start() for m in re.finditer(pattern, html, re.IGNORECASE)]
        for badge, pattern in BADGE_PATTERNS.items()
    }

    url_map = {}
    for m in re.finditer(
        r'(https://www\.mercadolivre\.com\.br/[a-zA-Z0-9_\-/]+/p/(MLB\d+))',
        html
    ):
        catalog_id = m.group(2)
        if catalog_id in url_map:
            continue
        pos = m.start()

        # Detecta o badge de maior prioridade dentro de ~3000 chars ao redor do link
        badge_detectado = None
        for badge in BADGE_PRIORIDADE:
            if any(abs(pos - bp) <= 3000 for bp in badge_pos[badge]):
                badge_detectado = badge
                break

        url_map[catalog_id] = {
            "url":          m.group(1),
            "badge":        badge_detectado,
            "mais_vendido": badge_detectado == "mais_vendido",  # compat legado
        }

    resumo = {b: sum(1 for v in url_map.values() if v["badge"] == b) for b in BADGE_PRIORIDADE}
    log.info(f"Badges detectados: " + " | ".join(f"{BADGE_LABELS[b]}: {resumo[b]}" for b in BADGE_PRIORIDADE))

    return url_map


def buscar_detalhes_catalog(catalog_id, token):
    """Busca detalhes e item de um produto de catálogo."""
    # Busca dados do catálogo
    r_cat = requests.get(
        f"https://api.mercadolibre.com/products/{catalog_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    if r_cat.status_code != 200:
        return None
    cat = r_cat.json()

    # Busca o melhor item desse catálogo
    r_items = requests.get(
        f"https://api.mercadolibre.com/products/{catalog_id}/items",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    if r_items.status_code != 200:
        return None

    items = r_items.json().get("results", [])
    if not items:
        return None

    # Pega o item mais barato
    item = sorted(items, key=lambda x: x.get("price", 9999))[0]

    preco_atual = float(item.get("price", 0))
    preco_orig  = float(item.get("original_price") or 0)

    if preco_atual <= 0:
        return None

    if preco_orig <= preco_atual:
        preco_orig = preco_atual

    desconto = round((1 - preco_atual / preco_orig) * 100) if preco_orig > preco_atual else 0

    # Busca sold_quantity, condição e vendedor — tenta do resumo, senão busca detalhe
    vendas    = item.get("sold_quantity", 0)
    condicao  = item.get("condition", "")
    seller_id = item.get("seller_id")
    if (vendas == 0 or not condicao or not seller_id) and item.get("item_id"):
        r_item = requests.get(
            f"https://api.mercadolibre.com/items/{item['item_id']}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r_item.status_code == 200:
            detalhe = r_item.json()
            if vendas == 0:
                vendas = detalhe.get("sold_quantity", 0)
            condicao  = detalhe.get("condition", condicao)
            seller_id = detalhe.get("seller_id", seller_id)

    # Imagem do catálogo
    imagem = ""
    pics = cat.get("pictures", [])
    if pics:
        imagem = pics[0].get("url", "")
    elif cat.get("main_features"):
        pass

    return {
        "id":            catalog_id,
        "item_id":       item.get("item_id", ""),
        "nome":          cat.get("name", ""),
        "preco":         preco_atual,
        "preco_orig":    preco_orig,
        "desconto":      desconto,
        "vendas":        vendas,
        "imagem_url":    imagem,
        "categoria":     cat.get("domain_id", ""),
        "condicao":      condicao,
        "seller_id":     seller_id,
        "link_afiliado": f"https://www.mercadolivre.com.br/p/{catalog_id}?matt_tool={ML_AFILIADO_ID}&matt_word={ML_AFILIADO_TAG}",
    }


# Cache de reputação de vendedores (evita repetir requisições para o mesmo seller_id)
_reputacao_cache = {}


def vendedor_reputacao_verde(seller_id, token):
    """Retorna True se a reputação do vendedor estiver no nível verde (5_green)."""
    if not seller_id:
        return False
    if seller_id in _reputacao_cache:
        return _reputacao_cache[seller_id]

    verde = False
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/users/{seller_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r.status_code == 200:
            level_id = r.json().get("seller_reputation", {}).get("level_id", "")
            verde = level_id == "5_green"
    except Exception:
        pass

    _reputacao_cache[seller_id] = verde
    return verde


PRODUTOS_POSTADOS_PATH = Path("produtos_postados.json")
BLOQUEIO_DIAS = 7  # dias que um produto fica bloqueado após ser postado


def carregar_produtos_postados():
    """Retorna dict {catalog_id: iso_datetime} dos produtos postados recentemente."""
    if not PRODUTOS_POSTADOS_PATH.exists():
        return {}
    with open(PRODUTOS_POSTADOS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def registrar_produto_postado(catalog_id):
    """Registra o catalog_id como postado agora e remove entradas com mais de 7 dias."""
    postados = carregar_produtos_postados()
    postados[catalog_id] = datetime.now().isoformat()

    # Remove entradas antigas para não crescer indefinidamente
    corte = datetime.now() - timedelta(days=BLOQUEIO_DIAS)
    postados = {cid: dt for cid, dt in postados.items()
                if datetime.fromisoformat(dt) >= corte}

    with open(PRODUTOS_POSTADOS_PATH, "w", encoding="utf-8") as f:
        json.dump(postados, f, ensure_ascii=False, indent=2)


def produto_ja_postado(catalog_id):
    """Retorna True se o produto foi postado nos últimos BLOQUEIO_DIAS dias."""
    postados = carregar_produtos_postados()
    if catalog_id not in postados:
        return False
    postado_em = datetime.fromisoformat(postados[catalog_id])
    return datetime.now() - postado_em < timedelta(days=BLOQUEIO_DIAS)


def categoria_bloqueada(prod):
    """Retorna True se o produto é de alimentos/bebidas (sem comissão de afiliado)."""
    dominio = prod.get("categoria", "").upper()
    if dominio in {c.upper() for c in CATEGORIAS_BLOQUEADAS}:
        return True
    nome = prod.get("nome", "").lower()
    return any(palavra in nome for palavra in PALAVRAS_BLOQUEADAS)


def comissao_categoria(domain_id):
    """Retorna a comissão estimada (%) para um domain_id do ML."""
    return COMISSAO_POR_CATEGORIA.get(domain_id, 0)


def _filtrar_candidatos(catalog_ids, url_map, grupo_ids, token, min_desconto,
                         ignorar_bloqueio_7d=False, usar_comissao=False, max_preco=None):
    """Busca e filtra candidatos a post dentro de um grupo de IDs permitidos.
    Se usar_comissao=True: exclui apenas comissão=0 e ordena por comissão DESC depois desconto DESC.
    Caso contrário: ordena só por desconto DESC.
    max_preco sobrescreve MAX_PRECO quando informado.
    """
    limite_preco = max_preco if max_preco is not None else MAX_PRECO
    produtos = []
    for catalog_id in catalog_ids:
        try:
            if catalog_id not in grupo_ids:
                continue

            if not ignorar_bloqueio_7d and produto_ja_postado(catalog_id):
                log.info(f"  {catalog_id}: ignorado (postado nos últimos {BLOQUEIO_DIAS} dias)")
                continue

            prod = buscar_detalhes_catalog(catalog_id, token)
            if prod is None:
                continue
            if categoria_bloqueada(prod):
                log.info(f"  {catalog_id}: descartado (alimento/bebida — sem comissão)")
                continue

            if prod.get("condicao") and prod["condicao"] != "new":
                log.info(f"  {catalog_id}: descartado (produto usado)")
                continue

            if not vendedor_reputacao_verde(prod.get("seller_id"), token):
                log.info(f"  {catalog_id}: descartado (reputação do vendedor não é verde)")
                continue

            if usar_comissao:
                comissao = comissao_categoria(prod["categoria"])
                if comissao == 0:
                    log.info(f"  {catalog_id}: descartado (categoria '{prod['categoria']}' sem programa de afiliados)")
                    continue
                prod["comissao"] = comissao

            if prod["desconto"] < min_desconto:
                continue
            if prod["preco"] > limite_preco:
                continue
            if prod["vendas"] > 0 and prod["vendas"] < MIN_VENDAS:
                log.info(f"  {catalog_id}: descartado ({prod['vendas']} vendas < {MIN_VENDAS})")
                continue

            produtos.append(prod)
        except Exception as e:
            log.warning(f"Erro ao buscar {catalog_id}: {e}")

    # Ordenação: categorias preferidas sempre primeiro, depois por comissão/desconto
    def sort_key(p):
        em_foco = 1 if p.get("categoria") in CATEGORIAS_PREFERIDAS else 0
        if usar_comissao:
            return (em_foco, p.get("comissao", 0), p["desconto"])
        return (em_foco, p["desconto"])

    return sorted(produtos, key=sort_key, reverse=True)


def selecionar_melhor_produto(ignorar_bloqueio=False, max_preco=None):
    """Busca produtos da página de ofertas do ML e retorna o melhor.

    Ordem de prioridade dos badges:
      1. Oferta do Dia
      2. Oferta Relâmpago
      3. Oferta Imperdível
      4. Mais Vendido
    Em cada badge tenta ≥15% de desconto. Se nenhum badge tiver produto novo
    suficiente, cai nos fallbacks abaixo.
    max_preco sobrescreve MAX_PRECO quando informado.
    """
    limite_preco = max_preco if max_preco is not None else MAX_PRECO
    log.info(f"Buscando ofertas do Mercado Livre... (preço máximo: R$ {limite_preco:.2f})")
    try:
        token = obter_token_ml()
        url_map = buscar_catalog_ids_ofertas()
        log.info(f"{len(url_map)} produtos encontrados na página de ofertas.")
    except Exception as e:
        log.warning(f"Erro ao buscar ofertas: {e}")
        return None

    ids = list(url_map.keys())[:30]

    # Agrupa IDs por badge
    grupos = {
        badge: {cid for cid, info in url_map.items() if info["badge"] == badge}
        for badge in BADGE_PRIORIDADE
    }

    # Tentativas 1–4: cada badge em ordem de prioridade, desconto ≥15%, produto novo
    for badge in BADGE_PRIORIDADE:
        grupo = grupos[badge]
        if not grupo:
            continue
        produtos = _filtrar_candidatos(ids, url_map, grupo, token, MIN_DESCONTO,
                                       ignorar_bloqueio_7d=ignorar_bloqueio, max_preco=limite_preco)
        if produtos:
            melhor = produtos[0]
            log.info(f"Melhor produto [{BADGE_LABELS[badge]}]: {melhor['nome']} — {melhor['desconto']}% off — R$ {melhor['preco']:.2f}")
            return melhor
        log.info(f"Nenhum produto novo com {MIN_DESCONTO}%+ e preço ≤ R$ {limite_preco} em [{BADGE_LABELS[badge]}].")

    # Tentativa 5: qualquer badge, desconto ≥5%, produto novo
    log.warning(f"Nenhum badge com {MIN_DESCONTO}%+ disponível. Tentando {MIN_DESCONTO_FALLBACK}%+ em qualquer badge...")
    todos_com_badge = {cid for cid, info in url_map.items() if info["badge"] is not None}
    if todos_com_badge:
        produtos = _filtrar_candidatos(ids, url_map, todos_com_badge, token, MIN_DESCONTO_FALLBACK,
                                       ignorar_bloqueio_7d=ignorar_bloqueio, max_preco=limite_preco)
        if produtos:
            melhor = produtos[0]
            log.info(f"Produto (fallback desconto ≥{MIN_DESCONTO_FALLBACK}%): {melhor['nome']} — {melhor['desconto']}% off — R$ {melhor['preco']:.2f}")
            return melhor

    # Tentativa 6: qualquer produto novo com comissão > 0, ordenado por comissão DESC
    log.warning("Nenhum badge novo disponível. Buscando qualquer produto com comissão (maior comissão primeiro)...")
    todos_ids = list(url_map.keys())[:30]
    produtos = _filtrar_candidatos(todos_ids, url_map, set(todos_ids), token, MIN_DESCONTO,
                                   ignorar_bloqueio_7d=ignorar_bloqueio, usar_comissao=True, max_preco=limite_preco)
    if produtos:
        melhor = produtos[0]
        log.info(f"Produto (tabela comissão): {melhor['nome']} — {melhor['desconto']}% off — {melhor.get('comissao', '?')}% comissão — R$ {melhor['preco']:.2f}")
        return melhor

    # Tentativa 7 (último recurso): repete badge mais_vendido já postado, comissão > 0
    log.warning("Nenhum produto novo disponível. Repetindo 'mais vendido' (nunca comissão zero)...")
    mais_vendidos = grupos["mais_vendido"]
    if mais_vendidos:
        produtos = _filtrar_candidatos(ids, url_map, mais_vendidos, token, MIN_DESCONTO,
                                       ignorar_bloqueio_7d=True, usar_comissao=True, max_preco=limite_preco)
        if produtos:
            melhor = produtos[0]
            log.info(f"Produto (repetição forçada): {melhor['nome']} — {melhor['desconto']}% off — R$ {melhor['preco']:.2f}")
            return melhor

    log.warning("Nenhum produto adequado encontrado.")
    return None


# ════════════════════════════════════════════════════════════════════
#  3. OPENAI — Gerar texto do post
# ════════════════════════════════════════════════════════════════════

def gerar_texto_post(produto):
    log.info("Gerando texto do post com IA...")
    cliente = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"""Crie um post chamativo para um grupo de ofertas no Facebook sobre este produto do Mercado Livre.

Produto: {produto['nome']}
Preço atual: R$ {produto['preco']:.2f}
Preço original: R$ {produto['preco_orig']:.2f}
Desconto: {produto['desconto']}%
Economia: R$ {produto['preco_orig'] - produto['preco']:.2f}
Categoria: {produto['categoria']}
Link: {produto['link_afiliado']}

Regras:
- Use emojis animados e seja urgente (ex: "HOJE SÓ!", "CORRE!")
- Destaque o desconto e a economia em reais
- Máximo 200 palavras
- Coloque o link no final como URL simples (sem formato Markdown, sem colchetes)
- Termine com estas hashtags: #oferta #desconto #mercadolivre #promocao #economize
- Escreva em português do Brasil
- Não invente especificações que não foram fornecidas"""

    resposta = cliente.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.85,
    )
    texto = resposta.choices[0].message.content.strip()
    log.info("Texto gerado com sucesso.")
    return texto


# ════════════════════════════════════════════════════════════════════
#  4. IMAGEM — Baixar e adicionar banner de desconto
# ════════════════════════════════════════════════════════════════════

def gerar_imagem_post(produto):
    log.info("Baixando imagem do produto...")
    Path("imagens").mkdir(exist_ok=True)

    caminho = f"imagens/post_{produto['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

    try:
        resp = requests.get(produto["imagem_url"], timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img.save(caminho, "JPEG", quality=95)
        log.info(f"Imagem salva: {caminho}")
        return caminho
    except Exception as e:
        log.warning(f"Erro ao baixar imagem do produto: {e}. Usando imagem placeholder.")
        img = Image.new("RGB", (600, 600), (30, 30, 30))
        img.save(caminho, "JPEG", quality=95)
        return caminho


# ════════════════════════════════════════════════════════════════════
#  5. FACEBOOK — Publicar post com imagem
# ════════════════════════════════════════════════════════════════════

def publicar_no_facebook(texto, link, imagem_path=None):
    log.info("Publicando no Facebook...")

    # Recarrega token do config.env a cada post (pega sempre o mais atualizado)
    load_dotenv("config.env", override=True)
    token = os.getenv("FB_PAGE_TOKEN")

    BASE = "https://graph.facebook.com/v19.0/me"

    try:
        media_fbid = None

        # Passo 1: upload da foto como não-publicada
        if imagem_path:
            log.info(f"Fazendo upload da imagem: {imagem_path}")
            with open(imagem_path, "rb") as f:
                r_foto = requests.post(
                    f"{BASE}/photos",
                    data={"access_token": token, "published": "false"},
                    files={"source": f},
                    timeout=30,
                )
            if r_foto.status_code == 200:
                media_fbid = r_foto.json().get("id")
                log.info(f"Foto carregada com ID: {media_fbid}")
            else:
                log.warning(f"Falha no upload da foto: {r_foto.status_code} — {r_foto.text}. Publicando com prévia de link.")

        # Passo 2: cria o post no feed
        # Quando há foto anexada, omite o parâmetro "link" para o FB não sobrepor com prévia
        post_data = {
            "access_token": token,
            "message":      texto,
        }
        if media_fbid:
            post_data["attached_media"] = json.dumps([{"media_fbid": media_fbid}])
        else:
            post_data["link"] = link

        r = requests.post(f"{BASE}/feed", data=post_data, timeout=30)
        log.info(f"Resposta Facebook: status={r.status_code} resp={r.text}")

        if r.status_code == 200:
            post_id = r.json().get("id")
            log.info(f"Post publicado no feed! ID: {post_id}")

            r_check = requests.get(
                f"https://graph.facebook.com/v19.0/{post_id}",
                params={
                    "access_token": token,
                    "fields": "id,message,created_time,is_published,story,permalink_url"
                },
                timeout=10,
            )
            log.info(f"Verificação do post: {r_check.text}")
            return post_id
        else:
            log.error(f"Erro ao publicar: {r.status_code} — {r.text}")
            return None
    except Exception as e:
        log.error(f"Erro ao publicar no Facebook: {e}", exc_info=True)
        return None


# ════════════════════════════════════════════════════════════════════
#  5b. INSTAGRAM — Publicar post com imagem
# ════════════════════════════════════════════════════════════════════

def preparar_caption_instagram(texto, link=None):
    """Remove o parágrafo do link de afiliado da legenda (e o parágrafo anterior, se
    mencionar 'link') e adiciona aviso de link no comentário fixado.
    Se link for informado, procura esse link específico; caso contrário, tenta encontrar
    qualquer link de afiliado via regex (usado para itens de backlog)."""
    padrao = re.escape(link) if link else LINK_AFILIADO_PATTERN.pattern

    paragrafos = re.split(r"\n\s*\n", texto)
    remover = set()
    for i, p in enumerate(paragrafos):
        if re.search(padrao, p):
            remover.add(i)
            if i > 0 and "link" in paragrafos[i - 1].lower():
                remover.add(i - 1)

    paragrafos = [p.strip() for i, p in enumerate(paragrafos) if i not in remover and p.strip()]
    texto_sem_link = "\n\n".join(paragrafos)

    return texto_sem_link + TEXTO_LINK_COMENTARIO


def comentar_link_instagram(media_id, link):
    """Posta um comentário com o link de afiliado no post do Instagram."""
    load_dotenv("config.env", override=True)
    token = os.getenv("FB_PAGE_TOKEN")

    try:
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{media_id}/comments",
            data={
                "access_token": token,
                "message": f"🔗 Link do produto: {link}",
            },
            timeout=15,
        )
        if r.status_code == 200:
            comment_id = r.json().get("id")
            log.info(f"Comentário com link postado no Instagram: {comment_id}")
            return comment_id
        else:
            log.warning(f"Falha ao comentar link no Instagram: {r.status_code} — {r.text}")
            return None
    except Exception as e:
        log.warning(f"Erro ao comentar link no Instagram: {e}")
        return None


def publicar_no_instagram(texto, imagem_path, link=None):
    log.info("Publicando no Instagram...")

    # Recarrega token e ID do config.env a cada post (pega sempre o mais atualizado)
    load_dotenv("config.env", override=True)
    token = os.getenv("FB_PAGE_TOKEN")
    ig_user_id = os.getenv("INSTAGRAM_USER_ID")

    if not ig_user_id:
        log.warning("INSTAGRAM_USER_ID não configurado — pulando publicação no Instagram.")
        return None

    # O Instagram Graph API exige uma URL pública de imagem (não aceita upload de arquivo local)
    imagem_url = imagem_path
    if not imagem_url:
        log.warning("Sem imagem disponível — Instagram exige imagem, pulando publicação.")
        return None

    BASE = f"https://graph.facebook.com/v19.0/{ig_user_id}"

    try:
        # Passo 1: cria o container de mídia
        r_media = requests.post(
            f"{BASE}/media",
            data={
                "access_token": token,
                "image_url":    imagem_url,
                "caption":      texto,
            },
            timeout=30,
        )
        if r_media.status_code != 200:
            log.error(f"Erro ao criar container do Instagram: {r_media.status_code} — {r_media.text}")
            return None
        creation_id = r_media.json().get("id")
        log.info(f"Container do Instagram criado: {creation_id}")

        # Aguarda o container terminar de processar a imagem antes de publicar
        # (evita erro 2207027 "Media ID is not available")
        for tentativa in range(10):
            r_status = requests.get(
                f"https://graph.facebook.com/v19.0/{creation_id}",
                params={"access_token": token, "fields": "status_code"},
                timeout=10,
            )
            status_code = r_status.json().get("status_code")
            if status_code == "FINISHED":
                break
            if status_code == "ERROR":
                log.error(f"Erro ao processar mídia do Instagram: {r_status.text}")
                return None
            time.sleep(2)
        else:
            log.warning("Container do Instagram não ficou pronto a tempo — tentando publicar mesmo assim.")

        # Passo 2: publica o container
        r_publish = requests.post(
            f"{BASE}/media_publish",
            data={
                "access_token": token,
                "creation_id":  creation_id,
            },
            timeout=30,
        )
        log.info(f"Resposta Instagram (publish): status={r_publish.status_code} resp={r_publish.text}")

        if r_publish.status_code == 200:
            media_id = r_publish.json().get("id")
            log.info(f"Post publicado no Instagram! ID: {media_id}")

            r_check = requests.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                params={
                    "access_token": token,
                    "fields": "id,permalink,timestamp"
                },
                timeout=10,
            )
            log.info(f"Verificação do post Instagram: {r_check.text}")

            if link:
                comentar_link_instagram(media_id, link)

            return media_id
        else:
            log.error(f"Erro ao publicar no Instagram: {r_publish.status_code} — {r_publish.text}")
            return None
    except Exception as e:
        log.error(f"Erro ao publicar no Instagram: {e}", exc_info=True)
        return None


# ════════════════════════════════════════════════════════════════════
#  5c. INSTAGRAM — Fila de backlog (repostagem de posts antigos do FB)
# ════════════════════════════════════════════════════════════════════

FILA_INSTAGRAM_BACKLOG = Path("fila_instagram_backlog.json")


def processar_fila_instagram_backlog():
    """Posta um item por vez da fila de backlog do Instagram (criada manualmente)."""
    if INSTAGRAM_PAUSADO:
        return

    if not FILA_INSTAGRAM_BACKLOG.exists():
        return

    with open(FILA_INSTAGRAM_BACKLOG, "r", encoding="utf-8") as f:
        fila = json.load(f)

    if not fila:
        return

    item = fila.pop(0)
    log.info(f"Processando item da fila de backlog do Instagram (restantes: {len(fila)}) — post original: {item['fb_post_id']}")

    link_match = LINK_AFILIADO_PATTERN.search(item["texto"])
    link = link_match.group(0) if link_match else None
    caption = preparar_caption_instagram(item["texto"], link=link) if link else item["texto"]

    media_id = publicar_no_instagram(caption, item["imagem_url"])
    if media_id:
        log.info(f"Backlog: post {item['fb_post_id']} repostado no Instagram com sucesso.")
    else:
        log.warning(f"Backlog: falha ao repostar {item['fb_post_id']} — item removido da fila mesmo assim.")

    with open(FILA_INSTAGRAM_BACKLOG, "w", encoding="utf-8") as f:
        json.dump(fila, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════════
#  6. FLUXO PRINCIPAL
# ════════════════════════════════════════════════════════════════════

def executar_post(modo_teste=False, max_preco=None):
    log.info("=" * 55)
    log.info(f"Iniciando ciclo de post — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    log.info("=" * 55)

    try:
        # 1. Busca melhor produto — com escalada de preço se necessário
        produto = None
        if max_preco is not None:
            # Tenta de 100 em 100 até MAX_PRECO
            limites = list(range(max_preco, MAX_PRECO + 1, 100))
            if MAX_PRECO not in limites:
                limites.append(MAX_PRECO)
            for limite in limites:
                produto = selecionar_melhor_produto(ignorar_bloqueio=modo_teste, max_preco=limite)
                if produto:
                    if limite > max_preco:
                        log.info(f"Produto encontrado com preço expandido para R$ {limite:.2f}")
                    break
        else:
            produto = selecionar_melhor_produto(ignorar_bloqueio=modo_teste)
        if not produto:
            log.warning("Nenhum produto adequado encontrado. Pulando ciclo.")
            return

        # 2. Gera texto com IA
        texto = gerar_texto_post(produto)
        print("\n" + "-" * 50)
        print("TEXTO DO POST:")
        print(texto.encode('cp1252', errors='replace').decode('cp1252'))
        print("-" * 50 + "\n")

        # 3. Baixa imagem do produto
        imagem_path = None
        if produto.get("imagem_url"):
            imagem_path = gerar_imagem_post(produto)

        # 4. Publica no Facebook com foto do produto
        if FB_PAGE_TOKEN and FB_PAGE_ID:
            post_id = publicar_no_facebook(texto, produto["link_afiliado"], imagem_path)
            if post_id:
                registrar_produto_postado(produto["id"])
        else:
            log.warning("Token do Facebook não configurado — post salvo localmente apenas.")
            registrar_produto_postado(produto["id"])

        # 5. Publica no Instagram (exige URL pública de imagem — usa a URL original do produto)
        if INSTAGRAM_PAUSADO:
            log.info("Publicação no Instagram pausada (INSTAGRAM_PAUSADO=True) — pulando.")
        else:
            # Legenda sem o link (vai como comentário fixado, pois o Instagram não permite links clicáveis na legenda)
            caption_instagram = preparar_caption_instagram(texto, link=produto["link_afiliado"])
            publicar_no_instagram(caption_instagram, produto.get("imagem_url"))

        # 6. Atualiza a vitrine (index.html) com o novo produto
        try:
            adicionar_produto(
                titulo=produto["nome"],
                link_afiliado=produto["link_afiliado"],
                preco=produto["preco"],
                categoria=mapear_categoria(produto["categoria"]),
                imagem_url=produto.get("imagem_url", ""),
                preco_original=produto["preco_orig"],
                desconto=produto["desconto"],
                auto_push=True,
            )
            log.info("Vitrine (index.html) atualizada e publicada.")
        except Exception as e:
            log.error(f"Erro ao atualizar a vitrine: {e}")

        # Salva histórico
        salvar_historico(produto, texto, imagem_path or produto["link_afiliado"])

    except Exception as e:
        log.error(f"Erro no ciclo de post: {e}", exc_info=True)


def salvar_historico(produto, texto, imagem):
    historico_path = Path("historico.json")
    historico = []
    if historico_path.exists():
        with open(historico_path, "r", encoding="utf-8") as f:
            historico = json.load(f)

    historico.append({
        "data":    datetime.now().isoformat(),
        "produto": produto["nome"],
        "preco":   produto["preco"],
        "desconto":produto["desconto"],
        "link":    produto["link_afiliado"],
        "imagem":  imagem,
        "texto":   texto[:100] + "...",
    })

    with open(historico_path, "w", encoding="utf-8") as f:
        json.dump(historico[-100:], f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════════
#  7. AGENDADOR
# ════════════════════════════════════════════════════════════════════

def iniciar_agendador():
    log.info("Agendador iniciado!")
    log.info("Posts agendados para: 09:00, 11:00, 13:00, 16:00 e 19:00")

    # Verifica token ao iniciar e todo dia às 08:00
    verificar_token_facebook()
    schedule.every().day.at("08:00").do(verificar_token_facebook)

    schedule.every().day.at("09:00").do(executar_post, max_preco=100)
    schedule.every().day.at("11:00").do(executar_post)
    schedule.every().day.at("13:00").do(executar_post, max_preco=100)
    schedule.every().day.at("16:00").do(executar_post)
    schedule.every().day.at("19:00").do(executar_post, max_preco=100)

    # Fila de backlog do Instagram — repostagem de posts antigos do FB,
    # 1 por horário (:30), espaçados ao longo do dia para não sobrecarregar
    # o limite de publicações do Instagram nem coincidir com os posts acima
    for hora in ["08:30", "09:30", "10:30", "11:30", "12:30", "13:30", "14:30",
                  "15:30", "16:30", "17:30", "18:30", "19:30", "20:30", "21:30",
                  "22:30", "23:30"]:
        schedule.every().day.at(hora).do(processar_fila_instagram_backlog)

    log.info("Sistema rodando... (Ctrl+C para parar)")
    while True:
        schedule.run_pending()
        time.sleep(60)


# ════════════════════════════════════════════════════════════════════
#  ENTRADA
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--testar":
        log.info("Modo de teste — executando um post agora (bloqueio de repetidos ignorado)...")
        executar_post(modo_teste=True)
    else:
        if not adquirir_lock():
            sys.exit(0)
        try:
            iniciar_agendador()
        finally:
            liberar_lock()
