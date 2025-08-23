import streamlit as st
import asyncio
import tempfile
import os
import uuid
import json
from langchain_core.messages import HumanMessage, AIMessage

# --- 딥리서치 빌더 임포트 ---
# ❗️ 프로젝트 구조에 맞게 경로를 확인해주세요.
from lawdeepresearch.research_agent_full import deep_researcher_builder


# --- LangGraph 객체 초기화 (캐싱) ---
@st.cache_resource
def get_research_scope():
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()
    scope = deep_researcher_builder.compile(checkpointer=checkpointer)
    return scope


scope = get_research_scope()

# --- 페이지 설정 ---
st.set_page_config(page_title="부동산 계약 안심 스캐너 🛡️", layout="wide")
st.title("부동산 계약 안심 스캐너 🛡️")

# --- 1. 왼쪽 사이드바: 파일 업로드 ---
with st.sidebar:
    st.header("파일 업로드")
    uploaded_files = st.file_uploader(
        "계약서, 등기부등본 등 분석할 파일을 올려주세요.",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    st.info("파일을 업로드한 후, 중앙 화면 하단 채팅창에 질문을 입력하세요.")

# --- 2. 중앙 메인 화면: 채팅창 ---
# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# 이전 대화 내용 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "files" in message and message["files"]:
            st.markdown(f"📄 *첨부 파일: {', '.join(message['files'])}*")
        st.markdown(message["content"])

# 화면 하단에 고정되는 채팅 입력창
if prompt := st.chat_input("파일을 올리고 질문을 입력하세요..."):
    # 사용자 메시지 표시
    attached_file_names = [f.name for f in uploaded_files]
    with st.chat_message("user"):
        if attached_file_names:
            st.markdown(f"📄 *첨부 파일: {', '.join(attached_file_names)}*")
        st.markdown(prompt)

    # 메시지 기록 저장
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "files": attached_file_names}
    )

    # AI 응답 처리
    # AI 응답 처리 (수정된 코드)
    with st.chat_message("assistant"):
        thinking_placeholder = st.empty()
        answer_placeholder = st.empty()
        temp_dir_obj = None

        try:
            document_paths = []
            if uploaded_files:
                temp_dir_obj = tempfile.TemporaryDirectory()
                for f in uploaded_files:
                    file_path = os.path.join(temp_dir_obj.name, f.name)
                    with open(file_path, "wb") as out_file:
                        out_file.write(f.getbuffer())
                    document_paths.append(file_path)

            async def stream_analysis():
                log_messages = ["분석을 시작합니다..."]
                thinking_placeholder.info("\n\n".join(log_messages))

                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                inputs = {
                    "messages": [HumanMessage(content=prompt)],
                    "document_paths": document_paths,
                }
                final_ai_message = ""

                # 디버깅용 expander는 이제 필요 없으므로 주석 처리하거나 삭제해도 됩니다.
                # debug_expander = st.expander("🕵️‍♂️ 실시간 이벤트 로그 (디버그용)")
                # events_container = debug_expander.container()

                async for event in scope.astream_events(
                    inputs, config=config, version="v2"
                ):
                    # events_container.json(event) # 디버깅 완료 후 비활성화

                    kind, name = event["event"], event["name"]

                    if kind == "on_chain_start" and name == "process_documents":
                        log_messages.append(
                            "📂 첨부된 문서들의 내용을 분석하고 있습니다..."
                        )
                        thinking_placeholder.info("\n\n".join(log_messages))

                    elif kind == "on_tool_start":
                        tool_input = event["data"].get("input", {})
                        query = tool_input.get("query") or json.dumps(
                            tool_input, ensure_ascii=False
                        )

                        if name == "statute_search":
                            log_messages.append(f"⚖️ **법령 검색:** '{query}'")
                        elif name == "case_law_search":
                            log_messages.append(f"👨‍⚖️ **판례 검색:** '{query}'")
                        elif name == "verify_identity_assumptions":
                            log_messages.append(
                                "👤 **명의자 확인:** 계약서와 등기부등본의 명의자를 비교합니다."
                            )
                        elif name == "think_tool":
                            if not log_messages[-1].startswith("🤔"):
                                log_messages.append("🤔 **분석 계획 수립 중...**")
                        elif name == "tavily_search":
                            log_messages.append(f"🌐 **웹 정보 검색:** '{query}'")

                        thinking_placeholder.info("\n\n".join(log_messages))

                    # --- 💡 [수정] 'LangGraph' 이름의 최종 이벤트를 정확히 포착 ---
                    elif kind == "on_chain_end" and name == "LangGraph":
                        log_messages.append("✍️ 현재까지의 분석을 정리하고 있습니다 ...")
                        thinking_placeholder.info("\n\n".join(log_messages))

                        final_output_data = event["data"].get("output")

                        if isinstance(final_output_data, dict):
                            # 우선순위 1: 'final_report' 키가 존재하고 내용이 있다면, 그것을 최종 답변으로 사용
                            # log_messages.append(
                            #     "✅ 최종 보고서를 생성하고 있습니다 ..."
                            # )
                            report_content = final_output_data.get("final_report")
                            if report_content:
                                final_ai_message = report_content

                            # 우선순위 2: 'final_report'가 없다면, 기존처럼 'messages' 리스트에서 마지막 AI 메시지를 찾음
                            elif (
                                "messages" in final_output_data
                                and final_output_data["messages"]
                            ):
                                for msg in reversed(final_output_data["messages"]):
                                    if isinstance(msg, AIMessage):
                                        final_ai_message = msg.content
                                        break

                if not final_ai_message:
                    final_ai_message = "죄송합니다, 답변을 생성하는 데 실패했습니다. 다시 시도해주세요."

                thinking_placeholder.empty()
                answer_placeholder.markdown(final_ai_message)
                st.session_state.messages.append(
                    {"role": "assistant", "content": final_ai_message}
                )

            asyncio.run(stream_analysis())

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
        finally:
            if temp_dir_obj:
                temp_dir_obj.cleanup()
