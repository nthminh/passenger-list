import base64
import io
import json
import os
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import requests
import streamlit as st

# Tải biến môi trường (Secrets trên Streamlit Cloud hoặc .env dưới local)
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


# --- HÀM TRÍCH XUẤT THÔNG TIN HÀNH KHÁCH BẰNG AI ---
def extract_passengers_from_files(uploaded_files: list, key: str) -> list:
    # 1. Tự động lấy danh sách Model khả thi từ Google API
    list_models_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    )
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

    # Nếu không tự lấy được, dùng danh sách tên model chuẩn dự phòng
    if not available_models:
        available_models = [
            "models/gemini-1.5-flash-latest",
            "models/gemini-2.0-flash-exp",
            "models/gemini-1.5-pro-latest",
        ]

    # 2. Đóng gói Prompt và dữ liệu các file đính kèm
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

    # 3. Thử lần lượt từng Model cho đến khi thành công
    last_error_msg = ""
    for model_name in available_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={key}"
        response = requests.post(
            url, headers=headers, data=json.dumps(payload), timeout=60
        )

        if response.status_code == 200:
            res_json = response.json()
            try:
                raw_text = res_json["candidates"][0]["content"]["parts"][0][
                    "text"
                ]
                clean_text = (
                    raw_text.strip()
                    .replace("```json", "")
                    .replace("