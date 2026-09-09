# PlayNext

PlayNext is a small video game recommender built around a knowledge graph. It uses an IGDB data snapshot, synthetic users, Neo4j for graph storage, TransE embeddings for link prediction, logical rules for filtering/reranking, and a simple Streamlit UI.

## Setup

Requirements:

- Python 3
- Docker
- Make

Create the local Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Run The Project

Run the commands in this order:

### 1. Prepare Data

```bash
make data
```

This runs:

```bash
python3 scripts/prepare_data.py
```

It reads the raw IGDB snapshot, normalizes the data and writes:

```text
data/nodes.csv
data/relationships.csv
```

`nodes.csv` contains `User`, `Game`, `Genre`, `Platform`, and `Franchise` nodes. `relationships.csv` contains graph edges such as `PLAYED`, `LIKES`, `OWNS_PLATFORM`, `HAS_GENRE`, `AVAILABLE_ON`, `PART_OF_FRANCHISE`, and `RELATED_TO`.

### 2. Load Neo4j

```bash
make neo4j
```

This starts Neo4j with docker compose and loads the csv graph.

Neo4j Browser:

```text
http://localhost:7474
```

Credentials:

```text
username: neo4j
password: playnext
```

### 3. Train Embeddings

```bash
make train
```

This runs:

```bash
.venv/bin/python scripts/train_embeddings.py
```

It converts the KG relationships into typed triples for PyKEEN, hides one known `LIKES` edge per eligible user for testing, trains a TransE link prediction model for:

```text
User --LIKES--> ?
```

and writes:

```text
data/embeddings/metrics.csv
data/embeddings/recommendations.csv
```

`metrics.csv` contains the embedding evaluation results, 
while `recommendations.csv` contains the generated game recommendations.

### 4. Apply Logical Reasoning

```bash
make logic
```

This runs:

```bash
python3 scripts/apply_logic.py
```

It reads the TransE recommendations and applies logical KG rules:

- remove games that are not available on a user's owned platform
- remove games the user already played, liked, or disliked
- add a bonus for preferred genre matches
- add a bonus for games from a liked franchise
- add a bonus for games recursively related to a liked game

It writes:

```text
data/reasoning/logical_recommendations.csv
data/reasoning/logical_game_candidates.csv
```

`logical_recommendations.csv` contains the final top recommendations. `logical_game_candidates.csv` contains all inspected candidates, including rejected ones and the reasons for each decision.

### 5. Run the UI

```bash
make app
```

This runs:

```bash
.venv/bin/python -m streamlit run scripts/app.py
```

The Streamlit UI lets you select a user, view that user's owned platforms and preferred genres, inspect final recommendations, see rejected candidates, and show a small graph for a recommended game.