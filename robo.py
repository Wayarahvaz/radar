from datetime import datetime, timedelta, timezone
import json
import os
import re
import time

import requests

# ===== 0. CONFIGURAÇÕES =====
# Aviso curtinho no WhatsApp com o link da página (False = desliga)
AVISO_WHATSAPP = True
LINK_PAGINA = "https://wayarahvaz.github.io/Pesquisador-de-vagas/"

apikey = os.environ.get("CALLMEBOT_APIKEY", "")
telefone = os.environ.get("CALLMEBOT_PHONE", "")
ARQUIVO = "vistas.json"        # caderno: o que o robô já viu
ARQUIVO_PAGINA = "vagas.json"  # o que a página mostra
FUSO_BR = timezone(timedelta(hours=-3))

# ===== 1. LISTAS (seus critérios) =====
cargos = [
    "Market Intelligence", "Inteligência de Mercado", "Inteligencia de Mercado",
    "Data Analyst", "Analista de BI", "Analista de Dados",
    "Business Intelligence", "Power BI", "Market Research",
    "Competitive Intelligence", "Business Analyst", "BI Analyst",
    "Pricing", "Research Analyst", "Revenue Operations",
    "Sales Operations", "Geopolitical Intelligence", "Trading",
    "Political Intelligence", "Corporate Intelligence",
    "Analista de Geopolítica", "Analista de Mercado",
    "Inteligência de Negócios", "Inteligencia de Negocios",
    "Análise de Mercado", "Business Operations",
]
cargos_min = [c.lower() for c in cargos]

proibidas = ["assistente", "assistant", "jr", "júnior", "junior", "bolsista",
             "banco de talentos", "internship", "estágio", "estagiário",
             "temporário", "temporario"]

regiao_sorocaba = ["sorocaba", "votorantim", "itu", "salto", "porto feliz",
                   "boituva", "araçoiaba da serra", "iperó", "mairinque",
                   "alumínio", "são roque", "piedade", "tatuí"]

remoto_aceito = ["", "worldwide", "anywhere", "global", "brazil", "brasil",
                 "são paulo", "sao paulo", "latam", "latin america",
                 "south america", "americas"]

empresas_prioritarias = [
    "logcomex", "ecomex", "logiez", "kuehne", "dhl", "dsv",
    "asia shipping", "craft", "maersk", "msc", "hapag", "cma cgm",
    "cargill", "bunge", "louis dreyfus", "vale", "glencore",
    "trafigura", "anglo american", "rumo", "flexport", "kpler", "loadsmart",
]

palavras_setor = [
    "comex", "comércio exterior", "logística internacional", "logistics",
    "freight", "shipping", "trading", "commodit", "mineração", "mining",
    "energia", "energy", "óleo e gás", "oil", "supply chain", "power bi",
    "sql", "pricing", "precificação", "geopolít", "geopolit",
]

empresas_greenhouse = ["flexport", "project44", "spire", "sayari", "planetlabs"]
empresas_lever = ["kpler", "loadsmart"]

dias_por_fonte = {"Greenhouse": 90, "Lever": 90}   # as outras usam 7

# ===== 2. PADRONIZADOR =====
def padrao(id, titulo, empresa, local, modelo, data, link, descricao, fonte):
    return {
        "id": f"{fonte}-{id}",
        "titulo": titulo or "",
        "empresa": empresa or "",
        "local": local or "",
        "modelo": modelo or "",
        "data": data,
        "link": link or "",
        "descricao": descricao or "",
        "fonte": fonte,
    }

def data_de_texto(txt):
    if not txt:
        return None
    try:
        d = datetime.fromisoformat(str(txt).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def data_de_numero(n, milissegundos=False):
    if not n:
        return None
    return datetime.fromtimestamp(n / 1000 if milissegundos else n, timezone.utc)

def adivinhar_modelo(texto):
    t = texto.lower()
    if "remote" in t or "remoto" in t or "home office" in t:
        return "remote"
    if "hybrid" in t or "híbrido" in t or "hibrido" in t:
        return "hybrid"
    return ""

# ===== 3. FONTES =====
def buscar_gupy():
    vagas = []
    for cargo in cargos:
        try:
            r = requests.get("https://portal.gupy.io/api/job-search/jobs",
                             params={"jobName": cargo, "limit": 50, "offset": 0}, timeout=30)
            r.raise_for_status()
            for v in r.json()["data"]:
                if v.get("type") == "vacancy_type_internship":
                    continue
                vagas.append(padrao(v["id"], v.get("name"), v.get("careerPageName"),
                                    v.get("city"), v.get("workplaceType"),
                                    data_de_texto(v.get("publishedDate")),
                                    v.get("jobUrl"), v.get("description"), "Gupy"))
        except Exception as e:
            print("  Gupy erro em", cargo, "→", e)
        time.sleep(0.5)
    return vagas

def buscar_greenhouse():
    vagas = []
    for empresa in empresas_greenhouse:
        try:
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{empresa}/jobs",
                             timeout=30)
            r.raise_for_status()
            for v in r.json().get("jobs", []):
                local = (v.get("location") or {}).get("name", "")
                vagas.append(padrao(v["id"], v.get("title"),
                                    v.get("company_name") or empresa, local,
                                    adivinhar_modelo(local + " " + v.get("title", "")),
                                    data_de_texto(v.get("first_published") or v.get("updated_at")),
                                    v.get("absolute_url"), "", "Greenhouse"))
        except Exception as e:
            print("  Greenhouse erro em", empresa, "→", e)
    return vagas

def buscar_lever():
    vagas = []
    for empresa in empresas_lever:
        try:
            r = requests.get(f"https://api.lever.co/v0/postings/{empresa}",
                             params={"mode": "json"}, timeout=30)
            r.raise_for_status()
            for v in r.json():
                cat = v.get("categories") or {}
                vagas.append(padrao(v["id"], v.get("text"), empresa,
                                    cat.get("location", ""), v.get("workplaceType", ""),
                                    data_de_numero(v.get("createdAt"), milissegundos=True),
                                    v.get("hostedUrl"), v.get("descriptionPlain"), "Lever"))
        except Exception as e:
            print("  Lever erro em", empresa, "→", e)
    return vagas

def buscar_himalayas(paginas=5):
    vagas = []
    for p in range(paginas):
        try:
            r = requests.get("https://himalayas.app/jobs/api",
                             params={"limit": 20, "offset": p * 20}, timeout=30)
            r.raise_for_status()
            for v in r.json().get("jobs", []):
                local = ", ".join(v.get("locationRestrictions") or [])
                vagas.append(padrao(v.get("guid"), v.get("title"), v.get("companyName"),
                                    local, "remote", data_de_numero(v.get("pubDate")),
                                    v.get("applicationLink"), v.get("description"), "Himalayas"))
        except Exception as e:
            print("  Himalayas erro na página", p, "→", e)
            break
        time.sleep(0.5)
    return vagas

def buscar_remoteok():
    vagas = []
    try:
        r = requests.get("https://remoteok.com/api",
                         headers={"User-Agent": "robo-vagas pessoal"}, timeout=30)
        r.raise_for_status()
        for v in r.json()[1:]:
            vagas.append(padrao(v.get("id"), v.get("position"), v.get("company"),
                                v.get("location"), "remote", data_de_texto(v.get("date")),
                                v.get("url"), v.get("description"), "RemoteOK"))
    except Exception as e:
        print("  RemoteOK erro →", e)
    return vagas

def buscar_remotive():
    vagas = []
    for termo in ["data analyst", "business intelligence", "market research", "pricing"]:
        try:
            r = requests.get("https://remotive.com/api/remote-jobs",
                             params={"search": termo, "limit": 50}, timeout=30)
            r.raise_for_status()
            for v in r.json().get("jobs", []):
                vagas.append(padrao(v.get("id"), v.get("title"), v.get("company_name"),
                                    v.get("candidate_required_location"), "remote",
                                    data_de_texto(v.get("publication_date")),
                                    v.get("url"), v.get("description"), "Remotive"))
        except Exception as e:
            print("  Remotive erro em", termo, "→", e)
            break
        time.sleep(0.5)
    return vagas

# ===== 4. FILTROS E NOTA =====
def titulo_ok(titulo):
    t = titulo.lower()
    for termo in cargos_min:
        if termo in t:
            return True
    return False

def titulo_proibido(titulo):
    t = titulo.lower()
    for palavra in proibidas:
        if palavra in t:
            return True
    return False

def local_ok(vaga):
    modelo = vaga["modelo"]
    local = vaga["local"].lower().strip()
    cidade = local.split(",")[0].strip()
    if modelo == "remote":
        if vaga["fonte"] == "Gupy":
            return True
        for lugar in remoto_aceito:
            if lugar == "" and local == "":
                return True
            if lugar and lugar in local:
                return True
        return False
    if cidade in regiao_sorocaba:
        return True
    if cidade == "são paulo" and modelo == "hybrid":
        return True
    return False

def recente(vaga):
    dias = dias_por_fonte.get(vaga["fonte"], 7)
    if vaga["data"] is None:
        return True
    return vaga["data"] >= datetime.now(timezone.utc) - timedelta(days=dias)

def nota(vaga):
    pontos = 0
    empresa = vaga["empresa"].lower()
    descricao = vaga["descricao"].lower()
    titulo = vaga["titulo"].lower()
    for e in empresas_prioritarias:
        if e in empresa:
            pontos += 10
            break
    for p in palavras_setor:
        if p in descricao:
            pontos += 1
    for s in ["sênior", "senior", "sr", "pleno", "especialista", "lead"]:
        if s in titulo:
            pontos += 2
            break
    return pontos

# ===== 5. MEMÓRIA =====
def carregar_vistas():
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_vistas(vistas):
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(vistas, f, indent=1)

# ===== 6. WHATSAPP =====
def enviar_whatsapp(texto):
    r = requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": telefone, "text": texto, "apikey": apikey},
        timeout=60,
    )
    print("Envio:", r.status_code)
    time.sleep(3)

# ===== 7. RODAR TUDO =====
fontes = [buscar_gupy, buscar_greenhouse, buscar_lever,
          buscar_himalayas, buscar_remoteok, buscar_remotive]

todas = {}
for buscar in fontes:
    resultado = buscar()
    print(f"{buscar.__name__.replace('buscar_', ''):>10}: {len(resultado)} vagas")
    for v in resultado:
        todas[v["id"]] = v
print(f"\n{len(todas)} vagas no total\n")

aprovadas = []
for vaga in todas.values():
    if not titulo_ok(vaga["titulo"]):
        continue
    if titulo_proibido(vaga["titulo"]):
        continue
    if not local_ok(vaga):
        continue
    if not recente(vaga):
        continue
    vaga["nota"] = nota(vaga)
    aprovadas.append(vaga)
aprovadas.sort(key=lambda v: v["nota"], reverse=True)

# ===== 8. MEMÓRIA: anota quando cada vaga apareceu pela 1ª vez =====
hoje_iso = datetime.now(FUSO_BR).strftime("%Y-%m-%d")
vistas = carregar_vistas()
novas = [v for v in aprovadas if v["id"] not in vistas]
for v in novas:
    vistas[v["id"]] = hoje_iso
salvar_vistas(vistas)
print(f"{len(aprovadas)} aprovadas, {len(novas)} novas hoje")

# ===== 9. SALVAR O ARQUIVO DA PÁGINA =====
def limpar_html(txt):
    sem_tags = re.sub(r"<[^>]+>", " ", txt or "")      # tira <p>, <b>...
    texto = re.sub(r"\s+", " ", sem_tags).strip()       # junta espaços
    return re.sub(r" ([,.;:!?])", r"\1", texto)         # tira espaço antes de vírgula

pagina = {
    "atualizado_em": datetime.now(FUSO_BR).strftime("%d/%m/%Y às %H:%M"),
    "hoje": hoje_iso,
    "vagas": [
        {
            "id": v["id"],
            "titulo": v["titulo"],
            "empresa": v["empresa"],
            "local": v["local"],
            "modelo": v["modelo"],
            "publicada": v["data"].strftime("%Y-%m-%d") if v["data"] else "",
            "visto_em": vistas.get(v["id"], hoje_iso),
            "link": v["link"].replace("?jobBoardSource=gupy_portal", ""),
            "fonte": v["fonte"],
            "nota": v["nota"],
            "resumo": limpar_html(v["descricao"])[:400],
        }
        for v in aprovadas
    ],
}
with open(ARQUIVO_PAGINA, "w", encoding="utf-8") as f:
    json.dump(pagina, f, ensure_ascii=False, indent=1)
print("Página atualizada:", len(pagina["vagas"]), "vagas")

# ===== 10. AVISO NO WHATSAPP (opcional) =====
if AVISO_WHATSAPP and apikey and telefone:
    hoje = datetime.now(FUSO_BR).strftime("%d/%m")
    enviar_whatsapp(f"🎯 *Robô de Vagas — {hoje}*\n"
                    f"{len(novas)} vagas novas · {len(aprovadas)} no radar\n"
                    f"{LINK_PAGINA}")
