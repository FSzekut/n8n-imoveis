"""Serviço de coleta: busca a página com navegador real e devolve anúncios em JSON."""
from contextlib import asynccontextmanager

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from extrator import extrair
from extrator import EXTRATORES

recursos = {}


@asynccontextmanager
async def ciclo_de_vida(app):
    # Um Chromium só, vivo enquanto o serviço estiver de pé. Abrir e fechar o
    # navegador a cada chamada acrescentaria uns 2 segundos em toda requisição.
    crawler = AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False))
    await crawler.start()
    recursos["crawler"] = crawler
    yield
    await crawler.close()


app = FastAPI(title="Coletor de imóveis", lifespan=ciclo_de_vida)


class Pedido(BaseModel):
    portal: str
    url: str


@app.post("/coleta")
async def coleta(pedido: Pedido):
    extrator = EXTRATORES.get(pedido.portal)
    if extrator is None:
        raise HTTPException(
            501, f"portal '{pedido.portal}' ainda não tem extrator; "
                 f"disponíveis: {sorted(EXTRATORES)}"
        )
    resultado = await recursos["crawler"].arun(
        url=pedido.url,
        config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000),
    )
    if not resultado.success:
        raise HTTPException(502, f"falha ao buscar {pedido.url}")

    itens, lancamentos, sem_preco = extrair(resultado.html, pedido.portal)
    return {
        "portal": pedido.portal,
        "total": len(itens),
        "lancamentos_ignorados": lancamentos,   # esperado
        "descartados_sem_preco": sem_preco,     # se subir, o slug mudou
        "itens": itens,
    }