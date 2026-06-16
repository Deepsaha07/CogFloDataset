import streamlit as st
import pandas as pd
import plotly.express as px

from services.firestore_service import fetch_firestore_data
from utils.processing import rows_to_dataframes
from utils.export_utils import create_excel_bytes, create_json_bytes


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


def go_home():
    st.session_state["page"] = "home"
    st.session_state["selected_app_config"] = None
    st.session_state["selected_user_id"] = None


def go_export():
    st.session_state["previous_page"] = st.session_state.get("page", "home")
    st.session_state["page"] = "export"


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
    
    
def compact_metric_label(name):
    label_map = {
        "Accuracy": "Acc",
        "Omission": "Omis",
        "Mean RT": "RT (ms)",
        "Conflict Score": "Conflict",
        "Final Score": "Score",
    }
    return label_map.get(name, name)


def compact_metric_class(name, value):
    if name == "Accuracy":
        return "metric-green"

    if name == "Omission":
        try:
            v = float(value)
            if v <= 1:
                v *= 100
            return "metric-red" if v > 0 else ""
        except Exception:
            return ""

    if name in ["Conflict Score", "Final Score"]:
        return "metric-blue"

    return ""


def render_compact_task_grid(session_tasks):
    task_order = [
        "cd",
        "gng",
        "msit",
        "survey_arousal",
        "survey_self_knowledge",
    ]

    cards_html = """
    <style>
    .compact-task-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(140px, 1fr));
        gap: 10px;
        margin-top: 8px;
        margin-bottom: 8px;
    }

    .compact-task-card {
        border: 1px solid rgba(250, 250, 250, 0.15);
        border-radius: 10px;
        padding: 12px 14px;
        background: rgba(255, 255, 255, 0.025);
        min-height: 95px;
    }

    .compact-task-title {
        font-size: 17px;
        font-weight: 700;
        margin-bottom: 14px;
        color: #f5f5f5;
    }

    .compact-metric-row {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
    }

    .compact-metric-label {
        font-size: 12px;
        color: rgba(250, 250, 250, 0.65);
        margin-bottom: 4px;
    }

    .compact-metric-value {
        font-size: 15px;
        font-weight: 700;
        color: #f5f5f5;
        white-space: nowrap;
    }

    .metric-green {
        color: #4ade80;
    }

    .metric-red {
        color: #f87171;
    }

    .metric-blue {
        color: #60a5fa;
    }
    </style>

    <div class="compact-task-grid">
    """

    for task_type in task_order:
        task_rows = session_tasks[
            session_tasks.apply(lambda r: get_task_type(r) == task_type, axis=1)
        ]

        if task_rows.empty:
            continue

        task_row = task_rows.iloc[0]
        display_name = TASK_DISPLAY_NAMES.get(task_type, task_type)
        icon = TASK_ICONS.get(task_type, "📌")
        metrics = get_task_summary_metrics(task_row)

        metric_items = ""

        for metric_name, metric_value in metrics.items():
            if metric_name in ["Accuracy", "Omission"]:
                value_text = fmt_value(metric_value, "%")
            elif "RT" in metric_name:
                value_text = fmt_value(metric_value, "")
            else:
                value_text = fmt_value(metric_value)

            metric_class = compact_metric_class(metric_name, metric_value)

            metric_items += f"""
            <div>
                <div class="compact-metric-label">{compact_metric_label(metric_name)}</div>
                <div class="compact-metric-value {metric_class}">{value_text}</div>
            </div>
            """

        cards_html += f"""
        <div class="compact-task-card">
            <div class="compact-task-title">{icon} {display_name}</div>
            <div class="compact-metric-row">
                {metric_items}
            </div>
        </div>
        """

    cards_html += "</div>"

    st.markdown(cards_html, unsafe_allow_html=True)


if "page" not in st.session_state:
    st.session_state["page"] = "home"

if "selected_app_config" not in st.session_state:
    st.session_state["selected_app_config"] = None

if "selected_user_id" not in st.session_state:
    st.session_state["selected_user_id"] = None

if "previous_page" not in st.session_state:
    st.session_state["previous_page"] = "home"


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

    age_map = {
        0: "<18",
        1: ">18",
        "0": "<18",
        "1": ">18",
    }

    gender_map = {
        1: "Male",
        2: "Female",
        "1": "Male",
        "2": "Female",
    }

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
            value = value * 100
        return f"{value:.2f}{suffix}"
    except Exception:
        return str(value)


def get_task_type(task_row):
    return (
        task_row.get("task.result.run.taskId")
        or task_row.get("task.context.taskId")
        or task_row.get("task_id")
    )


def get_task_summary_metrics(task_row):
    task_type = get_task_type(task_row)

    if task_type == "cd":
        return {
            "Accuracy": first_existing_value(task_row, ["task.result.summary.accuracy", "task.result.summary.cd_accuracy"]),
            "Omission": first_existing_value(task_row, ["task.result.summary.omission_rate", "task.result.summary.cd_omission_rate"]),
            "Mean RT": first_existing_value(task_row, ["task.result.summary.mean_rt"]),
        }

    if task_type == "gng":
        return {
            "Accuracy": first_existing_value(task_row, ["task.result.summary.accuracy", "task.result.summary.gng_go_accuracy"]),
            "Omission": first_existing_value(task_row, ["task.result.summary.omission_rate", "task.result.summary.gng_omission_rate"]),
            "Mean RT": first_existing_value(task_row, ["task.result.summary.mean_rt", "task.result.summary.gng_mean_go_rt"]),
        }

    if task_type == "msit":
        return {
            "Accuracy": first_existing_value(task_row, ["task.result.summary.d_accuracy", "task.result.summary.cc_prop_correct", "task.result.summary.prop_correct"]),
            "Conflict Score": first_existing_value(task_row, ["task.result.summary.conflict_score"]),
            "Mean RT": first_existing_value(task_row, ["task.result.summary.mean_rt", "task.result.summary.cc_mean_rt"]),
        }

    if task_type in ["survey_arousal", "survey_self_knowledge"]:
        return {
            "Final Score": first_existing_value(task_row, ["task.result.summary.final_score"]),
        }

    return {}


def render_metric_card(label, value, icon="📌"):
    with st.container(border=True):
        st.markdown(f"**{icon} {label}**")
        st.caption(fmt_value(value))

def render_task_summary_card(task_row):
    task_type = get_task_type(task_row)
    display_name = TASK_DISPLAY_NAMES.get(task_type, task_type)
    icon = TASK_ICONS.get(task_type, "📌")
    metrics = get_task_summary_metrics(task_row)

    with st.container(border=True):
        st.markdown(f"**{icon} {display_name}**")

        if not metrics:
            st.caption("No summary metrics detected.")
            return

        cols = st.columns(len(metrics))

        for col, (metric_name, metric_value) in zip(cols, metrics.items()):
            with col:
                if metric_name in ["Accuracy", "Omission"]:
                    value_text = fmt_value(metric_value, "%")
                elif "RT" in metric_name:
                    value_text = fmt_value(metric_value, " ms")
                else:
                    value_text = fmt_value(metric_value)

                st.caption(metric_name)
                st.markdown(f"**{value_text}**")


def render_accuracy_pie(task_name, accuracy):
    if accuracy is None or pd.isna(accuracy):
        return

    try:
        acc = float(accuracy)
        if acc <= 1:
            acc = acc * 100

        err = max(0, 100 - acc)

        pie_df = pd.DataFrame({
            "Outcome": ["Correct", "Error"],
            "Percent": [acc, err],
        })

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

    st.divider()

    nav1, nav2 = st.columns(2)

    with nav1:
        st.button("Home", use_container_width=True, disabled=True)

    with nav2:
        if st.button("Export", use_container_width=True):
            go_export()
            st.rerun()

    st.stop()


# ----------------------------
# EXPORT PAGE
# ----------------------------
if st.session_state["page"] == "export":
    top1, top2, _ = st.columns([1, 1, 4])

    with top1:
        if st.button("Home", use_container_width=True):
            go_home()
            st.rerun()

    with top2:
        if st.button("Go Back", use_container_width=True):
            go_back()
            st.rerun()

    st.title("Export Data")

    selected_config = st.session_state.get("selected_app_config")

    if selected_config:
        default_users = get_selected_config_users(df_users, selected_config)
        selected_config_label = APP_CONFIG_LABELS.get(selected_config, selected_config)
        st.caption(f"Current dataset: {selected_config_label}")
    else:
        default_users = df_users
        st.caption("Current dataset: All data")

    default_user_options = []

    for _, row in default_users.iterrows():
        name = row.get("user.fullName", "Unknown Name")
        user_id = row.get("user_id", "")
        updated = row.get("user.updatedAt", "")

        try:
            updated_str = pd.to_datetime(updated).strftime("%d %B, %Y")
        except Exception:
            updated_str = ""

        default_user_options.append(
            {
                "label": f"{name} | {user_id} | {updated_str}",
                "user_id": user_id,
            }
        )

    all_labels = [u["label"] for u in default_user_options]

    select_action = st.radio(
        "Selection mode",
        ["Select All", "Deselect All", "Multiple Selection"],
        horizontal=True,
    )

    if select_action == "Select All":
        selected_labels = all_labels
    elif select_action == "Deselect All":
        selected_labels = []
    else:
        selected_labels = st.multiselect(
            "Select users",
            options=all_labels,
            default=all_labels,
        )

    selected_export_user_ids = [
        u["user_id"] for u in default_user_options if u["label"] in selected_labels
    ]

    export_level = st.radio(
        "Export level",
        ["Subject/User level", "Milestone level", "Session level", "Game wise"],
        horizontal=True,
    )

    export_users = df_users[df_users["user_id"].isin(selected_export_user_ids)]
    export_milestones = df_milestones[
        df_milestones["user_id"].isin(selected_export_user_ids)
    ]
    export_scores = df_scores[df_scores["user_id"].isin(selected_export_user_ids)]
    export_sessions = df_sessions[
        df_sessions["user_id"].isin(selected_export_user_ids)
    ]
    export_task_runs = df_task_runs[
        df_task_runs["user_id"].isin(selected_export_user_ids)
    ]
    export_task_trials = df_task_trials[
        df_task_trials["user_id"].isin(selected_export_user_ids)
    ]

    if export_level == "Milestone level":
        valid_users = export_milestones["user_id"].unique().tolist()
        export_users = export_users[export_users["user_id"].isin(valid_users)]

    if export_level == "Session level":
        valid_users = export_sessions["user_id"].unique().tolist()
        export_users = export_users[export_users["user_id"].isin(valid_users)]

    if export_level == "Game wise":
        valid_users = export_task_runs["user_id"].unique().tolist()
        export_users = export_users[export_users["user_id"].isin(valid_users)]

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Users", len(export_users))
    c2.metric("Milestones", len(export_milestones))
    c3.metric("Scores", len(export_scores))
    c4.metric("Sessions", len(export_sessions))
    c5.metric("Task Runs", len(export_task_runs))
    c6.metric("Trial Rows", len(export_task_trials))

    json_file = create_json_bytes(
        export_users,
        export_milestones,
        export_scores,
        export_sessions,
        export_task_runs,
        export_level,
    )

    excel_file = create_excel_bytes(
        export_users,
        export_milestones,
        export_scores,
        export_sessions,
        export_task_runs,
        export_task_trials,
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.download_button(
            label="Download JSON",
            data=json_file,
            file_name="firestore_export.json",
            mime="application/json",
            use_container_width=True,
        )

    with col_b:
        st.download_button(
            label="Download Excel Workbook",
            data=excel_file,
            file_name="firestore_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.download_button(
        label="Download Task Trials CSV",
        data=export_task_trials.to_csv(index=False).encode("utf-8"),
        file_name="task_trials.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.stop()


# ----------------------------
# SUBJECT DASHBOARD PAGE
# ----------------------------
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

    # ----------------------------
    # OVERVIEW
    # ----------------------------
    with subject_tab1:
        st.subheader("Participant Overview")

        st.dataframe(
            make_user_home_table(subject_users).drop(columns=["_sort_time"], errors="ignore"),
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

                    task_cols = st.columns(5)

                    raw_score_mapping = [
                        ("cd", "CD", "🧠", ["score.flags.task_raw_scores.cd", "score.taskSubscores.cd"]),
                        ("gng", "GNG", "🎯", ["score.flags.task_raw_scores.gng", "score.taskSubscores.gng"]),
                        ("msit", "MSIT", "⚡", ["score.flags.task_raw_scores.msit", "score.taskSubscores.msit"]),
                        ("survey_arousal", "Arousal", "😊", ["score.flags.task_raw_scores.survey_arousal", "score.taskSubscores.survey_arousal"]),
                        ("survey_self_knowledge", "Self Knowledge", "📘", ["score.flags.task_raw_scores.survey_self_knowledge", "score.taskSubscores.survey_self_knowledge"]),
                    ]

                    for col, (_, display_name, icon, candidates) in zip(task_cols, raw_score_mapping):
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

                    for task_type, task_label, icon in [
                        ("cd", "CD", "🧠"),
                        ("gng", "GNG", "🎯"),
                        ("msit", "MSIT", "⚡"),
                    ]:
                        task_rows = milestone_tasks[
                            milestone_tasks.apply(lambda r: get_task_type(r) == task_type, axis=1)
                        ]

                        if not task_rows.empty:
                            task_row = task_rows.iloc[0]
                            metrics = get_task_summary_metrics(task_row)
                            accuracy = metrics.get("Accuracy")

                            with pie_cols[["cd", "gng", "msit"].index(task_type)]:
                                render_accuracy_pie(f"{icon} {task_label}", accuracy)

    # ----------------------------
    # MILESTONES
    # ----------------------------
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
                        ("CD", "🧠", ["score.flags.task_raw_scores.cd", "score.taskSubscores.cd"]),
                        ("GNG", "🎯", ["score.flags.task_raw_scores.gng", "score.taskSubscores.gng"]),
                        ("MSIT", "⚡", ["score.flags.task_raw_scores.msit", "score.taskSubscores.msit"]),
                        ("Arousal", "😊", ["score.flags.task_raw_scores.survey_arousal", "score.taskSubscores.survey_arousal"]),
                        ("Self Knowledge", "📘", ["score.flags.task_raw_scores.survey_self_knowledge", "score.taskSubscores.survey_self_knowledge"]),
                    ]

                    for col, (display_name, icon, candidates) in zip(task_cols, raw_score_mapping):
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

    # ----------------------------
    # SESSIONS TREE
    # ----------------------------
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
                                    task_types_order = [
                                        "cd",
                                        "gng",
                                        "msit",
                                        "survey_arousal",
                                        "survey_self_knowledge",
                                    ]

                                    render_compact_task_grid(session_tasks)

    # ----------------------------
    # RAW DATA
    # ----------------------------
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

    top1, top2, _ = st.columns([1, 1, 4])

    with top1:
        if st.button("Home", use_container_width=True):
            go_home()
            st.rerun()

    with top2:
        if st.button("Export", use_container_width=True):
            go_export()
            st.rerun()

    st.divider()
    st.subheader(f"{selected_config_label} Users")

    config_users = get_selected_config_users(df_users, selected_config)

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
        default=list(APP_CONFIG_LABELS.keys()),
        format_func=lambda x: APP_CONFIG_LABELS.get(x, x),
    )

    group_users = (
        df_users[df_users["user.appConfigId"].isin(group_config_options)]
        if "user.appConfigId" in df_users.columns
        else df_users.iloc[0:0]
    )

    group_user_ids = group_users["user_id"].tolist()

    group_milestones = df_milestones[df_milestones["user_id"].isin(group_user_ids)]
    group_scores = df_scores[df_scores["user_id"].isin(group_user_ids)]
    group_sessions = df_sessions[df_sessions["user_id"].isin(group_user_ids)]
    group_task_runs = df_task_runs[df_task_runs["user_id"].isin(group_user_ids)]
    group_task_trials = df_task_trials[df_task_trials["user_id"].isin(group_user_ids)]

    g1, g2, g3, g4, g5, g6 = st.columns(6)

    g1.metric("Users", len(group_users))
    g2.metric("Milestones", len(group_milestones))
    g3.metric("Scores", len(group_scores))
    g4.metric("Sessions", len(group_sessions))
    g5.metric("Task Runs", len(group_task_runs))
    g6.metric("Trial Rows", len(group_task_trials))

    group_tab1, group_tab2, group_tab3, group_tab4 = st.tabs(
        ["Users", "Scores", "Sessions", "Trial Outcomes"]
    )

    with group_tab1:
        group_users_display = make_user_home_table(group_users).drop(
            columns=["_sort_time"],
            errors="ignore",
        )

        group_table_event = st.dataframe(
            group_users_display,
            use_container_width=True,
            height=400,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        group_selected_rows = group_table_event.selection.rows

        if group_selected_rows:
            selected_row_index = group_selected_rows[0]
            selected_user_id = group_users_display.iloc[selected_row_index]["User ID"]
            open_subject(selected_user_id)
            st.rerun()

    with group_tab2:
        st.dataframe(group_scores, use_container_width=True, height=400)

    with group_tab3:
        st.dataframe(group_sessions, use_container_width=True, height=400)

    with group_tab4:
        st.dataframe(group_task_trials, use_container_width=True, height=400)

    st.stop()