# app.py — Planner de Treinos (GitHub CSV: treinos + exercicios + log)
import streamlit as st
import pandas as pd
from datetime import datetime
import base64
import json
import requests
import io
import time

st.set_page_config(page_title="Planner de Treinos", layout="wide")

# ============================================================
# 0) Helpers de navegação + dia de hoje
# ============================================================
EDIT_DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]


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


def init_state():
    if "screen" not in st.session_state:
        st.session_state.screen = "login"
    if "user" not in st.session_state:
        st.session_state.user = None
    if "day_selected" not in st.session_state:
        st.session_state.day_selected = today_pt()

    # edição (modais)
    if "edit_day" not in st.session_state:
        st.session_state.edit_day = today_pt() if today_pt() in EDIT_DAYS else "Segunda"
    if "open_day_modal" not in st.session_state:
        st.session_state.open_day_modal = False
    if "open_ex_modal" not in st.session_state:
        st.session_state.open_ex_modal = False
    if "edit_action" not in st.session_state:
        st.session_state.edit_action = None
    if "edit_row_id" not in st.session_state:
        st.session_state.edit_row_id = None

    # gerenciar exercícios (modal)
    if "open_exercise_modal" not in st.session_state:
        st.session_state.open_exercise_modal = False
    if "ex_action" not in st.session_state:
        st.session_state.ex_action = None
    if "ex_edit_name" not in st.session_state:
        st.session_state.ex_edit_name = ""


def _now_utc_z():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ============================================================
# 1) GitHub helpers (read/write)
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


def _clean_nans(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df
    df = df.copy()
    df = df.replace("nan", "").replace("NaN", "").fillna("")
    return df


# ============================================================
# 2) LOG (Data/treino_log.csv) — persistência (auto-save)
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
    df = _clean_nans(df)

    df["peso_kg"] = pd.to_numeric(df["peso_kg"], errors="coerce").fillna(0.0)
    df["feito"] = pd.to_numeric(df["feito"], errors="coerce").fillna(0).astype(int)
    for c in ["timestamp", "user", "dia", "grupo", "exercicio", "series_reps"]:
        df[c] = df[c].astype(str)
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
    df_all = _clean_nans(df_all)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_LOG_PATH, csv_txt, f"append treino log {_now_utc_z()}")
    if ok:
        load_history_from_github.clear()
    return ok


def _autolog_debounced(user: str, day: str, group: str, exercise_name: str, reps_done: str, weight: float, done: bool):
    """
    Auto-salva no treino_log.csv com debounce (evita spammar commits no GitHub).
    """
    k = f"__last_autosave__{user}__{day}"
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
# 3) Treinos em CSV (Data/treinos.csv)
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
    df = _clean_nans(df)

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
    df_all = _clean_nans(df_all)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_TREINOS_PATH, csv_txt, f"update treinos {_now_utc_z()}")
    if ok:
        load_treinos_from_github.clear()
    return ok


def _ensure_days_for_user(df_all: pd.DataFrame, user: str) -> pd.DataFrame:
    """Garante que existam registros (mesmo vazios) para Seg–Sex no treinos.csv daquele user."""
    df_all = df_all.copy()
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

    return _clean_nans(df_all)


# ============================================================
# 3B) Exercícios em CSV (Data/exercicios.csv)  <<< GIF URL AQUI
# ============================================================
GITHUB_EXERCICIOS_PATH = "Data/exercicios.csv"
EX_COLUMNS = ["exercicio", "grupo", "gif_key", "gif_url", "alt_group", "observacoes"]


@st.cache_data(ttl=60)
def load_exercicios_from_github() -> pd.DataFrame:
    txt, _ = gh_read_file(GITHUB_EXERCICIOS_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=EX_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=EX_COLUMNS)

    for col in EX_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[EX_COLUMNS].copy()
    df = _clean_nans(df)
    for c in EX_COLUMNS:
        df[c] = df[c].astype(str)
    return df


def save_exercicios_to_github(df_all: pd.DataFrame) -> bool:
    for col in EX_COLUMNS:
        if col not in df_all.columns:
            df_all[col] = ""

    df_all = df_all[EX_COLUMNS].copy()
    df_all = _clean_nans(df_all)
    for c in EX_COLUMNS:
        df_all[c] = df_all[c].astype(str)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_EXERCICIOS_PATH, csv_txt, f"update exercicios {_now_utc_z()}")
    if ok:
        load_exercicios_from_github.clear()
    return ok


def _thumb_from_url(url: str) -> str:
    return (url or "").strip()


def _exercise_lookup(df_ex: pd.DataFrame) -> dict:
    """
    index por nome (lower) => row dict
    """
    m = {}
    if df_ex is None or df_ex.empty:
        return m
    for _, r in df_ex.iterrows():
        name = str(r.get("exercicio", "") or "").strip()
        if not name:
            continue
        m[name.lower()] = {
            "exercicio": name,
            "grupo": str(r.get("grupo", "") or "").strip(),
            "gif_key": str(r.get("gif_key", "") or "").strip(),
            "gif_url": str(r.get("gif_url", "") or "").strip(),
            "alt_group": str(r.get("alt_group", "") or "").strip(),
            "observacoes": str(r.get("observacoes", "") or "").strip(),
        }
    return m


def _workouts_from_treinos_csv(df_treinos: pd.DataFrame, df_ex: pd.DataFrame, user: str) -> dict:
    """
    Converte treinos.csv do user em dict:
    { "Segunda": [ {grupo, exercicio, series_reps, gif_url}, ... ], ... }
    - grupo/gif_url podem vir do exercicios.csv se estiverem vazios no treinos.csv.
    """
    workouts = {d: [] for d in EDIT_DAYS}
    dfu = df_treinos[df_treinos["user"].astype(str) == str(user)].copy()
    if dfu.empty:
        return workouts

    ex_map = _exercise_lookup(df_ex)

    for d in EDIT_DAYS:
        dfd = dfu[dfu["dia"].astype(str) == str(d)].copy()
        dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)
        dfd = dfd.sort_values("ordem", ascending=True)

        dfd = dfd[dfd["exercicio"].astype(str).str.strip() != ""].copy()
        rows = []
        for _, r in dfd.iterrows():
            ex_name = str(r.get("exercicio", "") or "").strip()
            planned = str(r.get("series_reps", "") or "").strip()
            grupo = str(r.get("grupo", "") or "").strip()
            gif_url = ""
            alt_group = str(r.get("alt_group", "") or "").strip()

            ref = ex_map.get(ex_name.lower())
            if ref:
                if not grupo:
                    grupo = ref.get("grupo", "") or ""
                gif_url = ref.get("gif_url", "") or ""
                if not alt_group:
                    alt_group = ref.get("alt_group", "") or ""

            rows.append({
                "grupo": grupo,
                "exercicio": ex_name,
                "series_reps": planned,
                "gif_url": gif_url,
                "alt_group": alt_group,
            })
        workouts[d] = rows

    return workouts


# ============================================================
# 6) Histórico: último peso (por usuário/dia/exercicio)
# ============================================================
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


# ============================================================
# 7) TELAS
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
        if st.button("🧩 Gerenciar exercícios", use_container_width=True):
            goto("gerenciar_exercicios")
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

    # se teve que criar dias faltando, salva uma vez
    dfu_days = set(df_treinos[df_treinos["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        save_treinos_to_github(df_treinos)

    WORKOUTS = _workouts_from_treinos_csv(df_treinos, df_ex, user)

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

    exercises = WORKOUTS.get(day, [])
    st.subheader(f"{day} — Exercícios")

    if not exercises:
        st.info("Esse dia ainda não tem exercícios. Vá em **Alterar treino** para adicionar.")
        return

    done_flags = []

    for idx, ex in enumerate(exercises):
        group = str(ex.get("grupo", "") or "").strip()
        name = str(ex.get("exercicio", "") or "").strip()
        planned_reps = str(ex.get("series_reps", "") or "").strip()
        gif_url = str(ex.get("gif_url", "") or "").strip()

        reps_done_key = f"{user}_{day}_{idx}_reps_done"
        weight_key = f"{user}_{day}_{idx}_peso"
        done_key = f"{user}_{day}_{idx}_feito"

        if reps_done_key not in st.session_state:
            st.session_state[reps_done_key] = planned_reps

        if weight_key not in st.session_state:
            st.session_state[weight_key] = last_weight(df_history, user, day, name)

        if done_key not in st.session_state:
            st.session_state[done_key] = False

        def _on_any_change(idx_local=idx, group_local=group, ex_name=name, planned_local=planned_reps):
            reps_done_val = st.session_state.get(f"{user}_{day}_{idx_local}_reps_done", planned_local)
            weight_val = st.session_state.get(f"{user}_{day}_{idx_local}_peso", 0.0)
            done_val = st.session_state.get(f"{user}_{day}_{idx_local}_feito", False)

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
        if group:
            st.caption(group)

        cols = st.columns([2, 1])
        with cols[0]:
            if gif_url:
                st.image(gif_url, width=260)
            else:
                st.info("Sem GIF disponível (cadastre no Gerenciar exercícios).")

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
            for i in range(len(exercises)):
                st.session_state[f"{user}_{day}_{i}_reps_done"] = exercises[i].get("series_reps", "")
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
# Tela: Editar treino (cards de dias + modais)
#   - Escolhe exercício a partir do Data/exercicios.csv
#   - Grupo e GIF ficam padrão do cadastro (mas você pode sobrescrever)
# ============================================================
def screen_editar_treino():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title("✏️ Editar treino")
    top1, top2 = st.columns([1, 1])
    with top1:
        if st.button("⬅️ Voltar", use_container_width=True):
            goto("menu")
    with top2:
        if st.button("🔁 Trocar usuário", use_container_width=True):
            st.session_state.user = None
            goto("login")

    st.markdown("---")

    df_all = load_treinos_from_github()
    df_all = _ensure_days_for_user(df_all, user)

    dfu_days = set(df_all[df_all["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        save_treinos_to_github(df_all)

    df_ex = load_exercicios_from_github()
    ex_map = _exercise_lookup(df_ex)
    ex_names = sorted([v["exercicio"] for v in ex_map.values()])

    st.subheader("Escolha um dia para editar")
    cols = st.columns(5)
    for i, d in enumerate(EDIT_DAYS):
        with cols[i]:
            if st.button(d, use_container_width=True, key=f"btn_day_{d}"):
                st.session_state.edit_day = d
                st.session_state.open_day_modal = True
                st.rerun()

    if st.session_state.edit_day not in EDIT_DAYS:
        st.session_state.edit_day = "Segunda"
    day = st.session_state.edit_day

    # =========
    # Modal do dia
    # =========
    if st.session_state.open_day_modal:

        @st.dialog(f"📅 {day} — Exercícios", width="large")
        def day_modal():
            nonlocal df_all

            dfu = df_all[df_all["user"].astype(str) == str(user)].copy()
            dfd = dfu[dfu["dia"].astype(str) == str(day)].copy()
            dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)
            dfd = dfd.sort_values("ordem", ascending=True)

            dfd_show = dfd[dfd["exercicio"].astype(str).str.strip() != ""].copy()
            st.caption("Clique em um exercício para editar. Use + para adicionar novos.")

            if st.button("➕ Adicionar exercício", use_container_width=True):
                st.session_state.edit_action = "add"
                st.session_state.edit_row_id = None
                st.session_state.open_day_modal = False
                st.session_state.open_ex_modal = True
                st.rerun()

            st.markdown("---")

            if dfd_show.empty:
                st.info("Ainda não tem exercícios neste dia. Clique em **Adicionar exercício**.")
            else:
                for _, r in dfd_show.iterrows():
                    ordem = int(r.get("ordem", 9999))
                    exercicio = str(r.get("exercicio", "") or "").strip()
                    series = str(r.get("series_reps", "") or "").strip()
                    grupo = str(r.get("grupo", "") or "").strip()
                    alt_group = str(r.get("alt_group", "") or "").strip()

                    # preview via exercicios.csv
                    ref = ex_map.get(exercicio.lower())
                    gif_url = ref.get("gif_url", "") if ref else ""
                    grupo_show = grupo if grupo else (ref.get("grupo", "") if ref else "")

                    cA, cB, cC = st.columns([1, 4, 2], vertical_alignment="center")
                    with cA:
                        if gif_url:
                            st.image(gif_url, width=70)
                        else:
                            st.caption("sem gif")

                    with cB:
                        st.markdown(f"**{ordem}. {exercicio}**")
                        meta = []
                        if grupo_show:
                            meta.append(grupo_show)
                        if series:
                            meta.append(f"Séries: {series}")
                        if alt_group:
                            meta.append(f"alt_group: `{alt_group}`")
                        if meta:
                            st.caption(" · ".join(meta))

                    with cC:
                        if st.button("✏️ Editar", key=f"edit_{day}_{ordem}_{exercicio}", use_container_width=True):
                            st.session_state.edit_action = "edit"
                            st.session_state.edit_row_id = {"day": day, "ordem": ordem, "exercicio": exercicio}
                            st.session_state.open_day_modal = False
                            st.session_state.open_ex_modal = True
                            st.rerun()

                        if st.button("🗑️ Remover", key=f"del_{day}_{ordem}_{exercicio}", use_container_width=True):
                            mask = (
                                (df_all["user"].astype(str) == str(user)) &
                                (df_all["dia"].astype(str) == str(day)) &
                                (pd.to_numeric(df_all["ordem"], errors="coerce").fillna(9999).astype(int) == ordem) &
                                (df_all["exercicio"].astype(str) == str(exercicio))
                            )
                            df_all = df_all[~mask].copy()
                            if save_treinos_to_github(df_all):
                                st.success("Removido ✅")
                                st.rerun()
                            else:
                                st.error("Falha ao salvar no GitHub.")
                    st.divider()

            if st.button("Fechar", use_container_width=True):
                st.session_state.open_day_modal = False
                st.rerun()

        day_modal()

    # =========
    # Modal: adicionar/editar exercício do dia
    # =========
    if st.session_state.open_ex_modal:
        action = st.session_state.edit_action

        @st.dialog("🧩 Exercício do dia — adicionar/editar", width="large")
        def ex_modal():
            nonlocal df_all

            dfu = df_all[df_all["user"].astype(str) == str(user)].copy()
            dfd = dfu[dfu["dia"].astype(str) == str(day)].copy()
            dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)

            default_ordem = int(dfd["ordem"].max()) + 1 if not dfd.empty else 1
            default_ex = ""
            default_series = ""
            default_grupo_override = ""
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
                    default_ex = str(rr.get("exercicio", "") or "")
                    default_series = str(rr.get("series_reps", "") or "")
                    default_grupo_override = str(rr.get("grupo", "") or "")
                    default_alt_group = str(rr.get("alt_group", "") or "")

            st.caption("Escolha um exercício cadastrado. Grupo e GIF vêm do cadastro (você pode sobrescrever o grupo se quiser).")

            c1, c2 = st.columns(2)

            with c1:
                ordem = st.number_input("Ordem", min_value=1, step=1, value=int(default_ordem))

                # Select do exercício (biblioteca)
                options = ["(selecionar...)"] + ex_names
                idx = 0
                if default_ex and default_ex in ex_names:
                    idx = options.index(default_ex)
                selected_ex = st.selectbox("Exercício (biblioteca)", options=options, index=idx)

                # fallback manual se não tiver cadastrado
                manual = False
                if selected_ex == "(selecionar...)":
                    manual = True

                if manual:
                    exercicio = st.text_input("Nome do exercício (manual)", value=default_ex)
                else:
                    exercicio = selected_ex

                series = st.text_input("Séries x Reps", value=default_series)

            with c2:
                ref = ex_map.get(str(exercicio).strip().lower())
                grupo_padrao = ref.get("grupo", "") if ref else ""
                gif_url = ref.get("gif_url", "") if ref else ""
                alt_group_padrao = ref.get("alt_group", "") if ref else ""

                grupo_override = st.text_input("Grupo (opcional — se vazio usa o padrão)", value=default_grupo_override)
                alt_group = st.text_input("alt_group (opcional)", value=(default_alt_group or alt_group_padrao))

                if gif_url:
                    st.image(gif_url, width=180)
                else:
                    st.info("Sem preview (cadastre o GIF em Gerenciar exercícios).")

                if grupo_override.strip():
                    st.caption(f"Grupo exibido: **{grupo_override.strip()}**")
                elif grupo_padrao.strip():
                    st.caption(f"Grupo exibido: **{grupo_padrao.strip()}**")
                else:
                    st.caption("Grupo exibido: (vazio)")

            st.markdown("---")
            a, b = st.columns(2)

            with a:
                if st.button("💾 Salvar", use_container_width=True):
                    if not str(exercicio or "").strip():
                        st.error("Escolha ou preencha o exercício.")
                        return

                    # remove antigo se edit
                    if action == "edit" and st.session_state.edit_row_id:
                        rid = st.session_state.edit_row_id
                        ordem0 = int(rid["ordem"])
                        ex0 = str(rid["exercicio"])
                        mask_old = (
                            (df_all["user"].astype(str) == str(user)) &
                            (df_all["dia"].astype(str) == str(day)) &
                            (pd.to_numeric(df_all["ordem"], errors="coerce").fillna(9999).astype(int) == ordem0) &
                            (df_all["exercicio"].astype(str) == ex0)
                        )
                        df_all = df_all[~mask_old].copy()

                    # grupo: override > cadastro > vazio
                    ref2 = ex_map.get(str(exercicio).strip().lower())
                    grupo_final = (grupo_override or "").strip()
                    if not grupo_final:
                        grupo_final = (ref2.get("grupo", "") if ref2 else "").strip()

                    new_row = pd.DataFrame([{
                        "user": user,
                        "dia": day,
                        "ordem": int(ordem),
                        "grupo": grupo_final,
                        "exercicio": str(exercicio).strip(),
                        "series_reps": str(series or "").strip(),
                        "gif_key": (ref2.get("gif_key", "") if ref2 else ""),
                        "alt_group": str(alt_group or "").strip(),
                    }], columns=TREINOS_COLUMNS)

                    df_all = pd.concat([df_all, new_row], ignore_index=True)

                    if save_treinos_to_github(df_all):
                        st.success("Salvo ✅")
                        st.session_state.open_ex_modal = False
                        st.session_state.edit_action = None
                        st.session_state.edit_row_id = None
                        st.rerun()
                    else:
                        st.error("Falha ao salvar no GitHub.")

            with b:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.open_ex_modal = False
                    st.session_state.edit_action = None
                    st.session_state.edit_row_id = None
                    st.rerun()

        ex_modal()

    st.markdown("---")
    st.caption("Dica: cadastre todos os exercícios + GIFs em **Gerenciar exercícios**. Depois editar treino fica bem rápido.")


# ============================================================
# Tela: Gerenciar exercícios (listar/editar/excluir)
# ============================================================
def screen_gerenciar_exercicios():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title("🧩 Gerenciar exercícios")
    top1, top2 = st.columns([1, 1])
    with top1:
        if st.button("⬅️ Voltar", use_container_width=True):
            goto("menu")
    with top2:
        if st.button("🔁 Trocar usuário", use_container_width=True):
            st.session_state.user = None
            goto("login")

    st.markdown("---")

    df_ex = load_exercicios_from_github()
    df_ex = _clean_nans(df_ex)

    # filtros
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        q = st.text_input("Buscar (nome do exercício)", value="", placeholder="Ex: Supino, Remada, Abdutora…")
    with c2:
        grupos = sorted([g for g in df_ex["grupo"].astype(str).unique().tolist() if str(g).strip() != ""])
        grupo_sel = st.selectbox("Filtrar por grupo", options=["(todos)"] + grupos)
    with c3:
        if st.button("➕ Novo", use_container_width=True):
            st.session_state.ex_action = "add"
            st.session_state.ex_edit_name = ""
            st.session_state.open_exercise_modal = True
            st.rerun()

    df_show = df_ex.copy()
    if q.strip():
        df_show = df_show[df_show["exercicio"].astype(str).str.contains(q.strip(), case=False, na=False)]
    if grupo_sel != "(todos)":
        df_show = df_show[df_show["grupo"].astype(str) == str(grupo_sel)]

    df_show = df_show.sort_values(["grupo", "exercicio"], ascending=True)

    st.caption(f"Total: {len(df_show)} exercício(s)")

    if df_show.empty:
        st.info("Nenhum exercício encontrado.")
    else:
        for _, r in df_show.iterrows():
            ex_name = str(r.get("exercicio", "") or "").strip()
            grupo = str(r.get("grupo", "") or "").strip()
            gif_key = str(r.get("gif_key", "") or "").strip()
            gif_url = str(r.get("gif_url", "") or "").strip()
            alt_group = str(r.get("alt_group", "") or "").strip()
            obs = str(r.get("observacoes", "") or "").strip()

            thumb = _thumb_from_url(gif_url)

            cA, cB, cC = st.columns([1, 4, 2], vertical_alignment="center")
            with cA:
                if thumb:
                    st.image(thumb, width=70)
                else:
                    st.caption("sem gif")

            with cB:
                st.markdown(f"**{ex_name}**")
                meta = []
                if grupo:
                    meta.append(grupo)
                if gif_key:
                    meta.append(f"gif_key: `{gif_key}`")
                if alt_group:
                    meta.append(f"alt_group: `{alt_group}`")
                if meta:
                    st.caption(" · ".join(meta))
                if obs:
                    st.caption(f"📝 {obs}")

            with cC:
                if st.button("✏️ Editar", key=f"ex_edit_{ex_name}", use_container_width=True):
                    st.session_state.ex_action = "edit"
                    st.session_state.ex_edit_name = ex_name
                    st.session_state.open_exercise_modal = True
                    st.rerun()

                if st.button("🗑️ Excluir", key=f"ex_del_{ex_name}", use_container_width=True):
                    df_new = df_ex[df_ex["exercicio"].astype(str) != ex_name].copy()
                    ok = save_exercicios_to_github(df_new)
                    if ok:
                        st.success("Excluído ✅")
                        st.rerun()
                    else:
                        st.error("Não consegui salvar no GitHub.")

            st.divider()

    # Modal add/edit
    if st.session_state.open_exercise_modal:
        action = st.session_state.ex_action
        edit_name = str(st.session_state.ex_edit_name or "").strip()

        @st.dialog("🧩 Exercício — adicionar/editar", width="large")
        def exercise_modal():
            nonlocal df_ex

            d_exercicio = ""
            d_grupo = ""
            d_gif_key = ""
            d_gif_url = ""
            d_alt_group = ""
            d_obs = ""

            if action == "edit" and edit_name:
                row = df_ex[df_ex["exercicio"].astype(str) == edit_name]
                if not row.empty:
                    rr = row.iloc[0]
                    d_exercicio = str(rr.get("exercicio", "") or "")
                    d_grupo = str(rr.get("grupo", "") or "")
                    d_gif_key = str(rr.get("gif_key", "") or "")
                    d_gif_url = str(rr.get("gif_url", "") or "")
                    d_alt_group = str(rr.get("alt_group", "") or "")
                    d_obs = str(rr.get("observacoes", "") or "")

            st.caption("Cole a URL do GIF para aparecer no treino e no editor.")

            c1, c2 = st.columns(2)
            with c1:
                exercicio = st.text_input("Nome do exercício", value=d_exercicio, placeholder="Ex: Supino inclinado com halteres")
                grupo = st.text_input("Grupo muscular", value=d_grupo, placeholder="Ex: Peito / Tríceps / Ombro…")
                alt_group = st.text_input("alt_group (opcional)", value=d_alt_group, placeholder="Use para agrupar variações")
                observacoes = st.text_area("Observações (opcional)", value=d_obs, height=90)

            with c2:
                gif_key = st.text_input("gif_key (opcional)", value=d_gif_key, placeholder="Ex: supino_inclinado_db")
                gif_url = st.text_input("gif_url (cole a URL do GIF)", value=d_gif_url, placeholder="https://...gif")
                thumb = _thumb_from_url(gif_url)
                if thumb:
                    st.image(thumb, width=200)
                else:
                    st.info("Sem preview (cole a URL do GIF).")

            st.markdown("---")
            a, b = st.columns(2)

            with a:
                if st.button("💾 Salvar", use_container_width=True):
                    if not (exercicio or "").strip():
                        st.error("Preencha o nome do exercício.")
                        return

                    exercicio_clean = exercicio.strip()

                    # se editando e mudou o nome, remove antigo
                    if action == "edit" and edit_name:
                        df_ex = df_ex[df_ex["exercicio"].astype(str) != edit_name].copy()

                    # evita duplicado por nome (case-insensitive)
                    existing = df_ex["exercicio"].astype(str).str.lower().tolist()
                    if exercicio_clean.lower() in existing:
                        st.error("Já existe um exercício com esse nome. Use outro nome ou edite o existente.")
                        return

                    new_row = pd.DataFrame([{
                        "exercicio": exercicio_clean,
                        "grupo": (grupo or "").strip(),
                        "gif_key": (gif_key or "").strip(),
                        "gif_url": (gif_url or "").strip(),
                        "alt_group": (alt_group or "").strip(),
                        "observacoes": (observacoes or "").strip(),
                    }], columns=EX_COLUMNS)

                    df_ex = pd.concat([df_ex, new_row], ignore_index=True)
                    df_ex = _clean_nans(df_ex)

                    ok = save_exercicios_to_github(df_ex)
                    if ok:
                        st.success("Salvo ✅")
                        st.session_state.open_exercise_modal = False
                        st.session_state.ex_action = None
                        st.session_state.ex_edit_name = ""
                        st.rerun()
                    else:
                        st.error("Falha ao salvar no GitHub.")

            with b:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.open_exercise_modal = False
                    st.session_state.ex_action = None
                    st.session_state.ex_edit_name = ""
                    st.rerun()

        exercise_modal()


# ============================================================
# 8) Router principal
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
        "gerenciar_exercicios": screen_gerenciar_exercicios,
    }

    screens.get(st.session_state.screen, screen_login)()


if __name__ == "__main__":
    main()
