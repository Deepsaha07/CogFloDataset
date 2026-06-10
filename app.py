import streamlit as st
import pandas as pd
import plotly.express as px

from services.firestore_service import fetch_firestore_data
from utils.processing import rows_to_dataframes
from utils.export_utils import create_excel_bytes
from utils.export_utils import create_excel_bytes, create_json_bytes

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


tab_overview, tab_tree, tab_scores, tab_sessions, tab_tasks, tab_trials, tab_export = st.tabs(
    ["Overview", "Tree View", "Scores", "Sessions", "Task Runs", "Trial Outcomes", "Export"]
)

with tab_overview:
    st.subheader("Overview")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Users", len(f_users))
    c2.metric("Milestones", len(f_milestones))
    c3.metric("Scores", len(f_scores))
    c4.metric("Sessions", len(f_sessions))
    c5.metric("Task Runs", len(f_task_runs))
    c6.metric("Trial Rows", len(f_task_trials))

    st.divider()

    st.subheader("Users")

    users_view = f_users.copy()

    # Detect possible name/email/time columns naturally
    possible_name_cols = [
        col for col in users_view.columns
        if "name" in col.lower()
    ]

    possible_email_cols = [
        col for col in users_view.columns
        if "email" in col.lower()
    ]

    possible_time_cols = [
        col for col in users_view.columns
        if any(key in col.lower() for key in ["created", "updated", "recorded", "computed", "timestamp", "time"])
    ]

    name_col = possible_name_cols[0] if possible_name_cols else None
    email_col = possible_email_cols[0] if possible_email_cols else None

    sort_col = None

    sort_c1, sort_c2 = st.columns([2, 1])

    with sort_c1:
        if possible_time_cols:
            sort_col = st.selectbox(
                "Sort by time field",
                options=possible_time_cols,
            )
        else:
            st.info("No timestamp/time column detected for sorting.")

    with sort_c2:
        sort_order = st.radio(
            "Order",
            options=["Latest first", "Oldest first"],
            horizontal=False,
        )

    if sort_col:
        users_view["_sort_time"] = pd.to_datetime(
            users_view[sort_col],
            errors="coerce",
        )

        users_view = users_view.sort_values(
            "_sort_time",
            ascending=True if sort_order == "Oldest first" else False,
        )

        users_view = users_view.drop(columns=["_sort_time"])

    # Reorder columns: user_id, name, email first
    priority_cols = ["user_id"]

    if name_col and name_col not in priority_cols:
        priority_cols.append(name_col)

    if email_col and email_col not in priority_cols:
        priority_cols.append(email_col)

    remaining_cols = [
        col for col in users_view.columns
        if col not in priority_cols
    ]

    users_view = users_view[priority_cols + remaining_cols]

    st.dataframe(
        users_view,
        use_container_width=True,
        height=500,
    )

    st.divider()

    st.subheader("Selected Data Preview")

    preview_tab1, preview_tab2, preview_tab3, preview_tab4, preview_tab5, preview_tab6 = st.tabs(
        ["Users", "Milestones", "Scores", "Sessions", "Task Runs", "Trial Outcomes"]
    )

    with preview_tab1:
        st.dataframe(users_view, use_container_width=True, height=300)

    with preview_tab2:
        st.dataframe(f_milestones, use_container_width=True, height=300)

    with preview_tab3:
        st.dataframe(f_scores, use_container_width=True, height=300)

    with preview_tab4:
        st.dataframe(f_sessions, use_container_width=True, height=300)

    with preview_tab5:
        st.dataframe(f_task_runs, use_container_width=True, height=300)

    with preview_tab6:
        st.dataframe(f_task_trials, use_container_width=True, height=300)


with tab_scores:
    st.subheader("Scores")

    st.dataframe(f_scores, use_container_width=True, height=400)

    score_numeric_cols = f_scores.select_dtypes(include="number").columns.tolist()

    if score_numeric_cols and not f_scores.empty:
        selected_score_col = st.selectbox(
            "Select numeric score column for visualization",
            score_numeric_cols,
        )

        fig = px.bar(
            f_scores,
            x="user_id",
            y=selected_score_col,
            color="milestone_id" if "milestone_id" in f_scores.columns else None,
            title=f"{selected_score_col} by User",
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No numeric score columns available for visualization.")


with tab_sessions:
    st.subheader("Sessions")

    st.dataframe(f_sessions, use_container_width=True, height=500)

    session_numeric_cols = f_sessions.select_dtypes(include="number").columns.tolist()

    if session_numeric_cols and not f_sessions.empty:
        selected_session_col = st.selectbox(
            "Select numeric session column for visualization",
            session_numeric_cols,
        )

        fig = px.box(
            f_sessions,
            x="user_id",
            y=selected_session_col,
            title=f"{selected_session_col} distribution by User",
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No numeric session columns available for visualization.")


with tab_tasks:
    st.subheader("Task Runs / Games")

    if f_task_runs.empty:
        st.info("No task runs found.")
    else:
        task_ids = sorted(f_task_runs["task_id"].dropna().unique().tolist())

        selected_task_ids = st.multiselect(
            "Select task/game type",
            options=task_ids,
            default=task_ids,
        )

        task_view = f_task_runs[f_task_runs["task_id"].isin(selected_task_ids)]

        st.write(f"Rows: {len(task_view)}")
        st.dataframe(task_view, use_container_width=True, height=500)

        st.subheader("Detected fields from task JSON")

        detected_columns = [
            col
            for col in task_view.columns
            if col not in ["user_id", "milestone_id", "session_id", "task_id"]
        ]

        st.write(f"Detected {len(detected_columns)} task fields.")

        selected_columns = st.multiselect(
            "Select fields to display",
            options=detected_columns,
            default=detected_columns[:20],
        )

        base_columns = ["user_id", "milestone_id", "session_id", "task_id"]

        if selected_columns:
            st.dataframe(
                task_view[base_columns + selected_columns],
                use_container_width=True,
                height=500,
            )

with tab_trials:
    st.subheader("Trial-Level Outcomes")

    if f_task_trials.empty:
        st.info("No trial-level data found.")

    else:
        # -----------------------------
        # Filters
        # -----------------------------
        st.markdown("### Filters")

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

        task_types = sorted(f_task_trials["task_type"].dropna().unique().tolist())
        phases = sorted(f_task_trials["phase_type"].dropna().unique().tolist())
        milestone_ids = sorted(f_task_trials["milestone_id"].dropna().unique().tolist())
        session_ids = sorted(f_task_trials["session_id"].dropna().unique().tolist())

        with filter_col1:
            selected_trial_tasks = st.multiselect(
                "Task type",
                options=task_types,
                default=task_types,
            )

        with filter_col2:
            selected_phase = st.multiselect(
                "Phase",
                options=phases,
                default=phases,
            )

        with filter_col3:
            selected_trial_milestones = st.multiselect(
                "Milestone",
                options=milestone_ids,
                default=milestone_ids,
            )

        with filter_col4:
            selected_trial_sessions = st.multiselect(
                "Session",
                options=session_ids,
                default=session_ids,
            )

        view_level = st.radio(
            "View level",
            options=["Session-wise", "Milestone-wise"],
            horizontal=True,
        )

        trial_view = f_task_trials[
            (f_task_trials["task_type"].isin(selected_trial_tasks))
            & (f_task_trials["phase_type"].isin(selected_phase))
            & (f_task_trials["milestone_id"].isin(selected_trial_milestones))
            & (f_task_trials["session_id"].isin(selected_trial_sessions))
        ].copy()

        # Ensure boolean columns behave correctly
        if "was_correct" in trial_view.columns:
            trial_view["was_correct"] = trial_view["was_correct"].astype("boolean")

        if "was_timeout" in trial_view.columns:
            trial_view["was_timeout"] = trial_view["was_timeout"].astype("boolean")

        # -----------------------------
        # Summary Metrics
        # -----------------------------
        st.markdown("### Summary")

        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("Trials", len(trial_view))

        if not trial_view.empty and "was_correct" in trial_view.columns:
            accuracy = trial_view["was_correct"].mean() * 100
            c2.metric("Accuracy", f"{accuracy:.1f}%")
        else:
            c2.metric("Accuracy", "N/A")

        if not trial_view.empty and "was_timeout" in trial_view.columns:
            timeout_rate = trial_view["was_timeout"].mean() * 100
            c3.metric("Timeout Rate", f"{timeout_rate:.1f}%")
        else:
            c3.metric("Timeout Rate", "N/A")

        if not trial_view.empty and "error_type" in trial_view.columns:
            error_count = trial_view["error_type"].notna().sum()
            c4.metric("Errors", int(error_count))
        else:
            c4.metric("Errors", "N/A")

        if not trial_view.empty and "session_id" in trial_view.columns:
            c5.metric("Sessions", trial_view["session_id"].nunique())
        else:
            c5.metric("Sessions", "N/A")

        # -----------------------------
        # Display Table
        # -----------------------------
        st.markdown("### Trial Table")

        display_cols = [
            "user_id",
            "milestone_id",
            "session_id",
            "task_type",
            "trial_index",
            "phase_type",
            "was_correct",
            "expected_response",
            "response",
            "error_type",
            "was_timeout",
        ]

        available_display_cols = [
            col for col in display_cols if col in trial_view.columns
        ]

        st.dataframe(
            trial_view[available_display_cols],
            use_container_width=True,
            height=450,
        )

        # -----------------------------
        # Aggregation
        # -----------------------------
        st.markdown("### Aggregated Performance")

        if view_level == "Session-wise":
            group_cols = ["user_id", "milestone_id", "session_id", "task_type", "phase_type"]
        else:
            group_cols = ["user_id", "milestone_id", "task_type", "phase_type"]

        group_cols = [col for col in group_cols if col in trial_view.columns]

        if not trial_view.empty and "was_correct" in trial_view.columns:
            agg_df = (
                trial_view.groupby(group_cols, dropna=False)
                .agg(
                    trial_count=("trial_index", "count"),
                    accuracy=("was_correct", "mean"),
                    timeout_rate=("was_timeout", "mean")
                    if "was_timeout" in trial_view.columns
                    else ("was_correct", "mean"),
                    error_count=("error_type", lambda x: x.notna().sum())
                    if "error_type" in trial_view.columns
                    else ("was_correct", "count"),
                )
                .reset_index()
            )

            agg_df["accuracy_percent"] = agg_df["accuracy"] * 100

            if "timeout_rate" in agg_df.columns:
                agg_df["timeout_rate_percent"] = agg_df["timeout_rate"] * 100

            st.dataframe(
                agg_df,
                use_container_width=True,
                height=350,
            )

            # -----------------------------
            # Visualisations
            # -----------------------------
            st.markdown("### Visualisations")

            if view_level == "Session-wise" and "session_id" in agg_df.columns:
                x_axis = "session_id"
                chart_title = "Accuracy by Session"
            else:
                x_axis = "milestone_id"
                chart_title = "Accuracy by Milestone"

            fig_acc = px.bar(
                agg_df,
                x=x_axis,
                y="accuracy_percent",
                color="task_type",
                facet_col="phase_type",
                barmode="group",
                title=chart_title,
                hover_data=[
                    col for col in ["user_id", "milestone_id", "session_id", "trial_count"]
                    if col in agg_df.columns
                ],
            )

            st.plotly_chart(fig_acc, use_container_width=True)

            if "timeout_rate_percent" in agg_df.columns:
                fig_timeout = px.bar(
                    agg_df,
                    x=x_axis,
                    y="timeout_rate_percent",
                    color="task_type",
                    facet_col="phase_type",
                    barmode="group",
                    title="Timeout Rate by Task and Phase",
                    hover_data=[
                        col for col in ["user_id", "milestone_id", "session_id", "trial_count"]
                        if col in agg_df.columns
                    ],
                )

                st.plotly_chart(fig_timeout, use_container_width=True)

        else:
            st.info("No valid trial outcome data available for aggregation.")

        # -----------------------------
        # Error Type Distribution
        # -----------------------------
        st.markdown("### Error Type Distribution")

        if not trial_view.empty and "error_type" in trial_view.columns:
            err_view = trial_view.copy()
            err_view["error_type"] = err_view["error_type"].fillna("correct/no_error")

            if view_level == "Session-wise":
                error_group_cols = [
                    "task_type",
                    "phase_type",
                    "session_id",
                    "error_type",
                ]
                x_axis_error = "session_id"
                error_title = "Error Types by Session"
            else:
                error_group_cols = [
                    "task_type",
                    "phase_type",
                    "milestone_id",
                    "error_type",
                ]
                x_axis_error = "milestone_id"
                error_title = "Error Types by Milestone"

            error_group_cols = [
                col for col in error_group_cols if col in err_view.columns
            ]

            err_df = (
                err_view.groupby(error_group_cols, dropna=False)
                .size()
                .reset_index(name="count")
            )

            st.dataframe(err_df, use_container_width=True, height=300)

            fig_err = px.bar(
                err_df,
                x=x_axis_error,
                y="count",
                color="error_type",
                facet_col="task_type",
                barmode="stack",
                title=error_title,
            )

            st.plotly_chart(fig_err, use_container_width=True)
        else:
            st.info("No error type data available.")

with tab_export:
    st.subheader("Export Data")

    st.write(f"Exporting scope: **{export_scope}**")

    if export_scope == "Selected users" and not selected_users:
        st.warning("Select at least one user to export selected data.")
    else:
        export_task_runs = (
            f_task_runs
            if export_scope == "Selected users" and selected_users
            else df_task_runs
        )

        export_task_trials = (
            f_task_trials
            if export_scope == "Selected users" and selected_users
            else df_task_trials
        )

        excel_file = create_excel_bytes(
            export_users,
            export_milestones,
            export_scores,
            export_sessions,
            export_task_runs,
            export_task_trials,
        )
        
        json_scope_level = st.selectbox(
            "JSON export level",
            ["Subject/User level", "Milestone level", "Session level"],
        )
        
        json_file = create_json_bytes(
            export_users,
            export_milestones,
            export_scores,
            export_sessions,
            export_task_runs,
            json_scope_level
            )

        st.download_button(
            label="Download Raw JSON Export",
            data=json_file,
            file_name="firestore_export.json",
            mime="application/json",
            use_container_width=True,
        )

        st.download_button(
            label="Download Excel Workbook",
            data=excel_file,
            file_name="firestore_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.download_button(
            label="Download Users CSV",
            data=export_users.to_csv(index=False).encode("utf-8"),
            file_name="users.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.download_button(
            label="Download Milestones CSV",
            data=export_milestones.to_csv(index=False).encode("utf-8"),
            file_name="milestones.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.download_button(
            label="Download Scores CSV",
            data=export_scores.to_csv(index=False).encode("utf-8"),
            file_name="scores.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.download_button(
            label="Download Sessions CSV",
            data=export_sessions.to_csv(index=False).encode("utf-8"),
            file_name="sessions.csv",
            mime="text/csv",
            use_container_width=True,
        )

 
        
        st.download_button(
            label="Download Task Runs CSV",
            data=export_task_runs.to_csv(index=False).encode("utf-8"),
            file_name="task_runs.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.download_button(
            label="Download Task Trials CSV",
            data=export_task_trials.to_csv(index=False).encode("utf-8"),
            file_name="task_trials.csv",
            mime="text/csv",
            use_container_width=True,
        )