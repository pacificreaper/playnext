import csv
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IGDB_JSON = DATA_DIR / "igdb_data.json"
GAME_LIMIT = 600

# Normalize certain genres and platform names
GENRE_MAP = {
    "Platform": "Platformer",
    "Real Time Strategy (RTS)": "Real Time Strategy",
    "Role-playing (RPG)": "RPG",
    "Turn-based strategy (TBS)": "Turn-Based Strategy",
}

PLATFORM_MAP = {
    "Google Stadia": "Cloud Gaming",
    "Meta Quest 2": "VR",
    "Meta Quest 3": "VR",
    "Nintendo Entertainment System": "Nintendo",
    "Oculus Rift": "VR",
    "OnLive Game System": "Cloud Gaming",
    "PC (Microsoft Windows)": "PC",
    "PlayStation VR": "VR",
    "PlayStation VR2": "VR",
    "SteamVR": "VR",
    "Super Nintendo Entertainment System": "Nintendo",
}

RELATED_GAME_FIELDS = [
    "parent_game",
    "version_parent",
    "remakes",
    "remasters",
    "expanded_games",
    "expansions",
    "standalone_expansions",
    "forks",
]

USERS = ["Asal", "Mina", "Jonas", "Leila", "Sam", "Priya", "Nora", "Mateo", "Elena", "Theo",
         "Iris", "Omar", "Talia", "Ravi", "Sofia", "Noah", "Yara", "Felix", "Amara", "Kenji",
         "Luca", "Maya", "Niko", "Ava", "Zain", "Hana", "Eli", "Daria", "Milo", "Sara",
         "Cora", "Anika", "Vera", "Idris", "Jules", "Nadia", "Ren", "Chiara", "Luis", "Ari"]


def normalize_games() -> list[dict]:
    raw_games = json.loads(IGDB_JSON.read_text(encoding="utf-8"))
    games = []
    seen_game_names = set()

    for raw in raw_games:
        if len(games) >= GAME_LIMIT:
            break
        name = str(raw.get("name", "")).strip()
        if not name or name.lower() in seen_game_names:
            continue
        seen_game_names.add(name.lower())

        genres = []
        for item in raw.get("genres", []):
            genre = igdb_name(item)
            genres.append(GENRE_MAP.get(genre, genre))
        platforms = []
        for item in raw.get("platforms", []):
            platform = igdb_name(item)
            platforms.append(PLATFORM_MAP.get(platform, platform))
        franchise = igdb_name(raw.get("franchise"))
        if not franchise and raw.get("franchises"):
            franchise = igdb_name(raw["franchises"][0])

        games.append(
            {
                "game_id": f"game_{raw.get('id')}",
                "name": name,
                "release_year": str(datetime.fromtimestamp(raw["first_release_date"], tz=timezone.utc).year),
                "genres": sorted({item for item in genres if item}),
                "platforms": sorted({item for item in platforms if item}),
                "franchise": franchise,
                "related_game_ids": sorted(get_related_game_ids(raw)),
            }
        )

    return games


def igdb_name(value) -> str:
    return str((value or {}).get("name", "")).strip()


def get_related_game_ids(raw: dict) -> set[int]:
    """Find and extract games that are related (e.g. parent/remake/remaster...) so we can connect them in the KG"""
    related_ids = set()
    for field in RELATED_GAME_FIELDS:
        value = raw.get(field, [])
        if isinstance(value, dict):
            value = [value]
        related_ids.update(item["id"] for item in value if "id" in item)
    return related_ids


def build_nodes_and_relationships(games: list[dict]) -> tuple[list[dict], list[dict]]:
    genres: list[str] = sorted({genre for game in games for genre in game["genres"]})
    platforms: list[str] = sorted({platform for game in games for platform in game["platforms"]})
    franchises: list[str] = sorted({game["franchise"] for game in games if game["franchise"]})

    genre_ids = {name: f"genre_{create_id(name)}" for name in genres}
    platform_ids = {name: f"platform_{create_id(name)}" for name in platforms}
    franchise_ids = {name: f"franchise_{create_id(name)}" for name in franchises}

    users, user_relationships = generate_users(games, genres, platforms)

    nodes = []
    for user in users:
        nodes.append(node(user["user_id"], "User", user["name"]))
    for game in games:
        nodes.append(
            node(
                game["game_id"],
                "Game",
                game["name"],
                release_year=game["release_year"],
            )
        )
    for name, genre_id in genre_ids.items():
        nodes.append(node(genre_id, "Genre", name))
    for name, platform_id in platform_ids.items():
        nodes.append(node(platform_id, "Platform", name))
    for name, franchise_id in franchise_ids.items():
        nodes.append(node(franchise_id, "Franchise", name))

    relationships = []
    game_ids = {game["game_id"] for game in games}
    for game in games:
        for genre in game["genres"]:
            relationships.append(relationship(game["game_id"], "HAS_GENRE", genre_ids[genre]))
        for platform in game["platforms"]:
            relationships.append(relationship(game["game_id"], "AVAILABLE_ON", platform_ids[platform]))
        if game["franchise"]:
            relationships.append(relationship(game["game_id"], "PART_OF_FRANCHISE", franchise_ids[game["franchise"]]))

        for related_game_id in game["related_game_ids"]:
            related_game_id = f"game_{related_game_id}"
            if related_game_id in game_ids and related_game_id != game["game_id"]:
                relationships.append(relationship(game["game_id"], "RELATED_TO", related_game_id))

    for row in user_relationships["owns_platform"]:
        relationships.append(relationship(row["user_id"], "OWNS_PLATFORM", row["platform_id"]))
    for row in user_relationships["prefers_genre"]:
        relationships.append(relationship(row["user_id"], "PREFERS_GENRE", row["genre_id"]))
    for row in user_relationships["played"]:
        relationships.append(relationship(row["user_id"], "PLAYED", row["game_id"]))
    for row in user_relationships["likes"]:
        relationships.append(relationship(row["user_id"], "LIKES", row["game_id"]))
    for row in user_relationships["dislikes"]:
        relationships.append(relationship(row["user_id"], "DISLIKES", row["game_id"]))

    return sorted(nodes, key=lambda node_row: (node_row["type"], node_row["id"])), sorted(
        relationships,
        key=lambda relationship_row: (
            relationship_row["type"],
            relationship_row["source"],
            relationship_row["target"],
        ),
    )


def create_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def generate_users(games: list[dict], genre_names: list[str], platform_names: list[str]) -> tuple[list[dict], dict[str, list[dict]]]:
    users = []
    relationships = {
        "owns_platform": [],
        "prefers_genre": [],
        "played": [],
        "likes": [],
        "dislikes": [],
    }

    genre_ids = {name: f"genre_{create_id(name)}" for name in genre_names}
    platform_ids = {name: f"platform_{create_id(name)}" for name in platform_names}

    for index, name in enumerate(USERS, start=1):
        user_id = f"user_{index}"
        users.append({"user_id": user_id, "name": name})

        preferred_genres = choose_random_sample(genre_names, 2, 5)
        owned_platforms = choose_random_sample(platform_names, 1, 4)

        for platform in sorted(owned_platforms):
            relationships["owns_platform"].append({"user_id": user_id, "platform_id": platform_ids[platform]})
        for genre in sorted(preferred_genres):
            relationships["prefers_genre"].append(
                {
                    "user_id": user_id,
                    "genre_id": genre_ids[genre],
                }
            )

        ranked_games = sorted(
            games,
            key=lambda candidate_game: game_match_score(preferred_genres, owned_platforms, candidate_game),
            reverse=True,
        )
        num_games_played = random.randint(15, 50)
        played_games = ranked_games[:num_games_played]

        for game in played_games:
            genre_match = bool(preferred_genres.intersection(game["genres"]))
            like_probability = 0.60 if genre_match else 0.30
            dislike_probability = 0.15 if genre_match else 0.30
            relationships["played"].append(
                {
                    "user_id": user_id,
                    "game_id": game["game_id"],
                }
            )
            if random.random() < like_probability:
                relationships["likes"].append(
                    {
                        "user_id": user_id,
                        "game_id": game["game_id"],
                    }
                )
            elif random.random() < dislike_probability:
                relationships["dislikes"].append(
                    {
                        "user_id": user_id,
                        "game_id": game["game_id"],
                    }
                )

    return users, relationships


def choose_random_sample(values: list[str], min_count: int, max_count: int) -> set[str]:
    low = min(min_count, len(values))
    high = min(max_count, len(values))
    return set(random.sample(values, k=random.randint(low, high)))


def game_match_score(user_genres: set[str], owned_platforms: set[str], game: dict) -> float:
    """Score how well a game matches the user's genre preferences and owned platforms"""
    genre_overlap = len(user_genres.intersection(game["genres"]))
    platform_overlap = len(owned_platforms.intersection(game["platforms"]))
    return genre_overlap + platform_overlap + random.random()


def node(node_id: str, node_type: str, name: str, **properties) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "name": name,
        "release_year": properties.get("release_year", ""),
    }


def relationship(source: str, rel_type: str, target: str) -> dict:
    return {
        "source": source,
        "type": rel_type,
        "target": target,
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    random.seed(42)
    if not IGDB_JSON.exists():
        raise SystemExit(f"Missing IGDB data file: {IGDB_JSON}")

    games = normalize_games()
    if not games:
        raise SystemExit("No games found.")

    nodes, relationships = build_nodes_and_relationships(games)

    write_csv(DATA_DIR / "nodes.csv", nodes, ["id", "type", "name", "release_year"])
    write_csv(DATA_DIR / "relationships.csv", relationships, ["source", "type", "target"])


if __name__ == "__main__":
    main()
