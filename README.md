# PlayNext

PlayNext is a knowdledge graph-based video game recommender that uses an IGDB metadata snapshot, synthetic users, Neo4j for graph storage, TransE embeddings for link prediction, logical rules for filtering/reranking, and a simple Streamlit UI to recommend games to users.

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

This step reads the raw IGDB snapshot, normalizes the data and writes:

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

This converts the KG relationships into triples, hides one known `LIKES` edge per eligible user for testing, trains a TransE link prediction model for:

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

This reads the TransE recommendations and applies logical KG rules:

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
The Streamlit UI lets you select a user, view that user's owned platforms and preferred genres, inspect final recommendations, see rejected candidates, and show a small graph for a recommended game.