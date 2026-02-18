import streamlit as st
import pandas as pd
from datetime import datetime
import base64
import json
import requests
import io
import time
import re

st.set_page_config(page_title="Planner de Treinos", layout="wide")


# ============================================================
# 0) Helpers
# ============================================================
def today_pt() -> str:
    map_pt = {
        0: "Segunda",
        1: "Terça",
        2: "Quarta",
        3: "Quinta",
        4: "Sexta",
        5: "Sábado",
        6: "Domingo",
    }
    return map_pt[datetime.now().weekday()]


def goto(screen: str):
    st.session_state.screen = screen
    st.rerun()


def _now_utc_z():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _safe_id(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or f"ex_{int(time.time())}"


def init_state():
    if "screen" not in st.session_state:
        st.session_state.screen = "login"
    if "user" not in st.session_state:
        st.session_state.user = None
    if "day_selected" not in st.session_state:
        st.session_state.day_selected = today_pt()

    # edição
    if "edit_day" not in st.session_state:
        st.session_state.edit_day = today_pt()
    if "open_day_modal" not in st.session_state:
        st.session_state.open_day_modal = False
    if "open_ex_modal" not in st.session_state:
        st.session_state.open_ex_modal = False
    if "edit_action" not in st.session_state:
        st.session_state.edit_action = None
    if "edit_row_id" not in st.session_state:
        st.session_state.edit_row_id = None

    # cadastro de exercício
    if "open_new_ex_modal" not in st.session_state:
        st.session_state.open_new_ex_modal = False


# ============================================================
# 1) GitHub helpers
# ============================================================
def _gh():
    gh = st.secrets.get("github", {})
    return (
        gh.get("token", ""),
        gh.get("owner", "FelipeNovais89"),
        gh.get("repo", "GYM-Treino-Amor"),
        gh.get("branch", "main"),
    )


def _gh_headers(token: str):
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def gh_read_file(path: str) -> tuple[str, str]:
    """Retorna (texto, sha). Se não existir, ('','')."""
    token, owner, repo, branch = _gh()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    r = requests.get(url, headers=_gh_headers(token), timeout=20)
    if r.status_code == 404:
        return "", ""
    r.raise_for_status()
    data = r.json()
    sha = data.get("sha", "")
    content_b64 = data.get("content", "") or ""
    txt = base64.b64decode(content_b64).decode("utf-8", errors="replace") if content_b64 else ""
    return txt, sha


def gh_write_file(path: str, txt: str, message: str) -> bool:
    token, owner, repo, branch = _gh()
    if not token:
        st.error("Configure github.token em st.secrets (Streamlit Cloud → Settings → Secrets).")
        return False

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    _, sha = gh_read_file(path)

    payload = {
        "message": message,
        "content": base64.b64encode((txt or "").encode("utf-8")).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=_gh_headers(token), data=json.dumps(payload), timeout=20)
    if r.status_code not in (200, 201):
        st.error(f"Erro GitHub: {r.status_code} - {r.text}")
        return False
    return True


# ============================================================
# 2) LOG (Data/treino_log.csv)
# ============================================================
GITHUB_LOG_PATH = "Data/treino_log.csv"
LOG_COLUMNS = ["timestamp", "user", "dia", "grupo", "exercicio", "series_reps", "peso_kg", "feito"]


@st.cache_data(ttl=60)
def load_history_from_github() -> pd.DataFrame:
    txt, _ = gh_read_file(GITHUB_LOG_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=LOG_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=LOG_COLUMNS)

    for col in LOG_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col not in ("peso_kg", "feito") else (0.0 if col == "peso_kg" else 0)

    df = df[LOG_COLUMNS].copy()
    df["peso_kg"] = pd.to_numeric(df["peso_kg"], errors="coerce").fillna(0.0)
    df["feito"] = pd.to_numeric(df["feito"], errors="coerce").fillna(0).astype(int)
    df["timestamp"] = df["timestamp"].astype(str)
    df["user"] = df["user"].astype(str)
    df["dia"] = df["dia"].astype(str)
    df["exercicio"] = df["exercicio"].astype(str)
    df["grupo"] = df["grupo"].astype(str)
    df["series_reps"] = df["series_reps"].astype(str)
    return df


def append_history_to_github(df_new: pd.DataFrame) -> bool:
    df_old = load_history_from_github()

    for col in LOG_COLUMNS:
        if col not in df_new.columns:
            df_new[col] = "" if col not in ("peso_kg", "feito") else (0.0 if col == "peso_kg" else 0)
        if col not in df_old.columns:
            df_old[col] = "" if col not in ("peso_kg", "feito") else (0.0 if col == "peso_kg" else 0)

    df_old = df_old[LOG_COLUMNS].copy()
    df_new = df_new[LOG_COLUMNS].copy()

    df_old["peso_kg"] = pd.to_numeric(df_old["peso_kg"], errors="coerce").fillna(0.0)
    df_new["peso_kg"] = pd.to_numeric(df_new["peso_kg"], errors="coerce").fillna(0.0)

    df_old["feito"] = pd.to_numeric(df_old["feito"], errors="coerce").fillna(0).astype(int)
    df_new["feito"] = pd.to_numeric(df_new["feito"], errors="coerce").fillna(0).astype(int)

    df_all = pd.concat([df_old, df_new], ignore_index=True)
    csv_txt = df_all.to_csv(index=False, encoding="utf-8")

    ok = gh_write_file(GITHUB_LOG_PATH, csv_txt, f"append treino log {_now_utc_z()}")
    if ok:
        load_history_from_github.clear()
    return ok


def _autolog_debounced(user: str, day: str, group: str, exercise_name: str, reps_done: str, weight: float, done: bool):
    """
    Auto-salva no treino_log.csv com debounce (evita spammar commits no GitHub).
    """
    k = f"__last_autosave__{user}__{day}__{exercise_name}"
    now = time.time()
    last = float(st.session_state.get(k, 0.0) or 0.0)
    if now - last < 1.2:
        return
    st.session_state[k] = now

    df_new = pd.DataFrame(
        [{
            "timestamp": _now_utc_z(),
            "user": user,
            "dia": day,
            "grupo": group,
            "exercicio": exercise_name,
            "series_reps": str(reps_done or "").strip(),
            "peso_kg": float(weight or 0.0),
            "feito": int(bool(done)),
        }],
        columns=LOG_COLUMNS
    )
    append_history_to_github(df_new)


# ============================================================
# 3) TREINOS (Data/treinos.csv)  — mantém seu formato atual
# ============================================================
GITHUB_TREINOS_PATH = "Data/treinos.csv"
TREINOS_COLUMNS = ["user", "dia", "ordem", "grupo", "exercicio", "series_reps", "gif_key", "alt_group"]


@st.cache_data(ttl=60)
def load_treinos_from_github() -> pd.DataFrame:
    txt, _ = gh_read_file(GITHUB_TREINOS_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=TREINOS_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=TREINOS_COLUMNS)

    for col in TREINOS_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[TREINOS_COLUMNS].copy()
    df["user"] = df["user"].astype(str)
    df["dia"] = df["dia"].astype(str)
    df["ordem"] = pd.to_numeric(df["ordem"], errors="coerce").fillna(9999).astype(int)
    df["grupo"] = df["grupo"].astype(str)
    df["exercicio"] = df["exercicio"].astype(str)
    df["series_reps"] = df["series_reps"].astype(str)
    df["gif_key"] = df["gif_key"].astype(str)
    df["alt_group"] = df["alt_group"].astype(str)
    return df


def save_treinos_to_github(df_all: pd.DataFrame) -> bool:
    for col in TREINOS_COLUMNS:
        if col not in df_all.columns:
            df_all[col] = ""

    df_all = df_all[TREINOS_COLUMNS].copy()
    df_all["ordem"] = pd.to_numeric(df_all["ordem"], errors="coerce").fillna(9999).astype(int)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_TREINOS_PATH, csv_txt, f"update treinos {_now_utc_z()}")
    if ok:
        load_treinos_from_github.clear()
    return ok


# ============================================================
# 4) EXERCÍCIOS (Data/exercicios.csv) — agora com gif_url (Opção B)
# Mantém compatível com seu header atual:
# exercicio,grupo,gif_key,alt_group,observacoes
# e adiciona gif_url se não existir.
# ============================================================
GITHUB_EXERCICIOS_PATH = "Data/exercicios.csv"
EX_COLUMNS_CANON = ["exercicio", "grupo", "gif_key", "gif_url", "alt_group", "observacoes"]


@st.cache_data(ttl=60)
def load_exercicios_from_github() -> pd.DataFrame:
    txt, _ = gh_read_file(GITHUB_EXERCICIOS_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=EX_COLUMNS_CANON)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=EX_COLUMNS_CANON)

    # normaliza colunas
    df.columns = [str(c).strip() for c in df.columns]

    # adiciona colunas que faltam
    for col in EX_COLUMNS_CANON:
        if col not in df.columns:
            df[col] = ""

    df = df[EX_COLUMNS_CANON].copy()

    # limpa NaN
    for col in EX_COLUMNS_CANON:
        df[col] = df[col].fillna("").astype(str)

    # ordena por grupo + exercicio
    df["_grp"] = df["grupo"].astype(str)
    df["_ex"] = df["exercicio"].astype(str)
    df = df.sort_values(["_grp", "_ex"], ascending=True).drop(columns=["_grp", "_ex"])
    return df


def save_exercicios_to_github(df_all: pd.DataFrame) -> bool:
    for col in EX_COLUMNS_CANON:
        if col not in df_all.columns:
            df_all[col] = ""

    df_all = df_all[EX_COLUMNS_CANON].copy()
    for col in EX_COLUMNS_CANON:
        df_all[col] = df_all[col].fillna("").astype(str)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_EXERCICIOS_PATH, csv_txt, f"update exercicios {_now_utc_z()}")
    if ok:
        load_exercicios_from_github.clear()
    return ok


def _gif_url_for(ex_df: pd.DataFrame, exercicio: str, gif_key: str) -> str:
    """
    Resolve o GIF assim:
    1) se achar exercício no exercicios.csv e tiver gif_url -> usa
    2) senão, se tiver gif_key e existir gif_url associado (coluna) -> usa
    3) senão vazio
    """
    exercicio = (exercicio or "").strip()
    gif_key = (gif_key or "").strip()

    if ex_df is None or ex_df.empty:
        return ""

    # match por nome do exercício
    if exercicio:
        m = ex_df[ex_df["exercicio"].astype(str) == exercicio]
        if not m.empty:
            url = (m.iloc[0].get("gif_url", "") or "").strip()
            if url:
                return url

    # match por gif_key
    if gif_key:
        m2 = ex_df[ex_df["gif_key"].astype(str) == gif_key]
        if not m2.empty:
            url = (m2.iloc[0].get("gif_url", "") or "").strip()
            if url:
                return url

    return ""


# ============================================================
# 5) Helpers UI
# ============================================================
EDIT_DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]


def _ensure_days_for_user(df_all: pd.DataFrame, user: str) -> pd.DataFrame:
    """Garante registros (mesmo vazios) para Seg–Sex no treinos.csv daquele user."""
    dfu = df_all[df_all["user"].astype(str) == str(user)]
    existing_days = set(dfu["dia"].astype(str).unique().tolist())

    rows = []
    for d in EDIT_DAYS:
        if d not in existing_days:
            rows.append({
                "user": user,
                "dia": d,
                "ordem": 1,
                "grupo": "",
                "exercicio": "",
                "series_reps": "",
                "gif_key": "",
                "alt_group": "",
            })

    if rows:
        df_all = pd.concat([df_all, pd.DataFrame(rows)], ignore_index=True)

    return df_all


def last_weight(df_history: pd.DataFrame, user: str, day: str, exercise_name: str) -> float:
    if df_history is None or df_history.empty:
        return 0.0
    df = df_history.copy()
    df = df[df["user"].astype(str) == str(user)]
    df = df[df["dia"].astype(str) == str(day)]
    df = df[df["exercicio"].astype(str) == str(exercise_name)]
    if df.empty:
        return 0.0
    df = df.sort_values("timestamp", ascending=True)
    val = df.iloc[-1].get("peso_kg", 0.0)
    try:
        return float(val)
    except Exception:
        return 0.0


def _open_ex_modal(action: str, rid: dict | None):
    # IMPORTANT: fecha o modal do dia e abre o modal do exercício + rerun
    st.session_state.edit_action = action
    st.session_state.edit_row_id = rid
    st.session_state.open_ex_modal = True
    st.session_state.open_day_modal = False
    st.rerun()


# ============================================================
# 6) TELAS
# ============================================================
def screen_login():
    st.title("Planner de Treinos")
    st.caption("Escolha o usuário (sem senha).")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Teca Ernesto 🤍 (Futura Novais)", use_container_width=True):
            st.session_state.user = "Amor 🤍"
            st.session_state.day_selected = today_pt()
            goto("menu")
    with c2:
        if st.button("Tico Novais ❤️ (Enfezadinho do Oceano)", use_container_width=True):
            st.session_state.user = "Felipe 💪"
            st.session_state.day_selected = today_pt()
            goto("menu")


def screen_menu():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title(f"Olá, {user} 👋")
    st.caption("O que você quer fazer agora?")

    colA, colB = st.columns(2)
    with colA:
        if st.button("🏋️ Ir para o Treino (hoje)", use_container_width=True):
            st.session_state.day_selected = today_pt()
            goto("treino")
        if st.button("📈 Gráficos de evolução", use_container_width=True):
            goto("graficos")

    with colB:
        if st.button("✏️ Alterar treino", use_container_width=True):
            goto("editar_treino")
        if st.button("🗂 Histórico", use_container_width=True):
            goto("historico")

    st.markdown("---")
    if st.button("🚪 Trocar usuário", use_container_width=True):
        st.session_state.user = None
        goto("login")


def screen_treino():
    user = st.session_state.user
    if not user:
        goto("login")

    df_history = load_history_from_github()
    df_treinos = load_treinos_from_github()
    df_ex = load_exercicios_from_github()

    df_treinos = _ensure_days_for_user(df_treinos, user)
    dfu_days = set(df_treinos[df_treinos["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        save_treinos_to_github(df_treinos)

    st.title(f"Treino — {user}")

    topL, topR = st.columns([1, 1])
    with topL:
        if st.button("⬅️ Voltar", use_container_width=True):
            goto("menu")
    with topR:
        if st.button("🔁 Trocar usuário", use_container_width=True):
            st.session_state.user = None
            goto("login")

    st.markdown("---")

    available_days = EDIT_DAYS
    default_day = st.session_state.get("day_selected", today_pt())
    if default_day not in available_days:
        default_day = available_days[0]

    idx_default = available_days.index(default_day)
    day = st.selectbox("Dia do treino", options=available_days, index=idx_default, key="day_picker")
    st.session_state.day_selected = day

    dfu = df_treinos[df_treinos["user"].astype(str) == str(user)].copy()
    dfd = dfu[dfu["dia"].astype(str) == str(day)].copy()
    dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)
    dfd = dfd.sort_values("ordem", ascending=True)
    dfd = dfd[dfd["exercicio"].astype(str).str.strip() != ""].copy()

    st.subheader(f"{day} — Exercícios")

    if dfd.empty:
        st.info("Esse dia ainda não tem exercícios. Vá em **Alterar treino** para adicionar.")
        return

    done_flags = []

    for i, r in enumerate(dfd.to_dict("records")):
        group = str(r.get("grupo", "") or "")
        name = str(r.get("exercicio", "") or "")
        planned_reps = str(r.get("series_reps", "") or "")
        gif_key = str(r.get("gif_key", "") or "")
        gif_url = _gif_url_for(df_ex, name, gif_key)

        reps_done_key = f"{user}_{day}_{i}_reps_done"
        weight_key = f"{user}_{day}_{i}_peso"
        done_key = f"{user}_{day}_{i}_feito"

        if reps_done_key not in st.session_state:
            st.session_state[reps_done_key] = planned_reps

        if weight_key not in st.session_state:
            st.session_state[weight_key] = last_weight(df_history, user, day, name)

        if done_key not in st.session_state:
            st.session_state[done_key] = False

        def _on_any_change(i_local=i, group_local=group, ex_name=name, planned_local=planned_reps):
            reps_done_val = st.session_state.get(f"{user}_{day}_{i_local}_reps_done", planned_local)
            weight_val = st.session_state.get(f"{user}_{day}_{i_local}_peso", 0.0)
            done_val = st.session_state.get(f"{user}_{day}_{i_local}_feito", False)

            _autolog_debounced(
                user=user,
                day=day,
                group=group_local,
                exercise_name=ex_name,
                reps_done=str(reps_done_val or "").strip(),
                weight=float(weight_val or 0.0),
                done=bool(done_val),
            )

        st.markdown(f"### {name}")
        if group.strip() and group.lower() != "nan":
            st.caption(group)

        cols = st.columns([2, 1])
        with cols[0]:
            if gif_url:
                st.image(gif_url, width=260)
            else:
                st.info("Sem GIF disponível (cadastre a URL em Exercícios)")

        with cols[1]:
            st.write(f"● Planejado: **{planned_reps}**")
            st.text_input("Séries x Reps (feito)", key=reps_done_key, on_change=_on_any_change)
            st.number_input("Peso (kg)", min_value=0.0, step=0.5, key=weight_key, on_change=_on_any_change)
            st.checkbox("Feito?", key=done_key, on_change=_on_any_change)

        done_flags.append(bool(st.session_state[done_key]))
        st.markdown("---")

    if done_flags:
        celebrate_key = f"{user}_{day}_celebrated"
        all_done = all(done_flags)
        if all_done and not st.session_state.get(celebrate_key, False):
            st.balloons()
            if user == "Amor 🤍":
                st.success("🎉 Parabéns Amor ❤️\nMais um dia de treino feito")
            else:
                st.success("🎉 Treino completo! 💪")
            st.session_state[celebrate_key] = True
        elif not all_done:
            st.session_state[celebrate_key] = False

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📄 Ver histórico (últimas 50)", use_container_width=True):
            dfh = load_history_from_github()
            dfh = dfh[dfh["user"].astype(str) == str(user)]
            dfh = dfh.sort_values("timestamp", ascending=False).head(50)
            st.dataframe(dfh, use_container_width=True, height=280)
    with c2:
        if st.button("🧹 Limpar (só tela)", use_container_width=True):
            # não apaga histórico, só a tela
            for i in range(len(dfd)):
                st.session_state[f"{user}_{day}_{i}_reps_done"] = str(dfd.iloc[i].get("series_reps", "") or "")
                st.session_state[f"{user}_{day}_{i}_peso"] = 0.0
                st.session_state[f"{user}_{day}_{i}_feito"] = False
            st.info("Campos zerados (histórico no GitHub continua).")


def screen_historico():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title(f"Histórico — {user}")
    if st.button("⬅️ Voltar", use_container_width=True):
        goto("menu")

    dfh = load_history_from_github()
    dfh = dfh[dfh["user"].astype(str) == str(user)].copy()

    if dfh.empty:
        st.info("Ainda não há registros para este usuário.")
        return

    dfh = dfh.sort_values("timestamp", ascending=False)
    st.dataframe(dfh, use_container_width=True, height=520)


def screen_graficos():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title(f"Gráficos — {user}")
    if st.button("⬅️ Voltar", use_container_width=True):
        goto("menu")

    dfh = load_history_from_github()
    dfh = dfh[dfh["user"].astype(str) == str(user)].copy()
    if dfh.empty:
        st.info("Sem dados ainda. Mexa nos pesos/feito e ele vai salvando automaticamente.")
        return

    day_opts = ["(todos)"] + sorted(dfh["dia"].dropna().unique().tolist())
    dia_sel = st.selectbox("Filtrar por dia", options=day_opts)
    if dia_sel != "(todos)":
        dfh = dfh[dfh["dia"] == dia_sel]

    ex_opts = ["(todos)"] + sorted(dfh["exercicio"].dropna().unique().tolist())
    ex_sel = st.selectbox("Filtrar por exercício", options=ex_opts)
    if ex_sel != "(todos)":
        dfh = dfh[dfh["exercicio"] == ex_sel]

    dfh["peso_kg"] = pd.to_numeric(dfh["peso_kg"], errors="coerce").fillna(0.0)
    dfh = dfh.sort_values("timestamp", ascending=True)

    st.caption("Tabela filtrada (se quiser, eu coloco gráficos de linha/volume/PR).")
    st.dataframe(dfh.tail(300), use_container_width=True, height=520)


# ============================================================
# Tela: editar treino (modais + lista de exercícios cadastrados)
# ============================================================
def screen_editar_treino():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title("✏️ Editar treino")

    top1, top2, top3 = st.columns([1, 1, 1])
    with top1:
        if st.button("⬅️ Voltar", use_container_width=True):
            goto("menu")
    with top2:
        if st.button("🔁 Trocar usuário", use_container_width=True):
            st.session_state.user = None
            goto("login")
    with top3:
        if st.button("➕ Cadastrar novo exercício", use_container_width=True):
            st.session_state.open_new_ex_modal = True

    st.markdown("---")

    df_all = load_treinos_from_github()
    df_all = _ensure_days_for_user(df_all, user)

    dfu_days = set(df_all[df_all["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        save_treinos_to_github(df_all)

    df_ex = load_exercicios_from_github()

    # ====== GRID de dias
    st.subheader("Escolha um dia para editar")
    cols = st.columns(5)
    for i, d in enumerate(EDIT_DAYS):
        with cols[i]:
            if st.button(d, use_container_width=True, key=f"btn_day_{d}"):
                st.session_state.edit_day = d
                st.session_state.open_day_modal = True

    if st.session_state.edit_day not in EDIT_DAYS:
        st.session_state.edit_day = "Segunda"
    day = st.session_state.edit_day

    # ============================================================
    # Modal: cadastrar novo exercício
    # ============================================================
    if st.session_state.open_new_ex_modal:

        @st.dialog("➕ Cadastrar novo exercício", width="large")
        def new_ex_modal():
            nonlocal df_ex

            st.caption("Isso salva no **Data/exercicios.csv** no GitHub. Depois já aparece na lista pra montar treinos.")

            c1, c2 = st.columns(2)
            with c1:
                ex_name = st.text_input("Nome do exercício (ex: Supino reto na barra)")
                group = st.text_input("Grupo muscular (ex: Peito)")
                gif_key = st.text_input("gif_key (opcional, se você quiser manter um padrão)", value=_safe_id(ex_name))
            with c2:
                gif_url = st.text_input("GIF URL (cole o link do gif aqui)")
                alt_group = st.text_input("alt_group (opcional)")
                obs = st.text_area("Observações (opcional)", height=90)

            if gif_url and not (gif_url.startswith("http://") or gif_url.startswith("https://")):
                st.warning("O GIF URL precisa começar com http:// ou https://")

            st.markdown("---")
            a, b = st.columns(2)

            with a:
                if st.button("Salvar exercício", use_container_width=True):
                    if not ex_name.strip():
                        st.error("Preencha o nome do exercício.")
                        return
                    if not group.strip():
                        st.error("Preencha o grupo muscular.")
                        return

                    # garante colunas
                    for col in EX_COLUMNS_CANON:
                        if col not in df_ex.columns:
                            df_ex[col] = ""

                    # evita duplicar pelo nome
                    exists = df_ex[df_ex["exercicio"].astype(str) == ex_name.strip()]
                    if not exists.empty:
                        st.warning("Já existe um exercício com esse nome. Vou atualizar o registro existente.")
                        df_ex = df_ex[df_ex["exercicio"].astype(str) != ex_name.strip()].copy()

                    new_row = pd.DataFrame([{
                        "exercicio": ex_name.strip(),
                        "grupo": group.strip(),
                        "gif_key": (gif_key or "").strip(),
                        "gif_url": (gif_url or "").strip(),
                        "alt_group": (alt_group or "").strip(),
                        "observacoes": (obs or "").strip(),
                    }])

                    df_ex2 = pd.concat([df_ex, new_row], ignore_index=True)

                    if save_exercicios_to_github(df_ex2):
                        st.success("Exercício cadastrado ✅")
                        st.session_state.open_new_ex_modal = False
                        st.rerun()
                    else:
                        st.error("Falha ao salvar no GitHub.")

            with b:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.open_new_ex_modal = False
                    st.rerun()

        new_ex_modal()

    # ============================================================
    # Modal do dia (lista de exercícios do dia)
    # ============================================================
    if st.session_state.open_day_modal:

        @st.dialog(f"📅 {day} — Exercícios", width="large")
        def day_modal():
            nonlocal df_all

            dfu = df_all[df_all["user"].astype(str) == str(user)].copy()
            dfd = dfu[dfu["dia"].astype(str) == str(day)].copy()
            dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)
            dfd = dfd.sort_values("ordem", ascending=True)
            dfd_show = dfd[dfd["exercicio"].astype(str).str.strip() != ""].copy()

            st.caption("Use + para adicionar. Clique em editar para alterar. Agora abre na hora ✅")

            if st.button("➕ Adicionar exercício", use_container_width=True):
                _open_ex_modal("add", None)

            st.markdown("---")

            if dfd_show.empty:
                st.info("Ainda não tem exercícios neste dia. Clique em **Adicionar exercício**.")
            else:
                for _, r in dfd_show.iterrows():
                    ordem = int(r.get("ordem", 9999))
                    grupo = str(r.get("grupo", "") or "")
                    exercicio = str(r.get("exercicio", "") or "")
                    series = str(r.get("series_reps", "") or "")
                    gif_key = str(r.get("gif_key", "") or "")
                    alt_group = str(r.get("alt_group", "") or "")

                    thumb = _gif_url_for(df_ex, exercicio, gif_key)

                    cA, cB, cC = st.columns([1, 4, 2], vertical_alignment="center")

                    with cA:
                        if thumb:
                            st.image(thumb, width=70)
                        else:
                            st.caption("sem gif")

                    with cB:
                        st.markdown(f"**{ordem}. {exercicio}**")
                        meta = []
                        if grupo.strip() and grupo.lower() != "nan":
                            meta.append(grupo)
                        if series.strip() and series.lower() != "nan":
                            meta.append(f"Séries: {series}")
                        if alt_group.strip() and alt_group.lower() != "nan":
                            meta.append(f"alt: {alt_group}")
                        if meta:
                            st.caption(" · ".join(meta))

                    with cC:
                        if st.button("✏️ Editar", key=f"edit_{day}_{ordem}_{exercicio}", use_container_width=True):
                            _open_ex_modal("edit", {"day": day, "ordem": ordem, "exercicio": exercicio})

                        if st.button("🗑️ Remover", key=f"del_{day}_{ordem}_{exercicio}", use_container_width=True):
                            mask = (
                                (df_all["user"].astype(str) == str(user)) &
                                (df_all["dia"].astype(str) == str(day)) &
                                (pd.to_numeric(df_all["ordem"], errors="coerce").fillna(9999).astype(int) == ordem) &
                                (df_all["exercicio"].astype(str) == str(exercicio))
                            )
                            df_all2 = df_all[~mask].copy()
                            if save_treinos_to_github(df_all2):
                                st.success("Removido ✅")
                                st.rerun()
                            else:
                                st.error("Falha ao salvar no GitHub.")

                    st.divider()

            if st.button("Fechar", use_container_width=True):
                st.session_state.open_day_modal = False
                st.rerun()

        day_modal()

    # ============================================================
    # Modal: adicionar/editar exercício do dia
    # ============================================================
    if st.session_state.open_ex_modal:
        action = st.session_state.edit_action

        @st.dialog("🧩 Exercício — adicionar / editar", width="large")
        def ex_modal():
            nonlocal df_all

            # defaults do registro atual (se edit)
            default_ordem = 1
            default_exercicio = ""
            default_series = ""
            default_alt_group = ""

            if action == "edit" and st.session_state.edit_row_id:
                rid = st.session_state.edit_row_id
                ordem0 = int(rid["ordem"])
                ex0 = str(rid["exercicio"])
                mask = (
                    (df_all["user"].astype(str) == str(user)) &
                    (df_all["dia"].astype(str) == str(day)) &
                    (pd.to_numeric(df_all["ordem"], errors="coerce").fillna(9999).astype(int) == ordem0) &
                    (df_all["exercicio"].astype(str) == ex0)
                )
                row = df_all[mask]
                if not row.empty:
                    rr = row.iloc[0]
                    default_ordem = int(pd.to_numeric(rr.get("ordem", ordem0), errors="coerce") or ordem0)
                    default_exercicio = str(rr.get("exercicio", "") or "")
                    default_series = str(rr.get("series_reps", "") or "")
                    default_alt_group = str(rr.get("alt_group", "") or "")

            else:
                # add -> próxima ordem
                dfu = df_all[(df_all["user"].astype(str) == str(user)) & (df_all["dia"].astype(str) == str(day))].copy()
                dfu["ordem"] = pd.to_numeric(dfu["ordem"], errors="coerce").fillna(0).astype(int)
                default_ordem = int(dfu["ordem"].max()) + 1 if not dfu.empty else 1

            st.caption("Selecione um exercício cadastrado (com GIF + grupo automático).")

            # lista do catálogo
            df_ex_local = df_ex.copy()
            df_ex_local = df_ex_local[df_ex_local["exercicio"].astype(str).str.strip() != ""].copy()

            if df_ex_local.empty:
                st.warning("Seu Data/exercicios.csv está vazio. Cadastre exercícios primeiro.")
                if st.button("➕ Cadastrar novo exercício agora", use_container_width=True):
                    st.session_state.open_ex_modal = False
                    st.session_state.open_new_ex_modal = True
                    st.rerun()
                return

            # busca
            q = st.text_input("Buscar exercício (nome ou grupo)", value="")
            if q.strip():
                qq = q.strip().lower()
                df_ex_local = df_ex_local[
                    df_ex_local["exercicio"].astype(str).str.lower().str.contains(qq) |
                    df_ex_local["grupo"].astype(str).str.lower().str.contains(qq)
                ].copy()

            # opções (label = "Exercício — Grupo")
            opts = []
            map_label_to_name = {}
            for _, r in df_ex_local.iterrows():
                exn = str(r.get("exercicio", "") or "").strip()
                grp = str(r.get("grupo", "") or "").strip()
                if not exn:
                    continue
                label = f"{exn} — {grp}" if grp else exn
                opts.append(label)
                map_label_to_name[label] = exn

            opts = sorted(list(dict.fromkeys(opts)))

            # pré-seleção
            pre_label = None
            if default_exercicio:
                for lb, exn in map_label_to_name.items():
                    if exn == default_exercicio:
                        pre_label = lb
                        break
            if pre_label is None and opts:
                pre_label = opts[0]

            c1, c2 = st.columns([2, 1])
            with c1:
                ordem = st.number_input("Ordem", min_value=1, step=1, value=int(default_ordem))
                picked = st.selectbox("Exercício", options=opts, index=opts.index(pre_label) if pre_label in opts else 0)
                chosen_ex = map_label_to_name.get(picked, "")
                # puxa do catálogo
                row_ex = df_ex[df_ex["exercicio"].astype(str) == str(chosen_ex)]
                grp = str(row_ex.iloc[0].get("grupo", "") or "") if not row_ex.empty else ""
                gif_key = str(row_ex.iloc[0].get("gif_key", "") or "") if not row_ex.empty else ""
                gif_url = str(row_ex.iloc[0].get("gif_url", "") or "") if not row_ex.empty else ""
                if not gif_url:
                    gif_url = _gif_url_for(df_ex, chosen_ex, gif_key)

                st.text_input("Grupo (automático)", value=grp, disabled=True)

                series = st.text_input("Séries x Reps", value=default_series if default_series and default_series.lower() != "nan" else "")
                alt_group = st.text_input("alt_group (opcional)", value=default_alt_group if default_alt_group and default_alt_group.lower() != "nan" else "")

            with c2:
                if gif_url:
                    st.image(gif_url, width=160)
                else:
                    st.info("Sem GIF (cadastre o gif_url no Exercícios)")

                st.caption("Dica: Se quiser cadastrar um novo exercício, volte e use o botão **Cadastrar novo exercício**.")

            st.markdown("---")
            a, b = st.columns(2)

            with a:
                if st.button("💾 Salvar", use_container_width=True):
                    if not chosen_ex.strip():
                        st.error("Selecione um exercício.")
                        return

                    # remove antigo (se edit)
                    df_all2 = df_all.copy()
                    if action == "edit" and st.session_state.edit_row_id:
                        rid = st.session_state.edit_row_id
                        ordem0 = int(rid["ordem"])
                        ex0 = str(rid["exercicio"])
                        mask_old = (
                            (df_all2["user"].astype(str) == str(user)) &
                            (df_all2["dia"].astype(str) == str(day)) &
                            (pd.to_numeric(df_all2["ordem"], errors="coerce").fillna(9999).astype(int) == ordem0) &
                            (df_all2["exercicio"].astype(str) == ex0)
                        )
                        df_all2 = df_all2[~mask_old].copy()

                    new_row = pd.DataFrame([{
                        "user": user,
                        "dia": day,
                        "ordem": int(ordem),
                        "grupo": (grp or "").strip(),
                        "exercicio": chosen_ex.strip(),
                        "series_reps": (series or "").strip(),
                        "gif_key": (gif_key or "").strip(),
                        "alt_group": (alt_group or "").strip(),
                    }], columns=TREINOS_COLUMNS)

                    df_all2 = pd.concat([df_all2, new_row], ignore_index=True)

                    if save_treinos_to_github(df_all2):
                        st.success("Salvo ✅")
                        st.session_state.open_ex_modal = False
                        st.session_state.edit_action = None
                        st.session_state.edit_row_id = None
                        st.session_state.open_day_modal = True  # volta pro modal do dia já aberto
                        st.rerun()
                    else:
                        st.error("Falha ao salvar no GitHub.")

            with b:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.open_ex_modal = False
                    st.session_state.edit_action = None
                    st.session_state.edit_row_id = None
                    st.session_state.open_day_modal = True
                    st.rerun()

        ex_modal()

    st.markdown("---")
    st.caption("Agora os GIFs vêm do Data/exercicios.csv (coluna gif_url). Você cadastra colando a URL ✅")


# ============================================================
# 7) Router principal
# ============================================================
def main():
    init_state()

    screens = {
        "login": screen_login,
        "menu": screen_menu,
        "treino": screen_treino,
        "historico": screen_historico,
        "graficos": screen_graficos,
        "editar_treino": screen_editar_treino,
    }

    screens.get(st.session_state.screen, screen_login)()


if __name__ == "__main__":
    main()
