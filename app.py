import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Planner de Treinos", layout="wide")

# ---------- GIFs ----------
GIFS = {
    "hip_thrust": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Hip-Thrust.gif",
    "abdutora": "https://fitnessprogramer.com/wp-content/uploads/2021/02/HiP-ABDUCTION-MACHINE.gif",

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

    # ombro
    "lateral_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Lateral-Raise.gif",
    "shoulder_press": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Shoulder-Press.gif",

    # abs
    "plank": "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "leg_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lying-Leg-Raise.gif",

    # glúteo
    "cable_kickback": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cable-Hip-Extension.gif",

    # bíceps
    "barbell_curl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Curl.gif",
    "alt_db_curl": "https://fitnessprogramer.com/wp-content/uploads/2022/06/Seated-dumbbell-alternating-curl.gif",

    # tríceps (mantidos)
    "triceps_bar": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cable-Triceps-Pushdown.gif",  # (stand by)
    "triceps_rope": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Rope-Triceps-Pushdown.gif",  # (stand by)

    # NOVOS: pushdown + testa + pec deck
    "triceps_pushdown": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Pushdown.gif",
    "triceps_barbell_lying": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Triceps-Extension.gif",
    "pec_deck": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Pec-Deck-Fly.gif",

    # panturrilha
    "seated_calf": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Lever-Seated-Calf-Raise.gif",
    "standing_calf": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Standing-Calf-Raise.gif",

    # Afundo / Split Squat e variações
    "split_squat": "https://fitnessprogramer.com/wp-content/uploads/2022/12/ATG-Split-Squat.gif",
    "split_squat_db": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQMfPUcNXe8VtsptiC6de4ICwID4x17hXMcyQ&s",
    "split_squat_bb": "https://fitnessprogramer.com/wp-content/uploads/2022/04/Barbell-Split-Squat.gif",
    "split_squat_band": "https://fitnessprogramer.com/wp-content/uploads/2022/10/Banded-Split-Squat.gif",

    # Elevação frontal (mantida no código / stand by)
    "front_raise_db": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Front-Raise.gif",
    "front_raise_db_two": "https://fitnessprogramer.com/wp-content/uploads/2021/08/Two-Arm-Dumbbell-Front-Raise.gif",
    "front_raise_cable_two": "https://fitnessprogramer.com/wp-content/uploads/2021/08/Two-Arm-Cable-Front-Raise.gif",
}

# ---------- Treino por dia ----------
WORKOUTS = {
    "Segunda": [
        ("Glúteo e Posterior", "Cadeira abdutora", "4x15", GIFS["abdutora"]),
        ("Glúteo e Posterior", "Elevação pélvica (Hip Thrust)", "4x12", GIFS["hip_thrust"]),
        ("Glúteo e Posterior", "Coice e abdução na polia", "3x10", GIFS["cable_kickback"]),
        ("Glúteo e Posterior", "Búlgaro", "3x12", GIFS["bulgaro"]),
        ("Glúteo e Posterior", "Agachamento livre", "3x12", GIFS["squat"]),
        ("Glúteo e Posterior", "Stiff unilateral", "4x12", GIFS["stiff"]),
        ("Glúteo e Posterior", "Mesa flexora", "4x12", GIFS["leg_curl_lying"]),
    ],
    "Terça": [
        ("Costas / Bíceps / ABS / Panturrilha", "Puxada alta aberta", "3x12", GIFS["lat_pulldown_open"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Pulldown", "3x12", GIFS["straight_pulldown"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Remada baixa", "4x12", GIFS["seated_row"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Rosca direta com barra", "3x12", GIFS["barbell_curl"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Rosca alternada com halteres", "3x12", GIFS["alt_db_curl"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Prancha", "3x30–45s", GIFS["plank"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Abdominal infra (elevação de pernas)", "4x20", GIFS["leg_raise"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Elevação de panturrilha sentado", "3x15–20", GIFS["seated_calf"]),
    ],
    "Quarta": [
        ("Quadríceps e Glúteo", "Cadeira extensora", "5x15", GIFS["leg_extension"]),
        ("Quadríceps e Glúteo", "Agachamento livre", "4x12", GIFS["squat"]),
        ("Quadríceps e Glúteo", "Búlgaro", "3x12", GIFS["bulgaro"]),
        ("Quadríceps e Glúteo", "Afundo (Split Squat)", "3x12", GIFS["split_squat"]),
        ("Quadríceps e Glúteo", "Leg press", "3x12", GIFS["leg_press"]),
        ("Quadríceps e Glúteo", "Cadeira abdutora", "4x12", GIFS["abdutora"]),
        ("Quadríceps e Glúteo", "Coice na polia", "3x12", GIFS["cable_kickback"]),
    ],
    "Quinta": [
        ("Peito / Ombro / Tríceps / ABS / Panturrilha", "Crucifixo Máquina (Pec Deck Fly)", "3x12", GIFS["pec_deck"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Desenvolvimento com halteres", "3x12", GIFS["shoulder_press"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação lateral com halteres", "3x12", GIFS["lateral_raise"]),

        # Elevação frontal (stand by) NÃO entra no treino agora

        ("Ombro / Tríceps / ABS / Panturrilha", "Tríceps na Polia (Triceps Pushdown)", "3x12", GIFS["triceps_pushdown"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Tríceps Testa com Barra (Lying Barbell Triceps Extension)", "3x12", GIFS["triceps_barbell_lying"]),

        ("Ombro / Tríceps / ABS / Panturrilha", "Prancha", "3x30–45s", GIFS["plank"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Abdominal infra (elevação de pernas)", "4x20", GIFS["leg_raise"]),
    ],
    "Sexta": [
    ("Glúteo", "Elevação pélvica (Hip Thrust)", "4x12", GIFS["hip_thrust"]),
    ("Glúteo", "Cadeira abdutora", "4x15", GIFS["abdutora"]),
    ("Glúteo", "Coice na polia", "3x12", GIFS["cable_kickback"]),
    ("Glúteo", "Agachamento sumô", "4x12", GIFS["squat"]),
    ("Glúteo", "Búlgaro", "3x12", GIFS["bulgaro"]),
    ("Glúteo", "Stiff", "4x12", GIFS["stiff"]),
    ],
}

# ---------- Variações ----------
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
    # Stand by (não está no treino, mas fica pronto):
    "Elevação frontal c/ halter (Dumbbell Front Raise)": [
        ("Elevação frontal c/ halter (Dumbbell Front Raise)", GIFS["front_raise_db"]),
        ("Elevação frontal c/ halteres (Two Arm Dumbbell Front Raise)", GIFS["front_raise_db_two"]),
        ("Elevação frontal na Polia (Arm Cable Front Raise)", GIFS["front_raise_cable_two"]),
    ],
}

LOG_FILE = "treino_log.csv"

# Histórico para recuperar último peso / variação
if os.path.exists(LOG_FILE):
    try:
        df_history = pd.read_csv(LOG_FILE)
    except Exception:
        df_history = None
else:
    df_history = None

st.sidebar.title("Planner de Treinos")
day = st.sidebar.selectbox("Selecione o dia", ["Selecione..."] + list(WORKOUTS.keys()))
st.title("Planner de Treinos com GIFs")

if day == "Selecione...":
    st.write("👈 Selecione um dia da semana")
else:
    exercises = WORKOUTS[day]
    st.subheader(f"Treino de {day}")

    done_flags = []

    for idx, (group, name, reps, gif_url_default) in enumerate(exercises):
        alt_key = f"{day}_{idx}_alt"
        alt_options = ALT_EXERCISES.get(name, None)

        # Seleção de variação
        if alt_options:
            labels = [opt[0] for opt in alt_options]

            if alt_key not in st.session_state:
                selected_label = labels[0]
                if df_history is not None:
                    df_filt = df_history[
                        (df_history["dia"] == day) &
                        (df_history["exercicio"].isin(labels))
                    ]
                    if not df_filt.empty:
                        df_filt = df_filt.sort_values("timestamp")
                        selected_label = df_filt.iloc[-1]["exercicio"]
                st.session_state[alt_key] = selected_label

            selected_label = st.session_state[alt_key]

            selected_gif = gif_url_default
            for lbl, gif_alt in alt_options:
                if lbl == selected_label:
                    selected_gif = gif_alt
                    break
        else:
            selected_label = name
            selected_gif = gif_url_default

        st.markdown(f"### {name}")
        st.caption(group)

        cols = st.columns([2, 1])

        with cols[0]:
            if selected_gif:
                st.image(selected_gif, width=260)
            else:
                st.info("Sem GIF disponível")

        weight_key = f"{day}_{idx}_peso"
        done_key = f"{day}_{idx}_feito"

        # Inicializa peso com histórico
        if weight_key not in st.session_state:
            init_weight = 0.0
            if df_history is not None:
                if alt_options:
                    df_filt = df_history[(df_history["dia"] == day) & (df_history["exercicio"] == selected_label)]
                else:
                    df_filt = df_history[(df_history["dia"] == day) & (df_history["exercicio"] == name)]

                if not df_filt.empty:
                    df_filt = df_filt.sort_values("timestamp")
                    init_weight = float(df_filt.iloc[-1]["peso_kg"])

            st.session_state[weight_key] = init_weight

        if done_key not in st.session_state:
            st.session_state[done_key] = False

        with cols[1]:
            st.write(f"● Séries x Reps: **{reps}**")

            if alt_options:
                st.selectbox("Variação", options=[o[0] for o in alt_options], key=alt_key)

            st.number_input("Peso (kg)", min_value=0.0, key=weight_key)
            st.checkbox("Feito?", key=done_key)

        done_flags.append(st.session_state[done_key])
        st.markdown("---")

    # Comemoração
    if done_flags:
        celebrate_key = f"{day}_celebrated"
        all_done = all(done_flags)

        if all_done and not st.session_state.get(celebrate_key, False):
            st.balloons()
            st.success("🎉 Parabéns, amor ❤️\nMais um dia de treino feito!")
            st.session_state[celebrate_key] = True
        elif not all_done:
            st.session_state[celebrate_key] = False

    c1, c2 = st.columns(2)

    with c1:
        if st.button("💾 Salvar treino"):
            rows = []
            for idx, (group, name, reps, gif_url_default) in enumerate(exercises):
                alt_key = f"{day}_{idx}_alt"
                alt_options = ALT_EXERCISES.get(name, None)

                log_name = st.session_state.get(alt_key, name) if alt_options else name

                rows.append({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "dia": day,
                    "grupo": group,
                    "exercicio": log_name,
                    "series_reps": reps,
                    "peso_kg": st.session_state.get(f"{day}_{idx}_peso", 0.0),
                    "feito": bool(st.session_state.get(f"{day}_{idx}_feito", False)),
                })

            df_new = pd.DataFrame(rows)

            if os.path.exists(LOG_FILE):
                try:
                    df_old = pd.read_csv(LOG_FILE)
                    df_all = pd.concat([df_old, df_new], ignore_index=True)
                except Exception:
                    df_all = df_new
            else:
                df_all = df_new

            df_all.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")
            st.success("Treino salvo! (peso será usado como base na próxima vez)")

    with c2:
        if st.button("🧹 Limpar"):
            for idx, _ in enumerate(exercises):
                st.session_state[f"{day}_{idx}_peso"] = 0.0
                st.session_state[f"{day}_{idx}_feito"] = False
            st.info("Campos zerados para este dia (histórico continua salvo no CSV).")
