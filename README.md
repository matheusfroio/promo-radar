# Promo Radar — Vitrine de Afiliados (Mercado Livre)

Vitrine estática de produtos de afiliado, hospedada gratuitamente no **GitHub Pages**, atualizada automaticamente pelo bot `automacao.py` (via `vitrine.py`) sempre que um novo produto é postado no Instagram/Facebook.

O link da página fica fixo na bio das redes sociais — o conteúdo muda, o link nunca muda.

A página já está integrada ao bot existente (`automacao.py`): a cada post publicado, o produto é adicionado automaticamente à vitrine. Veja a seção 3.

---

## 1. Criar o repositório no GitHub

1. Acesse [github.com](https://github.com) e faça login (ou crie uma conta gratuita).
2. Clique em **New repository**.
3. Dê um nome ao repositório, por exemplo: `promo-radar`.
4. Marque como **Public** (necessário para o GitHub Pages gratuito).
5. Não marque "Add a README" se você já vai subir os arquivos deste projeto (`index.html`, `vitrine.py`, `README.md`).
6. Clique em **Create repository**.

Depois, suba os arquivos deste projeto para o repositório. No terminal, dentro da pasta do projeto:

```bash
git init
git add index.html vitrine.py README.md
git commit -m "Setup inicial da vitrine"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/promo-radar.git
git push -u origin main
```

> ⚠️ Esta pasta (`Projetinho Félas`) também contém o bot `automacao.py` e seus arquivos sensíveis (`config.env`, `ml_cookies.txt`, etc). **Não suba esses arquivos para o repositório público.** Suba apenas `index.html`, `vitrine.py` e `README.md` — ou crie um `.gitignore` cobrindo o restante antes de fazer o `git init`.

> Troque `SEU_USUARIO` pelo seu nome de usuário do GitHub.

---

## 2. Ativar o GitHub Pages

1. No repositório, vá em **Settings** (Configurações).
2. No menu lateral, clique em **Pages**.
3. Em **Source**, selecione a branch `main` e a pasta `/ (root)`.
4. Clique em **Save**.
5. Aguarde 1-2 minutos. O GitHub vai gerar um link parecido com:

```
https://SEU_USUARIO.github.io/promo-radar/
```

6. Esse é o link que você vai colocar **fixo na bio do Instagram e na página do Facebook**.

---

## 3. Instalar e configurar o bot

### Pré-requisitos

- Python 3.8 ou superior
- Git instalado e configurado (`git config --global user.name` e `user.email`)
- O repositório clonado localmente, na mesma pasta onde está `index.html` e `vitrine.py`

### Configuração do Git para push automático

Para que o `auto_push=True` funcione sem pedir usuário/senha a cada execução, configure um **Personal Access Token (PAT)** do GitHub e use a URL remota com o token, ou configure o `git credential.helper` (`store` ou `manager`) para salvar suas credenciais uma única vez:

```bash
git config credential.helper store
```

Na primeira vez que o bot fizer `git push`, será solicitado usuário e senha (use o token como senha). Depois disso, o Git lembra as credenciais.

### Integração já feita no `automacao.py`

O `automacao.py` já importa e chama `vitrine.adicionar_produto()` automaticamente. No topo do arquivo:

```python
from vitrine import adicionar_produto, mapear_categoria
```

E dentro de `executar_post()`, logo após a publicação no Facebook/Instagram:

```python
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
```

A função `mapear_categoria()` (em `vitrine.py`) converte automaticamente a categoria do Mercado Livre (ex.: `MLB-SNEAKERS`, `MLB-FITNESS_EQUIPMENT`) para uma das categorias exibidas na vitrine (Eletrônicos, Moda, Casa, Esporte, Beleza, Geral).

Sempre que `executar_post()` roda com sucesso, o bot:

1. Publica o post no Facebook e/ou Instagram (como já fazia).
2. Lê o `index.html`.
3. Insere o novo produto no topo da lista da vitrine.
4. Remove produtos mais antigos se já houver 40 ou mais.
5. Salva o arquivo.
6. Executa `git add`, `git commit` e `git push` automaticamente (`auto_push=True`).

Em poucos segundos, o GitHub Pages publica a nova versão e o site é atualizado — sem você precisar fazer nada manualmente.

**Pré-requisito:** a pasta do bot (`Projetinho Félas`) precisa ser o mesmo diretório do repositório Git criado na seção 1 (ou seja, rode `git init` / `git remote add` dentro desta pasta). Se o `git push` falhar (ex.: repositório não inicializado, credenciais não configuradas), o erro é apenas registrado no log (`froio_automacao.log`) — **não interrompe** a publicação dos posts no Facebook/Instagram.

> Após editar `automacao.py` ou `vitrine.py`, reinicie o processo (`pythonw.exe`) conforme descrito em `.claudemedata.md`, seção "Comandos Úteis".

---

## 4. Como personalizar o nome e as cores do site

### Nome do site

No arquivo `index.html`, procure por:

```html
<title>Promo Radar — Ofertas do Mercado Livre</title>
...
<div class="logo">Promo <span>Radar</span></div>
```

Edite esses dois trechos para o nome que você quiser usar.

### Links de Instagram e Facebook ("Siga")

Abaixo do cabeçalho existe uma barra discreta com dois links — "Siga no Instagram" e "Curta no Facebook":

```html
<div class="social-bar">
  <a class="social-link" href="https://www.instagram.com/promoradar128?..." target="_blank" rel="noopener">
    ... Siga no Instagram
  </a>
  <a class="social-link" href="https://www.facebook.com/share/1BNRZoRUsd/" target="_blank" rel="noopener">
    ... Curta no Facebook
  </a>
</div>
```

Para trocar os links, basta editar os atributos `href` dessas duas tags `<a>`.

### Cores

Todas as cores estão centralizadas no início do `<style>`, dentro de `:root`:

```css
:root {
  --bg: #FFFFFF;          /* fundo geral */
  --surface: #F7F8FA;     /* fundo dos cards */
  --accent: #FF6900;      /* cor principal (CTAs, preços, badges) */
  --accent-dark: #E05A00; /* cor do botão ao passar o mouse */
  --text-primary: #1A1A1A;
  --text-secondary: #6B7280;
  --border: #E5E7EB;
  --red: #E11D48;         /* badge de desconto */
  --green: #16A34A;       /* badge "Novo" */
}
```

Basta trocar os valores hexadecimais para mudar a identidade visual de todo o site.

### Categorias

As categorias e seus emojis de fallback estão definidos em dois lugares:

1. Nos botões de filtro (HTML), dentro de `<div class="filters" id="filtros">`.
2. No JavaScript, no objeto `EMOJI_CATEGORIA`.

Para adicionar uma nova categoria, adicione um botão `<button class="pill" data-categoria="NomeDaCategoria">...</button>` e uma entrada correspondente em `EMOJI_CATEGORIA`, e inclua `"NomeDaCategoria"` em `CATEGORIAS_VALIDAS` no `vitrine.py`.

---

## 5. Exemplos de uso do `vitrine.py`

### Produto simples, sem desconto

```python
from vitrine import adicionar_produto

adicionar_produto(
    titulo="Caneca Térmica de Aço Inox 500ml",
    link_afiliado="https://www.mercadolivre.com.br/sec/xyz789",
    preco=39.90,
    categoria="Casa",
)
```

### Produto com desconto e imagem

```python
adicionar_produto(
    titulo="Tênis Esportivo Confort Run",
    link_afiliado="https://www.mercadolivre.com.br/sec/tenis001",
    preco=129.90,
    preco_original=199.90,
    desconto=35,
    categoria="Esporte",
    imagem_url="https://http2.mlstatic.com/D_Q_NP_2X_tenis.jpg",
)
```

### Testando sem publicar (sem git push)

Útil para testar localmente antes de automatizar:

```python
adicionar_produto(
    titulo="Produto de teste",
    link_afiliado="https://www.mercadolivre.com.br/sec/teste",
    preco=99.90,
    auto_push=False,  # apenas atualiza o index.html local
)
```

### Tratando erros

```python
try:
    adicionar_produto(
        titulo="Fone Bluetooth Pro",
        link_afiliado="https://www.mercadolivre.com.br/sec/fone001",
        preco=89.90,
        preco_original=129.90,
        desconto=30,
        categoria="Eletrônicos",
        imagem_url="https://http2.mlstatic.com/exemplo.jpg",
    )
    print("Produto publicado com sucesso!")
except (FileNotFoundError, ValueError, RuntimeError) as erro:
    print(f"Erro ao publicar produto: {erro}")
```

---

## Estrutura dos arquivos

```
.
├── index.html   # Vitrine (HTML + CSS + JS, sem dependências externas)
├── vitrine.py   # Módulo Python usado pelo bot para injetar produtos
└── README.md    # Este arquivo
```

---

## Observações importantes

- O site exibe automaticamente um badge **"Novo"** verde em produtos adicionados nas últimas 2 horas.
- A ordenação padrão é por "Mais recentes". O visitante pode alternar para "Maior desconto".
- A busca e os filtros de categoria funcionam 100% no navegador (JavaScript puro), sem reload de página.
- O limite de 40 produtos evita que a página fique muito pesada — produtos antigos são removidos automaticamente pelo `vitrine.py`.
- Sempre use links de afiliado encurtados/oficiais do Mercado Livre (`/sec/...`) para garantir que a comissão seja registrada corretamente.
