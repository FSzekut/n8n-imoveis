"""Serviço de coleta: busca as páginas com navegador real e devolve anúncios em JSON."""
import asyncio

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from extrator import EXTRATORES

app = FastAPI(title="Coletor de imóveis")

# Os portais bloqueiam a SESSÃO, não o ritmo: a segunda busca no mesmo navegador
# volta 403 em meio segundo, com pausa de 3s ou de 8s, no ZAP e no VivaReal.
# Por isso cada página abre o próprio navegador e o fecha em seguida.
# O lock serializa as coletas — uma por vez, sem vários Chromium simultâneos.
_vez = asyncio.Lock()
PAUSA_ENTRE_PAGINAS = 3
TETO_DE_PAGINAS = 12


class Pedido(BaseModel):
    portal: str
    bairro: str
    url: str
    paginas: int = TETO_DE_PAGINAS


def _url_da_pagina(url, pagina):
    if pagina == 1:
        return url
    junta = "&" if "?" in url else "?"
    return f"{url}{junta}pagina={pagina}"


async def _buscar(url):
    """Uma página, um navegador — ver o comentário do lock acima."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        return await crawler.arun(
            url=url,
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000),
        )


@app.post("/coleta")
async def coleta(pedido: Pedido):
    extrator = EXTRATORES.get(pedido.portal)
    if extrator is None:
        raise HTTPException(
            501, f"portal '{pedido.portal}' ainda não tem extrator; "
                 f"disponíveis: {sorted(EXTRATORES)}"
        )

    itens, lancamentos, sem_preco, paginas_lidas = [], 0, 0, 0
    vistos = set()
    teto = max(1, min(pedido.paginas, TETO_DE_PAGINAS))

    async with _vez:
        for pagina in range(1, teto + 1):
            resultado = await _buscar(_url_da_pagina(pedido.url, pagina))

            if not resultado.success:
                # Falhar na primeira é falha de verdade. Falhar na quarta, com três
                # páginas já lidas, é melhor entregar o que se tem do que perder tudo.
                if pagina == 1:
                    raise HTTPException(
                        502, f"falha ao buscar {pedido.url} (status {resultado.status_code})"
                    )
                break

            da_pagina, lanc, sem = extrator(resultado.html, pedido.portal, pedido.bairro)

            # Fim da lista. Não dá para parar em "veio menos de 30": a última página
            # pode ter exatamente 30. Página fora do intervalo devolve 200 SEM o bloco
            # ItemList (não 404), então o vazio é o sinal confiável.
            if not da_pagina and not lanc:
                break

            # Guarda contra portal que devolve a página 1 quando o número passa do
            # fim: se nada veio inédito, estamos relendo o que já está na mão.
            # Verificado no VivaReal (devolve vazio); o ZAP não foi verificado.
            ineditos = [i for i in da_pagina if i["id"] not in vistos]
            if not ineditos:
                break

            vistos.update(i["id"] for i in ineditos)
            itens.extend(ineditos)
            lancamentos += lanc
            sem_preco += sem
            paginas_lidas = pagina

            await asyncio.sleep(PAUSA_ENTRE_PAGINAS)

    return {
        "portal": pedido.portal,
        "bairro": pedido.bairro,
        "paginas_lidas": paginas_lidas,
        "total": len(itens),
        "lancamentos_ignorados": lancamentos,
        "descartados_sem_preco": sem_preco,
        "itens": itens,
    }
