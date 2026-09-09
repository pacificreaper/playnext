import csv
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


@st.cache_data
def load_data() -> dict:
    nodes = read_csv(ROOT / "data" / "nodes.csv")
    relationships = read_csv(ROOT / "data" / "relationships.csv")
    recommendations = read_csv(ROOT / "data" / "reasoning" / "logical_recommendations.csv")
    candidates = read_csv(ROOT / "data" / "reasoning" / "logical_game_candidates.csv")

    nodes_by_type: dict[str, dict[str, dict]] = {}
    for row in nodes:
        nodes_by_type.setdefault(row["type"], {})[row["id"]] = row

    return {
        "users": {node_id: row["name"] for node_id, row in nodes_by_type["User"].items()},
        "games": nodes_by_type["Game"],
        "genres": {node_id: row["name"] for node_id, row in nodes_by_type["Genre"].items()},
        "platforms": {node_id: row["name"] for node_id, row in nodes_by_type["Platform"].items()},
        "franchises": {node_id: row["name"] for node_id, row in nodes_by_type["Franchise"].items()},
        "recommendations": recommendations,
        "candidates": candidates,
        "user_platforms": group_relationships(relationships, "OWNS_PLATFORM"),
        "user_genres": group_relationships(relationships, "PREFERS_GENRE"),
        "game_genres": group_relationships(relationships, "HAS_GENRE"),
        "game_platforms": group_relationships(relationships, "AVAILABLE_ON"),
        "game_franchises": group_relationships(relationships, "PART_OF_FRANCHISE"),
        "game_related": group_relationships(relationships, "RELATED_TO"),
        "user_likes": group_relationships(relationships, "LIKES"),
    }


def group_relationships(relationships: list[dict], relationship_type: str) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for row in relationships:
        if row["type"] == relationship_type:
            grouped.setdefault(row["source"], set()).add(row["target"])
    return grouped


def filtered_recommendations(data: dict, user_id: str, platform: str) -> list[dict]:
    user_entity = f"User:{user_id}"
    rows = []
    for row in data["recommendations"]:
        if row["user"] == user_entity and row["eligible"] == "True":
            rows.append(row)

    if platform != "Any owned platform":
        playable_rows = []
        for row in rows:
            matched_platforms = []
            for item in row["matched_platforms"].split(";"):
                platform_name = item.strip()
                if platform_name:
                    matched_platforms.append(platform_name)
            if platform in matched_platforms:
                playable_rows.append(row)
        rows = playable_rows

    return sorted(rows, key=lambda row: int(row["logic_rank"]))


def score_percent(row: dict, max_score: float) -> int:
    if max_score <= 0:
        return 0
    return min(99, max(1, round(float(row["final_score"]) / max_score * 100)))


def render_recommendation(row: dict, score: int) -> None:
    with st.container(border=True):
        left, right = st.columns([0.8, 0.2])
        left.subheader(f"{row['logic_rank']}. {row['game_name']}")
        right.metric("Score", f"{score}%")

        for reason in row["reasons"].split(" | "):
            if not reason.startswith("Removed:"):
                st.write(reason)


def build_game_graph(data: dict, game_id: str) -> str:
    game = data["games"][game_id]
    lines = [
        "digraph G {",
        "rankdir=LR;",
        'node [shape=box, style="rounded,filled", color="#d0d7de", fillcolor="#f6f8fa", fontname="Helvetica"];',
        'edge [color="#57606a", fontname="Helvetica"];',
        f'"game" [label="{graph_label(game["name"])}", fillcolor="#dff7e6", color="#2da44e"];',
    ]

    for genre_id in sorted(data["game_genres"].get(game_id, set())):
        name = data["genres"][genre_id]
        lines.append(f'"genre:{genre_id}" [label="{graph_label(name)}"];')
        lines.append(f'"game" -> "genre:{genre_id}" [label="HAS_GENRE"];')
    for platform_id in sorted(data["game_platforms"].get(game_id, set())):
        name = data["platforms"][platform_id]
        lines.append(f'"platform:{platform_id}" [label="{graph_label(name)}"];')
        lines.append(f'"game" -> "platform:{platform_id}" [label="AVAILABLE_ON"];')
    for franchise_id in sorted(data["game_franchises"].get(game_id, set())):
        name = data["franchises"][franchise_id]
        lines.append(f'"franchise:{franchise_id}" [label="{graph_label(name)}"];')
        lines.append(f'"game" -> "franchise:{franchise_id}" [label="PART_OF_FRANCHISE"];')
    for related_id in sorted(data["game_related"].get(game_id, set())):
        if related_id in data["games"]:
            related_name = data["games"][related_id]["name"]
            lines.append(f'"related:{related_id}" [label="{graph_label(related_name)}"];')
            lines.append(f'"game" -> "related:{related_id}" [label="RELATED_TO"];')
    for source_id, related_ids in data["game_related"].items():
        if game_id in related_ids and source_id in data["games"]:
            source_name = data["games"][source_id]["name"]
            lines.append(f'"source:{source_id}" [label="{graph_label(source_name)}"];')
            lines.append(f'"source:{source_id}" -> "game" [label="RELATED_TO"];')

    lines.append("}")
    return "\n".join(lines)


def graph_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    st.set_page_config(page_title="PlayNext", layout="wide")
    st.title("PlayNext")

    data = load_data()
    tabs = st.tabs(["Recommend Games", "Show Game Graph"])

    with tabs[0]:
        user_ids = sorted(data["users"], key=lambda user_id: int(user_id.split("_")[1]))
        selected_user = st.selectbox("User", user_ids, format_func=lambda user_id: data["users"][user_id])

        owned_platform_ids = data["user_platforms"].get(selected_user, set())
        preferred_genre_ids = data["user_genres"].get(selected_user, set())
        owned_platforms = sorted(data["platforms"][platform_id] for platform_id in owned_platform_ids)
        preferred_genres = sorted(data["genres"][genre_id] for genre_id in preferred_genre_ids)

        col_a, col_b = st.columns(2)
        selected_platform = col_a.selectbox("Platform", ["Any owned platform", *owned_platforms])
        col_b.write("Preferred genres")
        col_b.write(", ".join(preferred_genres))

        st.button("Recommend Games", type="primary")

        recommendations = filtered_recommendations(data, selected_user, selected_platform)
        if not recommendations:
            st.info("No recommendations found.")
        else:
            max_score = max(float(row["final_score"]) for row in recommendations)
            for row in recommendations:
                render_recommendation(row, score_percent(row, max_score))

        rejected_candidates = []
        for row in data["candidates"]:
            if row["user"] == f"User:{selected_user}" and row["eligible"] == "False":
                rejected_candidates.append(row)

        if rejected_candidates:
            with st.expander("Rejected candidates"):
                for row in rejected_candidates:
                    st.write(f"{row['game_name']}: {row['reasons']}")

    with tabs[1]:
        recommended_game_ids = []
        for row in data["recommendations"]:
            if row["user"] == f"User:{selected_user}" and row["eligible"] == "True":
                recommended_game_ids.append(row["game"].split(":", 1)[1])

        if not recommended_game_ids:
            st.info("No recommended games to show.")
            return

        selected_game = st.selectbox(
            "Recommended game",
            recommended_game_ids,
            format_func=lambda game_id: data["games"][game_id]["name"],
        )
        st.graphviz_chart(build_game_graph(data, selected_game), width="stretch")


if __name__ == "__main__":
    main()
