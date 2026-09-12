import streamlit as st
import os
import requests
import base64
import io
import time
import hashlib
from google import genai
from google.genai import types
from gtts import gTTS

# ==========================================
# 頁面基本設定
# ==========================================
st.set_page_config(
    page_title="C802 研究原型系統 - 雙向語音AI翻譯輔助工具",
    page_icon="🎙️",
    layout="wide"
)

st.markdown("""
    <style>
    .main { padding-top: 1rem; }
    .stButton>button { width: 100%; height: 3em; font-weight: bold; }
    .headset-box { background-color: #e8f4f8; padding: 15px; border-radius: 10px; border-left: 5px solid #2980b9; margin-top: 10px; }
    .speaker-box { background-color: #fef9e7; padding: 15px; border-radius: 10px; border-left: 5px solid #f39c12; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🎙️ C802 雙向語音 AI 翻譯輔助原型系統 (最新 3.6 Flash 模型版)")
st.caption("計畫名稱：AI翻譯輔助工具對餐飲業前場員工服務自我效能、適應性服務表現與跨語言服務焦慮之影響 (東吳企管 C802)")

# ==========================================
# 側邊欄： API 密鑰設定
# ==========================================
with st.sidebar:
    st.header("⚙️ API 金鑰設定")
    gemini_api_key = st.text_input("Google Gemini API Key", type="password")
    deepl_api_key = st.text_input("DeepL API Key (精準翻譯)", type="password")
    
    st.markdown("---")
    st.header("🧪 實驗情境設定")
    target_lang = st.selectbox("外籍顧客語言", ["English (英文)", "Japanese (日文)", "Korean (韓文)"])

# ==========================================
# 最新可用模型清單 (以 3.6-flash 與 2.5-flash 為主)
# ==========================================
MODELS = ['gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']

# ==========================================
# 工具函式
# ==========================================

def transcribe_audio_gemini(audio_bytes, mime_type, api_key, prompt_msg):
    """使用 Gemini 進行極速語音轉文字"""
    client = genai.Client(api_key=api_key)
    last_error_msg = ""
    
    for model_name in MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type=mime_type,
                    ),
                    prompt_msg
                ]
            )
            if response.text and response.text.strip():
                return response.text.strip(), "SUCCESS"
        except Exception as e:
            err_str = str(e)
            last_error_msg = err_str
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return None, "RATE_LIMIT"
            elif "404" in err_str or "NOT_FOUND" in err_str:
                continue  # 若遇到舊模型 404 自動切換至 3.6-flash 等新模型
            else:
                time.sleep(1)
                continue
                
    return last_error_msg, "ERROR"

def translate_deepl(text, target_lang_code, api_key):
    """DeepL 精準翻譯"""
    if not api_key:
        return f"[模擬翻譯]: {text}"
    url = "https://api-free.deepl.com/v2/translate"
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
    data = {
        "text": [text],
        "target_lang": target_lang_code
    }
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json()["translations"][0]["text"]
    else:
        return f"[DeepL 錯誤]: {response.status_code} - {response.text}"

def generate_free_tts(text, lang_code):
    """免費高速語音合成 (免 API Key)"""
    try:
        tts = gTTS(text=text, lang=lang_code)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except Exception as e:
        st.error(f"語音生成失敗: {e}")
        return None

def get_audio_html(audio_bytes, element_id):
    b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
    return f'''
        <audio id="{element_id}" controls autoplay style="width: 100%;">
            <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
        </audio>
    '''

def handle_rate_limit():
    """專屬冷卻倒數機制"""
    warning_placeholder = st.empty()
    for sec in range(15, 0, -1):
        warning_placeholder.warning(f"⏳ **API 請求暫時滿載！正在自動冷卻中，請等待 {sec} 秒後重新錄音...**")
        time.sleep(1)
    warning_placeholder.info("✅ **冷卻完成！請再次點擊麥克風講話。**")

# ==========================================
# 主介面：左右硬體分流區
# ==========================================
col_customer, col_staff = st.columns(2)

with col_customer:
    st.subheader("👤 顧客端 (Customer Area)")
    st.caption("收音：筆電麥克風 ｜ 播音：桌面藍牙喇叭 (顧客只聽外語)")
    
    customer_audio = st.audio_input("請顧客點擊麥克風講話：", key="customer_mic")
    
    if customer_audio:
        audio_hash = hashlib.md5(customer_audio.read()).hexdigest()
        customer_audio.seek(0)
        
        # 偵測到顧客新一輪錄音
        if st.session_state.get('last_cust_hash') != audio_hash:
            if not gemini_api_key:
                st.error("請在左側欄位輸入 Gemini API Key")
            else:
                with st.spinner("辨識顧客語音中..."):
                    mime_type = customer_audio.type if hasattr(customer_audio, 'type') else 'audio/wav'
                    res, status = transcribe_audio_gemini(
                        customer_audio.read(), 
                        mime_type, 
                        gemini_api_key, 
                        "Please transcribe the exact spoken words in this audio file. Output ONLY the transcribed text."
                    )
                    
                    if status == "RATE_LIMIT":
                        handle_rate_limit()
                    elif status == "SUCCESS" and res:
                        st.session_state['last_cust_hash'] = audio_hash
                        st.session_state['current_cust_text'] = res
                        st.session_state.pop('current_staff_reply', None)
                        st.session_state.pop('speaker_audio_data', None)
                    else:
                        st.error(f"⚠️ 辨識失敗，具體錯誤訊息：{res}")

with col_staff:
    st.subheader("🎧 前場員工面板 (Staff Dashboard)")
    st.caption("接收：藍牙耳機中文語音 ｜ 操作：講中文直接傳至桌面喇叭")
    
    # 1. 顧客講話 ➔ 員工耳機聽中文
    if 'current_cust_text' in st.session_state:
        cust_text = st.session_state['current_cust_text']
        
        if st.session_state.get('translated_cust_hash') != st.session_state.get('last_cust_hash'):
            with st.spinner("DeepL 翻譯中..."):
                zh_translation = translate_deepl(cust_text, "ZH", deepl_api_key)
                st.session_state['current_zh_translation'] = zh_translation
                st.session_state['headset_audio_data'] = generate_free_tts(zh_translation, "zh-tw")
                st.session_state['translated_cust_hash'] = st.session_state.get('last_cust_hash')
                
        if 'current_zh_translation' in st.session_state:
            st.markdown(f"### 💬 顧客原話中文翻譯：")
            st.info(f"**{st.session_state['current_zh_translation']}**")
            
            # 語音僅發送到員工藍牙耳機
            if 'headset_audio_data' in st.session_state and st.session_state['headset_audio_data']:
                st.markdown('<div class="headset-box"><b>🎧 輸出頻道：員工藍牙耳機</b><br>中文朗讀語音已自動送出至耳機：</div>', unsafe_allow_html=True)
                st.components.v1.html(get_audio_html(st.session_state['headset_audio_data'], "headset_audio"), height=80)

    st.markdown("---")
    st.subheader("📤 員工回答頻道")
    
    staff_audio = st.audio_input("請員工點擊麥克風講中文回答：", key="staff_mic")
    
    if staff_audio:
        staff_audio_hash = hashlib.md5(staff_audio.read()).hexdigest()
        staff_audio.seek(0)
        
        # 2. 員工講中文 ➔ 直接翻譯成外語傳至桌面喇叭
        if st.session_state.get('last_staff_hash') != staff_audio_hash:
            if not gemini_api_key:
                st.error("請在左側輸入 Gemini API Key")
            else:
                with st.spinner("辨識員工中文中..."):
                    mime_type = staff_audio.type if hasattr(staff_audio, 'type') else 'audio/wav'
                    res_staff, status_staff = transcribe_audio_gemini(
                        staff_audio.read(), 
                        mime_type, 
                        gemini_api_key, 
                        "請將此音訊中的中文話語轉成標準繁體中文文字，不要回應任何其他說明。"
                    )
                    
                    if status_staff == "RATE_LIMIT":
                        handle_rate_limit()
                    elif status_staff == "SUCCESS" and res_staff:
                        st.session_state['last_staff_hash'] = staff_audio_hash
                        
                        target_code = "EN"
                        tts_lang = "en"
                        if "日文" in target_lang:
                            target_code = "JA"
                            tts_lang = "ja"
                        elif "韓文" in target_lang:
                            target_code = "KO"
                            tts_lang = "ko"
                        
                        with st.spinner("翻譯並傳送至桌面藍牙喇叭..."):
                            translated_back = translate_deepl(res_staff, target_code, deepl_api_key)
                            st.session_state['speaker_audio_data'] = generate_free_tts(translated_back, tts_lang)
                            st.session_state.pop('headset_audio_data', None)
                    else:
                        st.error(f"⚠️ 中文辨識失敗，具體錯誤訊息：{res_staff}")

    # 外語朗讀語音只傳送至桌面藍牙喇叭播放給顧客聽
    if 'speaker_audio_data' in st.session_state and st.session_state['speaker_audio_data']:
        st.markdown('<div class="speaker-box"><b>📢 輸出頻道：桌面藍牙喇叭</b><br>外語朗讀語音已傳送至桌面喇叭播放：</div>', unsafe_allow_html=True)
        st.components.v1.html(get_audio_html(st.session_state['speaker_audio_data'], "speaker_audio"), height=80)

st.markdown("---")
st.caption("東吳大學企業管理學系 施智文教授指導 | 研究對象：餐飲業前場服務員 | 雙向硬體分流測試原型 (最新 3.6 Flash 模型版)")