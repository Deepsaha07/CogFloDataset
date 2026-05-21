import os
from io import BytesIO
import pandas as pd

from utils.processing import make_excel_safe


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