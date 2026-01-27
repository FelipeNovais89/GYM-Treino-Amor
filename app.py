import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Planner de Treinos", layout="wide")

# ---------- GIFs ----------
GIFS = {
    "hip_thrust": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Hip-Thrust.gif",
    "abdutora": "https://fitnessprogramer.com/wp-content/uploads/2021/02/HiP-ABDUCTION-MACHINE.gif",
    "lat_pulldown": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lat-Pulldown.gif",
    "seated_row": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Seated-Cable-Row.gif",
    "leg_press": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Leg-Press.gif",
    "stiff": "https://fitnessprogramer.com/wp-content/uploads/2022/01/Stiff-Leg-Deadlift.gif",
    "squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/BARBELL-SQUAT.gif",
    "bulgaro": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Barbell-Bulgarian-Split-Squat.gif",
    "lateral_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Lateral-Raise.gif",
    "shoulder_press": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Shoulder-Press.gif",
    "plank": "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "leg_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lying-Leg-Raise.gif",
    "cable_kickback": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cable-Hip-Extension.gif",
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
        ("Glúteo e Posterior", "Mesa flexora", "4x12", ""),
    ],
    "Terça": [
        ("Costas / Bíceps / ABS / Panturrilha", "Puxada alta aberta", "3x12", GIFS["lat_pulldown"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Pulldown", "3x12", GIFS["lat_pulldown"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Remada baixa", "4x12", GIFS["seated_row"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Rosca direta com barra", "3x12", ""),
        ("Costas / Bíceps / ABS / Panturrilha", "Rosca alternada com halteres", "3x12", ""),
        ("Costas / Bíceps / ABS / Panturrilha", "Prancha", "3x30–45s", GIFS["plank"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Abdominal infra (elevação de pernas)", "4x20", GIFS["leg_raise"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Elevação de panturrilha sentado", "3x15–20", ""),
    ],
    "Quarta": [
        ("Quadríceps e Glúteo", "Cadeira extensora", "5x15", ""),
        ("Quadríceps e Glúteo", "Agachamento livre", "4x12", GIFS["squat"]),
        ("Quadríceps e Glúteo", "Búlgaro", "3x12", GIFS["bulgaro"]),
        ("Quadríceps e Glúteo", "Afundo", "3x12", GIFS["bulgaro"]),
        ("Quadríceps e Glúteo", "Leg press", "3x12", GIFS["leg_press"]),
        ("Quadríceps e Glúteo", "Cadeira abdutora", "4x12", GIFS["abdutora"]),
        ("Quadríceps e Glúteo", "Coice na polia", "3x12", GIFS["cable_kickback"]),
    ],
    "Quinta": [
        ("Ombro / Tríceps / ABS / Panturrilha", "Desenvolvimento com halteres", "3x12", GIFS["shoulder_press"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação lateral com halteres", "3x12", GIFS["lateral_raise"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação frontal com halteres", "3x12", GIFS["lateral_raise"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Tríceps na polia (corda)", "3x12", ""),
        ("Ombro / Tríceps / ABS / Panturrilha", "Tríceps na polia (barra)", "3x12", ""),
        ("Ombro / Tríceps / ABS / Panturrilha", "Prancha", "3x30–45s", GIFS["plank"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Abdominal infra (elevação de pernas)", "4x20", GIFS["leg_raise"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação de panturrilha em pé", "3x15–20", ""),
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

LOG_FILE = "treino_log.csv"

st.sidebar.title("Planner de Treinos")
day = st.sidebar.selectbox("Selecione o dia", ["Selecione..."] + list(WORKOUTS.keys()))

st.title("Planner de Treinos com GIFs")

if day == "Selecione...":
    st.write("👈 Selecione um dia da semana")
else:
    exercises = WORKOUTS[day]
    st.subheader(f"Treino de {day}")

    for idx, (group, name, reps, gif_url) in enumerate(exercises):
        st.markdown(f"### {name}")
        st.caption(group)

        cols = st.columns([2, 1])

        with cols[0]:
            if gif_url:
                st.image(gif_url, width=260)
            else:
                st.info("Sem GIF disponível")

        weight_key = f"{day}_{idx}_peso"
        done_key = f"{day}_{idx}_feito"

        # inicializa estado apenas se não existir
        if weight_key not in st.session_state:
            st.session_state[weight_key] = 0.0
        if done_key not in st.session_state:
            st.session_state[done_key] = False

        with cols[1]:
            st.write(f"● Séries x Reps: **{reps}**")
            st.number_input(
                "Peso (kg)",
                min_value=0.0,
                key=weight_key,  # o widget cuida do session_state
            )
            st.checkbox(
                "Feito?",
                key=done_key,
            )

        st.markdown("---")

    c1, c2 = st.columns(2)

    with c1:
        if st.button("💾 Salvar treino"):
            rows = []
            for idx, (group, name, reps, gif_url) in enumerate(exercises):
                rows.append({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "dia": day,
                    "grupo": group,
                    "exercicio": name,
                    "series_reps": reps,
                    "peso_kg": st.session_state.get(f"{day}_{idx}_peso", 0.0),
                    "feito": bool(st.session_state.get(f"{day}_{idx}_feito", False)),
                })
            df_new = pd.DataFrame(rows)
            if os.path.exists(LOG_FILE):
                df_old = pd.read_csv(LOG_FILE)
                df_all = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df_all = df_new
            df_all.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")
            st.success("Treino salvo!")

    with c2:
        if st.button("🧹 Limpar"):
            for idx, _ in enumerate(exercises):
                st.session_state[f"{day}_{idx}_peso"] = 0.0
                st.session_state[f"{day}_{idx}_feito"] = False
            st.info("Campos zerados para este dia.")
