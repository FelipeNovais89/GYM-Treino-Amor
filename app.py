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

    # estado da edição
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

    # cache-busters (REFRESH IMEDIATO após salvar no GitHub)
    if "treinos_version" not in st.session_state:
        st.session_state.treinos_version = 0
    if "history_version" not in st.session_state:
        st.session_state.history_version = 0
    if "exercicios_version" not in st.session_state:
        st.session_state.exercicios_version = 0


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

def _now_utc_z():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ============================================================
# 2) LOG (Data/treino_log.csv) — persistência + refresh imediato
# ============================================================
GITHUB_LOG_PATH = "Data/treino_log.csv"
LOG_COLUMNS = ["timestamp", "user", "dia", "grupo", "exercicio", "series_reps", "peso_kg", "feito"]

@st.cache_data(ttl=3600)
def load_history_from_github(version: int = 0) -> pd.DataFrame:
    _ = int(version or 0)  # bust cache
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
    df_old = load_history_from_github(st.session_state.history_version)

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
        st.session_state.history_version = int(st.session_state.get("history_version", 0)) + 1
    return ok

def _autolog_debounced(user: str, day: str, group: str, exercise_name: str, reps_done: str, weight: float, done: bool):
    """
    Auto-salva no treino_log.csv com debounce (evita spammar commits no GitHub).
    """
    k = f"__last_autosave__{user}__{day}"
    now = time.time()
    last = float(st.session_state.get(k, 0.0) or 0.0)
    if now - last < 1.2:  # ajuste se quiser
        return
    st.session_state[k] = now

    df_new = pd.DataFrame([{
        "timestamp": _now_utc_z(),
        "user": user,
        "dia": day,
        "grupo": group,
        "exercicio": exercise_name,
        "series_reps": str(reps_done or "").strip(),
        "peso_kg": float(weight or 0.0),
        "feito": int(bool(done)),
    }], columns=LOG_COLUMNS)
    append_history_to_github(df_new)


# ============================================================
# 3) Exercícios em CSV (Data/exercicios.csv) — com GIF URL
# ============================================================
GITHUB_EXERCICIOS_PATH = "Data/exercicios.csv"
GITHUB_EXERCICIOS_PATH_ALT = "Data/exercícios.csv"  # caso você tenha criado com acento

EX_COLUMNS = ["exercicio", "grupo", "gif_url", "alt_group", "observacoes"]

@st.cache_data(ttl=3600)
def load_exercicios_from_github(version: int = 0) -> pd.DataFrame:
    _ = int(version or 0)

    txt, _ = gh_read_file(GITHUB_EXERCICIOS_PATH)
    if not (txt or "").strip():
        # tenta o arquivo com acento, se existir
        txt2, _ = gh_read_file(GITHUB_EXERCICIOS_PATH_ALT)
        txt = txt2

    if not (txt or "").strip():
        return pd.DataFrame(columns=EX_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=EX_COLUMNS)

    # compat: se ainda estiver no formato antigo com gif_key
    if "gif_url" not in df.columns and "gif_key" in df.columns:
        # mantém coluna gif_url vazia; você pode migrar colando URLs
        df["gif_url"] = ""

    for col in EX_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[EX_COLUMNS].copy()
    for c in EX_COLUMNS:
        df[c] = df[c].astype(str)

    # limpa "nan"
    df = df.replace("nan", "", regex=False)

    # remove duplicados por nome (mantém o último)
    df["__idx__"] = range(len(df))
    df = df.sort_values("__idx__", ascending=True)
    df = df.drop(columns=["__idx__"])
    df = df.drop_duplicates(subset=["exercicio"], keep="last")

    df = df.sort_values("exercicio", ascending=True)
    return df.reset_index(drop=True)

def save_exercicios_to_github(df_all: pd.DataFrame) -> bool:
    for col in EX_COLUMNS:
        if col not in df_all.columns:
            df_all[col] = ""
    df_all = df_all[EX_COLUMNS].copy()

    # normaliza "nan"
    df_all = df_all.replace("nan", "", regex=False)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_EXERCICIOS_PATH, csv_txt, f"update exercicios {_now_utc_z()}")
    if ok:
        load_exercicios_from_github.clear()
        st.session_state.exercicios_version = int(st.session_state.get("exercicios_version", 0)) + 1
    return ok

def ex_lookup(df_ex: pd.DataFrame) -> dict:
    """
    Retorna dict: nome -> {grupo, gif_url, alt_group, obs}
    """
    m = {}
    if df_ex is None or df_ex.empty:
        return m
    for _, r in df_ex.iterrows():
        nm = str(r.get("exercicio", "")).strip()
        if not nm:
            continue
        m[nm] = {
            "grupo": str(r.get("grupo", "") or "").strip(),
            "gif_url": str(r.get("gif_url", "") or "").strip(),
            "alt_group": str(r.get("alt_group", "") or "").strip(),
            "observacoes": str(r.get("observacoes", "") or "").strip(),
        }
    return m


# ============================================================
# 4) Treinos em CSV (Data/treinos.csv) — refresh imediato
# ============================================================
GITHUB_TREINOS_PATH = "Data/treinos.csv"
TREINOS_COLUMNS = ["user", "dia", "ordem", "grupo", "exercicio", "series_reps", "gif_url", "alt_group"]

@st.cache_data(ttl=3600)
def load_treinos_from_github(version: int = 0) -> pd.DataFrame:
    _ = int(version or 0)
    txt, _ = gh_read_file(GITHUB_TREINOS_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=TREINOS_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=TREINOS_COLUMNS)

    # compat: se ainda estiver com gif_key
    if "gif_url" not in df.columns and "gif_key" in df.columns:
        df["gif_url"] = ""

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
    df["gif_url"] = df["gif_url"].astype(str)
    df["alt_group"] = df["alt_group"].astype(str)

    # limpa "nan"
    df = df.replace("nan", "", regex=False)
    return df

def save_treinos_to_github(df_all: pd.DataFrame) -> bool:
    for col in TREINOS_COLUMNS:
        if col not in df_all.columns:
            df_all[col] = ""

    df_all = df_all[TREINOS_COLUMNS].copy()
    df_all["ordem"] = pd.to_numeric(df_all["ordem"], errors="coerce").fillna(9999).astype(int)
    df_all = df_all.replace("nan", "", regex=False)

    csv_txt = df_all.to_csv(index=False, encoding="utf-8")
    ok = gh_write_file(GITHUB_TREINOS_PATH, csv_txt, f"update treinos {_now_utc_z()}")
    if ok:
        load_treinos_from_github.clear()
        st.session_state.treinos_version = int(st.session_state.get("treinos_version", 0)) + 1
    return ok


# ============================================================
# 5) Helpers (UI)
# ============================================================
def _ensure_days_for_user(df_all: pd.DataFrame, user: str) -> pd.DataFrame:
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
                "gif_url": "",
                "alt_group": "",
            })

    if rows:
        df_all = pd.concat([df_all, pd.DataFrame(rows)], ignore_index=True)
    return df_all

def _workouts_from_treinos_csv(df_treinos: pd.DataFrame, user: str) -> dict:
    workouts = {d: [] for d in EDIT_DAYS}
    dfu = df_treinos[df_treinos["user"].astype(str) == str(user)].copy()
    if dfu.empty:
        return workouts

    for d in EDIT_DAYS:
        dfd = dfu[dfu["dia"].astype(str) == str(d)].copy()
        dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)
        dfd = dfd.sort_values("ordem", ascending=True)
        dfd = dfd[dfd["exercicio"].astype(str).str.strip() != ""].copy()

        rows = []
        for _, r in dfd.iterrows():
            grupo = str(r.get("grupo", "") or "")
            ex = str(r.get("exercicio", "") or "")
            series = str(r.get("series_reps", "") or "")
            gif_url = str(r.get("gif_url", "") or "")
            rows.append((grupo, ex, series, gif_url))
        workouts[d] = rows
    return workouts

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

    colA, colB, colC = st.columns(3)
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

    with colC:
        if st.button("🧩 Gerenciar exercícios", use_container_width=True):
            goto("gerenciar_exercicios")

    st.markdown("---")
    if st.button("🚪 Trocar usuário", use_container_width=True):
        st.session_state.user = None
        goto("login")

def screen_treino():
    user = st.session_state.user
    if not user:
        goto("login")

    df_history = load_history_from_github(st.session_state.history_version)

    df_treinos = load_treinos_from_github(st.session_state.treinos_version)
    df_treinos = _ensure_days_for_user(df_treinos, user)

    # se teve que criar dias faltando, salva 1x (e já refresha)
    dfu_days = set(df_treinos[df_treinos["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        if save_treinos_to_github(df_treinos):
            st.rerun()

    WORKOUTS = _workouts_from_treinos_csv(df_treinos, user)

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

    for idx, (group, name, planned_reps, gif_url) in enumerate(exercises):
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
                group=str(group_local or "").strip(),
                exercise_name=str(ex_name or "").strip(),
                reps_done=str(reps_done_val or "").strip(),
                weight=float(weight_val or 0.0),
                done=bool(done_val),
            )

        st.markdown(f"### {name}")
        if str(group).strip():
            st.caption(group)

        cols = st.columns([2, 1])
        with cols[0]:
            if str(gif_url).strip():
                st.image(gif_url, width=260)
            else:
                st.info("Sem GIF disponível")

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
            dfh = load_history_from_github(st.session_state.history_version)
            dfh = dfh[dfh["user"].astype(str) == str(user)]
            dfh = dfh.sort_values("timestamp", ascending=False).head(50)
            st.dataframe(dfh, use_container_width=True, height=280)
    with c2:
        if st.button("🧹 Limpar (só tela)", use_container_width=True):
            for i, _ in enumerate(exercises):
                st.session_state[f"{user}_{day}_{i}_reps_done"] = exercises[i][2]
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

    dfh = load_history_from_github(st.session_state.history_version)
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

    dfh = load_history_from_github(st.session_state.history_version)
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
# Tela: Gerenciar Exercícios (listar/editar/excluir + cadastrar)
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

    df_ex = load_exercicios_from_github(st.session_state.exercicios_version)
    if df_ex.empty:
        st.info("Ainda não existe Data/exercicios.csv (ou está vazio). Você pode cadastrar agora.")

    # filtro/busca
    q = st.text_input("Buscar exercício", value="", placeholder="Ex: Supino, Remada, Stiff...")
    view = df_ex.copy()
    if q.strip():
        mask = (
            view["exercicio"].str.contains(q, case=False, na=False) |
            view["grupo"].str.contains(q, case=False, na=False)
        )
        view = view[mask].copy()

    st.subheader("Lista")
    st.dataframe(view, use_container_width=True, height=260)

    st.markdown("---")
    cA, cB = st.columns(2)

    with cA:
        st.subheader("➕ Cadastrar / Atualizar")
        st.caption("Se você cadastrar com o mesmo nome, ele substitui (atualiza) o existente.")

        ex_name = st.text_input("Nome do exercício", value="")
        ex_group = st.text_input("Grupo muscular", value="")
        ex_gif = st.text_input("GIF URL", value="", placeholder="Cole a URL direta do .gif (ou imagem)")
        ex_alt = st.text_input("alt_group (opcional)", value="", placeholder="Ex: Afundo (Split Squat)")
        ex_obs = st.text_area("Observações (opcional)", value="", height=90)

        if st.button("💾 Salvar exercício", use_container_width=True):
            if not ex_name.strip():
                st.error("Preencha o nome do exercício.")
            else:
                new_row = pd.DataFrame([{
                    "exercicio": ex_name.strip(),
                    "grupo": ex_group.strip(),
                    "gif_url": ex_gif.strip(),
                    "alt_group": ex_alt.strip(),
                    "observacoes": ex_obs.strip(),
                }], columns=EX_COLUMNS)

                # remove antigo com mesmo nome (update)
                df2 = df_ex.copy()
                df2["exercicio"] = df2["exercicio"].astype(str)
                df2 = df2[df2["exercicio"].astype(str) != ex_name.strip()].copy()

                df2 = pd.concat([df2, new_row], ignore_index=True)
                if save_exercicios_to_github(df2):
                    st.success("Salvo ✅ (atualizando a tela...)")
                    st.rerun()

    with cB:
        st.subheader("✏️ Editar / 🗑️ Excluir")
        names = ["(selecione)"] + (df_ex["exercicio"].dropna().astype(str).tolist() if not df_ex.empty else [])
        sel = st.selectbox("Escolha um exercício", options=names)

        if sel != "(selecione)":
            row = df_ex[df_ex["exercicio"].astype(str) == str(sel)]
            r0 = row.iloc[0] if not row.empty else None

            e_group = st.text_input("Grupo", value=(str(r0.get("grupo", "")) if r0 is not None else ""))
            e_gif = st.text_input("GIF URL", value=(str(r0.get("gif_url", "")) if r0 is not None else ""))
            e_alt = st.text_input("alt_group", value=(str(r0.get("alt_group", "")) if r0 is not None else ""))
            e_obs = st.text_area("Observações", value=(str(r0.get("observacoes", "")) if r0 is not None else ""), height=120)

            if str(e_gif).strip():
                st.image(e_gif, width=220)

            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 Atualizar", use_container_width=True):
                    df2 = df_ex.copy()
                    df2 = df2[df2["exercicio"].astype(str) != str(sel)].copy()
                    df2 = pd.concat([df2, pd.DataFrame([{
                        "exercicio": str(sel),
                        "grupo": str(e_group).strip(),
                        "gif_url": str(e_gif).strip(),
                        "alt_group": str(e_alt).strip(),
                        "observacoes": str(e_obs).strip(),
                    }])], ignore_index=True)

                    if save_exercicios_to_github(df2):
                        st.success("Atualizado ✅ (atualizando a tela...)")
                        st.rerun()

            with b2:
                if st.button("🗑️ Excluir", use_container_width=True):
                    df2 = df_ex.copy()
                    df2 = df2[df2["exercicio"].astype(str) != str(sel)].copy()
                    if save_exercicios_to_github(df2):
                        st.success("Excluído ✅ (atualizando a tela...)")
                        st.rerun()


# ============================================================
# Tela: editar treino (mais intuitiva + modais) — refresh imediato
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
        if st.button("🧩 Gerenciar exercícios", use_container_width=True):
            goto("gerenciar_exercicios")

    st.markdown("---")

    df_ex = load_exercicios_from_github(st.session_state.exercicios_version)
    EXMAP = ex_lookup(df_ex)
    EXNAMES = sorted(EXMAP.keys())

    df_all = load_treinos_from_github(st.session_state.treinos_version)
    df_all = _ensure_days_for_user(df_all, user)

    # se teve que criar dias faltando, salva 1x e já refresha
    dfu_days = set(df_all[df_all["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        if save_treinos_to_github(df_all):
            st.rerun()

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
                st.session_state.open_ex_modal = True
                st.rerun()

            st.markdown("---")

            if dfd_show.empty:
                st.info("Ainda não tem exercícios neste dia. Clique em **Adicionar exercício**.")
            else:
                for _, r in dfd_show.iterrows():
                    ordem = int(r.get("ordem", 9999))
                    grupo = str(r.get("grupo", "") or "")
                    exercicio = str(r.get("exercicio", "") or "")
                    series = str(r.get("series_reps", "") or "")
                    gif_url = str(r.get("gif_url", "") or "")
                    alt_group = str(r.get("alt_group", "") or "")

                    cA, cB, cC = st.columns([1, 4, 2], vertical_alignment="center")

                    with cA:
                        if gif_url.strip():
                            st.image(gif_url, width=70)
                        else:
                            st.caption("sem gif")

                    with cB:
                        st.markdown(f"**{ordem}. {exercicio}**")
                        meta = []
                        if grupo.strip():
                            meta.append(grupo)
                        if series.strip():
                            meta.append(f"Séries: {series}")
                        if alt_group.strip():
                            meta.append(f"alt: `{alt_group}`")
                        if meta:
                            st.caption(" · ".join(meta))

                    with cC:
                        if st.button("✏️ Editar", key=f"edit_{day}_{ordem}_{exercicio}", use_container_width=True):
                            st.session_state.edit_action = "edit"
                            st.session_state.edit_row_id = {"day": day, "ordem": ordem, "exercicio": exercicio}
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
                                st.success("Removido ✅ (atualizando...)")
                                st.session_state.open_day_modal = True
                                st.rerun()
                            else:
                                st.error("Falha ao salvar no GitHub.")

                    st.divider()

            if st.button("Fechar", use_container_width=True):
                st.session_state.open_day_modal = False
                st.rerun()

        day_modal()

    # =========
    # Modal de edição/criação (COM LISTA de exercícios cadastrados)
    # =========
    if st.session_state.open_ex_modal:
        action = st.session_state.edit_action

        @st.dialog("🧩 Exercício — editar / adicionar", width="large")
        def ex_modal():
            nonlocal df_all

            dfu = df_all[df_all["user"].astype(str) == str(user)].copy()
            dfd = dfu[dfu["dia"].astype(str) == str(day)].copy()
            dfd["ordem"] = pd.to_numeric(dfd["ordem"], errors="coerce").fillna(9999).astype(int)

            default_ordem = int(dfd["ordem"].max()) + 1 if not dfd.empty else 1
            default_exercicio = ""
            default_series = ""
            default_alt_group = ""
            default_grupo = ""
            default_gif_url = ""

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
                    default_grupo = str(rr.get("grupo", "") or "")
                    default_exercicio = str(rr.get("exercicio", "") or "")
                    default_series = str(rr.get("series_reps", "") or "")
                    default_gif_url = str(rr.get("gif_url", "") or "")
                    default_alt_group = str(rr.get("alt_group", "") or "")

            st.caption("Dica: escolha um exercício da lista (com GIF) e o grupo/URL já vem preenchido.")

            c1, c2 = st.columns([1, 1])
            with c1:
                ordem = st.number_input("Ordem", min_value=1, step=1, value=int(default_ordem))

                # dropdown de exercícios cadastrados
                if EXNAMES:
                    # se tiver um default_exercicio que não está no csv, adiciona opção temporária
                    options = EXNAMES.copy()
                    if default_exercicio.strip() and default_exercicio.strip() not in options:
                        options = [default_exercicio.strip()] + options
                    sel_ex = st.selectbox("Exercício (cadastro)", options=options, index=(options.index(default_exercicio.strip()) if default_exercicio.strip() in options else 0))
                else:
                    sel_ex = st.text_input("Exercício (sem cadastro ainda)", value=default_exercicio)

                # permite sobrescrever manualmente também
                exercicio = st.text_input("Nome do exercício (pode editar)", value=str(sel_ex).strip())

                series = st.text_input("Séries x Reps", value=default_series)

            with c2:
                # auto-preenche a partir do cadastro
                grp_auto = EXMAP.get(exercicio.strip(), {}).get("grupo", "") if EXMAP else ""
                gif_auto = EXMAP.get(exercicio.strip(), {}).get("gif_url", "") if EXMAP else ""
                alt_auto = EXMAP.get(exercicio.strip(), {}).get("alt_group", "") if EXMAP else ""

                grupo = st.text_input("Grupo", value=(default_grupo if default_grupo.strip() else grp_auto))
                gif_url = st.text_input("GIF URL", value=(default_gif_url if default_gif_url.strip() else gif_auto))
                alt_group = st.text_input("alt_group (opcional)", value=(default_alt_group if default_alt_group.strip() else alt_auto))

                if str(gif_url).strip():
                    st.image(gif_url, width=160)
                else:
                    st.info("Sem preview (GIF URL vazio).")

            st.markdown("---")
            a, b, c = st.columns(3)

            with a:
                if st.button("💾 Salvar", use_container_width=True):
                    if not str(exercicio).strip():
                        st.error("Preencha o nome do exercício.")
                        return

                    # se era edit, remove o antigo
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

                    new_row = pd.DataFrame([{
                        "user": user,
                        "dia": day,
                        "ordem": int(ordem),
                        "grupo": str(grupo).strip(),
                        "exercicio": str(exercicio).strip(),
                        "series_reps": str(series).strip(),
                        "gif_url": str(gif_url).strip(),
                        "alt_group": str(alt_group).strip(),
                    }], columns=TREINOS_COLUMNS)

                    df_all = pd.concat([df_all, new_row], ignore_index=True)

                    if save_treinos_to_github(df_all):
                        st.success("Salvo ✅ (atualizando...)")
                        st.session_state.open_ex_modal = False
                        st.session_state.edit_action = None
                        st.session_state.edit_row_id = None
                        st.session_state.open_day_modal = True
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

            with c:
                if st.button("🧩 Ir para Gerenciar exercícios", use_container_width=True):
                    st.session_state.open_ex_modal = False
                    st.session_state.open_day_modal = False
                    goto("gerenciar_exercicios")

        ex_modal()

    st.markdown("---")
    st.caption("Agora, ao salvar/editar/remover, o app dá refresh imediato (cache-buster + rerun).")


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
        "gerenciar_exercicios": screen_gerenciar_exercicios,
    }

    screens.get(st.session_state.screen, screen_login)()

if __name__ == "__main__":
    main()
