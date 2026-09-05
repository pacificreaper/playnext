import csv
import os
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "TransE"

os.environ.setdefault("PYSTOW_HOME", str(ROOT / ".pystow"))

import torch
from pykeen.pipeline import pipeline
from pykeen.triples import TriplesFactory


def convert_to_triples() -> list[tuple[str, str, str]]:
    """Convert the node and relationship files into triples for embedding training"""
    nodes_path = ROOT / "data" / "nodes.csv"
    with nodes_path.open(encoding="utf-8", newline="") as nodes_file:
        node_types = {row["id"]: row["type"] for row in csv.DictReader(nodes_file)}

    relationships_path = ROOT / "data" / "relationships.csv"
    with relationships_path.open(encoding="utf-8", newline="") as relationships_file:
        return sorted(
            {
                (
                    f"{node_types[row['source']]}:{row['source']}",
                    row["type"],
                    f"{node_types[row['target']]}:{row['target']}",
                )
                for row in csv.DictReader(relationships_file)
            }
        )


def prepare_training_data(
    triples: list[tuple[str, str, str]],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Hide one LIKES edge per user so the model can be tested on predicting it"""
    rng = random.Random(42)
    train = [triple for triple in triples if triple[1] != "LIKES"]
    likes_by_user: dict[str, list[tuple[str, str, str]]] = {}

    for triple in triples:
        if triple[1] == "LIKES":
            user = triple[0]
            likes_by_user.setdefault(user, []).append(triple)

    test: list[tuple[str, str, str]] = []
    for user_likes in likes_by_user.values():
        rng.shuffle(user_likes)
        if len(user_likes) > 1:
            test.append(user_likes[0])
            train.extend(user_likes[1:])
        else:
            train.extend(user_likes)

    return sorted(set(train)), sorted(set(test))


def write_triples(path: Path, triples: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t", lineterminator="\n")
        writer.writerows(triples)


def train_model(training, testing):
    result = pipeline(
        training=training,
        testing=testing,
        model=MODEL_NAME,
        model_kwargs={"embedding_dim": 64},
        training_kwargs={"num_epochs": 100, "batch_size": 256},
        evaluator_kwargs={"filtered": True},
        random_seed=42,
        device="cpu",
    )
    return result


def user_played_games(triples: list[tuple[str, str, str]]) -> dict[str, set[str]]:
    played: dict[str, set[str]] = {}
    for head, relation, tail in triples:
        if relation in {"PLAYED", "LIKES", "DISLIKES"}:
            played.setdefault(head, set()).add(tail)
    return played


def recommend_games(model, factory: TriplesFactory, user: str, seen_games: set[str]) -> list[tuple[str, float]]:
    entity_to_id = factory.entity_to_id
    relation_to_id = factory.relation_to_id

    # score how likely the user is to like each game
    user_likes = torch.as_tensor([[entity_to_id[user], relation_to_id["LIKES"]]], device=model.model.device)
    with torch.no_grad():
        scores = model.model.score_t(user_likes).cpu().flatten()

    # keep only unseen games and rank by transE score
    candidates = [
        (game, float(scores[entity_to_id[game]]))
        for game in entity_to_id
        if game.startswith("Game:") and game not in seen_games
    ]
    return sorted(candidates, key=lambda item: item[1], reverse=True)[:20]


def write_csv(path: Path, header: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    triples = convert_to_triples()
    train_triples, test_triples = prepare_training_data(triples)

    embedding_data_dir = ROOT / "data" / "embeddings"
    train_path = embedding_data_dir / "train.tsv"
    test_path = embedding_data_dir / "test_likes.tsv"

    write_triples(train_path, train_triples)
    write_triples(test_path, test_triples)

    training = TriplesFactory.from_path(train_path)
    testing = TriplesFactory.from_path(
        test_path,
        entity_to_id=training.entity_to_id,
        relation_to_id=training.relation_to_id,
    )

    recommendations = []
    nodes_path = ROOT / "data" / "nodes.csv"
    with nodes_path.open(encoding="utf-8", newline="") as nodes_file:
        game_names = {
            f"Game:{row['id']}": row["name"]
            for row in csv.DictReader(nodes_file)
            if row["type"] == "Game"
        }

    model = train_model(training=training, testing=testing)
    metrics = [
        (
            len(test_triples),
            float(model.get_metric("mrr")),
            float(model.get_metric("hits_at_1")),
            float(model.get_metric("hits_at_3")),
            float(model.get_metric("hits_at_10")),
        )
    ]

    users = sorted(entity for entity in training.entity_to_id if entity.startswith("User:"))
    seen_by_user = user_played_games(triples)
    for user in users:
        for game, score in recommend_games(model, training, user, seen_by_user.get(user, set())):
            recommendation = (user, game, game_names.get(game, ""), score)
            recommendations.append(recommendation)

    write_csv(
        embedding_data_dir / "metrics.csv",
        ["test_likes", "mrr", "hits_at_1", "hits_at_3", "hits_at_10"],
        metrics,
    )
    write_csv(
        embedding_data_dir / "recommendations.csv",
        ["user", "game", "game_name", "score"],
        recommendations,
    )


if __name__ == "__main__":
    main()
