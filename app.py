import streamlit as st
import pandas as pd
import plotly.express as px

from services.firestore_service import fetch_firestore_data
from utils.processing import rows_to_dataframes
from utils.export_utils import (
    create_summary_rows_export,
    create_task_wise_trials_export,
    parse_trials,
)


st.set_page_config(
    page_title="CogFlo Analytics Dashboard",
    page_icon="📊",
    layout="wide",
)


APP_CONFIG_LABELS = {
    "app_config_quicktest": "Testing",
    "app_config_norm_study": "Norming",
    "app_config_default": "Public App",
}


TASK_DISPLAY_NAMES = {
    "cd": "CD",
    "gng": "GNG",
    "msit": "MSIT",
    "survey_arousal": "Arousal",
    "survey_self_knowledge": "Self Knowledge",
}

TASK_ICONS = {
    "cd": "🧠",
    "gng": "🎯",
    "msit": "⚡",
    "survey_arousal": "😊",
    "survey_self_knowledge": "📘",
}


def go_home():
    st.session_state["page"] = "home"
    st.session_state["selected_app_config"] = None
    st.session_state["selected_user_id"] = None


def go_back():
    if st.session_state.get("selected_app_config"):
        st.session_state["page"] = "dataset_view"
    else:
        st.session_state["page"] = st.session_state.get("previous_page", "home")


def open_dataset(app_config_id):
    st.session_state["selected_app_config"] = app_config_id
    st.session_state["page"] = "dataset_view"


def open_subject(user_id):
    st.session_state["selected_user_id"] = user_id
    st.session_state["previous_page"] = st.session_state.get("page", "dataset_view")
    st.session_state["page"] = "subject_view"


if "page" not in st.session_state:
    st.session_state["page"] = "home"

if "selected_app_config" not in st.session_state:
    st.session_state["selected_app_config"] = None

if "selected_user_id" not in st.session_state:
    st.session_state["selected_user_id"] = None

if "previous_page" not in st.session_state:
    st.session_state["previous_page"] = "home"
    
def create_group_task_summary_df(group_users, group_task_runs):
    rows = []

    for _, task_row in group_task_runs.iterrows():
        user_id = task_row.get("user_id")
        user_match = group_users[group_users["user_id"] == user_id]

        user_name = (
            user_match.iloc[0].get("user.fullName", "")
            if not user_match.empty
            else ""
        )

        task_type = get_task_type(task_row)
        task_name = TASK_DISPLAY_NAMES.get(task_type, task_type)

        metrics = get_task_summary_metrics(task_row)

        rows.append(
            {
                "user_id": user_id,
                "name": user_name,
                "milestone_id": task_row.get("milestone_id"),
                "session_id": task_row.get("session_id"),
                "task_type": task_type,
                "task_name": task_name,
                "accuracy": metrics.get("Accuracy"),
                "omission": metrics.get("Omission"),
                "mean_rt": metrics.get("Mean RT"),
                "conflict_score": metrics.get("Conflict Score"),
                "final_score": metrics.get("Final Score"),
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    for col in ["accuracy", "omission", "mean_rt", "conflict_score", "final_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["accuracy", "omission"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: x * 100 if pd.notna(x) and abs(x) <= 1 else x
            )

    return df


def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("Dashboard Access")
    password = st.text_input("Enter password", type="password")

    if st.button("Login"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")

    return False


if not check_password():
    st.stop()


st.title("CogFlo Analytics Dashboard")
st.caption("Users → Milestones → Scores → Sessions")


def format_datetime_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime(
        "%d %B, %Y, %I.%M.%S %p"
    )


def make_user_home_table(df):
    if df.empty:
        return pd.DataFrame(
            columns=["Name", "Email", "User ID", "Age", "Gender", "Last Used"]
        )

    out = pd.DataFrame(index=df.index)

    out["Name"] = df["user.fullName"] if "user.fullName" in df.columns else ""
    out["Email"] = df["user.email"] if "user.email" in df.columns else ""
    out["User ID"] = df["user_id"] if "user_id" in df.columns else ""

    age_map = {0: "<18", 1: ">18", "0": "<18", "1": ">18"}
    gender_map = {1: "Male", 2: "Female", "1": "Male", "2": "Female"}

    out["Age"] = (
        df["user.ageGroup"].map(age_map)
        if "user.ageGroup" in df.columns
        else ""
    )

    out["Gender"] = (
        df["user.sex"].map(gender_map)
        if "user.sex" in df.columns
        else ""
    )

    if "user.updatedAt" in df.columns:
        out["Last Used"] = format_datetime_series(df["user.updatedAt"])
        out["_sort_time"] = pd.to_datetime(df["user.updatedAt"], errors="coerce")
    else:
        out["Last Used"] = ""
        out["_sort_time"] = pd.NaT

    return out


def get_selected_config_users(df_users, selected_config):
    if "user.appConfigId" not in df_users.columns:
        return df_users.iloc[0:0]

    return df_users[df_users["user.appConfigId"] == selected_config].copy()


def first_existing_value(row, candidates, default=None):
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            return row[col]
    return default


def fmt_value(value, suffix=""):
    if value is None or pd.isna(value):
        return "N/A"

    try:
        value = float(value)
        if abs(value) <= 1 and suffix == "%":
            value *= 100
        return f"{value:.2f}{suffix}"
    except Exception:
        return str(value)


def get_task_type(task_row):
    task_type = (
        task_row.get("task.result.run.taskId")
        or task_row.get("task.context.taskId")
        or task_row.get("task_id")
    )

    if isinstance(task_type, str) and "-" in task_type:
        return task_type.split("-")[0]

    return task_type


def get_task_summary_metrics(task_row):
    task_type = get_task_type(task_row)

    if task_type == "cd":
        return {
            "Accuracy": first_existing_value(
                task_row,
                ["task.result.summary.accuracy", "task.result.summary.cd_accuracy"],
            ),
            "Omission": first_existing_value(
                task_row,
                [
                    "task.result.summary.omission_rate",
                    "task.result.summary.cd_omission_rate",
                ],
            ),
            "Mean RT": first_existing_value(
                task_row,
                ["task.result.summary.mean_rt"],
            ),
        }

    if task_type == "gng":
        return {
            "Accuracy": first_existing_value(
                task_row,
                [
                    "task.result.summary.accuracy",
                    "task.result.summary.gng_go_accuracy",
                ],
            ),
            "Omission": first_existing_value(
                task_row,
                [
                    "task.result.summary.omission_rate",
                    "task.result.summary.gng_omission_rate",
                ],
            ),
            "Mean RT": first_existing_value(
                task_row,
                [
                    "task.result.summary.mean_rt",
                    "task.result.summary.gng_mean_go_rt",
                ],
            ),
        }

    if task_type == "msit":
        return {
            "Accuracy": first_existing_value(
                task_row,
                [
                    "task.result.summary.d_accuracy",
                    "task.result.summary.cc_prop_correct",
                    "task.result.summary.prop_correct",
                ],
            ),
            "Conflict Score": first_existing_value(
                task_row,
                ["task.result.summary.conflict_score"],
            ),
            "Mean RT": first_existing_value(
                task_row,
                [
                    "task.result.summary.mean_rt",
                    "task.result.summary.cc_mean_rt",
                ],
            ),
        }

    if task_type in ["survey_arousal", "survey_self_knowledge"]:
        return {
            "Final Score": first_existing_value(
                task_row,
                ["task.result.summary.final_score"],
            )
        }

    return {}


def compact_metric_label(name):
    label_map = {
        "Accuracy": "Acc",
        "Omission": "Omis",
        "Mean RT": "RT",
        "Conflict Score": "Conflict",
        "Final Score": "Score",
    }
    return label_map.get(name, name)


def render_metric_card(label, value, icon="📌"):
    with st.container(border=True):
        st.markdown(f"**{icon} {label}**")
        st.caption(fmt_value(value))


def render_compact_task_grid(session_tasks):
    task_order = [
        "cd",
        "gng",
        "msit",
        "survey_arousal",
        "survey_self_knowledge",
    ]

    task_cols = st.columns(5)

    for col, task_type in zip(task_cols, task_order):
        task_rows = session_tasks[
            session_tasks.apply(lambda r: get_task_type(r) == task_type, axis=1)
        ]

        with col:
            if task_rows.empty:
                continue

            task_row = task_rows.iloc[0]
            display_name = TASK_DISPLAY_NAMES.get(task_type, task_type)
            icon = TASK_ICONS.get(task_type, "📌")
            metrics = get_task_summary_metrics(task_row)

            with st.container(border=True):
                st.markdown(f"**{icon} {display_name}**")

                for metric_name, metric_value in metrics.items():
                    if metric_name in ["Accuracy", "Omission"]:
                        value_text = fmt_value(metric_value, "%")
                    elif "RT" in metric_name:
                        value_text = fmt_value(metric_value, "")
                    else:
                        value_text = fmt_value(metric_value)

                    st.caption(compact_metric_label(metric_name))
                    st.markdown(f"**{value_text}**")


def render_accuracy_pie(task_name, accuracy):
    if accuracy is None or pd.isna(accuracy):
        return

    try:
        acc = float(accuracy)
        if acc <= 1:
            acc *= 100

        acc = max(0, min(acc, 100))
        err = 100 - acc

        pie_df = pd.DataFrame(
            {
                "Outcome": ["Correct", "Error"],
                "Percent": [acc, err],
            }
        )

        fig = px.pie(
            pie_df,
            names="Outcome",
            values="Percent",
            hole=0.55,
            title=f"{task_name} Accuracy",
        )

        st.plotly_chart(fig, use_container_width=True)

    except Exception:
        pass


@st.cache_data(show_spinner=False)
def load_data():
    user_rows, milestone_rows, score_rows, session_rows, task_run_rows = (
        fetch_firestore_data()
    )

    return rows_to_dataframes(
        user_rows,
        milestone_rows,
        score_rows,
        session_rows,
        task_run_rows,
    )


with st.sidebar:
    st.header("Controls")

    if st.button("Load / Refresh Firestore Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()


try:
    with st.spinner("Loading Firestore data..."):
        (
            df_users,
            df_milestones,
            df_scores,
            df_sessions,
            df_task_runs,
            df_task_trials,
        ) = load_data()
except Exception as e:
    st.error(f"Failed to load Firestore data: {e}")
    st.stop()


with st.sidebar:
    st.subheader("Dataset Summary")
    st.write(f"Users: {len(df_users)}")
    st.write(f"Milestones: {len(df_milestones)}")
    st.write(f"Scores: {len(df_scores)}")
    st.write(f"Sessions: {len(df_sessions)}")
    st.write(f"Tasks: {len(df_task_runs)}")
    st.write(f"Trial Rows: {len(df_task_trials)}")


# ----------------------------
# HOME PAGE
# ----------------------------
if st.session_state["page"] == "home":
    st.subheader("Dataset Home")

    card1, card2, card3 = st.columns(3)

    with card1:
        if st.button("Testing", use_container_width=True):
            open_dataset("app_config_quicktest")
            st.rerun()

    with card2:
        if st.button("Norming", use_container_width=True):
            open_dataset("app_config_norm_study")
            st.rerun()

    with card3:
        if st.button("Public App", use_container_width=True):
            open_dataset("app_config_default")
            st.rerun()

    st.stop()


# ----------------------------
# SUBJECT DASHBOARD PAGE
# ----------------------------
if st.session_state["page"] == "subject_view":
    selected_user_id = st.session_state["selected_user_id"]

    subject_users = df_users[df_users["user_id"] == selected_user_id]
    subject_milestones = df_milestones[df_milestones["user_id"] == selected_user_id]
    subject_scores = df_scores[df_scores["user_id"] == selected_user_id]
    subject_sessions = df_sessions[df_sessions["user_id"] == selected_user_id]
    subject_task_runs = df_task_runs[df_task_runs["user_id"] == selected_user_id]
    subject_task_trials = df_task_trials[df_task_trials["user_id"] == selected_user_id]

    top1, top2, _ = st.columns([1, 1, 4])

    with top1:
        if st.button("Home", use_container_width=True):
            go_home()
            st.rerun()

    with top2:
        if st.button("Go Back", use_container_width=True):
            go_back()
            st.rerun()

    if subject_users.empty:
        st.error("Subject not found.")
        st.stop()

    user_row = subject_users.iloc[0]

    subject_name = user_row.get("user.fullName", "Unknown Name")
    subject_email = user_row.get("user.email", "")

    st.title(subject_name)
    st.caption(f"{subject_email} | User ID: {selected_user_id}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Milestones", len(subject_milestones))
    m2.metric("Sessions", len(subject_sessions))
    m3.metric("Tasks", len(subject_task_runs))

    st.divider()

    subject_tab1, subject_tab2, subject_tab3, subject_tab4 = st.tabs(
        ["Overview", "Milestones", "Sessions Tree", "Raw Data"]
    )

    with subject_tab1:
        st.subheader("Participant Overview")

        st.dataframe(
            make_user_home_table(subject_users).drop(
                columns=["_sort_time"], errors="ignore"
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### Milestone Summary")

        if subject_scores.empty:
            st.info("No milestone score found.")
        else:
            for _, score_row in subject_scores.iterrows():
                milestone_id = score_row.get("milestone_id", "Unknown Milestone")

                with st.container(border=True):
                    st.markdown(f"## Milestone: {milestone_id}")

                    raw_score_mapping = [
                        (
                            "CD",
                            "🧠",
                            [
                                "score.flags.task_raw_scores.cd",
                                "score.taskSubscores.cd",
                            ],
                        ),
                        (
                            "GNG",
                            "🎯",
                            [
                                "score.flags.task_raw_scores.gng",
                                "score.taskSubscores.gng",
                            ],
                        ),
                        (
                            "MSIT",
                            "⚡",
                            [
                                "score.flags.task_raw_scores.msit",
                                "score.taskSubscores.msit",
                            ],
                        ),
                        (
                            "Arousal",
                            "😊",
                            [
                                "score.flags.task_raw_scores.survey_arousal",
                                "score.taskSubscores.survey_arousal",
                            ],
                        ),
                        (
                            "Self Knowledge",
                            "📘",
                            [
                                "score.flags.task_raw_scores.survey_self_knowledge",
                                "score.taskSubscores.survey_self_knowledge",
                            ],
                        ),
                    ]

                    task_cols = st.columns(5)

                    for col, (display_name, icon, candidates) in zip(
                        task_cols, raw_score_mapping
                    ):
                        with col:
                            value = first_existing_value(score_row, candidates)
                            render_metric_card(display_name, value, icon)

                    scaled_score = first_existing_value(
                        score_row,
                        [
                            "score.flags.summed_scaled_score",
                            "score.flags.index_score_lookup.indexScore",
                            "score.milestoneCfScore",
                        ],
                    )

                    st.markdown("### Scaled Score")

                    if scaled_score is not None and pd.notna(scaled_score):
                        try:
                            scaled_float = float(scaled_score)
                            st.progress(min(max(scaled_float / 100, 0), 1))
                            st.metric("Scaled Score", f"{scaled_float:.2f}")
                        except Exception:
                            st.metric("Scaled Score", scaled_score)
                    else:
                        st.info("Scaled score not available.")

                    st.markdown("### Accuracy / Error View")

                    milestone_tasks = subject_task_runs[
                        subject_task_runs["milestone_id"] == milestone_id
                    ]

                    pie_cols = st.columns(3)

                    for idx, (task_type, task_label, icon) in enumerate(
                        [
                            ("cd", "CD", "🧠"),
                            ("gng", "GNG", "🎯"),
                            ("msit", "MSIT", "⚡"),
                        ]
                    ):
                        task_rows = milestone_tasks[
                            milestone_tasks.apply(
                                lambda r: get_task_type(r) == task_type,
                                axis=1,
                            )
                        ]

                        with pie_cols[idx]:
                            if not task_rows.empty:
                                task_row = task_rows.iloc[0]
                                metrics = get_task_summary_metrics(task_row)
                                render_accuracy_pie(
                                    f"{icon} {task_label}",
                                    metrics.get("Accuracy"),
                                )
                            else:
                                st.info(f"{task_label}: no data.")

    with subject_tab2:
        st.subheader("Milestone-Level View")

        if subject_scores.empty:
            st.info("No milestone score found.")
        else:
            for _, score_row in subject_scores.iterrows():
                milestone_id = score_row.get("milestone_id", "Unknown Milestone")

                with st.expander(f"Milestone: {milestone_id}", expanded=True):
                    task_cols = st.columns(5)

                    raw_score_mapping = [
                        (
                            "CD",
                            "🧠",
                            [
                                "score.flags.task_raw_scores.cd",
                                "score.taskSubscores.cd",
                            ],
                        ),
                        (
                            "GNG",
                            "🎯",
                            [
                                "score.flags.task_raw_scores.gng",
                                "score.taskSubscores.gng",
                            ],
                        ),
                        (
                            "MSIT",
                            "⚡",
                            [
                                "score.flags.task_raw_scores.msit",
                                "score.taskSubscores.msit",
                            ],
                        ),
                        (
                            "Arousal",
                            "😊",
                            [
                                "score.flags.task_raw_scores.survey_arousal",
                                "score.taskSubscores.survey_arousal",
                            ],
                        ),
                        (
                            "Self Knowledge",
                            "📘",
                            [
                                "score.flags.task_raw_scores.survey_self_knowledge",
                                "score.taskSubscores.survey_self_knowledge",
                            ],
                        ),
                    ]

                    for col, (display_name, icon, candidates) in zip(
                        task_cols, raw_score_mapping
                    ):
                        with col:
                            value = first_existing_value(score_row, candidates)
                            render_metric_card(display_name, value, icon)

                    scaled_score = first_existing_value(
                        score_row,
                        [
                            "score.flags.summed_scaled_score",
                            "score.flags.index_score_lookup.indexScore",
                            "score.milestoneCfScore",
                        ],
                    )

                    st.markdown("#### Scaled Score")

                    if scaled_score is not None and pd.notna(scaled_score):
                        try:
                            scaled_float = float(scaled_score)
                            st.progress(min(max(scaled_float / 100, 0), 1))
                            st.metric("Scaled Score", f"{scaled_float:.2f}")
                        except Exception:
                            st.metric("Scaled Score", scaled_score)
                    else:
                        st.info("Scaled score not available.")

    with subject_tab3:
        st.subheader("Sessions Tree")

        if subject_milestones.empty:
            st.info("No milestones found.")
        else:
            for _, milestone_row in subject_milestones.iterrows():
                milestone_id = milestone_row["milestone_id"]

                milestone_sessions = subject_sessions[
                    subject_sessions["milestone_id"] == milestone_id
                ]

                with st.expander(
                    f"Milestone: {milestone_id} | Sessions: {len(milestone_sessions)}",
                    expanded=True,
                ):
                    if milestone_sessions.empty:
                        st.info("No sessions found.")
                    else:
                        for _, session_row in milestone_sessions.iterrows():
                            session_id = session_row["session_id"]

                            session_tasks = subject_task_runs[
                                (subject_task_runs["milestone_id"] == milestone_id)
                                & (subject_task_runs["session_id"] == session_id)
                            ]

                            with st.expander(
                                f"Session: {session_id} | Tasks: {len(session_tasks)}",
                                expanded=False,
                            ):
                                if session_tasks.empty:
                                    st.info("No task runs found.")
                                else:
                                    render_compact_task_grid(session_tasks)

                                    st.markdown("#### Trial Visualisation")

                                    available_trial_tasks = [
                                        task
                                        for task in ["cd", "gng", "msit"]
                                        if not session_tasks[
                                            session_tasks.apply(lambda r: get_task_type(r) == task, axis=1)
                                        ].empty
                                    ]

                                    if not available_trial_tasks:
                                        st.info("No CD/GNG/MSIT trial data found for this session.")
                                    else:
                                        selected_trial_task = st.selectbox(
                                            "Select task for trial visualisation",
                                            options=available_trial_tasks,
                                            format_func=lambda x: TASK_DISPLAY_NAMES.get(x, x),
                                            key=f"trial_viz_{milestone_id}_{session_id}",
                                        )

                                        task_row = session_tasks[
                                            session_tasks.apply(
                                                lambda r: get_task_type(r) == selected_trial_task,
                                                axis=1,
                                            )
                                        ].iloc[0]

                                        trial_rows = []

                                        for trial in parse_trials(task_row.get("task.result.trials")):
                                            outcome = trial.get("outcome", {}) or {}
                                            timings = trial.get("timings", {}) or {}

                                            trial_rows.append(
                                                {
                                                    "Index": trial.get("index"),
                                                    "Phase": trial.get("blockStage"),
                                                    "Correct": 1 if outcome.get("wasCorrect") is True else 0,
                                                    "Reaction time": timings.get("rt_ms"),
                                                    "Timeout": outcome.get("wasTimeout"),
                                                }
                                            )

                                        trial_df = pd.DataFrame(trial_rows)

                                        if trial_df.empty:
                                            st.info("No trial-level data found for this task.")
                                        else:
                                            fig_rt = px.histogram(
                                                trial_df.dropna(subset=["Reaction time"]),
                                                x="Reaction time",
                                                color="Phase",
                                                nbins=20,
                                                title="Reaction Time Distribution",
                                            )
                                            st.plotly_chart(fig_rt, use_container_width=True)

                                            fig_correct = px.bar(
                                                trial_df,
                                                x="Index",
                                                y="Correct",
                                                color="Phase",
                                                title="Correct / Incorrect by Trial",
                                            )
                                            st.plotly_chart(fig_correct, use_container_width=True)

                                            correct_percent = trial_df["Correct"].mean() * 100

                                            pie_df = pd.DataFrame(
                                                {
                                                    "Outcome": ["Correct", "Incorrect"],
                                                    "Percent": [correct_percent, 100 - correct_percent],
                                                }
                                            )

                                            fig_pie = px.pie(
                                                pie_df,
                                                names="Outcome",
                                                values="Percent",
                                                hole=0.5,
                                                title="Correct Response Percentage",
                                            )
                                            st.plotly_chart(fig_pie, use_container_width=True)

    with subject_tab4:
        raw_tab1, raw_tab2, raw_tab3, raw_tab4, raw_tab5 = st.tabs(
            ["Scores", "Milestones", "Sessions", "Task Runs", "Trial Outcomes"]
        )

        with raw_tab1:
            st.dataframe(subject_scores, use_container_width=True, height=400)

        with raw_tab2:
            st.dataframe(subject_milestones, use_container_width=True, height=400)

        with raw_tab3:
            st.dataframe(subject_sessions, use_container_width=True, height=400)

        with raw_tab4:
            st.dataframe(subject_task_runs, use_container_width=True, height=400)

        with raw_tab5:
            st.dataframe(subject_task_trials, use_container_width=True, height=400)

    st.stop()


# ----------------------------
# DATASET VIEW PAGE
# ----------------------------
if st.session_state["page"] == "dataset_view":
    selected_config = st.session_state["selected_app_config"]

    if selected_config is None:
        st.info("Select a dataset type above to view users.")
        st.stop()

    selected_config_label = APP_CONFIG_LABELS.get(selected_config, selected_config)

    top1, _ = st.columns([1, 5])

    with top1:
        if st.button("Home", use_container_width=True):
            go_home()
            st.rerun()

    st.divider()
    st.subheader(f"{selected_config_label} Users")

    config_users = get_selected_config_users(df_users, selected_config)
    config_user_ids = config_users["user_id"].dropna().tolist()

    export_users = df_users[df_users["user_id"].isin(config_user_ids)]
    export_milestones = df_milestones[df_milestones["user_id"].isin(config_user_ids)]
    export_scores = df_scores[df_scores["user_id"].isin(config_user_ids)]
    export_sessions = df_sessions[df_sessions["user_id"].isin(config_user_ids)]
    export_task_runs = df_task_runs[df_task_runs["user_id"].isin(config_user_ids)]
    export_task_trials = df_task_trials[df_task_trials["user_id"].isin(config_user_ids)]

    sort_col1, sort_col2 = st.columns([3, 1])

    with sort_col1:
        st.caption("Sorting based on Last Used")

    with sort_col2:
        sort_order = st.radio(
            "Sort",
            ["Latest first", "Oldest first"],
            horizontal=False,
            label_visibility="collapsed",
        )

    home_users_table = make_user_home_table(config_users)

    if "_sort_time" in home_users_table.columns:
        home_users_table = home_users_table.sort_values(
            "_sort_time",
            ascending=True if sort_order == "Oldest first" else False,
        )

    display_home_users = home_users_table.drop(columns=["_sort_time"], errors="ignore")

    if config_users.empty:
        st.info("No users found in this dataset.")
    else:
        user_table_event = st.dataframe(
            display_home_users,
            use_container_width=True,
            height=520,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        selected_rows = user_table_event.selection.rows

        if selected_rows:
            selected_row_index = selected_rows[0]
            selected_user_id = display_home_users.iloc[selected_row_index]["User ID"]
            open_subject(selected_user_id)
            st.rerun()

    st.divider()
    st.subheader("Group Analysis")

    group_config_options = st.multiselect(
        "Select dataset groups",
        options=list(APP_CONFIG_LABELS.keys()),
        default=[selected_config],
        format_func=lambda x: APP_CONFIG_LABELS.get(x, x),
    )

    group_users_base = (
        df_users[df_users["user.appConfigId"].isin(group_config_options)]
        if "user.appConfigId" in df_users.columns
        else df_users.iloc[0:0]
    )

    subject_options = make_user_home_table(group_users_base)

    selected_group_user_ids = st.multiselect(
        "Select subjects for group analysis",
        options=subject_options["User ID"].dropna().tolist(),
        default=subject_options["User ID"].dropna().tolist(),
    )

    group_users = group_users_base[
        group_users_base["user_id"].isin(selected_group_user_ids)
    ]

    group_user_ids = group_users["user_id"].dropna().tolist()

    group_milestones = df_milestones[df_milestones["user_id"].isin(group_user_ids)]
    group_scores = df_scores[df_scores["user_id"].isin(group_user_ids)]
    group_sessions = df_sessions[df_sessions["user_id"].isin(group_user_ids)]
    group_task_runs = df_task_runs[df_task_runs["user_id"].isin(group_user_ids)]
    group_task_trials = df_task_trials[df_task_trials["user_id"].isin(group_user_ids)]

    group_task_summary = create_group_task_summary_df(
        group_users,
        group_task_runs,
    )

    g1, g2, g3, g4, g5 = st.columns(5)

    g1.metric("Selected Users", len(group_users))
    g2.metric("Completed Milestones", group_milestones["milestone_id"].nunique() if "milestone_id" in group_milestones.columns else 0)
    g3.metric("Completed Sessions", group_sessions["session_id"].nunique() if "session_id" in group_sessions.columns else 0)
    g4.metric("Task Runs", len(group_task_runs))
    g5.metric("Trial Rows", len(group_task_trials))

    analysis_tab1, analysis_tab2, analysis_tab3, analysis_tab4 = st.tabs(
        [
            "Task Score Summary",
            "Accuracy Distribution",
            "Session-wise Analysis",
            "Raw Group Data",
        ]
    )

    with analysis_tab1:
        st.markdown("### Task-wise Statistical Summary")

        if group_task_summary.empty:
            st.info("No task summary data found.")
        else:
            stats_cols = [
                col for col in [
                    "accuracy",
                    "omission",
                    "mean_rt",
                    "conflict_score",
                    "final_score",
                ]
                if col in group_task_summary.columns
            ]

            stats_df = (
                group_task_summary
                .groupby("task_name")[stats_cols]
                .agg(["count", "mean", "std", "min", "max"])
                .reset_index()
            )

            stats_df.columns = [
                "_".join(col).strip("_") if isinstance(col, tuple) else col
                for col in stats_df.columns
            ]

            st.dataframe(stats_df, use_container_width=True, height=350)

            plot_metric = st.selectbox(
                "Select metric for distribution plot",
                options=stats_cols,
                format_func=lambda x: {
                    "accuracy": "Accuracy",
                    "omission": "Omission",
                    "mean_rt": "Mean RT",
                    "conflict_score": "Conflict Score",
                    "final_score": "Final Score",
                }.get(x, x),
            )

            fig_box = px.box(
                group_task_summary.dropna(subset=[plot_metric]),
                x="task_name",
                y=plot_metric,
                points="all",
                color="task_name",
                title=f"{plot_metric.replace('_', ' ').title()} Distribution by Task",
            )

            st.plotly_chart(fig_box, use_container_width=True)

    with analysis_tab2:
        st.markdown("### Accuracy Distribution Across Users and Sessions")

        if group_task_summary.empty or "accuracy" not in group_task_summary.columns:
            st.info("No accuracy data found.")
        else:
            accuracy_df = group_task_summary.dropna(subset=["accuracy"])

            if accuracy_df.empty:
                st.info("No valid accuracy values found.")
            else:
                fig_hist = px.histogram(
                    accuracy_df,
                    x="accuracy",
                    color="task_name",
                    nbins=20,
                    marginal="box",
                    title="Accuracy Distribution Across All Users and Sessions",
                )

                st.plotly_chart(fig_hist, use_container_width=True)

                fig_user = px.box(
                    accuracy_df,
                    x="task_name",
                    y="accuracy",
                    color="task_name",
                    points="all",
                    hover_data=["name", "user_id", "milestone_id", "session_id"],
                    title="Task Accuracy Spread Across Subjects",
                )

                st.plotly_chart(fig_user, use_container_width=True)

    with analysis_tab3:
        st.markdown("### Session-wise Task Analysis")

        if group_task_summary.empty:
            st.info("No session-level task data found.")
        else:
            session_stats = (
                group_task_summary
                .groupby(["milestone_id", "session_id", "task_name"], dropna=False)
                .agg(
                    subjects=("user_id", "nunique"),
                    accuracy_mean=("accuracy", "mean"),
                    accuracy_std=("accuracy", "std"),
                    omission_mean=("omission", "mean"),
                    mean_rt_mean=("mean_rt", "mean"),
                    mean_rt_std=("mean_rt", "std"),
                    final_score_mean=("final_score", "mean"),
                    final_score_std=("final_score", "std"),
                )
                .reset_index()
            )

            st.dataframe(session_stats, use_container_width=True, height=350)

            if "accuracy_mean" in session_stats.columns:
                fig_session_acc = px.bar(
                    session_stats.dropna(subset=["accuracy_mean"]),
                    x="session_id",
                    y="accuracy_mean",
                    color="task_name",
                    facet_col="milestone_id",
                    barmode="group",
                    title="Mean Accuracy by Session and Task",
                )

                st.plotly_chart(fig_session_acc, use_container_width=True)

            if "mean_rt_mean" in session_stats.columns:
                fig_session_rt = px.bar(
                    session_stats.dropna(subset=["mean_rt_mean"]),
                    x="session_id",
                    y="mean_rt_mean",
                    color="task_name",
                    facet_col="milestone_id",
                    barmode="group",
                    title="Mean Reaction Time by Session and Task",
                )

                st.plotly_chart(fig_session_rt, use_container_width=True)

            if "final_score_mean" in session_stats.columns:
                fig_session_score = px.bar(
                    session_stats.dropna(subset=["final_score_mean"]),
                    x="session_id",
                    y="final_score_mean",
                    color="task_name",
                    facet_col="milestone_id",
                    barmode="group",
                    title="Survey Final Score by Session",
                )

                st.plotly_chart(fig_session_score, use_container_width=True)

    with analysis_tab4:
        raw_group_tab1, raw_group_tab2, raw_group_tab3, raw_group_tab4, raw_group_tab5 = st.tabs(
            ["Users", "Scores", "Sessions", "Task Summary", "Trial Outcomes"]
        )

        with raw_group_tab1:
            st.dataframe(
                make_user_home_table(group_users).drop(columns=["_sort_time"], errors="ignore"),
                use_container_width=True,
                height=400,
                hide_index=True,
            )

        with raw_group_tab2:
            st.dataframe(group_scores, use_container_width=True, height=400)

        with raw_group_tab3:
            st.dataframe(group_sessions, use_container_width=True, height=400)

        with raw_group_tab4:
            st.dataframe(group_task_summary, use_container_width=True, height=400)

        with raw_group_tab5:
            st.dataframe(group_task_trials, use_container_width=True, height=400)

    st.divider()
    st.subheader(f"{selected_config_label} Export")

    export_tab1, export_tab2, export_tab3 = st.tabs(
        [
            "Milestone Based Analysis",
            "Session Based Analysis",
            "Task Level Export",
        ]
    )

    with export_tab1:
        milestone_file = create_summary_rows_export(
            export_users,
            export_sessions,
            export_task_runs,
        )

        st.download_button(
            label="Download Milestone Based Analysis",
            data=milestone_file,
            file_name=f"{selected_config_label.lower().replace(' ', '_')}_milestone_based_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with export_tab2:
        st.info("Session Based Analysis export will be added next.")

    with export_tab3:
        task_file = create_task_wise_trials_export(
            export_users,
            export_task_runs,
        )

        st.download_button(
            label="Download Task Level Export",
            data=task_file,
            file_name=f"{selected_config_label.lower().replace(' ', '_')}_task_level_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.stop()