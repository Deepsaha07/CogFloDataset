import streamlit as st
import pandas as pd
import plotly.express as px

from services.firestore_service import fetch_firestore_data
from utils.processing import rows_to_dataframes
from utils.export_utils import create_excel_bytes
from utils.export_utils import create_excel_bytes, create_json_bytes

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

def format_datetime_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d %B, %Y, %I.%M.%S %p")


def make_user_home_table(df):
    if df.empty:
        return pd.DataFrame(columns=["Name", "Email", "User ID", "Age", "Gender", "Last Used"])

    out = pd.DataFrame()

    out["Name"] = df.get("user.fullName", "")
    out["Email"] = df.get("user.email", "")
    out["User ID"] = df.get("user_id", "")

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

    out["Age"] = df.get("user.ageGroup", "").map(age_map) if "user.ageGroup" in df.columns else ""
    out["Gender"] = df.get("user.sex", "").map(gender_map) if "user.sex" in df.columns else ""

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

st.set_page_config(
    page_title="Firestore Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("CogFlo Analytics Dashboard")
st.caption("Users → Milestones → Scores → Sessions")

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

@st.cache_data(show_spinner=False)
def load_data():
    user_rows, milestone_rows, score_rows, session_rows, task_run_rows = fetch_firestore_data()
    return rows_to_dataframes(user_rows, milestone_rows, score_rows, session_rows, task_run_rows)

with st.sidebar:
    st.header("Controls")

    if st.button("Load / Refresh Firestore Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

try:
    with st.spinner("Loading Firestore data..."):
        df_users, df_milestones, df_scores, df_sessions, df_task_runs, df_task_trials = load_data()
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

    st.divider()

    user_ids = sorted(df_users["user_id"].dropna().unique().tolist()) if not df_users.empty else []

    selected_users = st.multiselect(
        "Select user IDs",
        options=user_ids,
        default=[],
    )

    export_scope = st.radio(
        "Export scope",
        ["All", "Selected users"],
        horizontal=False,
    )


if selected_users:
    f_users = df_users[df_users["user_id"].isin(selected_users)]
    f_milestones = df_milestones[df_milestones["user_id"].isin(selected_users)]
    f_scores = df_scores[df_scores["user_id"].isin(selected_users)]
    f_sessions = df_sessions[df_sessions["user_id"].isin(selected_users)]
    f_task_runs = df_task_runs[df_task_runs["user_id"].isin(selected_users)]
    f_task_trials = df_task_trials[df_task_trials["user_id"].isin(selected_users)]

else:
    f_users = df_users
    f_milestones = df_milestones
    f_scores = df_scores
    f_sessions = df_sessions
    f_task_runs = df_task_runs
    f_task_trials = df_task_trials


if export_scope == "Selected users" and selected_users:
    export_users = f_users
    export_milestones = f_milestones
    export_scores = f_scores
    export_sessions = f_sessions
    export_task_run = f_task_runs
else:
    export_users = df_users
    export_milestones = df_milestones
    export_scores = df_scores
    export_sessions = df_sessions
    export_task_runs = df_task_runs


if "selected_app_config" not in st.session_state:
    st.session_state["selected_app_config"] = None

st.subheader("Dataset Home")

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



if st.session_state["page"] == "subject_view":
    selected_user_id = st.session_state["selected_user_id"]

    subject_users = df_users[df_users["user_id"] == selected_user_id]
    subject_milestones = df_milestones[df_milestones["user_id"] == selected_user_id]
    subject_scores = df_scores[df_scores["user_id"] == selected_user_id]
    subject_sessions = df_sessions[df_sessions["user_id"] == selected_user_id]
    subject_task_runs = df_task_runs[df_task_runs["user_id"] == selected_user_id]
    subject_task_trials = df_task_trials[df_task_trials["user_id"] == selected_user_id]

    top1, top2, top3 = st.columns([1, 1, 4])

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

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Milestones", len(subject_milestones))
    m2.metric("Sessions", len(subject_sessions))
    m3.metric("Task Runs", len(subject_task_runs))
    m4.metric("Trial Rows", len(subject_task_trials))

    st.divider()

    subject_tab1, subject_tab2, subject_tab3, subject_tab4, subject_tab5 = st.tabs(
        ["Summary", "Milestones", "Sessions", "Task Runs", "Trial Outcomes"]
    )

    with subject_tab1:
        st.subheader("Subject Summary")

        st.dataframe(
            make_user_home_table(subject_users).drop(columns=["_sort_time"], errors="ignore"),
            use_container_width=True,
        )

        if not subject_scores.empty:
            st.markdown("### Milestone-Level Scores")
            st.dataframe(subject_scores, use_container_width=True, height=300)

        if not subject_task_runs.empty:
            st.markdown("### Task Run Summary")
            compact_task_cols = [
                col for col in subject_task_runs.columns
                if col in ["user_id", "milestone_id", "session_id", "task_id"]
                or col.startswith("task.result.summary")
                or col in ["task.status", "task.result.run.durationMs", "task.result.run.taskId"]
            ]
            st.dataframe(subject_task_runs[compact_task_cols], use_container_width=True)

    with subject_tab2:
        if subject_milestones.empty:
            st.info("No milestones found.")
        else:
            for _, milestone_row in subject_milestones.iterrows():
                milestone_id = milestone_row["milestone_id"]

                milestone_sessions = subject_sessions[
                    subject_sessions["milestone_id"] == milestone_id
                ]

                milestone_scores = subject_scores[
                    subject_scores["milestone_id"] == milestone_id
                ]

                with st.expander(
                    f"Milestone: {milestone_id} | Sessions: {len(milestone_sessions)}"
                ):
                    st.write("Milestone Details")
                    st.dataframe(pd.DataFrame([milestone_row]), use_container_width=True)

                    st.write("Score")
                    st.dataframe(milestone_scores, use_container_width=True)

                    for _, session_row in milestone_sessions.iterrows():
                        session_id = session_row["session_id"]

                        session_tasks = subject_task_runs[
                            (subject_task_runs["milestone_id"] == milestone_id)
                            & (subject_task_runs["session_id"] == session_id)
                        ]

                        with st.expander(
                            f"Session: {session_id} | Task Runs: {len(session_tasks)}"
                        ):
                            st.dataframe(pd.DataFrame([session_row]), use_container_width=True)
                            st.dataframe(session_tasks, use_container_width=True)

    with subject_tab3:
        st.dataframe(subject_sessions, use_container_width=True, height=450)

    with subject_tab4:
        st.dataframe(subject_task_runs, use_container_width=True, height=450)

    with subject_tab5:
        st.dataframe(subject_task_trials, use_container_width=True, height=450)

    st.stop()
    
    
selected_config = st.session_state["selected_app_config"]

if selected_config is None:
    st.info("Select a dataset type above to view users.")
    st.stop()


selected_config_label = APP_CONFIG_LABELS.get(selected_config, selected_config)

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

st.dataframe(
    display_home_users,
    use_container_width=True,
    height=450,
)

st.divider()
st.subheader("Subject-wise Inspection")

if config_users.empty:
    st.info("No users found in this dataset.")
else:
    user_options = []

    for _, row in config_users.iterrows():
        name = row.get("user.fullName", "Unknown Name")
        user_id = row.get("user_id", "")
        updated = row.get("user.updatedAt", "")

        updated_str = ""
        try:
            updated_str = pd.to_datetime(updated).strftime("%d %B, %Y")
        except Exception:
            updated_str = ""

        user_options.append(
            {
                "label": f"{name} | {user_id} | {updated_str}",
                "user_id": user_id,
            }
        )

    selected_user_label = st.selectbox(
        "Select subject",
        options=[u["label"] for u in user_options],
    )

    selected_user_id = next(
        u["user_id"] for u in user_options if u["label"] == selected_user_label
    )

    subject_users = df_users[df_users["user_id"] == selected_user_id]
    subject_milestones = df_milestones[df_milestones["user_id"] == selected_user_id]
    subject_scores = df_scores[df_scores["user_id"] == selected_user_id]
    subject_sessions = df_sessions[df_sessions["user_id"] == selected_user_id]
    subject_task_runs = df_task_runs[df_task_runs["user_id"] == selected_user_id]
    subject_task_trials = df_task_trials[df_task_trials["user_id"] == selected_user_id]

    st.markdown("### Subject Details")

    detail_tab1, detail_tab2, detail_tab3, detail_tab4, detail_tab5 = st.tabs(
        ["Tree View", "Milestones", "Sessions", "Task Runs", "Trial Outcomes"]
    )

    with detail_tab1:
        if subject_milestones.empty:
            st.info("No milestones found for this subject.")
        else:
            for _, milestone_row in subject_milestones.iterrows():
                milestone_id = milestone_row["milestone_id"]

                milestone_sessions = subject_sessions[
                    subject_sessions["milestone_id"] == milestone_id
                ]

                milestone_scores = subject_scores[
                    subject_scores["milestone_id"] == milestone_id
                ]

                with st.expander(
                    f"Milestone: {milestone_id} | Sessions: {len(milestone_sessions)}"
                ):
                    st.write("Milestone Details")
                    st.dataframe(pd.DataFrame([milestone_row]), use_container_width=True)

                    st.write("Milestone Score")
                    if milestone_scores.empty:
                        st.info("No score found.")
                    else:
                        st.dataframe(milestone_scores, use_container_width=True)

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
                                f"Session: {session_id} | Task Runs: {len(session_tasks)}"
                            ):
                                st.dataframe(
                                    pd.DataFrame([session_row]),
                                    use_container_width=True,
                                )

                                if session_tasks.empty:
                                    st.info("No task runs found.")
                                else:
                                    st.dataframe(session_tasks, use_container_width=True)

    with detail_tab2:
        st.dataframe(subject_milestones, use_container_width=True, height=400)

    with detail_tab3:
        st.dataframe(subject_sessions, use_container_width=True, height=400)

    with detail_tab4:
        st.dataframe(subject_task_runs, use_container_width=True, height=400)

    with detail_tab5:
        st.dataframe(subject_task_trials, use_container_width=True, height=400)
        
        
st.divider()
st.subheader("Group Analysis")

group_config_options = st.multiselect(
    "Select dataset groups",
    options=list(APP_CONFIG_LABELS.keys()),
    default=list(APP_CONFIG_LABELS.keys()),
    format_func=lambda x: APP_CONFIG_LABELS.get(x, x),
)

group_users = df_users[
    df_users["user.appConfigId"].isin(group_config_options)
] if "user.appConfigId" in df_users.columns else df_users.iloc[0:0]

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
    st.dataframe(group_users_display, use_container_width=True, height=400)

with group_tab2:
    st.dataframe(group_scores, use_container_width=True, height=400)

with group_tab3:
    st.dataframe(group_sessions, use_container_width=True, height=400)

with group_tab4:
    st.dataframe(group_task_trials, use_container_width=True, height=400)
    
if st.session_state["page"] == "export":
    top1, top2, top3 = st.columns([1, 1, 4])

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
    export_milestones = df_milestones[df_milestones["user_id"].isin(selected_export_user_ids)]
    export_scores = df_scores[df_scores["user_id"].isin(selected_export_user_ids)]
    export_sessions = df_sessions[df_sessions["user_id"].isin(selected_export_user_ids)]
    export_task_runs = df_task_runs[df_task_runs["user_id"].isin(selected_export_user_ids)]
    export_task_trials = df_task_trials[df_task_trials["user_id"].isin(selected_export_user_ids)]

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