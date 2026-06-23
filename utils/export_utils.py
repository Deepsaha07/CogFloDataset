import os
from io import BytesIO
import pandas as pd

from utils.processing import make_excel_safe
import ast
import json
from io import BytesIO

TASK_NAME_MAP = {
    "cd": "CD",
    "gng": "GNG",
    "msit": "MSIT",
    "survey_arousal": "Arousal",
    "survey_self_knowledge": "Self Knowledge",
}


def safe_sheet_name(name):
    invalid = ["\\", "/", "*", "?", ":", "[", "]"]
    for ch in invalid:
        name = name.replace(ch, "_")
    return str(name)[:31]


def parse_trials(value):
    if value is None or pd.isna(value):
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    return []


def get_task_type_from_row(task_row):
    return (
        task_row.get("task.result.run.taskId")
        or task_row.get("task.context.taskId")
        or task_row.get("task_id", "").split("-")[0]
    )


def make_trial_export_rows(task_row):
    trials = parse_trials(task_row.get("task.result.trials"))
    rows_by_phase = {"practice": [], "test": []}

    for trial in trials:
        if not isinstance(trial, dict):
            continue

        outcome = trial.get("outcome", {}) or {}
        timings = trial.get("timings", {}) or {}

        block_stage = str(trial.get("blockStage", "")).lower()
        phase = "practice" if block_stage == "practice" else "test"

        rows_by_phase[phase].append(
            {
                "Index": trial.get("index"),
                "Actual": outcome.get("expectedResponse"),
                "Response": outcome.get("response"),
                "Correct response": 1 if outcome.get("wasCorrect") is True else 0,
                "Reaction time": timings.get("rt_ms"),
                "Timeout": outcome.get("wasTimeout"),
            }
        )

    return rows_by_phase

def create_task_wise_trials_export(df_users, df_task_runs):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if df_task_runs.empty:
            pd.DataFrame().to_excel(writer, sheet_name="empty", index=False)
            output.seek(0)
            return output

        grouped = df_task_runs.groupby(
            ["milestone_id", "session_id"],
            dropna=False,
        )

        for (milestone_id, session_id), group_df in grouped:
            for task_type in ["cd", "gng", "msit"]:
                task_rows = group_df[
                    group_df.apply(
                        lambda r: get_task_type_from_row(r) == task_type,
                        axis=1,
                    )
                ]

                if task_rows.empty:
                    continue

                sheet_rows = []

                for _, task_row in task_rows.iterrows():
                    user_id = task_row.get("user_id")

                    user_match = df_users[df_users["user_id"] == user_id]
                    if not user_match.empty:
                        user_name = user_match.iloc[0].get("user.fullName", "")
                        user_email = user_match.iloc[0].get("user.email", "")
                    else:
                        user_name = ""
                        user_email = ""

                    sheet_rows.append(
                        {
                            "Index": f"Participant: {user_name}",
                            "Actual": f"User ID: {user_id}",
                            "Response": f"Email: {user_email}",
                            "Correct response": "",
                            "Reaction time": "",
                            "Timeout": "",
                        }
                    )
                    sheet_rows.append({})

                    phase_rows = make_trial_export_rows(task_row)

                    for phase_label, phase_key in [("Practice", "practice"), ("Test", "test")]:
                        rows = phase_rows.get(phase_key, [])

                        if not rows:
                            continue

                        sheet_rows.append(
                            {
                                "Index": phase_label,
                                "Actual": "",
                                "Response": "",
                                "Correct response": "",
                                "Reaction time": "",
                                "Timeout": "",
                            }
                        )

                        sheet_rows.extend(rows)

                        sheet_rows.append({})
                        sheet_rows.append({})
                        sheet_rows.append({})

                sheet_name = safe_sheet_name(
                    f"{milestone_id}_{session_id}_{TASK_NAME_MAP.get(task_type, task_type)}"
                )

                pd.DataFrame(sheet_rows).to_excel(
                    writer,
                    sheet_name=sheet_name,
                    index=False,
                )

    output.seek(0)
    return output

def create_json_bytes(df_users, df_milestones, df_scores, df_sessions, df_task_runs, scope_level):
    data = []

    for _, user in df_users.iterrows():
        user_id = user["user_id"]

        user_obj = {
            "user_id": user_id,
            "user_data": user.dropna().to_dict(),
            "milestones": [],
        }

        user_milestones = df_milestones[df_milestones["user_id"] == user_id]

        for _, milestone in user_milestones.iterrows():
            milestone_id = milestone["milestone_id"]

            milestone_obj = {
                "milestone_id": milestone_id,
                "milestone_data": milestone.dropna().to_dict(),
                "scores": [],
                "sessions": [],
            }

            milestone_scores = df_scores[
                (df_scores["user_id"] == user_id)
                & (df_scores["milestone_id"] == milestone_id)
            ]

            milestone_obj["scores"] = [
                row.dropna().to_dict() for _, row in milestone_scores.iterrows()
            ]

            milestone_sessions = df_sessions[
                (df_sessions["user_id"] == user_id)
                & (df_sessions["milestone_id"] == milestone_id)
            ]

            for _, session in milestone_sessions.iterrows():
                session_id = session["session_id"]

                session_obj = {
                    "session_id": session_id,
                    "session_data": session.dropna().to_dict(),
                    "task_runs": [],
                }

                session_tasks = df_task_runs[
                    (df_task_runs["user_id"] == user_id)
                    & (df_task_runs["milestone_id"] == milestone_id)
                    & (df_task_runs["session_id"] == session_id)
                ]

                session_obj["task_runs"] = [
                    row.dropna().to_dict() for _, row in session_tasks.iterrows()
                ]

                milestone_obj["sessions"].append(session_obj)

            user_obj["milestones"].append(milestone_obj)

        data.append(user_obj)

    json_text = json.dumps(data, indent=2, default=str)
    return json_text.encode("utf-8")

def create_excel_bytes(
    df_users,
    df_milestones,
    df_scores,
    df_sessions,
    df_task_runs,
    df_task_trials,
):
    output = BytesIO()

    df_users_excel = make_excel_safe(df_users)
    df_milestones_excel = make_excel_safe(df_milestones)
    df_scores_excel = make_excel_safe(df_scores)
    df_sessions_excel = make_excel_safe(df_sessions)
    df_task_runs_excel = make_excel_safe(df_task_runs)
    df_task_trials_excel = make_excel_safe(df_task_trials)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_users_excel.to_excel(writer, sheet_name="users", index=False)
        df_milestones_excel.to_excel(writer, sheet_name="milestones", index=False)
        df_scores_excel.to_excel(writer, sheet_name="scores", index=False)
        df_sessions_excel.to_excel(writer, sheet_name="sessions", index=False)
        df_task_runs_excel.to_excel(writer, sheet_name="task_runs", index=False)
        df_task_trials_excel.to_excel(writer, sheet_name="task_trials", index=False)

    output.seek(0)
    return output


def save_excel_file(df_users, df_milestones, df_scores, df_sessions):
    os.makedirs("exports", exist_ok=True)

    path = "exports/firestore_export.xlsx"

    df_users_excel = make_excel_safe(df_users)
    df_milestones_excel = make_excel_safe(df_milestones)
    df_scores_excel = make_excel_safe(df_scores)
    df_sessions_excel = make_excel_safe(df_sessions)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_users_excel.to_excel(writer, sheet_name="users", index=False)
        df_milestones_excel.to_excel(writer, sheet_name="milestones", index=False)
        df_scores_excel.to_excel(writer, sheet_name="scores", index=False)
        df_sessions_excel.to_excel(writer, sheet_name="sessions", index=False)

    return path

from io import BytesIO
import pandas as pd


def create_summary_rows_export(df_users, df_sessions, df_task_runs):
    rows = []

    summary_cols = [
        col for col in df_task_runs.columns
        if col.startswith("task.result.summary.")
    ]

    for _, task_row in df_task_runs.iterrows():
        user_id = task_row.get("user_id")
        milestone_id = task_row.get("milestone_id")
        session_id = task_row.get("session_id")
        task_id = (
            task_row.get("task.result.run.taskId")
            or task_row.get("task.context.taskId")
            or task_row.get("task_id")
        )

        user_match = df_users[df_users["user_id"] == user_id]
        name = user_match.iloc[0].get("user.fullName", "") if not user_match.empty else ""
        email = user_match.iloc[0].get("user.email", "") if not user_match.empty else ""

        for col in summary_cols:
            value = task_row.get(col)

            if pd.isna(value):
                continue

            clean_metric = col.replace("task.result.summary.", "")
            export_row_name = f"{task_id}_{clean_metric}"

            rows.append({
                "user_id": user_id,
                "name": name,
                "email": email,
                "milestone_id": milestone_id,
                "session_id": session_id,
                "task_id": task_id,
                "export_row_name": export_row_name,
                "source_column": col,
                "value": value,
            })

    df_long = pd.DataFrame(rows)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_long.to_excel(writer, sheet_name="summary_rows_all", index=False)

        if not df_long.empty:
            df_template = df_long.copy()

        df_template["subject_session_column"] = (
            df_template["user_id"].astype(str)
            + "_"
            + df_template["milestone_id"].astype(str)
            + "_"
            + df_template["session_id"].astype(str)
        )

        df_template = df_template.pivot_table(
            index="export_row_name",
            columns="subject_session_column",
            values="value",
            aggfunc="first",
        ).reset_index()

        df_template.columns = [str(col) for col in df_template.columns]

        df_template.to_excel(writer, sheet_name="template_like", index=False)

    output.seek(0)
    return output