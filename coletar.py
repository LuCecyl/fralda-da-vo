"""Coleta os preços da Bigfral Moviment G/XG e grava data/precos.json e data/historico.json.

Fontes:
- Buscapé e Zoom (trazem ofertas da Amazon, Magalu, Americanas…)
- São João e Pague Menos (catálogo público das farmácias)

- Mercado Livre e Shopee pelas APIs oficiais (ligam quando os secrets existem)
Panvel bloqueia leitura automática; no site fica como botão de busca.
Só usa a biblioteca padrão do Python. Rode: python3 coletar.py
"""
import gzip, json, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DATA = Path(__file__).parent / "data"
BRT = timezone(timedelta(hours=-3))

BUSCAS = ["bigfral moviment g/xg", "bigfral moviment g/xg 7 unidades",
          "bigfral moviment g/xg 16 unidades", "bigfral moviment g/xg 32 unidades"]
FARMACIAS = {"São João": "www.saojoaofarmacias.com.br", "Pague Menos": "www.paguemenos.com.br"}
COMPARADORES = {"Buscapé": "https://www.buscape.com.br", "Zoom": "https://www.zoom.com.br"}
NOMES_LOJA = {"Magazine Luiza": "Magalu"}


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9",
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8", "replace")


def interpretar(nome):
    """Devolve (unidades, feminina) se for Bigfral Moviment G/XG; senão None."""
    n = nome.lower()
    if "moviment" not in n or not re.search(r"\bg\s*/\s*xg\b|\bgxg\b|\bg\s+xg\b|\bg-xg\b", n):
        return None
    if re.search(r"noturn|derma|pants|p/m.*g/xg|absorvente", n):
        return None
    m = re.search(r"(\d{1,3})\s*(?:un\b|un\.|unid|unidades|tiras|fraldas)", n)
    if not m:
        return None
    unidades = int(m.group(1))
    kit = re.search(r"\b(?:kit|combo|leve)\s*(?:com\s*)?(\d{1,2})\b", n)
    if kit:
        unidades *= int(kit.group(1))
    if unidades < 5 or unidades > 200:
        return None
    return unidades, "feminin" in n


def de_comparador(fonte, base):
    ofertas = []
    for q in BUSCAS:
        try:
            h = baixar(f"{base}/search?q={urllib.parse.quote(q)}")
            dados = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))
            hits = dados["props"]["initialReduxState"]["hits"]["hits"]
        except Exception as e:
            print(f"[{fonte}] falhou '{q}': {e}", file=sys.stderr)
            continue
        for x in hits:
            info = interpretar(x.get("name", ""))
            if not info or not x.get("price") or x.get("type") != "offer":
                continue
            loja = x.get("merchantName") or "?"
            cb = ((x.get("cashback") or {}).get("formula") or {}).get("cashbackRate")
            ofertas.append({
                "loja": NOMES_LOJA.get(loja, loja), "nome": x["name"], "unidades": info[0], "feminina": info[1],
                "preco": round(float(x["price"]), 2), "link": base + x["url"], "via": fonte,
                "cashback": round(cb * 100, 1) if cb else 0,
                "baixou": round(float(x.get("loweringPercentage") or 0)),
                "id": f"{fonte}:{x.get('sourceId') or x.get('objectId')}",
            })
        time.sleep(2)
    return ofertas


def de_farmacia(loja, dominio):
    ofertas = []
    url = f"https://{dominio}/api/catalog_system/pub/products/search?ft={urllib.parse.quote('bigfral moviment')}&_from=0&_to=49"
    try:
        produtos = json.loads(baixar(url))
    except Exception as e:
        print(f"[{loja}] falhou: {e}", file=sys.stderr)
        return ofertas
    for p in produtos:
        info = interpretar(p.get("productName", ""))
        if not info:
            continue
        for item in p.get("items", []):
            for s in item.get("sellers", []):
                o = s.get("commertialOffer", {})
                if o.get("AvailableQuantity", 0) > 0 and o.get("Price"):
                    ofertas.append({
                        "loja": loja, "nome": p["productName"].replace("  ", " "), "unidades": info[0],
                        "feminina": info[1], "preco": round(float(o["Price"]), 2),
                        "precoAntigo": round(float(o.get("ListPrice") or 0), 2), "link": p.get("link"),
                        "cashback": 0, "baixou": 0,
                        "via": loja, "id": f"{loja}:{item.get('itemId')}",
                    })
                    break
    return ofertas


def de_mercado_livre():
    """API oficial do Mercado Livre. Precisa dos secrets ML_CLIENT_ID e ML_CLIENT_SECRET."""
    import os
    cid, sec = os.environ.get("ML_CLIENT_ID", "").strip(), os.environ.get("ML_CLIENT_SECRET", "").strip()
    if not (cid and sec):
        return []
    ofertas = []
    try:
        dados = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}).encode()
        req = urllib.request.Request("https://api.mercadolibre.com/oauth/token", data=dados,
                                     headers={"Accept": "application/json"})
        token = json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]
        url = "https://api.mercadolibre.com/sites/MLB/search?limit=50&q=" + urllib.parse.quote("bigfral moviment g/xg")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())["results"]
    except Exception as e:
        print(f"[Mercado Livre] falhou: {e}", file=sys.stderr)
        return []
    for x in res:
        info = interpretar(x.get("title", ""))
        if not info or not x.get("price"):
            continue
        ofertas.append({
            "loja": "Mercado Livre", "nome": x["title"], "unidades": info[0], "feminina": info[1],
            "preco": round(float(x["price"]), 2), "precoAntigo": round(float(x.get("original_price") or 0), 2),
            "link": x.get("permalink"), "via": "Mercado Livre", "cashback": 0, "baixou": 0,
            "oficial": bool(x.get("official_store_id")), "id": f"ML:{x.get('id')}",
        })
    return ofertas


def de_shopee():
    """API oficial do Shopee Afiliados. Precisa dos secrets SHOPEE_APP_ID e SHOPEE_SECRET."""
    import os, hashlib
    app, sec = os.environ.get("SHOPEE_APP_ID", "").strip(), os.environ.get("SHOPEE_SECRET", "").strip()
    if not (app and sec):
        return []
    consulta = ('{productOfferV2(keyword:"bigfral moviment g/xg", sortType:2, page:1, limit:50)'
                '{nodes{itemId productName priceMin priceMax offerLink productLink shopName}}}')
    corpo = json.dumps({"query": consulta}, separators=(",", ":"))
    ts = str(int(time.time()))
    assinatura = hashlib.sha256((app + ts + corpo + sec).encode()).hexdigest()
    try:
        req = urllib.request.Request("https://open-api.affiliate.shopee.com.br/graphql", data=corpo.encode(), headers={
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={app}, Timestamp={ts}, Signature={assinatura}"})
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        nodes = res["data"]["productOfferV2"]["nodes"]
    except Exception as e:
        print(f"[Shopee] falhou: {e} {locals().get('res', '')}", file=sys.stderr)
        return []
    ofertas = []
    for x in nodes:
        info = interpretar(x.get("productName", ""))
        preco = float(x.get("priceMin") or 0)
        if not info or not preco:
            continue
        ofertas.append({
            "loja": "Shopee", "nome": x["productName"], "unidades": info[0], "feminina": info[1],
            "preco": round(preco, 2), "precoAntigo": 0, "link": x.get("offerLink") or x.get("productLink"),
            "via": "Shopee", "cashback": 0, "baixou": 0, "id": f"Shopee:{x.get('itemId')}",
        })
    return ofertas


# ---------------- Cupons ----------------
LOJAS_CUPOM = {  # loja: (slug Cuponomia, slug Promobit)
    "Amazon": ("amazon", "amazon"), "Mercado Livre": ("mercado-livre", "mercado-livre"),
    "Shopee": ("shopee", "shopee"), "Magalu": ("magazine-luiza", "magazine-luiza"),
    "Americanas": ("americanas", "americanas"), "Panvel": ("panvel", None),
    "São João": ("farmacias-sao-joao", None), "Pague Menos": ("pague-menos", None),
}
SERVE = (r"sa[uú]de|farm[aá]cia|higiene|fralda|geri[aá]tric|incontin|cuidado pessoal|todo o site|todo site|site todo|"
         r"qualquer|todos os produtos|toda a loja|primeira compra|1[ªa] compra|compras acima de|pedidos acima de|compras a partir de")
TALVEZ = (r"selecionad|participantes|\blinha\b|\bmarca\b|bahia|pernambuco|cear[aá]|maranh|para[ií]ba|piau[ií]|alagoas|sergipe|"
          r"rio grande do norte|minas|esp[ií]rito santo|goi[aá]s|amazonas|distrito federal|\bregi")
NAO_SERVE = (r"moda|m[oó]ve(is|l)|colch|sof[aá]|chocolate|lacta|heinz|nivea|tecnologia|eletr[oô]|ve[ií]culo|decora|constru|brinquedo|brinca|jogos|"
             r"dermo|cabelo|infant|suplement|vitamina|beleza|perfum|maquiagem|pet\b|livro|game|celular|smartphone|iphone|notebook|"
             r"\btv|tv\d|televis|jardim|esporte|ferrament|gelol|be better|bebida|vinho|cerveja|supermercado|"
             r"papelaria|toy|natal|viage|passage|hotel|ingresso|curso|assinatura|prime video|kindle|alexa|echo|medicamento|\bmed\b|\bmed\d")


def _txt(s):
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def classificar(titulo, desc, codigo="", amplo=False):
    t = f"{titulo} {desc} {codigo}".lower()
    if re.search(NAO_SERVE, t):
        return None
    if re.search(TALVEZ, t):
        return "talvez"
    if amplo:
        return "serve"
    return "serve" if re.search(SERVE, t) else "talvez"


def detalhes(t):
    t = t.replace(".", "").replace(",", ".")
    m = re.search(r"(?:acima de|a partir de|m[ií]nimo de|minimo de)\s*R\$\s*(\d+(?:\.\d{1,2})?)", t, re.I)
    minimo = float(m.group(1)) if m else 0
    v = re.search(r"R\$\s*(\d+(?:\.\d{1,2})?)\s*(?:OFF|de desconto)", t, re.I)
    pct = re.search(r"(\d{1,2})\s*%\s*(?:OFF|de desconto)", t, re.I)
    teto = re.search(r"(?:limitad[oa] a|m[aá]ximo (?:de )?|at[eé] o limite de)\s*R\$\s*(\d+(?:\.\d{1,2})?)", t, re.I)
    ate = bool(re.search(r"at[eé]\s*(?:R\$\s*)?\d+\s*%?\s*(?:OFF|de desconto)|progressiv|de R\$\s*\d+ a R\$", t, re.I))
    return minimo, (float(v.group(1)) if v else 0), (int(pct.group(1)) if pct else 0), (float(teto.group(1)) if teto else 0), ate


def faixas(t):
    """Descontos progressivos: lista de [mínimo, valor], ex. R$20 OFF acima de R$199,90 | R$30 OFF acima de R$289,90."""
    out = []
    for seg in re.split(r"[|;]|\.\s", t):
        seg = seg.replace(".", "").replace(",", ".")
        v = re.search(r"R\$\s*(\d+(?:\.\d{1,2})?)\s*(?:OFF|de desconto)", seg, re.I) or \
            re.search(r"(?:ganh[ea]|garanta|obtenha|desconto de)\s*R\$\s*(\d+(?:\.\d{1,2})?)", seg, re.I)
        m = re.search(r"(?:acima de|a partir de)\s*:?\s*R\$\s*(\d+(?:\.\d{1,2})?)", seg, re.I)
        if v and not m:
            nums = re.findall(r"R\$\s*(\d+(?:\.\d{1,2})?)", seg)
            if len(nums) >= 2 and nums[0] != v.group(1):
                out.append([float(nums[0]), float(v.group(1))])
        elif v and m:
            out.append([float(m.group(1)), float(v.group(1))])
    return sorted(out) if len(out) >= 2 else []


def cupons_cuponomia(slug):
    h = baixar(f"https://www.cuponomia.com.br/desconto/{slug}")
    m = re.search(r'<ul class="coupon-list valid-coupons.*?</ul>', h, re.S)
    out = []
    for it in re.findall(r'<li class="item[^"]*"(.*?)</li>', m.group(0) if m else "", re.S):
        g = lambda p: (lambda x: _txt(x.group(1)) if x else "")(re.search(p, it, re.S))
        if g(r'data-type="(\w+)"') != "code":
            continue
        out.append({"titulo": g(r"<h3[^>]*>(.*?)</h3>"), "desc": g(r'class="item-desc">(.*?)</div>'),
                    "codigo": g(r'js-itemCode">(.*?)</span>'), "amplo": g(r'data-is-store-wide="(\w+)"') == "true",
                    "validade": "", "fonte": "Cuponomia", "link": f"https://www.cuponomia.com.br/desconto/{slug}"})
    return out


def cupons_promobit(slug):
    h = baixar(f"https://www.promobit.com.br/cupons/loja/{slug}/")
    pp = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))["props"]["pageProps"]
    agora = datetime.now(BRT)
    out = []
    for x in (pp.get("serverCoupons") or {}).get("coupons") or []:
        ate = x.get("couponUntil")
        if x.get("couponStatusName") != "APPROVED":
            continue
        if ate and datetime.strptime(ate[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=BRT) < agora:
            continue
        out.append({"titulo": _txt(x.get("couponTitle")), "desc": _txt(x.get("couponInstructions"))[:200],
                    "codigo": _txt(x.get("couponCode")), "amplo": False, "validade": (ate or "")[:10],
                    "fonte": "Promobit", "link": f"https://www.promobit.com.br/cupons/loja/{slug}/"})
    return out


def coletar_cupons():
    todos = {}
    for loja, (cn, pb) in LOJAS_CUPOM.items():
        brutos = []
        for f, slug in ((cupons_cuponomia, cn), (cupons_promobit, pb)):
            if not slug:
                continue
            try:
                brutos += f(slug)
            except Exception as e:
                print(f"[cupons {loja} {f.__name__}] falhou: {e}", file=sys.stderr)
            time.sleep(1)
        lista, vistos = [], set()
        for c in brutos:
            tipo = classificar(c["titulo"], c["desc"], c["codigo"], c["amplo"])
            cod = c["codigo"]
            if not tipo or not cod:
                continue
            chave = cod.upper() if not re.search(r"link|ative|resgat", cod, re.I) else c["titulo"]
            if chave in vistos:
                continue
            vistos.add(chave)
            minimo, valor, pct, teto, ate = detalhes(f"{c['titulo']} {c['desc']}")
            fx = faixas(c["desc"])
            if fx:
                minimo, valor, ate = fx[0][0], max(v for _, v in fx), False
            c.update(tipo=tipo, minimo=minimo, valor=valor, pct=pct, teto=teto, ate=ate, faixas=fx,
                     primeira=bool(re.search(r"primeira compra|1[ªa] compra|novos clientes", f"{c['titulo']} {c['desc']} {cod}", re.I)),
                     semCodigo=bool(re.search(r"link|ative|resgat", cod, re.I)))
            c.pop("amplo", None)
            lista.append(c)
        lista.sort(key=lambda c: (c["tipo"] != "serve", c["primeira"], -(c["valor"] or c["pct"])))
        todos[loja] = lista[:6]
    return todos


def main():
    ofertas = []
    for fonte, base in COMPARADORES.items():
        ofertas += de_comparador(fonte, base)
    for loja, dominio in FARMACIAS.items():
        ofertas += de_farmacia(loja, dominio)
    ofertas += de_mercado_livre()
    ofertas += de_shopee()

    # Remove repetidos (mesma loja, mesmo pacote, mesmo preço) e calcula preço por fralda
    unicas = {}
    for o in ofertas:
        chave = (o["loja"], o["unidades"], o["feminina"], o["preco"])
        unicas.setdefault(chave, o)
    ofertas = sorted(unicas.values(), key=lambda o: o["preco"] / o["unidades"])
    for o in ofertas:
        o["porFralda"] = round(o["preco"] / o["unidades"], 2)

    agora = datetime.now(BRT)
    fontes_ok = sorted({o["via"] for o in ofertas})
    if not ofertas:
        print("Nenhuma oferta encontrada; mantendo os dados anteriores.", file=sys.stderr)
        sys.exit(1)

    try:
        cupons = coletar_cupons()
    except Exception as e:
        print(f"[cupons] falhou: {e}", file=sys.stderr)
        cupons = {}
    DATA.mkdir(exist_ok=True)
    (DATA / "precos.json").write_text(json.dumps(
        {"atualizado": agora.isoformat(timespec="minutes"), "fontes": fontes_ok, "ofertas": ofertas, "cupons": cupons},
        ensure_ascii=False, indent=1), encoding="utf-8")

    # Histórico: o menor preço por fralda de cada dia (por loja), para ver a tendência
    hist_path = DATA / "historico.json"
    hist = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    hoje = agora.date().isoformat()
    melhor_por_loja = {}
    for o in ofertas:
        if o["loja"] not in melhor_por_loja:
            melhor_por_loja[o["loja"]] = o["porFralda"]
    dia = next((d for d in hist if d["data"] == hoje), None)
    if dia is None:
        dia = {"data": hoje, "lojas": {}}
        hist.append(dia)
    for loja, v in melhor_por_loja.items():
        dia["lojas"][loja] = min(v, dia["lojas"].get(loja, v))
    dia["melhor"] = min(dia["lojas"].values())
    hist = sorted(hist, key=lambda d: d["data"])[-730:]
    hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(ofertas)} ofertas de {', '.join(fontes_ok)}. Melhor: {ofertas[0]['loja']} "
          f"{ofertas[0]['unidades']}un R$ {ofertas[0]['preco']} (R$ {ofertas[0]['porFralda']}/fralda)")
    verificar_alerta(ofertas, hist, hoje)


# ---------------- Alerta por e-mail ----------------

def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def verificar_alerta(ofertas, hist, hoje):
    cfg = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    alvo = float(cfg["precoAlvoPorFralda"])
    dias = int(cfg.get("diasParaMenorPreco", 14))
    lista = [o for o in ofertas if cfg.get("incluirFeminina", True) or not o["feminina"]]
    if not lista:
        return
    melhor = lista[0]
    anteriores = [d["melhor"] for d in hist if d["data"] < hoje][-dias:]
    motivos = []
    if melhor["porFralda"] <= alvo:
        motivos.append(f"está abaixo do seu preço-alvo de {brl(alvo)} por fralda")
    if len(anteriores) >= 5 and melhor["porFralda"] < min(anteriores) * 0.98:
        motivos.append(f"é o menor preço dos últimos {len(anteriores)} dias (antes: {brl(min(anteriores))})")
    if not motivos:
        print("Sem alerta hoje.")
        return

    # Não repetir o mesmo alerta: só manda de novo se baixou mais ou se já passou uma semana
    est_path = DATA / "alerta.json"
    ult = json.loads(est_path.read_text(encoding="utf-8")) if est_path.exists() else {}
    if ult and melhor["porFralda"] >= ult.get("porFralda", 0) and \
            (datetime.fromisoformat(hoje) - datetime.fromisoformat(ult["data"])).days < 7:
        print("Alerta já enviado recentemente para este preço.")
        return

    import os, smtplib
    from email.mime.text import MIMEText
    usuario, senha, para = (os.environ.get(k, "").strip() for k in ("EMAIL_USUARIO", "EMAIL_SENHA_APP", "EMAIL_PARA"))
    if not (usuario and senha and para):
        print("Alerta disparou, mas o e-mail não está configurado (secrets EMAIL_*).", file=sys.stderr)
        return

    linhas = "".join(
        f"<tr><td>{i+1}º</td><td><b>{o['loja']}</b><br><small>Pacote de {o['unidades']}"
        f"{' · feminina' if o['feminina'] else ''}</small></td><td align=right><b>{brl(o['porFralda'])}</b>/fralda"
        f"<br><small>{brl(o['preco'])}</small></td><td><a href=\"{o['link']}\">abrir</a></td></tr>"
        for i, o in enumerate(lista[:5]))
    site = cfg.get("site", "")
    corpo = f"""<div style="font-family:Arial,sans-serif;font-size:15px;color:#1f2a2e">
<h2 style="color:#1f7a4d;margin:0 0 8px">Fralda da vó em promoção: {brl(melhor['porFralda'])} por fralda</h2>
<p><b>{melhor['loja']}</b> · pacote de {melhor['unidades']} por <b>{brl(melhor['preco'])}</b>. Esse preço {' e '.join(motivos)}.</p>
<p><a href="{melhor['link']}" style="background:#2f6f5e;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:bold">Abrir na loja</a></p>
<table cellpadding=6 style="border-collapse:collapse;margin-top:12px">{linhas}</table>
<p style="color:#5f6b70;font-size:13px">Confira o preço final e o frete na loja antes de pagar.{f' Ver tudo: <a href="{site}">{site}</a>' if site else ''}</p></div>"""
    msg = MIMEText(corpo, "html", "utf-8")
    msg["Subject"] = f"Fralda da vó: {brl(melhor['porFralda'])} por fralda na {melhor['loja']}"
    msg["From"] = usuario
    msg["To"] = para
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(usuario, senha)
        smtp.sendmail(usuario, [e.strip() for e in para.split(",") if e.strip()], msg.as_string())
    est_path.write_text(json.dumps({"data": hoje, "porFralda": melhor["porFralda"]}), encoding="utf-8")
    print("Alerta enviado por e-mail.")


if __name__ == "__main__":
    main()
