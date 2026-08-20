"""Extrai anúncios do JSON-LD (schema.org) das páginas de portais."""
import json
import re

# O preço não existe como campo no JSON-LD: só aparece no slug da URL.
PRECO_NA_URL = re.compile(r"-RS(\d+)-id-")
# O bairro também. O título é texto livre e só traz o bairro em 2 de 25 casos;
# o slug traz em todos. Fica entre o tipo/quartos e o "-curitiba-".
BAIRRO_NO_SLUG = re.compile(r"/imovel/[a-z]+-(?:\d+-quartos?-)?(.+?)-curitiba-")
# Lançamento é outro tipo de coisa: prédio inteiro, muitas unidades, sem preço único.
LANCAMENTO = re.compile(r"/imoveis-lancamentos/")
TEM_GARAGEM = re.compile(r"-com-garagem-")
VAGAS_NO_NOME = re.compile(r"(\d+)\s+vaga")

BLOCO_LD = re.compile(
    r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S
)


def _anuncios_brutos(html):
    """Devolve os dicionários schema.org de imóvel presentes na página."""
    for m in BLOCO_LD.finditer(html):
        try:
            dado = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        if isinstance(dado, list):
            for item in dado:
                if isinstance(item, dict) and item.get("@id"):
                    yield item


def extrair(html, portal):
    """Normaliza os anúncios.

    Devolve três coisas de propósito: os itens, quantos lançamentos foram
    ignorados (esperado, acontece toda rodada) e quantos anúncios comuns
    ficaram sem preço legível (não esperado — se subir, o slug mudou).
    """
    itens, lancamentos, sem_preco = [], 0, 0
    for bruto in _anuncios_brutos(html):
        url = bruto.get("url", "")

        if LANCAMENTO.search(url):
            lancamentos += 1
            continue

        preco = PRECO_NA_URL.search(url)
        if not preco:
            sem_preco += 1
            continue

        nome = bruto.get("name", "")
        bairro = BAIRRO_NO_SLUG.search(url)
        vagas = VAGAS_NO_NOME.search(nome)

        itens.append({
            "portal": portal,
            "id": bruto["@id"],
            "preco": int(preco.group(1)),
            "bairro": bairro.group(1) if bairro else None,
            "quartos": bruto.get("numberOfBedrooms"),
            "banheiros": bruto.get("numberOfBathroomsTotal"),
            "vagas": int(vagas.group(1)) if vagas else None,
            "tem_garagem": bool(TEM_GARAGEM.search(url)),
            "area": bruto.get("floorSize", {}).get("value"),
            "andar": bruto.get("floorLevel"),
            "rua": (bruto.get("address") or {}).get("streetAddress"),
            "titulo": nome,
            "url": url,
        })
    return itens, lancamentos, sem_preco

# Cada portal tem seu próprio formato de URL e seu próprio lugar para o preço.
# O dicionário deixa isso explícito: portal sem extrator falha na porta de
# entrada, em vez de descartar 30 anúncios e parecer um problema de parsing.
EXTRATORES = {
    "vivareal": extrair,
}