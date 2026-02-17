import streamlit as st
import pandas as pd
from datetime import datetime
import base64
import json
import requests
import io

st.set_page_config(page_title="Planner de Treinos", layout="wide")


# ============================================================
# 0) Helpers de navegação + dia de hoje
# ============================================================
def today_pt() -> str:
    # datetime.weekday(): Mon=0 ... Sun=6
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


# ============================================================
# 1) GitHub CSV (LOG) — persistência de verdade no Streamlit Cloud
# ============================================================
GITHUB_CSV_PATH = "Data/treino_log.csv"
CSV_COLUMNS = ["timestamp", "user", "dia", "grupo", "exercicio", "series_reps", "peso_kg", "feito"]


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


@st.cache_data(ttl=60)
def load_history_from_github() -> pd.DataFrame:
    txt, _ = gh_read_file(GITHUB_CSV_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=CSV_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=CSV_COLUMNS)

    # compatibilidade (se seu CSV ainda não tinha "user")
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col != "peso_kg" else 0.0

    df = df[CSV_COLUMNS].copy()
    df["peso_kg"] = pd.to_numeric(df["peso_kg"], errors="coerce").fillna(0.0)
    df["feito"] = pd.to_numeric(df["feito"], errors="coerce").fillna(0).astype(int)
    df["timestamp"] = df["timestamp"].astype(str)
    df["user"] = df["user"].astype(str)
    return df


def append_history_to_github(df_new: pd.DataFrame) -> bool:
    df_old = load_history_from_github()

    for col in CSV_COLUMNS:
        if col not in df_new.columns:
            df_new[col] = "" if col != "peso_kg" else 0.0
        if col not in df_old.columns:
            df_old[col] = "" if col != "peso_kg" else 0.0

    df_old = df_old[CSV_COLUMNS].copy()
    df_new = df_new[CSV_COLUMNS].copy()

    df_old["peso_kg"] = pd.to_numeric(df_old["peso_kg"], errors="coerce").fillna(0.0)
    df_new["peso_kg"] = pd.to_numeric(df_new["peso_kg"], errors="coerce").fillna(0.0)

    df_old["feito"] = pd.to_numeric(df_old["feito"], errors="coerce").fillna(0).astype(int)
    df_new["feito"] = pd.to_numeric(df_new["feito"], errors="coerce").fillna(0).astype(int)

    df_all = pd.concat([df_old, df_new], ignore_index=True)
    csv_txt = df_all.to_csv(index=False, encoding="utf-8")

    ok = gh_write_file(
        GITHUB_CSV_PATH,
        csv_txt,
        f"append treino log {datetime.utcnow().isoformat(timespec='seconds')}Z",
    )
    if ok:
        load_history_from_github.clear()
    return ok


# ============================================================
# 2) GIFs (keys limpas)
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

    # stand-by
    "front_raise_db": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Front-Raise.gif",
    "front_raise_db_two": "https://fitnessprogramer.com/wp-content/uploads/2021/08/Two-Arm-Dumbbell-Front-Raise.gif",
    "front_raise_cable_two": "https://fitnessprogramer.com/wp-content/uploads/2021/08/Two-Arm-Cable-Front-Raise.gif",
}


# ============================================================
# 3) Treinos (CSV no GitHub) — "duas abas" por user
# ============================================================
TREINOS_CSV_PATH = "Data/treinos.csv"
TREINOS_COLUMNS = ["user", "dia", "ordem", "grupo", "exercicio", "series_reps", "gif_key", "alt_group"]


@st.cache_data(ttl=60)
def load_treinos_from_github() -> pd.DataFrame:
    txt, _ = gh_read_file(TREINOS_CSV_PATH)
    if not (txt or "").strip():
        return pd.DataFrame(columns=TREINOS_COLUMNS)

    try:
        df = pd.read_csv(io.StringIO(txt))
    except Exception:
        return pd.DataFrame(columns=TREINOS_COLUMNS)

    df.columns = [str(c).strip() for c in df.columns]

    for c in TREINOS_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    df["ordem"] = pd.to_numeric(df["ordem"], errors="coerce").fillna(9999).astype(int)
    df = df[TREINOS_COLUMNS].fillna("")
    return df


def get_available_days_for_user(user: str) -> list[str]:
    df = load_treinos_from_github()
    dfu = df[df["user"].astype(str) == str(user)]
    days = sorted(dfu["dia"].astype(str).unique().tolist())
    return days


def get_workouts_for_day(user: str, day: str):
    """
    Retorna lista no formato:
      [(grupo, exercicio, series_reps, gif_url_default, alt_group), ...]
    """
    df = load_treinos_from_github()
    dfu = df[df["user"].astype(str) == str(user)]
    dfd = dfu[dfu["dia"].astype(str) == str(day)].sort_values("ordem")

    out = []
    for _, r in dfd.iterrows():
        group = str(r["grupo"])
        name = str(r["exercicio"])
        reps = str(r["series_reps"])
        gif_key = str(r["gif_key"]).strip()
        alt_group = str(r["alt_group"]).strip()

        gif_url = GIFS.get(gif_key, "")
        out.append((group, name, reps, gif_url, alt_group))
    return out


# ============================================================
# 4) Alternativas (variações)
# ============================================================
ALT_EXERCISES = {
    "Mesa flexora": [
        ("Mesa flexora", GIFS["leg_curl_lying"]),
        ("Cadeira flexora", GIFS["leg_curl_seated"]),
    ],
    "Afundo (Split Squat)": [
        ("Afundo (Split Squat)", GIFS["split_squat"]),
        ("Afundo com Halteres (Dumbbell Split Squat)", GIFS["split_squat_db"]),
        ("Afundo com Barra (Barbell Split Squat)", GIFS["split_squat_bb"]),
        ("Afundo com Elástico (Banded Split Squat)", GIFS["split_squat_band"]),
    ],
    "Elevação frontal c/ halter (Dumbbell Front Raise)": [
        ("Elevação frontal c/ halter (Dumbbell Front Raise)", GIFS["front_raise_db"]),
        ("Elevação frontal c/ halteres (Two Arm Dumbbell Front Raise)", GIFS["front_raise_db_two"]),
        ("Elevação frontal na Polia (Arm Cable Front Raise)", GIFS["front_raise_cable_two"]),
    ],
}


# ============================================================
# 5) Funções de apoio: último peso / última variação (por usuário)
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


def last_alt_choice(df_history: pd.DataFrame, user: str, day: str, labels: list[str]) -> str:
    if df_history is None or df_history.empty:
        return labels[0]
    df = df_history.copy()
    df = df[df["user"].astype(str) == str(user)]
    df = df[df["dia"].astype(str) == str(day)]
    df = df[df["exercicio"].isin(labels)]
    if df.empty:
        return labels[0]
    df = df.sort_values("timestamp", ascending=True)
    return str(df.iloc[-1]["exercicio"])


# ============================================================
# 6) TELAS
# ============================================================
def screen_login():
    st.title("Planner de Treinos")
    st.caption("Escolha o usuário (sem senha).")

    c1, c2 = st.columns(2)

    # BOTÃO com nome "Teca..." -> user interno = "Amor 🤍"
    with c1:
        if st.button("Teca Ernesto 🤍 (Futura Novais)", use_container_width=True):
            st.session_state.user = "Amor 🤍"
            st.session_state.day_selected = today_pt()
            goto("menu")

    # BOTÃO com nome "Tico..." -> user interno = "Felipe 💪"
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
        if st.button("✏️ Alterar treino (em breve)", use_container_width=True):
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

    # histórico (GitHub)
    df_history = load_history_from_github()

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

    # dias disponíveis do CSV (por usuário)
    available_days = get_available_days_for_user(user)
    if not available_days:
        st.error("Nenhum treino encontrado no Data/treinos.csv para este usuário.")
        st.info("Verifique se o CSV tem a coluna 'user' e valores 'Amor 🤍' / 'Felipe 💪'.")
        return

    default_day = st.session_state.get("day_selected", today_pt())
    if default_day not in available_days:
        default_day = available_days[0]

    idx_default = available_days.index(default_day)
    day = st.selectbox("Dia do treino", options=available_days, index=idx_default, key="day_picker")
    st.session_state.day_selected = day

    exercises = get_workouts_for_day(user, day)
    st.subheader(f"{day} — Exercícios")

    done_flags = []

    for idx, (group, name, reps, gif_url_default, alt_group) in enumerate(exercises):
        alt_group = (alt_group or "").strip()
        alt_options = ALT_EXERCISES.get(alt_group, None) if alt_group else None

        alt_key = f"{user}_{day}_{idx}_alt"
        weight_key = f"{user}_{day}_{idx}_peso"
        done_key = f"{user}_{day}_{idx}_feito"

        # variação
        if alt_options:
            labels = [opt[0] for opt in alt_options]
            if alt_key not in st.session_state:
                st.session_state[alt_key] = last_alt_choice(df_history, user, day, labels)

            selected_label = st.session_state[alt_key]
            selected_gif = gif_url_default
            for lbl, gif_alt in alt_options:
                if lbl == selected_label:
                    selected_gif = gif_alt
                    break
        else:
            selected_label = name
            selected_gif = gif_url_default

        # init peso / feito
        if weight_key not in st.session_state:
            st.session_state[weight_key] = last_weight(df_history, user, day, selected_label)
        if done_key not in st.session_state:
            st.session_state[done_key] = False

        st.markdown(f"### {name}")
        st.caption(group)

        cols = st.columns([2, 1])
        with cols[0]:
            if selected_gif:
                st.image(selected_gif, width=260)
            else:
                st.info("Sem GIF disponível")

        with cols[1]:
            st.write(f"● Séries x Reps: **{reps}**")
            if alt_options:
                st.selectbox("Variação", options=[o[0] for o in alt_options], key=alt_key)
                selected_label = st.session_state.get(alt_key, selected_label)

            st.number_input("Peso (kg)", min_value=0.0, step=0.5, key=weight_key)
            st.checkbox("Feito?", key=done_key)

        done_flags.append(bool(st.session_state[done_key]))
        st.markdown("---")

    # Comemoração
    if done_flags:
        celebrate_key = f"{user}_{day}_celebrated"
        all_done = all(done_flags)
        if all_done and not st.session_state.get(celebrate_key, False):
            st.balloons()
            if user == "Amor 🤍":
                st.success("🎉 Parabéns, amor 🤍\nMais um dia de treino feito!")
            else:
                st.success("🎉 Treino completo! 💪")
            st.session_state[celebrate_key] = True
        elif not all_done:
            st.session_state[celebrate_key] = False

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("💾 Salvar treino", use_container_width=True):
            rows = []
            for idx, (group, name, reps, gif_url_default, alt_group) in enumerate(exercises):
                alt_group = (alt_group or "").strip()
                alt_options = ALT_EXERCISES.get(alt_group, None) if alt_group else None

                log_name = st.session_state.get(f"{user}_{day}_{idx}_alt", name) if alt_options else name

                rows.append({
                    "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "user": user,
                    "dia": day,
                    "grupo": group,
                    "exercicio": log_name,
                    "series_reps": reps,
                    "peso_kg": float(st.session_state.get(f"{user}_{day}_{idx}_peso", 0.0)),
                    "feito": int(bool(st.session_state.get(f"{user}_{day}_{idx}_feito", False))),
                })

            df_new = pd.DataFrame(rows, columns=CSV_COLUMNS)
            ok = append_history_to_github(df_new)
            if ok:
                st.success("Treino salvo no GitHub ✅ (não some ao reiniciar)")
            else:
                st.error("Não consegui salvar no GitHub. Veja o erro acima.")

    with c2:
        if st.button("🧹 Limpar (só tela)", use_container_width=True):
            for idx, _ in enumerate(exercises):
                st.session_state[f"{user}_{day}_{idx}_peso"] = 0.0
                st.session_state[f"{user}_{day}_{idx}_feito"] = False
            st.info("Campos zerados (histórico no GitHub continua).")

    with c3:
        if st.button("📄 Ver histórico (últimas 50)", use_container_width=True):
            dfh = load_history_from_github()
            dfh = dfh[dfh["user"].astype(str) == str(user)]
            dfh = dfh.sort_values("timestamp", ascending=False).head(50)
            st.dataframe(dfh, use_container_width=True, height=260)


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
        st.info("Sem dados ainda. Salve alguns treinos para ver gráficos.")
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

    st.caption("Se quiser, eu coloco gráficos (linha do peso, volume total, recordes, etc.).")
    st.dataframe(dfh.tail(200), use_container_width=True, height=520)


def screen_editar_treino():
    user = st.session_state.user
    if not user:
        goto("login")

    st.title("Alterar treino (próximo passo)")
    if st.button("⬅️ Voltar", use_container_width=True):
        goto("menu")

    st.info(
        "Agora que os treinos estão no Data/treinos.csv, o próximo passo é criar uma tela "
        "para editar e salvar o CSV direto pelo app (sem abrir o GitHub)."
    )


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
