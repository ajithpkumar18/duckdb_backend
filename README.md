# 🧠 AI-Powered Product Insights API (Open Food Facts Canada)

An AI-powered backend service that transforms raw Open Food Facts data into clear, actionable insights using **LLMs (Gemini)**, **DuckDB**, and **FastAPI**.

---

## 🚀 Features

- 🔍 Product Search API
- 📊 Structured Product Summary
- 🤖 AI-Powered Insights
- 🌍 Bilingual Support (EN/FR)
- ⚡ DuckDB OLAP Queries
- 🧠 LLM Caching

---

## 🏗️ Architecture

````
Client
  │
  ▼
FastAPI
  │
  ├── Check Cache ──► If HIT → Return
  │
  ├── Query DuckDB → Get product data
  │
  └── Call Gemini LLM → Generate insights
           │
           ▼
        Store in Cache
           │
           ▼
         Return
---

## 📦 Installation

```bash
git clone https://github.com/your-username/off-ai-insights.git
cd off-ai-insights
pip install -r requirements.txt
````

Create `.env`:

```
GEMINI_API_KEY=your_api_key_here
```

---

## ▶️ Run

```bash
uvicorn main:app --reload
or
uvicorn server:app --reload --reload-dir .
```

---

## 📡 API

### /search?q=

Search products

### /summary?q=&lang=en|fr

Structured product data

### /insights?q=&lang=en|fr

AI-generated insights

---

## 🧠 How It Works

1. Query product data from DuckDB
2. Clean and structure nutrients
3. Send data to Gemini LLM
4. Generate JSON insights
5. Cache results
6. Return cache results if user query's the same product

---

## 🌍 Bilingual Support

Supports English and French outputs for Canadian users.

---

## 🔮 Future Work

- Better recommendations
- Vector search using cosine similariy
- Product Page Integration

---
