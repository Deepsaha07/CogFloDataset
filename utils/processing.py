from datetime import datetime
import pandas as pd
import ast
import json
import pandas as pd


def parse_trials_value(value):
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


def get_nested(d, path, default=None):
    current = d

    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)

    return current


def create_task_trials_dataframe(df_task_runs):
    trial_rows = []

    if df_task_runs.empty:
        return pd.DataFrame(
            columns=[
                "user_id",
                "milestone_id",
                "session_id",
                "task_id",
                "task_type",
                "trial_index",
                "block_stage",
                "phase_type",
                "was_correct",
                "expected_response",
                "response",
                "error_type",
                "was_timeout",
            ]
        )

    for _, task_row in df_task_runs.iterrows():
        trials = parse_trials_value(task_row.get("task.result.trials"))

        task_type = (
            task_row.get("task.result.run.taskId")
            or task_row.get("task.context.taskId")
            or task_row.get("task_id")
        )

        for idx, trial in enumerate(trials):
            if not isinstance(trial, dict):
                continue

            outcome = trial.get("outcome", {}) or {}

            block_stage = (
                trial.get("blockStage")
                or trial.get("block_stage")
                or trial.get("stage")
                or ""
            )

            phase_type = "practice" if str(block_stage).lower() == "practice" else "main"

            trial_rows.append(
                {
                    "user_id": task_row.get("user_id"),
                    "milestone_id": task_row.get("milestone_id"),
                    "session_id": task_row.get("session_id"),
                    "task_id": task_row.get("task_id"),
                    "task_type": task_type,
                    "trial_index": idx,
                    "block_stage": block_stage,
                    "phase_type": phase_type,
                    "was_correct": outcome.get("wasCorrect"),
                    "expected_response": outcome.get("expectedResponse"),
                    "response": outcome.get("response"),
                    "error_type": outcome.get("errorType"),
                    "was_timeout": outcome.get("wasTimeout"),
                    "raw_trial": str(trial),
                }
            )

    return pd.DataFrame(trial_rows)

def day_suffix(day):
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_readable_datetime(dt):
    if pd.isnull(dt):
        return ""

    day = dt.day
    suffix = day_suffix(day)
    return f"{day}{suffix} {dt.strftime('%B, %Y, %I.%M.%S %p')}"


def make_excel_safe(df):
    df = df.copy()

    for col in df.columns:
        df[col] = df[col].apply(
            lambda x: x.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(x, datetime) and pd.notnull(x) and x.tzinfo is not None
            else (
                x.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(x, datetime) and pd.notnull(x)
                else x
            )
        )


    return df


def clean_scores_dataframe(df_scores):
    df_scores = df_scores.copy()

    columns_to_drop = [
        "score.entityVersion",
        "score.hashedUserId",
        "score.scoreBasisSignature",
        "score.flags.scoreHistory",
        "score.flags.summed_scaled_score",
        "score.flags.scoring_fallback.reason",
        "score.flags.scoring_fallback.primaryFailureMessage",
        "score.flags.scoring_fallback.effectiveConfigId",
        "score.flags.scoring_fallback.primaryConfigId",
    ]

    df_scores = df_scores.drop(
        columns=[c for c in columns_to_drop if c in df_scores.columns],
        errors="ignore",
    )

    if "score.computedAt" in df_scores.columns:
        df_scores["score.computedAt"] = pd.to_datetime(
            df_scores["score.computedAt"], errors="coerce"
        ).apply(format_readable_datetime)

    return df_scores


def rows_to_dataframes(user_rows, milestone_rows, score_rows, session_rows, task_run_rows):
    df_users = pd.DataFrame(user_rows)
    df_milestones = pd.DataFrame(milestone_rows)
    df_scores = pd.DataFrame(score_rows)
    df_sessions = pd.DataFrame(session_rows)

    df_task_runs = pd.DataFrame(task_run_rows)

    if df_task_runs.empty:
        df_task_runs = pd.DataFrame(
            columns=["user_id", "milestone_id", "session_id", "task_id"]
        )

    df_scores = clean_scores_dataframe(df_scores)

    df_task_trials = create_task_trials_dataframe(df_task_runs)

    return df_users, df_milestones, df_scores, df_sessions, df_task_runs, df_task_trials