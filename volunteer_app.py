import streamlit as st
import pandas as pd
from datetime import datetime, date

# --- CONFIGURATION ---
VOLUNTEER_SHEET_ID = "19FjWUsEeAfQbObZK7MULN8ONvZEhAwSWBGrL9QyNo_s"

VOLUNTEER_TAB_NAMES = {
    "config":                 "Config",
    "open_shifts":            "Open_shifts",
    "volunteers":             "Volunteers",
    "volunteer_registration": "Volunteer_registration",
}

SERVICE_ACCOUNT_FILE = "service_account.json"


# ---------------------------------------------------------------------------
# Volunteer coordination — sheet connection
# ---------------------------------------------------------------------------
def _get_volunteer_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    if not VOLUNTEER_SHEET_ID:
        raise ValueError("VOLUNTEER_SHEET_ID is not configured.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    except Exception:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(VOLUNTEER_SHEET_ID)


def _load_vol_config():
    sh = _get_volunteer_sheet()
    ws = sh.worksheet(VOLUNTEER_TAB_NAMES["config"])
    config = {}
    for row in ws.get_all_values():
        if len(row) >= 2 and row[0].strip():
            val = row[1]
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                val = val[1:-1]
            config[row[0].strip()] = val
    return config


def _load_vol_open_shifts():
    sh = _get_volunteer_sheet()
    ws = sh.worksheet(VOLUNTEER_TAB_NAMES["open_shifts"])
    df = pd.DataFrame(ws.get_all_records())
    if df.empty:
        return df
    df = df[df["Event"].astype(str).str.strip().str.lower() != "placeholder"]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    today = pd.Timestamp(date.today())
    df = df[df["Date"].notna() & (df["Date"] > today)]
    return df.reset_index(drop=True)


def _write_registration(sh, email, shift_info, meets_reqs, added_to_event):
    reg_ws = sh.worksheet(VOLUNTEER_TAB_NAMES["volunteer_registration"])
    event_date = shift_info["Date"].isoformat() if shift_info.get("Date") else ""
    # Columns: Date_of_registration, Email, Event, Type, Meets_reqs, Added_to_event, Shift_duration, Event_date
    reg_ws.append_row([
        date.today().isoformat(),
        email,
        shift_info["Event"],
        shift_info["Type"],
        str(meets_reqs),
        added_to_event,
        str(shift_info.get("Shift_duration", "")),
        event_date,
    ], value_input_option="RAW")


def _find_shift_row(all_values, headers, shift_info):
    """Return (1-indexed row number, row_dict) for the matching open shift, or (None, None)."""
    for i, row_vals in enumerate(all_values[1:], start=2):
        row_dict = dict(zip(headers, row_vals + [""] * max(0, len(headers) - len(row_vals))))
        row_date = pd.to_datetime(row_dict.get("Date", ""), errors="coerce")
        if (row_dict.get("Event") == shift_info["Event"]
                and row_dict.get("Type") == shift_info["Type"]
                and pd.notna(row_date)
                and row_date.date() == shift_info["Date"]):
            return i, row_dict
    return None, None


def _process_signup(shift_info, email, config):
    email = email.strip().lower()
    msg_invalid = config.get("Message_on_invalid_email", "Email not found.")
    msg_approval = config.get("Message_on_shift_approval", "You are signed up!")
    msg_denial = config.get("Message_on_shift_denial", "You are not eligible for this shift.")
    msg_oversubscribed = config.get("Message_on_shift_oversubscribed", "This shift is full.")
    require_active = config.get("require_IS_active", "No").strip().lower() == "yes"
    enforce_training = config.get("enforce_training_reqs", "No").strip().lower() == "yes"

    try:
        sh = _get_volunteer_sheet()

        vol_ws = sh.worksheet(VOLUNTEER_TAB_NAMES["volunteers"])
        vol_df = pd.DataFrame(vol_ws.get_all_records())
        active_col = next((c for c in vol_df.columns if "Active/Inactive" in str(c)), None)
        vol_df["_enorm"] = vol_df["Email"].astype(str).str.strip().str.lower()
        match = vol_df[vol_df["_enorm"] == email]

        if match.empty:
            st.session_state["vol_result_msg"] = msg_invalid
            st.session_state["vol_pending_shift"] = None
            return

        volunteer = match.iloc[0]
        vol_name = str(volunteer["Applicant"]).strip()

        if require_active and active_col:
            if str(volunteer.get(active_col, "")).strip().upper() != "ACTIVE":
                _write_registration(sh, email, shift_info, False, "No")
                st.session_state["vol_result_msg"] = msg_denial
                st.session_state["vol_pending_shift"] = None
                return

        shifts_ws = sh.worksheet(VOLUNTEER_TAB_NAMES["open_shifts"])
        all_values = shifts_ws.get_all_values()
        headers = all_values[0] if all_values else []
        shift_row_num, row_dict = _find_shift_row(all_values, headers, shift_info)

        if shift_row_num is None:
            st.session_state["vol_result_msg"] = "Shift not found. Please refresh and try again."
            return

        signups_raw = row_dict.get("Sign_ups", "") or ""
        if signups_raw.lower() == "nan":
            signups_raw = ""
        signups_list = [s.strip() for s in signups_raw.split(",") if s.strip()]

        if vol_name in signups_list:
            st.session_state["vol_result_msg"] = "You are already registered for this shift."
            st.session_state["vol_pending_shift"] = None
            return

        meets_reqs = True
        if enforce_training:
            req_str = row_dict.get("Training_reqs", "") or ""
            all_req = row_dict.get("All_trainings_required", "No").strip().lower() == "yes"
            req_list = [t.strip() for t in req_str.split(",") if t.strip()]
            roles_raw = str(volunteer.get("Roles Trained For", "") or "")
            vol_roles = [t.strip() for t in roles_raw.split(",") if t.strip() and t.strip().lower() != "nan"]
            if req_list:
                meets_reqs = all(t in vol_roles for t in req_list) if all_req else any(t in vol_roles for t in req_list)

        if not meets_reqs:
            _write_registration(sh, email, shift_info, False, "No")
            st.session_state["vol_result_msg"] = msg_denial
            st.session_state["vol_pending_shift"] = None
            return

        try:
            max_su = int(row_dict.get("Max_sign_ups", 0) or 0)
        except (ValueError, TypeError):
            max_su = 0

        if len(signups_list) >= max_su:
            _write_registration(sh, email, shift_info, True, "No")
            st.session_state["vol_result_msg"] = msg_oversubscribed
            st.session_state["vol_pending_shift"] = None
            return

        new_signups = (signups_raw.strip() + ", " + vol_name) if signups_raw.strip() else vol_name
        shifts_ws.update_cell(shift_row_num, headers.index("Sign_ups") + 1, new_signups)
        _write_registration(sh, email, shift_info, True, "Yes")
        st.session_state["vol_result_msg"] = msg_approval
        st.session_state["vol_pending_shift"] = None

    except Exception as e:
        st.error(f"Signup error: {e}")


def _process_cancellation(shift_info, email, config):
    email = email.strip().lower()
    msg_invalid = config.get("Message_on_invalid_email", "Email not found.")
    msg_removal = config.get("Message_on_shift_removal", "Cancellation processed.")

    try:
        sh = _get_volunteer_sheet()

        vol_ws = sh.worksheet(VOLUNTEER_TAB_NAMES["volunteers"])
        vol_df = pd.DataFrame(vol_ws.get_all_records())
        vol_df["_enorm"] = vol_df["Email"].astype(str).str.strip().str.lower()
        match = vol_df[vol_df["_enorm"] == email]

        if match.empty:
            st.session_state["vol_result_msg"] = msg_invalid
            st.session_state["vol_pending_shift"] = None
            return

        vol_name = str(match.iloc[0]["Applicant"]).strip()

        shifts_ws = sh.worksheet(VOLUNTEER_TAB_NAMES["open_shifts"])
        all_values = shifts_ws.get_all_values()
        headers = all_values[0] if all_values else []
        shift_row_num, row_dict = _find_shift_row(all_values, headers, shift_info)

        if shift_row_num is not None and row_dict is not None:
            signups_raw = row_dict.get("Sign_ups", "") or ""
            if signups_raw.lower() == "nan":
                signups_raw = ""
            signups_list = [s.strip() for s in signups_raw.split(",") if s.strip()]

            if vol_name in signups_list:
                signups_list.remove(vol_name)
                shifts_ws.update_cell(shift_row_num, headers.index("Sign_ups") + 1, ", ".join(signups_list))

                reg_ws = sh.worksheet(VOLUNTEER_TAB_NAMES["volunteer_registration"])
                reg_values = reg_ws.get_all_values()
                if len(reg_values) > 1:
                    reg_hdrs = reg_values[0]
                    try:
                        ei = reg_hdrs.index("Email")
                        evi = reg_hdrs.index("Event")
                    except ValueError:
                        ei = evi = None
                    if ei is not None and evi is not None:
                        hits = [
                            i + 2
                            for i, row in enumerate(reg_values[1:])
                            if (len(row) > max(ei, evi)
                                and row[ei].strip().lower() == email
                                and row[evi] == shift_info["Event"])
                        ]
                        if hits:
                            reg_ws.delete_rows(hits[-1])

        st.session_state["vol_result_msg"] = msg_removal
        st.session_state["vol_pending_shift"] = None

    except Exception as e:
        st.error(f"Cancellation error: {e}")


def render_volunteer_signup():
    for key in ("vol_pending_shift", "vol_pending_action", "vol_result_msg"):
        if key not in st.session_state:
            st.session_state[key] = None

    try:
        config = _load_vol_config()
    except Exception as e:
        st.error(f"Could not load volunteer config: {e}")
        return

    if st.session_state["vol_result_msg"]:
        st.info(st.session_state["vol_result_msg"])
        if st.button("Dismiss", key="vol_dismiss"):
            st.session_state["vol_result_msg"] = None
            st.rerun()

    msg_above = config.get("Message_above_shift_selection", "").strip()
    if msg_above:
        st.markdown(msg_above)

    if st.session_state["vol_pending_shift"] is not None:
        shift_info = st.session_state["vol_pending_shift"]
        action = st.session_state["vol_pending_action"]
        btn_label = "Sign Up" if action == "signup" else "Cancel Registration"
        st.subheader(shift_info["Display"])

        with st.form("vol_action_form"):
            email_input = st.text_input("Your email address:")
            c1, c2 = st.columns(2)
            submitted = c1.form_submit_button(btn_label)
            go_back = c2.form_submit_button("Back to Shifts")

        if submitted:
            if action == "signup":
                _process_signup(shift_info, email_input, config)
            else:
                _process_cancellation(shift_info, email_input, config)
            st.rerun()
        elif go_back:
            st.session_state["vol_pending_shift"] = None
            st.session_state["vol_pending_action"] = None
            st.rerun()
        return

    try:
        df = _load_vol_open_shifts()
    except Exception as e:
        st.error(f"Could not load shifts: {e}")
        return

    if df is None or df.empty:
        st.info("No upcoming shifts available.")
        return

    search = st.text_input("Search shifts:", key="vol_search")
    if search:
        mask = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include="object").columns:
            mask |= df[col].astype(str).str.contains(search, case=False, na=False)
        df = df[mask]

    if df.empty:
        st.info("No shifts match your search.")
        return

    hdr = st.columns([2, 1.5, 1, 2, 1, 1])
    for label, col in zip(["Event / Type", "Date", "Duration", "Spots", "", ""], hdr):
        col.markdown(f"**{label}**")
    st.divider()

    for _, row in df.iterrows():
        signups_raw = str(row.get("Sign_ups", "") or "")
        signups_raw = "" if signups_raw.lower() == "nan" else signups_raw
        signups_list = [s.strip() for s in signups_raw.split(",") if s.strip()]
        try:
            max_su = int(row.get("Max_sign_ups", 0) or 0)
        except (ValueError, TypeError):
            max_su = 0

        date_val = row["Date"]
        date_str = date_val.strftime("%Y-%m-%d") if pd.notna(date_val) else ""
        shift_info = {
            "Event": str(row["Event"]),
            "Type": str(row["Type"]),
            "Date": date_val.date() if pd.notna(date_val) else None,
            "Shift_duration": row.get("Shift_duration", ""),
            "Display": f"{row['Event']} ({row['Type']}) on {date_str}",
        }
        bk = f"{row['Event']}_{row['Type']}_{date_str}".replace(" ", "_")

        cols = st.columns([2, 1.5, 1, 2, 1, 1])
        cols[0].write(f"{row['Event']} / {row['Type']}")
        cols[1].write(date_str)
        cols[2].write(str(row.get("Shift_duration", "")))
        names_str = ", ".join(signups_list) if signups_list else "—"
        cols[3].write(f"{len(signups_list)} / {max_su}  \n{names_str}")

        if cols[4].button("Sign Up", key=f"su_{bk}"):
            st.session_state["vol_pending_shift"] = shift_info
            st.session_state["vol_pending_action"] = "signup"
            st.session_state["vol_result_msg"] = None
            st.rerun()
        if cols[5].button("Cancel", key=f"can_{bk}"):
            st.session_state["vol_pending_shift"] = shift_info
            st.session_state["vol_pending_action"] = "cancel"
            st.session_state["vol_result_msg"] = None
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.set_page_config(page_title="SoundBio Volunteer Signup", layout="centered")
st.title("SoundBio Volunteer Signup")
render_volunteer_signup()
