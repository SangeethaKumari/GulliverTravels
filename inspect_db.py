import sqlite3
import json
import os
import sys

def inspect_database(db_path):
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        return

    print("=" * 60)
    print(f"🔍 INSPECTING SQLITE DATABASE: {db_path}")
    print("=" * 60)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"📋 Tables Found: {', '.join(tables)}\n")

        # 2. Schema details
        for table in tables:
            print(f"--- Schema for Table: {table} ---")
            cursor.execute(f"PRAGMA table_info({table});")
            for col in cursor.fetchall():
                # col: (cid, name, type, notnull, dflt_value, pk)
                pk_marker = "🔑 [PK]" if col[5] else ""
                print(f"  • {col[1]:<20} {col[2]:<10} {pk_marker}")
            print()

        # 3. Sessions State
        if "storage_session" in tables:
            print("--- Stored Sessions (storage_session) ---")
            cursor.execute("SELECT app_name, user_id, id, state, create_time, update_time FROM storage_session;")
            sessions = cursor.fetchall()
            if not sessions:
                print("  (No session records found)")
            for s in sessions:
                app_name, user_id, sid, state_str, ctime, utime = s
                try:
                    state_json = json.loads(state_str) if state_str else {}
                    state_fmt = json.dumps(state_json, indent=2)
                except Exception:
                    state_fmt = state_str
                
                print(f"  • Session ID  : {sid}")
                print(f"    User ID     : {user_id}")
                print(f"    App Name    : {app_name}")
                print(f"    Create Time : {ctime}")
                print(f"    Update Time : {utime}")
                print(f"    State Delta :")
                # Indent lines of state JSON
                for line in str(state_fmt).splitlines():
                    print(f"      {line}")
                print()

        # 4. App States
        if "storage_app_state" in tables:
            print("--- Stored App States (storage_app_state) ---")
            cursor.execute("SELECT app_name, state FROM storage_app_state;")
            app_states = cursor.fetchall()
            for app_name, state_str in app_states:
                print(f"  • App: {app_name} | State: {state_str}")
            print()

        # 5. User States
        if "storage_user_state" in tables:
            print("--- Stored User States (storage_user_state) ---")
            cursor.execute("SELECT app_name, user_id, state FROM storage_user_state;")
            user_states = cursor.fetchall()
            for app_name, user_id, state_str in user_states:
                print(f"  • App: {app_name} | User: {user_id} | State: {state_str}")
            print()

        # 6. Events Log
        if "storage_event" in tables:
            print("--- Recorded Session Events (storage_event) ---")
            cursor.execute("SELECT id, session_id, timestamp, name, type FROM storage_event ORDER BY timestamp ASC;")
            events = cursor.fetchall()
            if not events:
                print("  (No event logs found)")
            for ev in events:
                eid, sid, ts, name, etype = ev
                print(f"  • [{ts}] ID: {eid:<3} | Session: {sid:<15} | Event: {name:<25} ({etype})")
            print()

    except Exception as e:
        print(f"❌ Error reading database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Inspect default database locations
    db_options = ["orchestrator_state.db", "backend/src/travelagent/orchestrator_state.db"]
    for path in db_options:
        if os.path.exists(path):
            inspect_database(path)
            print("\n" + "=" * 60 + "\n")
