.PHONY: data train logic app neo4j

data:
	python3 scripts/prepare_data.py

neo4j:
	docker compose up -d
	docker compose exec neo4j cypher-shell -u neo4j -p playnext -f /cypher/load_csv.cypher

train:
	.venv/bin/python scripts/train_embeddings.py

logic:
	python3 scripts/apply_logic.py

app:
	.venv/bin/python -m streamlit run scripts/app.py
