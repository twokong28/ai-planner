import streamlit as st
from google import genai  # 👈 최신 라이브러리로 임포트
import datetime 
import pandas as pd
import json
import math
# ==============================================================================
# 🔴 [API 연동 지점] 여기에 "새로 발급받은" Gemini API 키를 입력하세요. 🔴
# ==============================================================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

client = genai.Client(api_key=GEMINI_API_KEY) # 👈 새로운 클라이언트 초기화 방식
# ==============================================================================
# ==============================================================================

# --- 세션 상태 초기화 (데이터 저장용) ---
if 'assignments' not in st.session_state:
    st.session_state.assignments = []
if 'user_history_multiplier' not in st.session_state:
    st.session_state.user_history_multiplier = 1.0 # 기본 1.0배 (기능 6: 사용자 맞춤 학습)

# --- 기능 3, 4, 5, 12, 13: Gemini AI 과제 분석 호출 함수 ---
def analyze_assignment_with_ai(title, subject, desc, file_text=""):
    """과제 정보를 Gemini API로 보내 JSON 형태로 분석 결과를 받아오는 함수"""
    prompt = f"""
    당신은 대학생의 과제를 분석해주는 AI 플래너입니다. 아래 과제 정보를 분석하여 반드시 JSON 형식으로만 답변하세요.
    
    [과제 정보]
    과제명: {title}
    과목명: {subject}
    과제 설명 및 공지: {desc}
    첨부파일 내용: {file_text}
    
    [JSON 출력 형식]
    {{
        "task_type": "과제 유형 (예: 프로그래밍/CS, 회계/수리, 어학/에세이 중 택 1)",
        "tasks": [
            {{"name": "세부 태스크명", "estimated_hours": 예상 소요시간(실수형, 예: 1.5)}}
        ],
        "total_estimated_hours": 총 예상 소요시간(실수형),
        "checklist": [
            "제출 전 체크해야 할 양식 및 조건 1",
            "제출 전 체크해야 할 양식 및 조건 2"
        ]
    }}
    JSON 외의 다른 설명은 절대 추가하지 마세요.
    """
    try:
        # 👈 새로운 API 호출 방식과 gemini-1.5-flash 모델 적용
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
        )
        # Markdown JSON 블록 제거 후 파싱
        cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(cleaned_text)
    except Exception as e:
        st.error(f"AI 분석 중 오류가 발생했습니다: {e}")
        return None

# --- UI 레이아웃 시작 ---
st.set_page_config(page_title="AI 과제 플래너", layout="wide")
st.title("📚 AI 과제 플래너")

# 사이드바: 1. 과제 정보 입력 & 2. 파일 업로드
with st.sidebar:
    st.header("📝 새 과제 등록")
    # 예시로 전산회계나 자바 프로그래밍 과제 등을 입력해 볼 수 있습니다.
    new_title = st.text_input("과제명", placeholder="예: 챕터 1~3 분개 및 재무제표 작성")
    new_subject = st.text_input("과목명", placeholder="예: 전산회계")
    new_deadline = st.date_input("마감일", min_value=datetime.date.today())
    new_desc = st.text_area("과제 설명 및 교수님 공지", placeholder="과제 세부 내용이나 제한사항을 입력하세요.")
    
    uploaded_file = st.file_uploader("과제 파일 업로드 (선택)", type=['pdf', 'docx', 'txt', 'hwp', 'png', 'jpg'])
    
    if st.button("🚀 AI 분석 및 플랜 생성"):
        if new_title and new_subject:
            with st.spinner('AI가 과제를 분석하고 세부 계획을 세우는 중입니다...'):
                # (실제 구현 시 여기에 파일 텍스트 추출 로직 추가)
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
                    st.success("과제가 성공적으로 분석되어 추가되었습니다!")
        else:
            st.warning("과제명과 과목명을 입력해주세요.")

# --- 메인 대시보드 ---
if not st.session_state.assignments:
    st.info("👈 왼쪽 사이드바에서 새로운 과제를 등록해주세요.")
else:
    # --- 데이터 사전 처리 ---
    today = datetime.date.today()
    for assign in st.session_state.assignments:
        days_left = (assign['deadline'] - today).days
        assign['days_left'] = days_left if days_left >= 0 else 0
        
        # 기능 6: 사용자 맞춤 시간 예측 적용 (기본 소요시간 * 내 작업 속도 배수)
        assign['adjusted_total_hours'] = assign['base_total_hours'] * st.session_state.user_history_multiplier
        
        # 기능 11: 마감 위험도 예측
        # 하루 가용 시간을 4시간으로 가정했을 때의 위험도 계산
        available_hours = assign['days_left'] * 4 
        if available_hours >= assign['adjusted_total_hours'] * 1.5:
            assign['risk'] = "🟢 안전"
        elif available_hours >= assign['adjusted_total_hours']:
            assign['risk'] = "🟡 주의"
        else:
            assign['risk'] = "🔴 위험"

    # 기능 10: 과제 우선순위 자동 정렬 (마감일 오름차순, 소요시간 내림차순)
    sorted_assignments = sorted(st.session_state.assignments, key=lambda x: (x['days_left'], -x['adjusted_total_hours']))

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📊 전체 과제 현황 및 우선순위")
        for assign in sorted_assignments:
            with st.expander(f"[{assign['risk']}] {assign['title']} - {assign['subject']} (마감 D-{assign['days_left']})", expanded=True):
                st.caption(f"과제 유형: {assign['type']} | AI 예상 시간: {assign['base_total_hours']}h | 🕒 나의 예상 소요 시간(보정됨): {assign['adjusted_total_hours']:.1f}h")
                
                # 기능 8: 진행률 자동 계산
                completed_tasks = sum(1 for t in assign['tasks'] if t['completed'])
                total_tasks = len(assign['tasks'])
                progress_pct = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
                st.progress(progress_pct, text=f"진행률: {progress_pct}% ({completed_tasks}/{total_tasks})")
                
                # 기능 7: 작업량 시각화 (블록)
                st.write("**작업량 시각화 (1블록 = 30분):**")
                for task in assign['tasks']:
                    # 사용자 맞춤 보정시간을 태스크에도 적용
                    adj_task_time = task['estimated_hours'] * st.session_state.user_history_multiplier
                    blocks = "■" * max(1, math.ceil(adj_task_time * 2))
                    st.markdown(f"**{task['name']}** ({adj_task_time:.1f}h)<br><span style='color:#4CAF50;'>{blocks}</span>", unsafe_allow_html=True)
                
                st.divider()
                
                # 체크박스로 태스크 진행 상황 업데이트
                st.write("**세부 태스크 진행**")
                for i, task in enumerate(assign['tasks']):
                    task['completed'] = st.checkbox(task['name'], value=task['completed'], key=f"task_{assign['id']}_{i}")

    with col2:
        # 기능 9: 오늘 해야 할 일 추천
        st.subheader("💡 오늘 해야 할 일")
        today_tasks_shown = False
        for assign in sorted_assignments:
            if assign['days_left'] <= 3 and progress_pct < 100: # 마감일 3일 이내 과제 우선
                incomplete_tasks = [t['name'] for t in assign['tasks'] if not t['completed']]
                if incomplete_tasks:
                    st.info(f"**{assign['title']}**\n\n👉 {incomplete_tasks[0]}")
                    today_tasks_shown = True
                    break # 가장 급한 과제의 첫 번째 태스크만 추천
        if not today_tasks_shown:
            st.success("오늘 급하게 처리할 태스크가 없습니다! 🎉")

       # 기능 14: 제출물 최종 점검 (기능 12, 13 AI 생성 체크리스트)
        st.subheader("📋 제출 전 최종 점검")
        target_assign_id = st.selectbox("과제 선택", [a['title'] for a in st.session_state.assignments])
        selected_assign = next((a for a in st.session_state.assignments if a['title'] == target_assign_id), None)
        
        if selected_assign and selected_assign['checklist']:
            st.write("교수님 공지 및 양식 기반 자동 생성 체크리스트")
            
            # 👇 변경된 부분 1: 모든 항목이 체크되었는지 추적하는 변수 추가
            all_checked = True 
            
            for i, item in enumerate(selected_assign['checklist']):
                # 사용자가 체크박스를 눌렀는지(True/False) 값을 받아옵니다.
                is_checked = st.checkbox(item, key=f"check_{selected_assign['id']}_{i}")
                
                # 하나라도 체크가 안 되어 있다면 상태를 False로 바꿉니다.
                if not is_checked:
                    all_checked = False
            
            # 👇 변경된 부분 2: 버튼 클릭 시 조건문(if-else) 추가
            if st.button("최종 제출 확인", type="primary", use_container_width=True):
                if all_checked:
                    st.balloons()
                    st.success("모든 조건이 충족되었습니다. 제출을 진행하세요!")
                else:
                    st.warning("⚠️ 앗! 아직 체크하지 않은 항목이 있습니다. 감점될 수 있으니 제출 전 다시 한 번 생각해 보세요!")
