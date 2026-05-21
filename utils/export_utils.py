import os
from io import BytesIO
import pandas as pd

from utils.processing import make_excel_safe

import json
from io import BytesIO


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