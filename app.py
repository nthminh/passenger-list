import base64
import io
import json
import os
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import requests
import streamlit as st

# Tải biến môi trường
load_dotenv()

api_key = ""
try:
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

if not api_key:
    api_key = os.getenv("GEMINI_API_KEY", "")

# --- CẤU HÌNH GIAO DIỆN WEB ---
st.set_page_config(
    page_title="Lập Danh Sách Hành Khách Xuất Bến",
    page_icon="🚢",
    layout="wide",
)

st.title("🚢 Hệ Thống Tự Động Lập Danh Sách Hành Khách Xuất Bến (Mẫu 04)")

# --- SIDEBAR THÔNG TIN TÀU ---
with st.sidebar:
    st.header("⚙️ Thông Tin Tàu & Chuyến Đi")
    if api_key:
        st.success("🟢 AI sẵn sàng xử lý")
    else:
        st.error("🔴 Chưa cấu hình API Key trên Server!")

    ship_name = st.text_input("Tên tàu thuyền", value="San Hô Đỏ")
    ship_code = st.text_input("Số đăng ký", value="HP – 5595")
    ship_owner = st.text_input("Tên chủ tàu", value="Lê Tiến Hậu")
    captain_name = st.text_input("Thuyền trưởng", value="Phạm Văn Viên")
    captain_phone = st.text_input("SĐT Thuyền trưởng", value="0368410805")
    route_name = st.text_input("Tuyến vận tải", value="Tham quan tuyến 2")
    departure_time = st.text_input(
        "Thời gian rời bến", value="09 giờ 00, ngày 02/07/2026"
    )

    st.markdown("---")
    st.markdown(
        "👉 **Hướng dẫn:**\n"
        "1. Tải lên hàng loạt ảnh/PDF CCCD, Passport.\n"
        "2. Nhấn **Quét & Tạo Danh Sách Hành Khách**.\n"
        "3. Chỉnh sửa dữ liệu trực tiếp trên bảng nếu cần và tải về file Excel."
    )


# --- HÀM TRÍCH XUẤT THÔNG TIN HÀNH KHÁCH BẰNG AI (ĐÃ XỬ LÝ CHUỖI URL) ---
def extract_passengers_from_files(uploaded_files: list, key: str) -> list:
    # Làm sạch API Key (loại bỏ hoàn toàn khoảng trắng, ký tự xuống dòng thừa)
    clean_key = str(key).strip().strip('"').strip("'")

    list_models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_key}"
    available_models = []
    try:
        res_models = requests.get(list_models_url, timeout=10)
        if res_models.status_code == 200:
            models_data = res_models.json().get("models", [])
            for m in models_data:
                if "generateContent" in m.get(
                    "supportedGenerationMethods", []
                ):
                    name = m.get("name")
                    if "flash" in name or "pro" in name:
                        available_models.append(name)
    except Exception:
        pass

    if not available_models:
        available_models = [
            "models/gemini-1.5-flash-latest",
            "models/gemini-2.0-flash-exp",
            "models/gemini-1.5-pro-latest",
        ]

    parts = []
    prompt = """
    Phân tích toàn bộ các file hình ảnh/PDF (CCCD, Hộ chiếu) được gửi lên.
    Mỗi ảnh hoặc trang tài liệu có thể là thông tin của 1 hành khách.
    Hãy trích xuất danh sách thông tin hành khách chính xác theo định dạng JSON Array chứa các Object sau:
    [
        {
            "full_name": "Họ và tên đầy đủ (viết hoa chữ cái đầu hoặc viết hoa toàn bộ)",
            "birth_year": "Năm sinh (4 chữ số dạng chuỗi, ví dụ '2005')",
            "gender": "Nam" hoặc "Nữ",
            "nationality": "Quốc tịch (mặc định 'VN' nếu là Việt Nam, hoặc tên/mã quốc gia khác)",
            "address": "Tỉnh/Thành phố hoặc Huyện/Tỉnh nơi thường trú (ví dụ 'Mỹ Đức, Hà Nội')",
            "id_card": "Số CCCD / CMND / Số Hộ chiếu",
            "note": "Điền 'TE' nếu hành khách sinh từ năm 2012 trở lại đây (Trẻ em), ngược lại để chuỗi rỗng ''"
        }
    ]
    Lưu ý:
    - Nếu có nhiều file, trích xuất tất cả hành khách từ tất cả các file.
    - Chỉ trả về duy nhất chuỗi JSON Array thuần túy, không chứa markdown hay bất kỳ câu giải thích nào.
    """
    parts.append({"text": prompt})

    for file in uploaded_files:
        file_bytes = file.getvalue()
        mime_type = file.type if file.type else "application/pdf"
        base64_data = base64.b64encode(file_bytes).decode("utf-8")
        parts.append(
            {"inline_data": {"mime_type": mime_type, "data": base64_data}}
        )

    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": parts}]}

    last_error_msg = ""
    for model_name in available_models:
        # Loại bỏ gạch chéo đầu nếu có để URL không bị gãy
        clean_model = model_name.lstrip("/")
        url = f"https://generativelanguage.googleapis.com/v1beta/{clean_model}:generateContent?key={clean_key}"

        response = requests.post(
            url, headers=headers, data=json.dumps(payload), timeout=60
        )

        if response.status_code == 200:
            res_json = response.json()
            try:
                raw_text = res_json["candidates"][0]["content"]["parts"][0][
                    "text"
                ]
                clean_text = raw_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                clean_text = clean_text.strip()
                return json.loads(clean_text)
            except Exception as e:
                raise Exception(f"Lỗi đọc dữ liệu JSON từ AI: {e}")
        else:
            last_error_msg = response.text

    raise Exception(f"Lỗi kết nối API: {last_error_msg}")

# --- GIAO DIỆN CHÍNH ---
col_upload, col_result = st.columns([1, 2], gap="large")

with col_upload:
    st.subheader("1. Tải lên CCCD / Hộ chiếu")
    uploaded_files = st.file_uploader(
        "Kéo thả hoặc chọn nhiều ảnh/PDF CCCD, Passport của khách",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.info(f"Đã chọn **{len(uploaded_files)}** file tài liệu.")
        if st.button(
            "🚀 Quét & Tạo Danh Sách Hành Khách",
            type="primary",
            use_container_width=True,
        ):
            if not api_key:
                st.error("Chưa cấu hình API Key!")
            else:
                with st.spinner("AI đang quét dữ liệu giấy tờ..."):
                    try:
                        passengers = extract_passengers_from_files(
                            uploaded_files, api_key
                        )
                        st.session_state["passengers_list"] = passengers
                        st.success("Trích xuất danh sách thành công!")
                    except Exception as e:
                        st.error(f"Lỗi xử lý: {e}")

with col_result:
    st.subheader("2. Danh sách hành khách trích xuất (Mẫu 04)")

    if (
        "passengers_list" in st.session_state
        and st.session_state["passengers_list"]
    ):
        data_list = st.session_state["passengers_list"]

        df = pd.DataFrame(data_list)
        df.insert(0, "STT", range(1, len(df) + 1))
        df.rename(
            columns={
                "full_name": "Họ và tên",
                "birth_year": "Năm sinh",
                "gender": "Giới tính",
                "nationality": "Quốc tịch",
                "address": "Địa chỉ",
                "id_card": "Số CCCD / Hộ chiếu",
                "note": "Ghi chú",
            },
            inplace=True,
        )

        edited_df = st.data_editor(
            df, num_rows="dynamic", use_container_width=True
        )

        total_pax = len(edited_df)
        nam_count = (edited_df["Giới tính"] == "Nam").sum()
        nu_count = (edited_df["Giới tính"] == "Nữ").sum()
        vn_count = (edited_df["Quốc tịch"] == "VN").sum()
        nn_count = total_pax - vn_count

        st.markdown(
            f"📊 **Tổng số hành khách:** {total_pax} người | **Nam:** {nam_count} | **Nữ:** {nu_count} | **Việt Nam:** {vn_count} | **Nước ngoài:** {nn_count}"
        )

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            edited_df.to_excel(
                writer, index=False, sheet_name="Danh_Sach_Hanh_Khach"
            )

        st.download_button(
            label="📥 Tải về Danh sách Hành khách (.xlsx)",
            data=output.getvalue(),
            file_name=f"Danh_sach_hanh_khach_{ship_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )