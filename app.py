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
        st.session_state.edit_day = today_pt()
    if "open_day_modal" not in st.session_state:
        st.session_state.open_day_modal = False
    if "open_ex_modal" not in st.session_state:
        st.session_state.open_ex_modal = False
    if "edit_action" not in st.session_state:
        st.session_state.edit_action = None
    if "edit_row_id" not in st.session_state:
        st.session_state.edit_row_id = None


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
# 2) LOG (treino_log.csv) — persistência
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
# 4) GIFs (chaves) — usadas no treino + editor
# ============================================================
GIFS = {
    # glúteo
    "hip_thrust": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Hip-Thrust.gif",
    "hip_abduction": "https://fitnessprogramer.com/wp-content/uploads/2021/02/HiP-ABDUCTION-MACHINE.gif",
    "hip_adduction": "https://fitnessprogramer.com/wp-content/uploads/2021/02/HIP-ADDUCTION-MACHINE.gif",
    "cable_kickback": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cable-Hip-Extension.gif",
    # costas
    "lat_pulldown_open": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lat-Pulldown.gif",
    "straight_pulldown": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Cable-Straight-Arm-Pulldown.gif",
    "seated_row": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Seated-Cable-Row.gif",
    # pernas
    "leg_press": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Leg-Press.gif",
    "stiff": "https://fitnessprogramer.com/wp-content/uploads/2022/01/Stiff-Leg-Deadlift.gif",
    "squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/BARBELL-SQUAT.gif",
    "bulgaro": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Barbell-Bulgarian-Split-Squat.gif",
    "leg_extension": "https://fitnessprogramer.com/wp-content/uploads/2021/02/LEG-EXTENSION.gif",
    "leg_curl_lying": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Leg-Curl.gif",
    "leg_curl_seated": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Seated-Leg-Curl.gif",
    "calf_seated": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Lever-Seated-Calf-Raise.gif",
    # ombro
    "lateral_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Lateral-Raise.gif",
    "shoulder_press": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Shoulder-Press.gif",
    # abs
    "plank": "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "leg_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lying-Leg-Raise.gif",
    # bíceps
    "barbell_curl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Curl.gif",
    "alt_db_curl": "https://fitnessprogramer.com/wp-content/uploads/2022/06/Seated-dumbbell-alternating-curl.gif",
    # tríceps / peito
    "triceps_pushdown": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Pushdown.gif",
    "triceps_barbell_lying": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Triceps-Extension.gif",
    "pec_deck": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Pec-Deck-Fly.gif",
    # split squat
    "split_squat": "https://fitnessprogramer.com/wp-content/uploads/2022/12/ATG-Split-Squat.gif",
    "split_squat_db": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQMfPUcNXe8VtsptiC6de4ICwID4x17hXMcyQ&s",
    "split_squat_bb": "https://fitnessprogramer.com/wp-content/uploads/2022/04/Barbell-Split-Squat.gif",
    "split_squat_band": "https://fitnessprogramer.com/wp-content/uploads/2022/10/Banded-Split-Squat.gif",
}

# ============================================================
# 4.1) Biblioteca de exercícios (Grupo -> lista) para o editor
# - grupo vira padrão (automático)
# - escolha por dropdown com preview do GIF
# ============================================================
EXERCISE_LIBRARY = {
    "Peito": [
        {"name": "Crucifixo Máquina (Pec Deck)", "gif_key": "pec_deck"},
    ],
    "Costas": [
        {"name": "Puxada alta aberta", "gif_key": "lat_pulldown_open"},
        {"name": "Pulldown", "gif_key": "straight_pulldown"},
        {"name": "Remada baixa", "gif_key": "seated_row"},
    ],
    "Pernas": [
        {"name": "Agachamento Livre (Barbell Squat)", "gif_key": "squat"},
        {"name": "Leg Press 45°", "gif_key": "leg_press"},
        {"name": "Cadeira Extensora", "gif_key": "leg_extension"},
        {"name": "Mesa flexora", "gif_key": "leg_curl_lying"},
        {"name": "Cadeira flexora", "gif_key": "leg_curl_seated"},
        {"name": "Elevação de panturrilha sentado", "gif_key": "calf_seated"},
        {"name": "Cadeira Abdutora", "gif_key": "hip_abduction"},
        {"name": "Cadeira Adutora", "gif_key": "hip_adduction"},
    ],
    "Glúteo": [
        {"name": "Elevação pélvica (Hip Thrust)", "gif_key": "hip_thrust"},
        {"name": "Coice na polia", "gif_key": "cable_kickback"},
    ],
    "Ombro": [
        {"name": "Desenvolvimento com halteres", "gif_key": "shoulder_press"},
        {"name": "Elevação lateral com halteres", "gif_key": "lateral_raise"},
    ],
    "Bíceps": [
        {"name": "Rosca direta com barra", "gif_key": "barbell_curl"},
        {"name": "Rosca alternada com halteres", "gif_key": "alt_db_curl"},
    ],
    "Tríceps": [
        {"name": "Tríceps na Polia (Pushdown)", "gif_key": "triceps_pushdown"},
        {"name": "Tríceps Testa com Barra", "gif_key": "triceps_barbell_lying"},
    ],
    "Abs": [
        {"name": "Prancha", "gif_key": "plank"},
        {"name": "Abdominal infra (elevação de pernas)", "gif_key": "leg_raise"},
    ],
}

def find_exercise_in_library(ex_name: str):
    for grp, items in EXERCISE_LIBRARY.items():
        for it in items:
            if it["name"] == ex_name:
                return grp, it.get("gif_key", "")
    return "", ""


# ============================================================
# 5) Helpers extras para a tela de edição (UI)
# ============================================================
EDIT_DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]


def _thumb_from_gifkey(gif_key: str) -> str:
    gif_key = (gif_key or "").strip()
    return GIFS.get(gif_key, "")


def _ensure_days_for_user(df_all: pd.DataFrame, user: str) -> pd.DataFrame:
    """Garante que existam registros (mesmo vazios) para Seg–Sex no CSV daquele user."""
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


def _workouts_from_treinos_csv(df_treinos: pd.DataFrame, user: str) -> dict:
    """
    Converte o treinos.csv do user em WORKOUTS dict:
    { "Segunda": [(grupo, exercicio, series_reps, gif_url), ...], ... }
    """
    workouts = {}
    dfu = df_treinos[df_treinos["user"].astype(str) == str(user)].copy()
    if dfu.empty:
        return {d: [] for d in EDIT_DAYS}

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
            gif_key = str(r.get("gif_key", "") or "")
            gif_url = GIFS.get(gif_key, "")
            rows.append((grupo, ex, series, gif_url))
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
    df_treinos = _ensure_days_for_user(df_treinos, user)

    # se teve que criar dias faltando, salva uma vez
    dfu_days = set(df_treinos[df_treinos["user"].astype(str) == str(user)]["dia"].astype(str).unique().tolist())
    if dfu_days != set(EDIT_DAYS):
        save_treinos_to_github(df_treinos)

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
                group=group_local,
                exercise_name=ex_name,
                reps_done=str(reps_done_val or "").strip(),
                weight=float(weight_val or 0.0),
                done=bool(done_val),
            )

        st.markdown(f"### {name}")
        if group.strip():
            st.caption(group)

        cols = st.columns([2, 1])
        with cols[0]:
            if gif_url:
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
            dfh = load_history_from_github()
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
# Tela: editar treino (mais intuitiva + modais)
# - Corrige o bug de “só abre ao fechar”:
#   ao clicar Editar/Adicionar dentro do modal do dia, ele fecha o modal do dia,
#   seta open_ex_modal=True e dá rerun. Aí abre direto o modal do exercício.
# - Grupo vira padrão: escolhido pelo “Grupo” e “Exercício” da biblioteca
# - GIF aparece automático (gif_key) e com preview
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

    st.subheader("Escolha um dia para editar")
    cols = st.columns(5)
    for i, d in enumerate(EDIT_DAYS):
        with cols[i]:
            if st.button(d, use_container_width=True, key=f"btn_day_{d}"):
                st.session_state.edit_day = d
                st.session_state.open_day_modal = True
                st.session_state.open_ex_modal = False
                st.session_state.edit_action = None
                st.session_state.edit_row_id = None
                st.rerun()

    if st.session_state.edit_day not in EDIT_DAYS:
        st.session_state.edit_day = "Segunda"
    day = st.session_state.edit_day

    # ------------ Modal do dia ------------
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
                    grupo = str(r.get("grupo", "") or "")
                    exercicio = str(r.get("exercicio", "") or "")
                    series = str(r.get("series_reps", "") or "")
                    gif_key = str(r.get("gif_key", "") or "")
                    alt_group = str(r.get("alt_group", "") or "")

                    thumb = _thumb_from_gifkey(gif_key)

                    cA, cB, cC = st.columns([1, 4, 2], vertical_alignment="center")

                    with cA:
                        if thumb:
                            st.image(thumb, width=70)
                        else:
                            st.caption("sem gif")

                    with cB:
                        st.markdown(f"**{ordem}. {exercicio}**")
                        meta = []
                        if grupo.strip():
                            meta.append(grupo)
                        if series.strip():
                            meta.append(f"Séries: {series}")
                        if gif_key.strip():
                            meta.append(f"gif_key: `{gif_key}`")
                        if alt_group.strip() and alt_group.lower() != "nan":
                            meta.append(f"alt: `{alt_group}`")
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

    # ------------ Modal exercício (Add/Edit) ------------
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
            default_series = "3x10"

            # edit -> carrega
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
                    default_series = str(rr.get("series_reps", "") or default_series)

            # Descobre grupo/gif da biblioteca (se existir)
            grp0, gif0 = find_exercise_in_library(default_exercicio)
            if not grp0:
                # fallback: tenta usar o que está no CSV (se for edit)
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
                        grp0 = str(rr.get("grupo", "") or "")
                        gif0 = str(rr.get("gif_key", "") or "")

            st.caption("Selecione o **Grupo** e o **Exercício** (o grupo fica automático).")

            # Grupo
            groups = ["(selecione)"] + sorted(EXERCISE_LIBRARY.keys())
            grp_index = groups.index(grp0) if grp0 in groups else 0
            group_sel = st.selectbox("Grupo", options=groups, index=grp_index)

            # Exercício dentro do grupo
            ex_name = ""
            gif_key = ""
            if group_sel != "(selecione)":
                items = EXERCISE_LIBRARY[group_sel]
                names = [it["name"] for it in items]

                # tenta manter o exercício atual no dropdown
                ex_index = names.index(default_exercicio) if default_exercicio in names else 0
                ex_name = st.selectbox("Exercício", options=names, index=ex_index)

                gif_key = next((it["gif_key"] for it in items if it["name"] == ex_name), "")
                thumb = _thumb_from_gifkey(gif_key)
                if thumb:
                    st.image(thumb, width=180)
                else:
                    st.info("Sem preview (gif_key não encontrado no GIFS).")

            st.markdown("---")
            ordem = st.number_input("Ordem", min_value=1, step=1, value=int(default_ordem))
            series = st.text_input("Séries x Reps", value=str(default_series or "").strip())

            st.markdown("---")
            a, b = st.columns(2)

            with a:
                if st.button("💾 Salvar", use_container_width=True):
                    if group_sel == "(selecione)" or not ex_name:
                        st.error("Selecione um grupo e um exercício.")
                        st.stop()

                    # remove antigo se era edit
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
                        "grupo": str(group_sel).strip(),
                        "exercicio": str(ex_name).strip(),
                        "series_reps": str(series or "").strip(),
                        "gif_key": str(gif_key or "").strip(),
                        "alt_group": "",
                    }])

                    df_all = pd.concat([df_all, new_row], ignore_index=True)

                    if save_treinos_to_github(df_all):
                        st.success("Salvo ✅")
                        # volta pro modal do dia
                        st.session_state.open_ex_modal = False
                        st.session_state.open_day_modal = True
                        st.session_state.edit_action = None
                        st.session_state.edit_row_id = None
                        st.rerun()
                    else:
                        st.error("Falha ao salvar no GitHub.")

            with b:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.open_ex_modal = False
                    st.session_state.open_day_modal = True
                    st.session_state.edit_action = None
                    st.session_state.edit_row_id = None
                    st.rerun()

        ex_modal()

    st.markdown("---")
    st.caption("Dica: se quiser, eu adiciono busca por exercício + favoritos (fica MUITO rápido no celular).")


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
    }

    screens.get(st.session_state.screen, screen_login)()


if __name__ == "__main__":
    main()
