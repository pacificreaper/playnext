import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_reasoning_context() -> dict:
    # group nodes for lookup
    with (ROOT / "data" / "nodes.csv").open(encoding="utf-8", newline="") as nodes_file:
        nodes: dict[str, dict[str, dict]] = {}
        for row in csv.DictReader(nodes_file):
            nodes.setdefault(row["type"], {})[row["id"]] = row

    with (ROOT / "data" / "relationships.csv").open(encoding="utf-8", newline="") as relationships_file:
        relationships = list(csv.DictReader(relationships_file))

    return {
        "games": nodes["Game"],
        "genres": {identifier: row["name"] for identifier, row in nodes["Genre"].items()},
        "platforms": {identifier: row["name"] for identifier, row in nodes["Platform"].items()},
        "franchises": {identifier: row["name"] for identifier, row in nodes["Franchise"].items()},
        "game_genres": group_relationships(relationships, "HAS_GENRE"),
        "game_platforms": group_relationships(relationships, "AVAILABLE_ON"),
        "game_franchises": group_relationships(relationships, "PART_OF_FRANCHISE"),
        "user_platforms": group_relationships(relationships, "OWNS_PLATFORM"),
        "user_genres": group_relationships(relationships, "PREFERS_GENRE"),
        "user_likes": group_relationships(relationships, "LIKES"),
        "user_dislikes": group_relationships(relationships, "DISLIKES"),
        "user_seen": group_relationships(relationships, {"PLAYED", "LIKES", "DISLIKES"}),
        "related_games": build_related_game_chains(relationships),
    }


def group_relationships(rows: list[dict], rel_types: str | set[str]) -> dict[str, set[str]]:
    if isinstance(rel_types, str):
        rel_types = {rel_types}

    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["type"] in rel_types:
            groups[row["source"]].add(row["target"])
    return groups


def build_related_game_chains(rows: list[dict]) -> dict[str, set[str]]:
    direct_relations: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["type"] == "RELATED_TO":
            direct_relations[row["source"]].add(row["target"])
            direct_relations[row["target"]].add(row["source"])

    related_game_chains = {}
    for game in direct_relations:
        related_games = find_related_games(game, direct_relations, {game})
        related_games.remove(game)
        related_game_chains[game] = related_games

    return related_game_chains


def find_related_games(game: str, direct_relations: dict[str, set[str]], seen: set[str]) -> set[str]:
    for related_game in direct_relations.get(game, set()):
        if related_game not in seen:
            seen.add(related_game)
            find_related_games(related_game, direct_relations, seen)
    return seen


def apply_logic_to_recommendations(recommendations: list[dict], context: dict) -> tuple[list[dict], list[dict]]:
    recommendations_by_user: dict[str, list[dict]] = defaultdict(list)
    for rec in recommendations:
        recommendations_by_user[rec["user"]].append(rec)

    final_recommendations = []
    all_scored_candidates = []

    for _user, user_rec in sorted(recommendations_by_user.items()):
        user_rec.sort(key=lambda recommendation: float(recommendation["score"]), reverse=True)

        scored_candidates = []
        for rank, rec in enumerate(user_rec[:20], start=1): # we only look at top 20 recs for a user
            scored_candidate = score_candidate(rec, rank=rank, context=context)
            scored_candidates.append(scored_candidate)
            all_scored_candidates.append(scored_candidate)

        eligible_candidates = [candidate for candidate in scored_candidates if candidate["eligible"]]
        eligible_candidates.sort(key=lambda candidate: candidate["final_score"], reverse=True)

        for rank, rec in enumerate(eligible_candidates[:5], start=1): # select top 5 recs as final result
            final_recommendation = dict(rec)
            final_recommendation["logic_rank"] = rank
            final_recommendations.append(final_recommendation)

    return final_recommendations, all_scored_candidates


def score_candidate(row: dict, rank: int, context: dict) -> dict:
    user_id = row["user"].split(":", 1)[1]
    game_id = row["game"].split(":", 1)[1]

    # user specific info
    owned_platforms = context["user_platforms"].get(user_id, set())
    preferred_genres = context["user_genres"].get(user_id, set())
    liked_games = context["user_likes"].get(user_id, set())
    disliked_games = context["user_dislikes"].get(user_id, set())
    seen_games = context["user_seen"].get(user_id, set())

    liked_franchises = set()
    for liked_game in liked_games:
        liked_franchises.update(context["game_franchises"].get(liked_game, set()))

    # candidate game info
    game_platforms = context["game_platforms"].get(game_id, set())
    game_genres = context["game_genres"].get(game_id, set())
    game_franchises = context["game_franchises"].get(game_id, set())

    matched_platforms = sorted(owned_platforms & game_platforms)
    matched_genres = sorted(preferred_genres & game_genres)
    matched_franchises = sorted(game_franchises & liked_franchises)

    related_liked_games = []
    for liked_game in liked_games:
        if liked_game in context["related_games"].get(game_id, set()):
            related_liked_games.append(liked_game)
    related_liked_games.sort()

    playable = bool(matched_platforms)
    already_seen = game_id in seen_games
    disliked = game_id in disliked_games
    eligible = playable and not already_seen and not disliked

    embedding_rank_score = 1.0 / rank
    bonus_score = 0.0
    reasons = []

    # remove unsuitable games and add bonus points for matching user preferences and related games
    if playable:
        reasons.append("Available on " + ", ".join(context["platforms"][platform] for platform in matched_platforms))
    else:
        reasons.append("Removed: no owned platform match")
    if already_seen:
        reasons.append("Removed: already played")
    if disliked:
        reasons.append("Removed: disliked")

    if matched_genres:
        bonus_score += 0.25
        reasons.append("Matches preferred genre: " + ", ".join(context["genres"][genre] for genre in matched_genres))
    if matched_franchises:
        bonus_score += 0.20
        reasons.append("Same franchise as liked game: " + ", ".join(context["franchises"][franchise] for franchise in matched_franchises))
    if related_liked_games:
        bonus_score += 0.15
        related_names = [context["games"][game]["name"] for game in related_liked_games if game in context["games"]]
        reasons.append("Related to liked game: " + ", ".join(related_names))

    return {
        "user": f"User:{user_id}",
        "game": f"Game:{game_id}",
        "game_name": context["games"].get(game_id, {}).get("name", row.get("game_name", "")),
        "embedding_rank": rank,
        "embedding_score": row["score"],
        "final_score": round(embedding_rank_score + bonus_score, 6) if eligible else 0.0,
        "eligible": eligible,
        "matched_platforms": "; ".join(context["platforms"][platform] for platform in matched_platforms),
        "matched_genres": "; ".join(context["genres"][genre] for genre in matched_genres),
        "matched_franchises": "; ".join(context["franchises"][franchise] for franchise in matched_franchises),
        "related_liked_games": "; ".join(context["games"][game]["name"] for game in related_liked_games if game in context["games"]),
        "reasons": " | ".join(reasons),
    }


def write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    reasoning_context = build_reasoning_context()
    with (ROOT / "data" / "embeddings" / "recommendations.csv").open(encoding="utf-8", newline="") as recommendations_file:
        recommendations = list(csv.DictReader(recommendations_file))

    final_recs, candidates = apply_logic_to_recommendations(recommendations, context=reasoning_context)

    recommendation_columns = [
        "user",
        "logic_rank",
        "game",
        "game_name",
        "embedding_rank",
        "embedding_score",
        "final_score",
        "eligible",
        "matched_platforms",
        "matched_genres",
        "matched_franchises",
        "related_liked_games",
        "reasons",
    ]

    candidate_columns = []
    for column in recommendation_columns:
        # rejected candidates do not have a final rank
        if column != "logic_rank":
            candidate_columns.append(column)

    write_rows( ROOT / "data" / "reasoning" / "logical_recommendations.csv", final_recs, recommendation_columns)
    write_rows( ROOT / "data" / "reasoning" / "logical_game_candidates.csv", candidates, candidate_columns)


if __name__ == "__main__":
    main()
