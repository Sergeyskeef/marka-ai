import json

import matplotlib.pyplot as plt
import networkx as nx
import streamlit as st

st.set_page_config(page_title="Sandbox Dashboard", layout="wide")
st.title("🧪 Sandbox Dashboard")

# --- Карта архитектуры ---
st.header("Карта архитектуры проекта")
try:
    with open("project_map.json", encoding="utf-8") as f:
        data = json.load(f)
    G = nx.DiGraph()
    for mod in data.get("modules", {}):
        G.add_node(mod)
    edge_count = 0
    for edge in data.get("edges", []):
        if isinstance(edge, dict) and "from" in edge and "to" in edge:
            src, dst = edge["from"], edge["to"]
        elif isinstance(edge, list | tuple) and len(edge) == 2:
            src, dst = edge[0], edge[1]
        else:
            continue
        G.add_edge(src, dst)
        edge_count += 1
    if len(G.nodes) == 0:
        st.info("Граф пустой: нет ни одного модуля.")
    elif edge_count == 0:
        st.info("Граф построен, но нет ни одного ребра (зависимости не найдены).")
    else:
        fig, ax = plt.subplots(figsize=(18, 12))
        pos = nx.spring_layout(G, k=0.3)
        nx.draw(
            G, pos, with_labels=True, node_size=200, font_size=6, ax=ax, arrows=True,
            width=0.5, edge_color='gray', node_color='skyblue'
        )
        plt.tight_layout()
        st.pyplot(fig)
except Exception as e:
    st.warning(f"Не удалось отобразить карту: {e}")

# --- История изменений ---
st.header("История изменений (журнал)")
try:
    with open("sandbox_experiments.log", encoding="utf-8") as f:
        lines = f.readlines()[-20:]
    for line in lines:
        st.text(line.strip())
except Exception as e:
    st.warning(f"Не удалось прочитать журнал: {e}")

# --- Diff-отчёт ---
st.header("Последний diff-отчёт")
diff = None
try:
    with open("sandbox_diff_report.txt", encoding="utf-8") as f:
        diff = f.read()
except UnicodeDecodeError as e:
    try:
        with open("sandbox_diff_report.txt", encoding="latin1") as f:
            diff = f.read()
        st.warning(f"Diff-отчёт содержит не-UTF-8 символы, показан в latin1: {e}")
    except Exception as e2:
        st.warning(f"Не удалось прочитать diff-отчёт даже в latin1: {e2}")
except Exception as e:
    st.warning(f"Не удалось прочитать diff-отчёт: {e}")
if diff:
    lines = diff.splitlines()
    max_lines = 200
    if len(lines) > max_lines:
        st.text_area("Diff (показаны первые 200 строк)", "\n".join(lines[:max_lines]), height=300)
        st.info(f"Показаны только первые {max_lines} строк из {len(lines)}.")
    else:
        st.text_area("Diff", diff, height=300)
