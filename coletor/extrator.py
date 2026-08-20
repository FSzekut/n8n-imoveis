"""Extrai anúncios do JSON-LD (schema.org) das páginas dos portais.

VivaReal e ZAP são do mesmo grupo e publicam a mesma estrutura: um bloco
`ItemList` cujo `itemListElement[].item` traz o anúncio completo, com o preço
em `offers.price`. Por isso um extrator só atende os dois.

O bloco solto de `Apartment` que existe na mesma página tem título truncado e
não tem `offers` — não serve.
"""
import json
import re

BLOCO_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
# Lançamento é prédio inteiro: muitas unidades, sem preço único. Os dois portais
# marcam na URL, com caminhos diferentes.
LANCAMENTO = re.compile(r"/(?:imoveis-)?lancamentos/")
VAGAS_NO_NOME = re.compile(r"(\d+)\s+vagas?")
BAIRRO_NO_NOME = re.compile(r"\bem\s+(.+?),\s*Curitiba")


def _itens_do_itemlist(html):
    """Devolve os anúncios do bloco ItemList, o único que carrega `offers`."""
    for m in BLOCO_LD.finditer(html):
        try:
            dado = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        if isinstance(dado, dict) and dado.get("@type") == "ItemList":
            for elemento in dado.get("itemListElement") or []:
                item = elemento.get("item") or {}
                if item.get("@id"):
                    yield item


def extrair(html, portal, bairro):
    """Normaliza os anúncios de uma.

    O bairro não é extraído, vem da busca — o que o torna oficial por
    construção. Extrair não serviria: o `name` só traz o bairro em 9 de 30
    anúncios, e o slug do ZAP usa nome comercial (`ecoville` onde o bairro
    oficial é Campina do Siqueira).
    """
    itens, lancamentos, sem_preco = [], 0, 0
    for bruto in _itens_do_itemlist(html):
        url = bruto.get("url", "")
        if LANCAMENTO.search(url):
            lancamentos += 1
            continue

        preco = (bruto.get("offers") or {}).get("price")
        if not preco:
            sem_preco += 1
            continue

        nome = bruto.get("name", "")
        vagas = VAGAS_NO_NOME.search(nome)
        declarado = BAIRRO_NO_NOME.search(nome)

        itens.append({
            "portal": portal,
            "id": bruto["@id"],
            "preco": int(preco),
            "bairro": bairro,
            # Conferência: o filtroor Água Verde,
            # 1 dos 30 se declarou Portão.
            "bairro_declarado": declarado.group(1) if declarado else None,
            "quartos": bruto.get("numberOfBedrooms"),
            "banheiros": bruto.get("numberOfBathroomsTotal"),
            "vagas": int(vagas.group(1)) if vagas else None,
            "area": (bruto.get("floorSize") or {}).get("value"),
            "rua": (bruto.get("address") or {}).get("streetAddress"),
            "titulo": nome,
            "url": url,
        })
    return itens, lancamentos, sem_preco


EXTRATORES = {"vivareal": extrair, "zap": extrair}