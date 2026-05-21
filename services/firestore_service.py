import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st



ROOT_COLLECTION = "users"

MILESTONES_COLLECTION = "milestones"

SCORE_COLLECTION = "score"

SESSIONS_COLLECTION = "sessions"

TASK_RUNS_COLLECTION = "task_runs"






def init_firestore():
    if not firebase_admin._apps:
        service_account_info = dict(st.secrets["firebase_service_account"])
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)

    return firestore.client()


def flatten_dict(d, parent_key="", sep="."):
    items = []

    if not isinstance(d, dict):
        return {parent_key: d} if parent_key else {"value": d}

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, str(v)))
        else:
            items.append((new_key, v))

    return dict(items)


def safe_doc_to_dict(doc_snapshot):
    return flatten_dict(doc_snapshot.to_dict() or {})


def fetch_firestore_data():
    db = init_firestore()

    user_rows = []
    milestone_rows = []
    score_rows = []
    session_rows = []
    task_run_rows = []

    user_docs = list(db.collection(ROOT_COLLECTION).stream())

    for user_doc in user_docs:
        user_id = user_doc.id
        user_data = safe_doc_to_dict(user_doc)

        user_row = {"user_id": user_id}
        for k, v in user_data.items():
            user_row[f"user.{k}"] = v
        user_rows.append(user_row)

        milestone_docs = list(
            user_doc.reference.collection(MILESTONES_COLLECTION).stream()
        )

        for milestone_doc in milestone_docs:
            milestone_id = milestone_doc.id
            milestone_data = safe_doc_to_dict(milestone_doc)

            milestone_row = {
                "user_id": user_id,
                "milestone_id": milestone_id,
            }

            for k, v in milestone_data.items():
                milestone_row[f"milestone.{k}"] = v

            milestone_rows.append(milestone_row)

            score_docs = list(
                milestone_doc.reference.collection(SCORE_COLLECTION).stream()
            )

            for score_doc in score_docs:
                score_doc_id = score_doc.id
                score_data = safe_doc_to_dict(score_doc)

                score_row = {
                    "user_id": user_id,
                    "milestone_id": milestone_id,
                    "score_doc_id": score_doc_id,
                }

                for k, v in score_data.items():
                    score_row[f"score.{k}"] = v

                score_rows.append(score_row)

            session_docs = list(
                milestone_doc.reference.collection(SESSIONS_COLLECTION).stream()
            )

            for session_doc in session_docs:
                session_id = session_doc.id
                session_data = safe_doc_to_dict(session_doc)

                session_row = {
                    "user_id": user_id,
                    "milestone_id": milestone_id,
                    "session_id": session_id,
                }

                for k, v in session_data.items():
                    session_row[f"session.{k}"] = v

                session_rows.append(session_row)
                
        #print("SESSION PATH:", session_doc.reference.path)
        #print("SESSION SUBCOLLECTIONS:", [c.id for c in session_doc.reference.collections()])
                
                print("SESSION PATH:", session_doc.reference.path)
                print("SESSION SUBCOLLECTIONS:", [c.id for c in session_doc.reference.collections()])

                task_runs_ref = session_doc.reference.collection("task_runs")
                task_docs = list(task_runs_ref.stream())

                print(
                    f"FOUND {len(task_docs)} TASK RUNS UNDER:",
                    f"{session_doc.reference.path}/task_runs"
                )

                for task_doc in task_docs:
                    print("TASK DOC ID:", task_doc.id)
                    print("TASK DATA:", task_doc.to_dict())

                    task_id = task_doc.id
                    task_data = safe_doc_to_dict(task_doc)

                    task_row = {
                        "user_id": user_id,
                        "milestone_id": milestone_id,
                        "session_id": session_id,
                        "task_id": task_id,
                    }

                    for k, v in task_data.items():
                        task_row[f"task.{k}"] = v

                    task_run_rows.append(task_row)

    return user_rows, milestone_rows, score_rows, session_rows, task_run_rows