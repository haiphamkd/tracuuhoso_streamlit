import streamlit as st
import pandas as pd
import os
import re
import json
import time
import psycopg2 
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone

# --- 1. CẤU HÌNH TRANG & CSS ---
st.set_page_config(page_title="Hệ Thống Tra Cứu Drive", page_icon="📂", layout="wide")

# --- QUẢN LÝ SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = 'guest'
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
if 'is_running' not in st.session_state:
    st.session_state.is_running = False

# --- HÀM HỖ TRỢ CẤU HÌNH ---
DATA_FILE = "danh_sach_thu_muc.csv"
CONFIG_FILE = "config.json"
SESSION_FILE = "session.json"
DEFAULT_KEY_FILE = "service_account.json"
DEFAULT_ADMIN_PASS = "admin" 
DEFAULT_DB_CONFIG = {
    "host": "26.31.124.134",
    "port": "5432",
    "database": "phongkhamtmh",
    "user": "medisoft",
    "password": "Links1920"
}

# --- XỬ LÝ LƯU PHIÊN ĐĂNG NHẬP ---
def save_login_session(user_role):
    try:
        session_data = {"logged_in": True, "user_role": user_role, "login_time": str(datetime.now())}
        with open(SESSION_FILE, 'w') as f: json.dump(session_data, f)
    except: pass

def check_login_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                if data.get("logged_in"): return True, data.get("user_role")
        except: pass
    return False, "guest"

def clear_login_session():
    if os.path.exists(SESSION_FILE):
        try: os.remove(SESSION_FILE)
        except: pass

# Init State
is_logged_in, role = check_login_session()
if not st.session_state.logged_in and is_logged_in:
    st.session_state.logged_in = True
    st.session_state.user_role = role

# --- HÀM HỖ TRỢ ---
def get_now_vn(): return datetime.utcnow() + timedelta(hours=7)

def convert_drive_time_to_vn(iso_str):
    try:
        dt_utc = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt_utc.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
    except: return None

def load_config():
    config = {"drive_url": "", "key_file_path": DEFAULT_KEY_FILE, "admin_password": DEFAULT_ADMIN_PASS, "db_config": DEFAULT_DB_CONFIG}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
            config.update(saved)
            if "db_config" not in config: config["db_config"] = DEFAULT_DB_CONFIG
    elif hasattr(st, "secrets"):
        if "general" in st.secrets:
            config["drive_url"] = st.secrets["general"].get("drive_url", "")
            config["admin_password"] = st.secrets["general"].get("admin_password", DEFAULT_ADMIN_PASS)
        if "db_config" in st.secrets:
            config["db_config"] = dict(st.secrets["db_config"])
    return config

def save_config(url, key_path, password, db_config):
    config = {"drive_url": url, "key_file_path": key_path, "admin_password": password, "db_config": db_config}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f)

# --- CSS CHUNG ---
st.markdown("""
    <style>
    header[data-testid="stHeader"] { height: 0px; background: transparent; }
    
    /* 1. Reset nền trang về mặc định (Trắng) */
    .block-container { 
        padding-top: 0rem !important; 
        padding-bottom: 2rem !important; 
        background-color: transparent !important; 
    }
    
    /* 2. Chỉ đổi màu nền ô tìm kiếm (Xanh nhạt) */
    .stTextInput input {
        background-color: #e3f2fd !important; /* Xanh nhạt */
        border: 1px solid #90caf9 !important;
        color: #0d47a1 !important;
        font-weight: 500;
    }
    
    /* 3. Tiêu đề bảng màu xanh đậm */
    [data-testid="stDataFrame"] thead th {
        background-color: #1565c0 !important; /* Xanh đậm */
        color: white !important;
    }
    
    h1 { margin-top: -1rem !important; padding-bottom: 1rem !important; font-size: 2rem !important; color: #0d47a1 !important; z-index: 999; }
    div[data-testid="stVerticalBlock"] > div:has(div.sticky-marker) {
        position: sticky; top: 0rem; background-color: white; z-index: 990;
        padding-top: 10px; padding-bottom: 15px; border-bottom: 1px solid #e3f2fd;
    }
    .sticky-marker { display: none; }
    [data-testid="stSidebar"] { min-width: 400px !important; max-width: 400px !important; background-color: #f8fbff; border-right: 1px solid #e1e9f5; }
    [data-testid="stSidebar"] .stButton button, [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
        background-color: #1976d2 !important; color: white !important; border: none !important; border-radius: 8px;
        height: 45px !important; font-weight: 600; width: 100% !important; box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }
    [data-testid="stSidebar"] .stButton button:hover, [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:hover {
        background-color: #1565c0 !important; box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .stop-btn button { background-color: #d32f2f !important; color: white !important; }
    .stop-btn button:hover { background-color: #b71c1c !important; }
    [data-testid="stDataFrame"] { border: 1px solid #dbe4ef; border-radius: 8px; overflow: hidden; }
    
    .logout-btn button {
        background-color: white !important; color: #d32f2f !important; border: 2px solid #ef9a9a !important; margin-top: 5px !important; box-shadow: none !important;
    }
    .logout-btn button:hover { background-color: #ffebee !important; border-color: #d32f2f !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. LOGIC GOOGLE DRIVE ---
def extract_folder_id(url):
    if not url: return None
    patterns = [r'folders/([-a-zA-Z0-9_]+)', r'id=([-a-zA-Z0-9_]+)']
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: return match.group(1)
    return url

def get_drive_service(key_file_path):
    if os.path.exists(key_file_path):
        try:
            creds = service_account.Credentials.from_service_account_file(
                key_file_path, scopes=['https://www.googleapis.com/auth/drive.readonly'])
            return build('drive', 'v3', credentials=creds), None
        except Exception as e: return None, f"⚠️ Lỗi File Key: {str(e)}"
    elif hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            creds_info = dict(st.secrets["gcp_service_account"])
            creds = service_account.Credentials.from_service_account_info(
                creds_info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
            return build('drive', 'v3', credentials=creds), None
        except Exception as e: return None, f"⚠️ Lỗi Secrets Key: {str(e)}"
    return None, "⚠️ Không tìm thấy Key (File hoặc Secrets)"

def count_items_in_folder(service, folder_id):
    folder_count = 0; file_count = 0; page_token = None
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        while True:
            response = service.files().list(
                q=query, fields='nextPageToken, files(mimeType)',
                pageToken=page_token, pageSize=1000, supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            for file in response.get('files', []):
                if file['mimeType'] == 'application/vnd.google-apps.folder': folder_count += 1
                else: file_count += 1
            page_token = response.get('nextPageToken', None)
            if page_token is None: break
    except Exception: pass
    return folder_count, file_count

def fetch_folders_smart(service, folder_id, existing_data_dict):
    results = []
    page_token = None
    status_container = st.empty()
    
    # Thống kê
    stats = {"new": 0, "update": 0, "skip": 0}
    
    try:
        query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        while True:
            if not st.session_state.get('is_running', False):
                status_container.warning("🛑 Đã dừng cập nhật."); break

            # Lấy thêm trường modifiedTime để so sánh
            response = service.files().list(
                q=query, spaces='drive',
                fields='nextPageToken, files(id, name, webViewLink, createdTime, modifiedTime)',
                pageToken=page_token, supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            
            files_list = response.get('files', [])
            
            for i, file in enumerate(files_list):
                if not st.session_state.get('is_running', False): break 

                f_id = file.get('id'); f_name = file.get('name')
                created_time_vn = convert_drive_time_to_vn(file.get('createdTime'))
                
                # Lấy thời gian sửa đổi hiện tại trên Drive
                current_mod_time = file.get('modifiedTime')
                
                # Giá trị mặc định
                f_c = 0; fl_c = 0
                
                # LOGIC SMART UPDATE
                if f_id in existing_data_dict:
                    old_data = existing_data_dict[f_id]
                    saved_mod_time = old_data.get('ModifiedTimeDrive')
                    
                    if saved_mod_time == current_mod_time:
                        # Cũ & Không đổi -> SKIP (Lấy số liệu cũ)
                        f_c = old_data.get('Số Thư Mục Con', 0)
                        fl_c = old_data.get('Số File', 0)
                        status_container.text(f"⏩ Đã có (Không đổi): {f_name}")
                        stats["skip"] += 1
                    else:
                        # Cũ & Có thay đổi -> SCAN LẠI
                        status_container.info(f"🔄 Có thay đổi: {f_name} -> Đang cập nhật...")
                        f_c, fl_c = count_items_in_folder(service, f_id)
                        stats["update"] += 1
                else:
                    # Mới tinh -> SCAN MỚI
                    status_container.info(f"🆕 Mới: {f_name} -> Đang phân tích...")
                    f_c, fl_c = count_items_in_folder(service, f_id)
                    stats["new"] += 1

                results.append({
                    'ID': f_id, 'Mã bệnh nhân': f_name, 'Link Truy Cập': file.get('webViewLink'),
                    'Ngày Tạo': created_time_vn, 
                    'Số Thư Mục Con': f_c, 'Số File': fl_c,
                    'ModifiedTimeDrive': current_mod_time # Lưu lại thời gian sửa đổi mới nhất
                })
            
            page_token = response.get('nextPageToken', None)
            if page_token is None or not st.session_state.get('is_running', False): break
        
        if st.session_state.get('is_running', False):
            msg = f"✅ Hoàn tất! {stats['new']} Mới | {stats['update']} Cập nhật | {stats['skip']} Bỏ qua."
            status_container.success(msg)
        time.sleep(2); status_container.empty()
        return results, stats["new"] + stats["update"]
        
    except Exception as e: st.error(f"API Error: {e}"); return [], 0

# --- 3. DB LOGIC ---
def fetch_patient_info_from_db(patient_ids, db_config):
    if not patient_ids: return {}
    pmap = {}; conn = None
    try:
        conn = psycopg2.connect(
            user=db_config['user'], password=db_config['password'],
            host=db_config['host'], port=db_config['port'], database=db_config['database'])
        cur = conn.cursor()
        chunk = 500
        for i in range(0, len(patient_ids), chunk):
            c = patient_ids[i:i+chunk]
            p = ','.join(['%s']*len(c))
            cur.execute(f"SELECT mabn, hoten, namsinh FROM medibv.btdbn WHERE mabn IN ({p})", tuple(c))
            for r in cur.fetchall(): pmap[str(r[0]).strip()] = {'hoten':r[1], 'namsinh':r[2]}
    except Exception as e: st.error(f"DB Error: {e}")
    finally:
        if conn: conn.close()
    return pmap

# --- 4. DATA OPS ---
def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE, dtype={'ID':str, 'Link Truy Cập':str, 'Năm Sinh':str, 'ModifiedTimeDrive': str})
        if 'Tên Thư Mục' in df.columns: df.rename(columns={'Tên Thư Mục':'Mã bệnh nhân'}, inplace=True)
        if 'Ngày Cập Nhật' in df.columns: df['Ngày Cập Nhật'] = pd.to_datetime(df['Ngày Cập Nhật'], errors='coerce')
        if 'Ngày Tạo' in df.columns: df['Ngày Tạo'] = pd.to_datetime(df['Ngày Tạo'], errors='coerce')
        
        # Đảm bảo đủ cột
        for c in ['Tên Bệnh Nhân','Năm Sinh', 'ModifiedTimeDrive']: 
            if c not in df.columns: df[c]=""
        for c in ['Số Thư Mục Con','Số File']: 
            if c not in df.columns: df[c]=0
        return df
    return pd.DataFrame(columns=['ID','Mã bệnh nhân','Tên Bệnh Nhân','Năm Sinh','Số Thư Mục Con','Số File','Link Truy Cập','Ngày Cập Nhật','Ngày Tạo', 'ModifiedTimeDrive'])

def save_data_upsert(new_df):
    curr = load_data()
    new_df['Ngày Cập Nhật'] = get_now_vn()
    new_df['Mã bệnh nhân'] = new_df['Mã bệnh nhân'].astype(str); new_df['ID'] = new_df['ID'].astype(str)
    
    if new_df.empty: return curr, 0
    if curr.empty: final = new_df; added = len(new_df)
    else:
        # Xóa những dòng cũ đã có trong new_df để thay bằng dòng mới (cập nhật)
        new_ids = new_df['ID'].unique()
        old_kept = curr[~curr['ID'].isin(new_ids)]
        final = pd.concat([new_df, old_kept], ignore_index=True)
        
        # Tính số lượng mới thực sự (không tính update)
        added = len(new_df[~new_df['ID'].isin(curr['ID'].unique())])
    
    final[['Số Thư Mục Con','Số File']] = final[['Số Thư Mục Con','Số File']].fillna(0).astype(int)
    final.to_csv(DATA_FILE, index=False, date_format="%Y-%m-%d %H:%M:%S")
    return load_data(), added

def logout_user():
    clear_login_session()
    st.session_state.logged_in = False
    st.session_state.user_role = "guest"
    st.rerun()

# --- 5. UI ---
if not st.session_state.logged_in:
    st.markdown("""<style>.stApp{background-color:#f1f5f9}.stTextInput input{background:white;border:1px solid #cbd5e1;height:45px}.login-btn button{background:#2563eb;color:white;font-weight:600}.login-btn button:hover{background:#1d4ed8}.guest-btn button{background:white;color:#2563eb;border:1px solid #2563eb;font-weight:600}.guest-btn button:hover{background:#eff6ff}</style>""", unsafe_allow_html=True)
    c1,cm,c2 = st.columns([1,0.6,1])
    with cm:
        st.markdown("<div style='height:80px'></div><div style='text-align:center;margin-bottom:30px'><h2 style='color:#1e293b;margin:0;font-weight:800'>HỆ THỐNG TRA CỨU</h2><p style='color:#64748b;margin-top:5px'>Kho dữ liệu Nội soi & Hình ảnh</p></div>", unsafe_allow_html=True)
        u = st.text_input("Tên đăng nhập", placeholder="Nhập tên đăng nhập")
        p = st.text_input("Mật khẩu", type="password", placeholder="Nhập mật khẩu")
        st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
        b1,b2 = st.columns(2)
        with b1:
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            if st.button("🔐 Đăng Nhập", use_container_width=True):
                cfg = load_config()
                if u=="admin" and p==cfg.get("admin_password", DEFAULT_ADMIN_PASS):
                    save_login_session("admin")
                    st.session_state.logged_in=True; st.session_state.user_role="admin"; st.rerun()
                else: st.toast("Sai thông tin!", icon="❌")
            st.markdown('</div>', unsafe_allow_html=True)
        with b2:
            st.markdown('<div class="guest-btn">', unsafe_allow_html=True)
            if st.button("👤 Khách (Xem)", use_container_width=True):
                save_login_session("guest")
                st.session_state.logged_in=True; st.session_state.user_role="guest"; st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

df = load_data()
current_config = load_config()

with st.sidebar:
    role = "QUẢN TRỊ VIÊN" if st.session_state.user_role == 'admin' else "KHÁCH"
    st.markdown(f"<h3 style='text-align:center;color:#1565c0'>{role}</h3><hr>", unsafe_allow_html=True)
    
    if st.session_state.user_role == 'admin':
        with st.expander("🛠️ Cấu Hình Kết Nối"):
            uk = st.file_uploader("Upload Key (JSON)", type=['json'], label_visibility="collapsed")
            if uk: 
                with open(DEFAULT_KEY_FILE, "wb") as f: f.write(uk.getbuffer())
                st.success("Lưu Key thành công!")
            st.caption(f"Key Local: {'✅ Có' if os.path.exists(DEFAULT_KEY_FILE) else '⚠️ Dùng Secrets'}")
            url = st.text_input("Link Drive", value=current_config.get("drive_url",""))
            st.caption("Database:")
            db = current_config.get("db_config", DEFAULT_DB_CONFIG)
            h = st.text_input("Host", db['host']); pt = st.text_input("Port", db['port'])
            us = st.text_input("User", db['user']); ps = st.text_input("Pass", db['password'], type="password")
            dbn = st.text_input("DB Name", db['database'])
            if st.button("💾 Lưu Cấu Hình", use_container_width=True):
                save_config(url, DEFAULT_KEY_FILE, current_config.get("admin_password"), {"host":h,"port":pt,"user":us,"password":ps,"database":dbn})
                st.toast("Đã lưu!", icon="✅"); st.rerun()

        with st.expander("🔄 Quản Lý Dữ Liệu", expanded=True):
            st.info("Cập nhật danh sách mới từ Drive.")
            bp = st.empty()
            if not st.session_state.is_running:
                if bp.button("🚀 Cập nhật ngay", use_container_width=True):
                    st.session_state.is_running = True; st.rerun()
            else:
                st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
                if bp.button("🛑 Dừng cập nhật", use_container_width=True):
                    st.session_state.is_running = False; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
                
                fid = extract_folder_id(current_config.get("drive_url",""))
                svc, err = get_drive_service(DEFAULT_KEY_FILE)
                if fid and svc:
                    # Lấy dữ liệu cũ và index theo ID để tra cứu nhanh
                    ex_dict = df.set_index('ID').to_dict('index') if not df.empty else {}
                    
                    # FETCH SMART
                    ndata, cnt = fetch_folders_smart(svc, fid, ex_dict)
                    
                    if ndata and st.session_state.is_running:
                        # Logic tìm những ID cần query DB (Mới hoặc chưa có tên)
                        q_ids = []
                        for it in ndata:
                            old = ex_dict.get(it['ID'])
                            # Nếu là item mới HOẶC item cũ nhưng chưa có tên
                            if not old or not old.get('Tên Bệnh Nhân') or old.get('Tên Bệnh Nhân')=="Chưa tìm thấy":
                                q_ids.append(it['Mã bệnh nhân'])
                        
                        p_info = {}
                        if q_ids:
                            with st.spinner(f"Đang tra cứu DB cho {len(q_ids)} hồ sơ..."):
                                p_info = fetch_patient_info_from_db(list(set(q_ids)), current_config.get("db_config", DEFAULT_DB_CONFIG))
                        
                        final = []
                        for it in ndata:
                            ma = it['Mã bệnh nhân']
                            if ma in p_info: 
                                it['Tên Bệnh Nhân']=p_info[ma]['hoten']
                                it['Năm Sinh']=p_info[ma]['namsinh']
                            else:
                                # Nếu không tìm thấy trong DB, cố gắng giữ lại thông tin cũ
                                o = ex_dict.get(it['ID'], {})
                                it['Tên Bệnh Nhân']=o.get('Tên Bệnh Nhân',"Chưa tìm thấy")
                                it['Năm Sinh']=o.get('Năm Sinh',"")
                            final.append(it)
                        
                        save_data_upsert(pd.DataFrame(final))
                        st.success("Cập nhật hoàn tất!")
                    st.session_state.is_running = False; st.rerun()
                else: st.error(err or "Lỗi Drive"); st.session_state.is_running=False; st.rerun()

        with st.expander("🔐 Đổi Mật Khẩu"):
            with st.form("pf"):
                o = st.text_input("Mật khẩu cũ", type="password")
                n = st.text_input("Mật khẩu mới", type="password")
                c = st.text_input("Nhập lại", type="password")
                if st.form_submit_button("💾 Lưu Thay Đổi", use_container_width=True):
                    if o == current_config.get("admin_password") and n==c and n:
                        save_config(current_config.get("drive_url"), DEFAULT_KEY_FILE, n, current_config.get("db_config"))
                        st.success("Đổi thành công!")
                    else: st.error("Thông tin không hợp lệ")

    st.markdown('<div class="logout-btn">', unsafe_allow_html=True)
    if st.button("🚪 Đăng Xuất", use_container_width=True): logout_user()
    st.markdown('</div>', unsafe_allow_html=True)

sticky = st.container()
with sticky:
    st.markdown('<div class="sticky-marker"></div>', unsafe_allow_html=True)
    st.title("TRA CỨU HỒ SƠ & TÀI LIỆU")
    if not df.empty:
        c1,c2,c3 = st.columns([8,0.5,2.5])
        with c1: search = st.text_input("Tìm kiếm", value=st.session_state.search_query, placeholder="Nhập mã, tên, năm sinh...", label_visibility="collapsed", key="s_input", on_change=lambda: st.session_state.update(search_query=st.session_state.s_input))
        with c2: 
            if st.button("❌"): st.session_state.search_query=""; st.rerun()
        with c3: st.markdown(f"<div style='color:#1565c0;font-weight:bold;padding-top:10px'>Tổng: {len(df)} hồ sơ</div>", unsafe_allow_html=True)

if not df.empty:
    q = st.session_state.search_query
    dff = df[df.apply(lambda r: q.lower() in str(r.values).lower(), axis=1)].copy() if q else df.copy()
    dff['Link (Copy)'] = dff['Link Truy Cập']
    
    cfg = {
        "Mã bệnh nhân": st.column_config.TextColumn("Mã BN", width="small", required=True),
        "Tên Bệnh Nhân": st.column_config.TextColumn("Họ Tên bệnh nhân", width=None),
        "Năm Sinh": st.column_config.TextColumn("Năm Sinh", width=None),
        "Ngày Tạo": st.column_config.DatetimeColumn("Ngày tạo", format="DD/MM/YYYY HH:mm", width=None),
        "Số Thư Mục Con": st.column_config.NumberColumn("Thư mục", format="%d 📂", width="None"),
        "Số File": st.column_config.NumberColumn("File", format="%d 📄", width="None"),
        "Link Truy Cập": st.column_config.LinkColumn("Truy Cập", display_text="Mở Link 🔗", width=None),
        "ID": st.column_config.TextColumn("ID Drive", width="small"),
        "Link (Copy)": st.column_config.TextColumn("Link (Copy)", width="large", help="Bấm vào để copy nhanh"),
    }
    od = ["Mã bệnh nhân", "Tên Bệnh Nhân", "Năm Sinh", "Ngày Tạo", "Số Thư Mục Con", "Số File", "Link Truy Cập", "ID", "Link (Copy)"]
    dis = [c for c in od if c != "Link (Copy)"]

    st.data_editor(dff, column_config=cfg, column_order=od, hide_index=True, use_container_width=True, height=750, disabled=dis)
    if st.session_state.user_role=='admin': st.download_button("📥 Tải CSV", dff.to_csv(index=False).encode('utf-8'), 'ds.csv')
else: st.warning("📭 Chưa có dữ liệu.")