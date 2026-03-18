from fastapi import FastAPI
import duckdb
from google import genai
from google.genai import types
from dotenv import load_dotenv
import json
import os
import re

app = FastAPI()
con = duckdb.connect("off_canada.db")
load_dotenv()
print("GEMINI KEY:", os.getenv("GEMINI_API_KEY"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@app.get("/search")
def search(q: str):
    query = """
        SELECT product_name[1].text AS product_name, nutriscore_grade 
        FROM products 
        WHERE array_to_string(list_transform(product_name, x -> x.text), ',') ILIKE ?
        LIMIT 10
    """
    results = con.execute(query, [f'%{q}%']).fetchall()
    return {"results": [{"product_name": row[0], "nutriscore_grade": row[1]} for row in results]}


@app.get("/summary")
def summary(q: str, lang: str = "en"):
    query = """
        SELECT 
            (LIST_FILTER(product_name, x -> x.lang = 'en'))[1].text as name_en,
            (LIST_FILTER(product_name, x -> x.lang = 'fr'))[1].text as name_fr,
            brands,
            nutriscore_grade,
            nova_group,
            ecoscore_grade,
            LIST(struct_extract(n, 'name') || ': ' || 
            CAST(struct_extract(n, '100g') AS VARCHAR)) as nutrients
        FROM products, UNNEST(nutriments) AS t(n)
        WHERE code = ?
        GROUP BY name_en, name_fr, brands, nutriscore_grade, nova_group, ecoscore_grade
    """
    
    results = con.execute(query, [q]).fetchall()

    if not results:
        return {"error": "Product not found"}

    row = results[0]

    name_en = row[0] if row[0] else None
    name_fr = row[1] if row[1] else None

    available_languages = []
    if name_en: available_languages.append("en")
    if name_fr: available_languages.append("fr")

    primary_name = name_en or name_fr
    # pick primary name based on requested lang
    if lang == "fr":
        display_name = name_fr or name_en  # fallback to en if fr missing
    else:
        display_name = name_en or name_fr  # fallback to fr if en missing
    
    nutrients_dict = {}
    for nutrient in row[6]:
        name, value = nutrient.split(": ")
        # skip internal/calculated fields
        if name in ['nutrition-score-fr', 'fruits-vegetables-nuts-estimate-from-ingredients', 
                    'fruits-vegetables-legumes-estimate-from-ingredients', 'nova-group']:
            continue
        # clean up key names
        clean_name = name.replace("-", "_")
        nutrients_dict[clean_name] = round(float(value), 2)

    return {
        "code": q,
        "lang": lang,
        "primary_name": primary_name,
        "display_name": display_name,
        "product_name": {
            "en": name_en,
            "fr": name_fr,
        },
        "available_languages": available_languages,
        "bilingual": len(available_languages) == 2,
        "brands": row[2],
        "nutriscore_grade": row[3],
        "nova_group": row[4],
        "ecoscore_grade": row[5],
        "nutrients": nutrients_dict
    }

@app.get("/insights")
async def insights(q: str, lang: str = "en"):
    # Step 1 - check cache
    cache = con.execute(
        "SELECT llm_summary_en, llm_summary_fr FROM llm_cache WHERE code = ?", [q]
    ).fetchone() if table_exists("llm_cache") else None

    # if cache:
    #     return {"code": q, "summary": cache[0] if lang == "en" else cache[1]}

    # Step 2 - fetch product data
    product_query = """
        SELECT 
            (LIST_FILTER(product_name, x -> x.lang = 'en'))[1].text as name_en,
            (LIST_FILTER(product_name, x -> x.lang = 'fr'))[1].text as name_fr,
            brands,
            nutriscore_grade,
            nova_group,
            ecoscore_grade,
            LIST(struct_extract(n, 'name') || ': ' || 
            CAST(struct_extract(n, '100g') AS VARCHAR)) as nutrients
        FROM products, UNNEST(nutriments) AS t(n)
        WHERE code = ?
        GROUP BY name_en, name_fr, brands, nutriscore_grade, nova_group, ecoscore_grade
    """
    results = con.execute(product_query, [q]).fetchall()

    if not results:
        return {"error": "Product not found"}

    row = results[0]
    product_data = {
        "name": row[0] or row[1],
        "brands": row[2],
        "nutriscore_grade": row[3],
        "nova_group": row[4],
        "ecoscore_grade": row[5],
        "nutrients": row[6]
    }

    # Step 3 - call LLM
    summary_en = await call_llm(product_data, "en")
    summary_fr = await call_llm(product_data, "fr")

    # Step 4 - cache the result
    con.execute("""
        CREATE TABLE IF NOT EXISTS llm_cache (
            code VARCHAR PRIMARY KEY,
            llm_summary_en VARCHAR,
            llm_summary_fr VARCHAR
        )
    """)
    con.execute(
        "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?)",
        [q, summary_en, summary_fr]
    )

    return {"code": q, "summary": summary_en if lang == "en" else summary_fr}


async def call_llm(product_data: dict, lang: str) -> str:
    lang_instruction = "All output fields MUST be written in english." if lang == "en" else "Tous les champs de sortie DOIVENT être écrits en français."
    
    prompt = f"""
IMPORTANT RULES:
- Only use the data provided below.
- Do NOT assume or invent missing information.
- If information is missing, say "Not available".
- Return ONLY valid JSON.
- Do NOT include markdown, code blocks, or explanations.
- Make recommendations specific and actionable when possible.
- Avoid strong claims if data is limited.
- Do NOT wrap the response in ```.

{lang_instruction}

PRODUCT DATA:
Name: {product_data['name']}
Brand: {product_data['brands']}
NutriScore: {product_data['nutriscore_grade']} (a=best, e=worst)
NOVA Group: {product_data['nova_group']} (1=unprocessed, 4=ultra-processed)
EcoScore: {product_data['ecoscore_grade']}
Nutrients per 100g: {', '.join(product_data['nutrients'])}

OUTPUT FORMAT (STRICT JSON):
{{
  "summary": "...",
  "health_insight": "...",
  "recommendation": "..."
}}
"""
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        config= types.GenerateContentConfig(
            system_instruction="You are a nutrition expert analyzing a Canadian food product."),
        contents=prompt
    )
    response_text = re.sub(r"```json|```", "", response.text).strip()
    try:
        parsed=json.loads(response_text)
    except:
        parsed={"summary":response_text}

    required_keys = ["summary", "health_insight", "recommendation"]

    if not all(k in parsed for k in required_keys):
        return {"summary": "Incomplete AI response"}    
    return parsed

def table_exists(table_name: str) -> bool:
    result = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name]
    ).fetchone()
    return result[0] > 0
