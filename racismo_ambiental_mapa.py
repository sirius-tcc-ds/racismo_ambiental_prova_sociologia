import requests
import pandas as pd
import folium

def buscar_json(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()

print("1. Baixando dados demográficos (Cor/Raça) do Censo 2022...")
url_raca = "https://servicodados.ibge.gov.br/api/v3/agregados/9605/periodos/2022/variaveis/1000093?localidades=N6[N3[35]]&classificacao=86[2777,2779,2780]"
resp_raca = buscar_json(url_raca)

dados_raca = {}
for resultado in resp_raca[0].get("resultados", []):
    for serie in resultado.get("series", []):
        localidade = serie.get("localidade", {})
        cod_mun = str(localidade.get("id"))
        nome_mun = localidade.get("nome", "Desconhecido")
        valor = serie.get("serie", {}).get("2022")

        if cod_mun not in dados_raca:
            dados_raca[cod_mun] = {
                "cod_ibge": cod_mun,
                "municipio": nome_mun,
                "pop_negra_indigena_pct": 0.0
            }

        if valor not in ["-", "...", None]:
            dados_raca[cod_mun]["pop_negra_indigena_pct"] += float(valor)

df_raca = pd.DataFrame(list(dados_raca.values()))

print("2. Descobrindo códigos da Tabela 6805 e baixando dados de saneamento...")
# Consulta os metadados da tabela 6805 para pegar o ID exato de "Rede geral..."
meta_6805 = buscar_json("https://servicodados.ibge.gov.br/api/v3/agregados/6805/metadados")
id_classificacao = None
id_categoria_rede = None

for clf in meta_6805.get("classificacoes", []):
    for cat in clf.get("categorias", []):
        if "Rede geral" in cat.get("nome", "") and "ligada à rede" in cat.get("nome", ""):
            id_classificacao = clf["id"]
            id_categoria_rede = cat["id"]
            break

# Usa a variável 1000381 (Percentual do total geral) com os IDs descobertos dinamicamente
url_esgoto = f"https://servicodados.ibge.gov.br/api/v3/agregados/6805/periodos/2022/variaveis/1000381?localidades=N6[N3[35]]&classificacao={id_classificacao}[{id_categoria_rede}]"
resp_esgoto = buscar_json(url_esgoto)

dados_esgoto = []
for resultado in resp_esgoto[0].get("resultados", []):
    for serie in resultado.get("series", []):
        localidade = serie.get("localidade", {})
        cod_mun = str(localidade.get("id"))
        valor_com_rede = serie.get("serie", {}).get("2022")

        if valor_com_rede not in ["-", "...", None]:
            sem_rede = 100.0 - float(valor_com_rede)
        else:
            sem_rede = None

        dados_esgoto.append({
            "cod_ibge": cod_mun,
            "sem_rede_esgoto_pct": round(sem_rede, 2) if sem_rede is not None else 0.0
        })

df_esgoto = pd.DataFrame(dados_esgoto)

# Cruzando as duas tabelas pelo Código IBGE
df_final = pd.merge(df_raca, df_esgoto, on="cod_ibge")
df_final["pop_negra_indigena_pct"] = df_final["pop_negra_indigena_pct"].round(2)

# Print rápido no terminal para você conferir os primeiros municípios antes de abrir o mapa
print("\nAmostra dos dados cruzados:")
print(df_final.head(10))

print("\n3. Baixando malha geográfica (polígonos GeoJSON) de SP...")
url_malha = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=municipio"
geojson_sp = buscar_json(url_malha)

dados_dict = df_final.set_index("cod_ibge").to_dict("index")
for feature in geojson_sp.get("features", []):
    cod = str(feature["properties"].get("codarea"))
    info = dados_dict.get(cod, {})
    feature["properties"]["municipio"] = info.get("municipio", "Desconhecido")
    feature["properties"]["raca_pct"] = f"{info.get('pop_negra_indigena_pct', 0)}%"
    feature["properties"]["esgoto_pct"] = f"{info.get('sem_rede_esgoto_pct', 0)}%"

print("4. Renderizando o mapa interativo...")
mapa = folium.Map(location=[-22.5, -48.5], zoom_start=7, tiles="CartoDB positron")

choropleth = folium.Choropleth(
    geo_data=geojson_sp,
    name="Déficit de Saneamento (%)",
    data=df_final,
    columns=["cod_ibge", "sem_rede_esgoto_pct"],
    key_on="feature.properties.codarea",
    fill_color="YlOrRd",
    fill_opacity=0.75,
    line_opacity=0.2,
    legend_name="Domicílios sem Rede Geral de Esgoto (%) - Censo 2022"
).add_to(mapa)

folium.GeoJsonTooltip(
    fields=["municipio", "raca_pct", "esgoto_pct"],
    aliases=["Município:", "Pop. Negra e Indígena:", "Sem Rede de Esgoto:"],
    localize=True,
    sticky=False,
    labels=True,
    style="""
        background-color: #F0EFEF;
        border: 1px solid black;
        border-radius: 3px;
        box-shadow: 3px;
    """
).add_to(choropleth.geojson)

arquivo_saida = "mapa_racismo_ambiental_ibge.html"
mapa.save(arquivo_saida)
print(f"Concluído! Abra '{arquivo_saida}' no seu navegador.")