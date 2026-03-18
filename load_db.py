import duckdb

con = duckdb.connect("off_canada.db")
con.execute("PRAGMA enable_progress_bar")
con.execute("PRAGMA temp_directory='temp'")
con.execute("""
CREATE TABLE IF NOT EXISTS products AS SELECT * FROM read_parquet('food.parquet') WHERE array_to_string(countries_tags, ',') LIKE '%canada%' LIMIT 10000
""")

# check how many products
count=con.execute(""" SELECT COUNT(*) FROM products""").fetchone()

print("Products Loaded: ", count[0])

con.close()