import streamlit as st
from google import genai 
import datetime 
import pandas as pd
import json
import math
import os

# ==============================================================================
# 🔴 [API 연동 지점] 
# ==============================================================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=GEMINI_API_KEY) 

# ==============================================================================
# 💾 데이터 영구 저장 및 불러오기 설정
# ==============================================================================
DATA_FILE = "assignments_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for assign in data:
                assign['deadline'] = datetime.datetime.strptime(assign['deadline'], "%Y-%m-%d").date()
            return data
    return []

def save_data(data):
    def date_converter(obj):
        if isinstance(obj, datetime.date):
            return obj.strftime("%Y-%m-%d")
        raise TypeError("Type not serializable")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=date_converter)

# --- 세션 상태 초기화 ---
if 'assignments' not in st.session_state:
    st.session_state.assignments = load_data() 
if 'user_history_multiplier' not in st.session_state:
    st.session_state.user_history_multiplier = 1.0

def sync_task(assign_id, task_idx, key_name):
    """체크박스가 클릭되는 즉시 세션 상태를 저장 파일과 동기화합니다."""
    new_val = st.session_state[key_name]
    for a in st.session_state.assignments:
        if a['id'] == assign_id:
            a['tasks'][task_idx]['completed'] = new_val
            break
    save_data(st.session_state.assignments)


# ==============================================================================
# 🤖 AI 과제 분석 호출 함수
# ==============================================================================
def analyze_assignment_with_ai(title, subject, desc, file_text=""):
    prompt = f"""
    당신은 대학생의 과제를 분석해주는 AI 플래너입니다. 아래 과제 정보를 분석하여 반드시 JSON 형식으로만 답변하세요.
    
    [과제 정보]
    과제명: {title}
    과목명: {subject}
    과제 설명 및 공지: {desc}
    첨부파일 내용: {file_text}
    
    [JSON 출력 형식]
    {{
        "task_type": "과제 유형",
        "tasks": [
            {{"name": "세부 태스크명", "estimated_hours": 1.5}}
        ],
        "total_estimated_hours": 5.0,
        "checklist": [
            "제출 전 체크해야 할 양식 및 조건 1"
        ]
    }}
    JSON 외의 다른 설명은 절대 추가하지 마세요.
    """
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
        )
        cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(cleaned_text)
    except Exception as e:
        st.error(f"AI 분석 중 오류가 발생했습니다: {e}")
        return None


# ==============================================================================
# 🎨 UI 레이아웃 시작
# ==============================================================================
st.set_page_config(page_title="AI 과제 플래너", layout="wide")
st.title("📚 AI 과제 플래너")

with st.sidebar:
    st.header("📝 새 과제 등록")
    new_title = st.text_input("과제명", placeholder="예: 챕터 1~3 분개 및 재무제표 작성")
    new_subject = st.text_input("과목명", placeholder="예: 전산회계")
    new_deadline = st.date_input("마감일", min_value=datetime.date.today())
    new_desc = st.text_area("과제 설명 및 교수님 공지", placeholder="과제 세부 내용이나 제한사항을 입력하세요.")
    
    uploaded_file = st.file_uploader("과제 파일 업로드 (선택)", type=['pdf', 'docx', 'txt', 'hwp', 'png', 'jpg'])
    
    if st.button("➕ 새 과제 분석 및 등록", type="primary", use_container_width=True):
        if new_title and new_subject:
            with st.spinner('AI가 과제를 분석하고 세부 계획을 세우는 중입니다...'):
                file_text = "업로드된 파일 텍스트" if uploaded_file else ""
                ai_result = analyze_assignment_with_ai(new_title, new_subject, new_desc, file_text)
                
                if ai_result:
                    new_assignment = {
                        "id": len(st.session_state.assignments) + 1,
                        "title": new_title,
                        "subject": new_subject,
                        "deadline": new_deadline,
                        "type": ai_result.get("task_type", "기타"),
                        "tasks": [{"name": t["name"], "estimated_hours": t["estimated_hours"], "completed": False} for t in ai_result.get("tasks", [])],
                        "base_total_hours": ai_result.get("total_estimated_hours", 0),
                        "checklist": ai_result.get("checklist", [])
                    }
                    st.session_state.assignments.append(new_assignment)
                    save_data(st.session_state.assignments) 
                    st.session_state.assign_selector = new_title
                    st.success("과제가 성공적으로 분석되어 추가되었습니다!")
        else:
            st.warning("과제명과 과목명을 입력해주세요.")


# --- 메인 대시보드 ---
if not st.session_state.assignments:
    st.info("👈 왼쪽 사이드바에서 ➕ 버튼을 눌러 새로운 과제를 등록해주세요.")
else:
    # --- 데이터 사전 처리 및 분류 ---
    now = datetime.datetime.now()
    today = now.date()
    
    active_assignments = []
    completed_assignments = []

    for assign in st.session_state.assignments:
        # 시간 및 날짜 계산
        days_left = (assign['deadline'] - today).days
        assign['days_left'] = days_left if days_left >= 0 else 0
        assign['adjusted_total_hours'] = assign['base_total_hours'] * st.session_state.user_history_multiplier
        
        # 마감시간까지 남은 '시간(Hour)' 계산 (마감일 밤 11시 59분 기준)
        deadline_dt = datetime.datetime.combine(assign['deadline'], datetime.time(23, 59, 59))
        hours_left = int((deadline_dt - now).total_seconds() / 3600)
        assign['hours_left'] = hours_left

        # 위험도 계산
        available_hours = assign['days_left'] * 4 
        if available_hours >= assign['adjusted_total_hours'] * 1.5:
            assign['risk'] = "🟢 안전"
        elif available_hours >= assign['adjusted_total_hours']:
            assign['risk'] = "🟡 주의"
        else:
            assign['risk'] = "🔴 위험"

        # 진행률 계산
        completed_tasks = sum(1 for t in assign['tasks'] if t['completed'])
        total_tasks = len(assign['tasks'])
        progress_pct = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        assign['progress_pct'] = progress_pct

        # 👇 요구사항 1: 완료된 과제와 진행 중인 과제 분류
        if progress_pct == 100:
            completed_assignments.append(assign)
        else:
            active_assignments.append(assign)

    # 우선순위 정렬 (마감일 오름차순, 소요시간 내림차순)
    active_assignments = sorted(active_assignments, key=lambda x: (x['days_left'], -x['adjusted_total_hours']))

    # 👇 요구사항 2: 긴급 알림 기능 (마감 48시간 이내인 미완료 과제)
    for assign in active_assignments:
        if 0 <= assign['hours_left'] <= 48:
            st.error(f"🚨 **[{assign['title']}]** 마감시간까지 **{assign['hours_left']}시간** 남았어!! 진짜 해야 돼! 🔥")
        elif assign['hours_left'] < 0:
            st.error(f"☠️ **[{assign['title']}]** 마감 시간이 지났습니다. 서둘러 마무리하세요!")

    col1, col2 = st.columns([2, 1])

    with col1:
        # 탭을 사용하여 화면 분리
        tab1, tab2 = st.tabs(["🔥 진행 중인 과제", "✅ 지난(완료된) 과제"])
        
        with tab1:
            if not active_assignments:
                st.success("진행 중인 과제가 없습니다. 여유를 즐기세요! ☕")
            
            for assign in active_assignments:
                with st.expander(f"[{assign['risk']}] {assign['title']} - {assign['subject']} (마감 D-{assign['days_left']})", expanded=True):
                    st.caption(f"과제 유형: {assign['type']} | AI 예상 시간: {assign['base_total_hours']}h | 🕒 나의 예상 소요 시간(보정됨): {assign['adjusted_total_hours']:.1f}h")
                    st.progress(assign['progress_pct'], text=f"진행률: {assign['progress_pct']}%")
                    
                    st.write("**작업량 시각화 (1블록 = 30분):**")
                    for task in assign['tasks']:
                        adj_task_time = task['estimated_hours'] * st.session_state.user_history_multiplier
                        blocks = "■" * max(1, math.ceil(adj_task_time * 2))
                        st.markdown(f"**{task['name']}** ({adj_task_time:.1f}h)<br><span style='color:#4CAF50;'>{blocks}</span>", unsafe_allow_html=True)
                    
                    st.divider()
                    st.write("**세부 태스크 진행**")
                    for i, task in enumerate(assign['tasks']):
                        key_name = f"task_{assign['id']}_{i}"
                        st.checkbox(task['name'], value=task['completed'], key=key_name, on_change=sync_task, args=(assign['id'], i, key_name))

        with tab2:
            if not completed_assignments:
                st.info("아직 완료된 과제가 없습니다. 첫 번째 과제를 끝내보세요! 💪")
            
            for assign in completed_assignments:
                with st.expander(f"🎉 {assign['title']} - {assign['subject']} (완료)", expanded=False):
                    st.success("모든 태스크를 완료했습니다! 고생하셨습니다. 👏")
                    st.progress(100, text="진행률: 100%")
                    for task in assign['tasks']:
                        st.checkbox(task['name'], value=True, disabled=True, key=f"done_{assign['id']}_{task['name']}")

    with col2:
        st.subheader("💡 오늘 해야 할 일")
        today_tasks_shown = False
        for assign in active_assignments:
            incomplete_tasks = [t['name'] for t in assign['tasks'] if not t['completed']]
            if assign['days_left'] <= 3 and incomplete_tasks: 
                st.info(f"**{assign['title']}**\n\n👉 {incomplete_tasks[0]}")
                today_tasks_shown = True
                break
        if not today_tasks_shown:
            st.success("오늘 급하게 처리할 태스크가 없습니다! 🎉")

        st.subheader("📋 제출 전 최종 점검")
        target_assign_title = st.selectbox(
            "과제 선택", 
            [a['title'] for a in active_assignments], # 완료된 과제는 제외
            key="assign_selector" 
        )
        selected_assign = next((a for a in active_assignments if a['title'] == target_assign_title), None)
        
        if selected_assign and selected_assign['checklist']:
            st.write("교수님 공지 및 양식 기반 자동 생성 체크리스트")
            all_checked = True 
            for i, item in enumerate(selected_assign['checklist']):
                is_checked = st.checkbox(item, key=f"check_{selected_assign['id']}_{i}")
                if not is_checked:
                    all_checked = False
            
            if st.button("최종 제출 확인", type="primary", use_container_width=True):
                if all_checked:
                    st.balloons()
                    st.success("모든 조건이 충족되었습니다. 제출을 진행하세요!")
                else:
                    st.warning("⚠️ 앗! 아직 체크하지 않은 항목이 있습니다. 감점될 수 있으니 제출 전 다시 한 번 생각해 보세요!")
