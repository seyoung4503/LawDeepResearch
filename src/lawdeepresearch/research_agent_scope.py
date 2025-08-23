"""
User Clarification, Document Processing, and Review Brief Generation.

This module implements the scoping phase of the legal review workflow, where we:
1. Assess if the user's request needs clarification (role, document provision).
2. Process the provided legal documents using Upstage Document AI.
3. Generate a detailed and structured review brief from the conversation and parsed data.

이 모듈은 법률 검토 워크플로우의 '스코핑(Scoping)' 단계를 구현합니다. 주요 기능은 다음과 같습니다.
1. 사용자의 요청이 명확한지(역할, 문서 제공 여부)를 평가합니다.
2. 제공된 법률 문서를 Upstage Document AI를 사용해 처리합니다.
3. 대화 내용과 분석된 데이터를 바탕으로 상세하고 구조화된 검토 브리핑을 생성합니다.
"""

import json
import requests
from datetime import datetime
from typing import Literal
from dotenv import load_dotenv

# Upstage 모델과 LangChain의 핵심 컴포넌트를 가져옵니다.
# from langchain_upstage import ChatUpstage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, get_buffer_string

# LangGraph 관련 컴포넌트를 가져옵니다.
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from lawdeepresearch.prompts import clarify_user_instruction, plan_legal_review_prompt

# 우리 프로젝트에 맞게 수정한 State와 스키마를 가져옵니다.
# (프로젝트 이름은 'lawdeepresearch'로 가정)
from lawdeepresearch.state_scope import (
    AgentState,
    AgentInputState,
    ClarifyWithUser,
    ResearchQuestion,
)

# ===== 유틸리티 함수 =====


def get_today_str() -> str:
    """Get current date in a human-readable format. / 현재 날짜를 사람이 읽기 쉬운 형태로 반환합니다."""
    return datetime.now().strftime("%a %b %#d, %Y")  # 윈도우


# ===== 설정(CONFIGURATION) =====

# Upstage Solar 모델을 초기화합니다.
# 실제 사용 시에는 API 키를 환경 변수 등에 안전하게 설정해야 합니다.
# model = ChatUpstage(model_name="solar-1-mini-chat", temperature=0)


# 최신 모델인 Gemini 1.5 Flash를 사용합니다. 성능이 더 중요하다면 "gemini-1.5-pro-latest"를 사용할 수 있습니다.
# convert_system_message_to_human=True는 Gemini 모델과의 호환성을 위한 중요한 옵션입니다.
import os

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    api_key=API_KEY,
    temperature=0,
    convert_system_message_to_human=True,
)

upstage_api_key = os.getenv("UPSTAGE_API_KEY")

# ===== 워크플로우 노드(NODES) =====


def clarify_with_user(
    state: AgentState,
) -> Command[Literal["process_documents", "__end__"]]:
    """
    Determine if the user's request contains sufficient information to proceed.
    Routes to document processing or ends with a clarification question.

    사용자의 요청에 분석을 시작하기에 충분한 정보가 있는지 판단합니다.
    문서 처리 단계로 넘어가거나, 명확한 질문과 함께 종료됩니다.
    """
    # LLM이 ClarifyWithUser 스키마에 맞춰 구조화된 답변을 생성하도록 설정합니다.
    structured_output_model = model.with_structured_output(ClarifyWithUser)

    # 이전에 정의한 프롬프트를 사용하여 LLM을 호출합니다.
    # clarify_user_instruction 프롬프트 내용을 여기에 직접 넣거나 파일에서 불러옵니다.
    # clarify_prompt = "..." # 여기에 clarify_user_instruction 프롬프트 내용을 채워주세요.
    print(f"   전달된 데이터: {state['document_paths']}")
    response = structured_output_model.invoke(
        [
            HumanMessage(
                content=clarify_user_instruction.format(
                    messages=get_buffer_string(messages=state["messages"]),
                    document_paths=state.get("document_paths", []),
                    date=get_today_str(),
                )
            )
        ]
    )

    # LLM의 판단에 따라 다음 단계를 결정합니다.
    if response.need_clarification:
        return Command(
            goto=END, update={"messages": [AIMessage(content=response.question)]}
        )
    else:
        return Command(
            goto="process_documents",
            update={"messages": [AIMessage(content=response.verification)]},
        )


# def process_documents(state: AgentState) -> dict:
#     """
#     Process multiple documents using Upstage Document AI from the paths in the state.
#     Updates the state with a list of parsed JSON data.

#     상태(State)에 저장된 여러 문서 경로를 가져와 Upstage Document AI로 처리합니다.
#     추출된 JSON 데이터들의 리스트를 상태의 'parsed_data' 필드에 저장합니다.
#     """
#     # 1. 상태(State)에서 문서 경로 리스트를 가져옵니다.
#     document_paths = state.get("document_paths", [])
#     if not document_paths:
#         print("Error: No documents to process.")
#         return {}

#     all_parsed_data = []

#     # 2. 반복문을 사용해 리스트에 있는 각 문서를 순서대로 처리합니다. # 수정 필요함
#     for path in document_paths:
#         print(f"Processing document: '{path}'...")

#         # 3. (가상) Upstage Document AI API 호출
#         # 이 부분에 실제 Upstage Document AI SDK 또는 API 호출 코드를 작성합니다.
#         # 문서 종류를 식별하여 그에 맞는 파서나 모델을 호출하는 로직을 추가할 수 있습니다.
#         parsed_json = {
#             # 어떤 파일의 분석 결과인지 알 수 있도록 파일명을 추가합니다.
#             "file_name": path.split('/')[-1],
#             # 파일명에 포함된 키워드로 문서 종류를 간단히 식별하는 예시입니다.
#             "document_type": "Lease Agreement" if "contract" in path.lower() else "Property Registration",
#             # ... (실제 파싱 결과가 여기에 들어갑니다) ...
#             "content": {
#                 "lessor": "Hong Gil-dong",
#                 "lessee": "Seong Chun-hyang",
#                 "deposit": "100,000,000 KRW"
#             }
#         }
#         all_parsed_data.append(parsed_json)

#     print("All documents processed successfully.")

#     # 4. 추출된 모든 데이터 리스트를 상태에 업데이트하기 위해 반환합니다.
#     return {"parsed_data": all_parsed_data}


def process_documents(state: AgentState) -> dict:
    """상태에 저장된 문서 경로를 바탕으로 가상의 문서 분석(파싱)을 수행합니다."""
    document_paths = state.get("document_paths", [])
    if not document_paths:
        print("오류: 처리할 문서가 없습니다.")
        return {}

    all_parsed_data = []
    print("\n--- 문서 처리 시작 ---")

    document_analysis_prompt_template = """

    You are a highly skilled legal expert AI specializing in the analysis of South Korean real estate documents.
    Your mission is to analyze the HTML content of a document extracted via OCR, summarize its key information, and, most importantly, clearly identify potential risks or points of caution for the user.

    Review the [Document HTML Content] below and perform the following tasks in order:
    1. Identify Document Type: Determine if the document is a '주택임대차계약서' (Housing Lease Agreement) or a '등기부등본' (Real Estate Register).

    2. Extract and Summarize Key Information: Based on the identified document type, extract and summarize all relevant information precisely as shown in the [Output Format] examples below. The final output must be a single JSON object.
    
    3. Analyze Risk Factors (for Lease Agreements only): If the document is a '주택임대차계약서', analyze its contents for any unusual clauses, provisions that could be disadvantageous to the tenant, or obvious errors (e.g., mismatched amounts). Describe these findings clearly in the 주의사항 (warnings) field. If no risks are found, return an empty list [].

    [Document HTML Content]
    {html_content}

    [Output Format]
    You must strictly adhere to the JSON structure defined below. Return only the raw JSON object without any markdown formatting (like ```json ... ```).

    **'주택 임대차 계약서'인 경우:**
    ```json
    {{
    "document_type": "주택 임대차 계약서",
    "summary": {{
        "기본 정보": {{
        "임대인": "추출된 임대인 이름",
        "임차인": "추출된 임차인 이름",
        "부동산 주소": "추출된 전체 주소",
        "임차할 부분": "추출된 임차 범위"
        }},
        "보증금 및 계약 기간": {{
        "총 보증금": "추출된 총 보증금 (숫자와 단위 포함)",
        "계약금": "추출된 계약금",
        "중도금": "추출된 중도금 (지급일 포함)",
        "잔금": "추출된 잔금 (지급일 포함)",
        "계약 기간": "YYYY-MM-DD ~ YYYY-MM-DD (총 O년) 형식",
        "주의사항": [
            "분석된 위험 요소 또는 이례적 조항에 대한 설명 1",
            "분석된 위험 요소 또는 이례적 조항에 대한 설명 2"
        ]
        }},
        "주요 특약사항": [
        {{
            "조항": "특약사항 제목 요약",
            "내용": "특약사항 전체 내용"
        }}
        ],
        "기타 확인사항": {{
        "집주인 권리관계": "미납 세금 및 선순위 권리자 유무",
        "중개보수": "추출된 중개보수 정보",
        "원상복구의무 범위": "추출된 원상복구 관련 내용"
        }}
    }}
    }}

    **'등기부등본'인 경우:**
    {{
    "document_type": "등기부등본",
    "summary": {{
        "기본 정보": {{
        "소재지번": "추출된 주소",
        "부동산 종류": "예: 토지, 건물, 집합건물"
        }},
        "소유권 현황 (갑구)": {{
        "현재 소유자": {{
            "성명": "추출된 현재 소유자 이름",
            "주소": "추출된 소유자 주소",
            "등기원인": "예: 매매, 상속 등"
        }},
        "주의사항(압류/가압류 등)": [
            "갑구에서 발견된 소유권 제한 관련 내용 요약 1",
            "갑구에서 발견된 소유권 제한 관련 내용 요약 2"
        ]
        }},
        "소유권 외 권리 현황 (을구)": {{
        "근저당권 및 기타 권리": [
            {{
            "권리 종류": "예: 근저당권",
            "채권최고액": "추출된 금액",
            "채권자": "추출된 채권자(은행 등)",
            "설정일자": "YYYY-MM-DD"
            }}
        ],
        "주의사항": "을구가 깨끗한지, 아니면 과도한 대출 또는 빛이 있는지에 대한 종합적인 분석 의견"
        }}
    }}
    }}
    """

    for path in document_paths:
        print(f"문서 처리 중: '{path}'...")

        filename = path

        url = "https://api.upstage.ai/v1/document-digitization"
        headers = {"Authorization": f"Bearer {upstage_api_key}"}
        files = {"document": open(filename, "rb")}
        data = {"ocr": "force", "model": "document-parse"}
        response = requests.post(url, headers=headers, files=files, data=data)
        upstage_result = response.json()
        html_from_api = upstage_result.get("content", {}).get("html", "")

        model_output = model.invoke(
            [
                HumanMessage(
                    content=document_analysis_prompt_template.format(
                        html_content=html_from_api
                    )
                )
            ]
        )

        model_output_text = model_output.content
        json_str = model_output_text.strip().replace("```json", "").replace("```", "")

        model_output_text
        parsed_json = json.loads(json_str)

        # 최종 결과물에 파일 이름 추가
        final_output = {"file_name": path, **parsed_json}

        print(f"'{path}' 처리 완료.")
        all_parsed_data.append(final_output)
        print(final_output)

    print("--- 모든 문서 처리 완료 ---\n")
    return {"parsed_data": all_parsed_data}


# if "contract" in path.lower():
#     parsed_json = {
#         "file_name": os.path.basename(path),
#         "document_type": "주택 임대차 계약서",
#         "content": {
#             "임대인": "홍길동",
#             "임차인": "성춘향",
#             "주소": "서울특별시 강남구 테헤란로 427",
#             "보증금": "500,000,000원",
#             "계약 기간": "2025-09-01 ~ 2027-08-31",
#             "특약사항": "임차인은 반려동물을 키울 수 없다.",
#         },
#     }
# elif "registration" in path.lower():
#     parsed_json = {
#         "file_name": os.path.basename(path),
#         "document_type": "등기부등본",
#         "content": {
#             "소유자": "홍길동",
#             "주소": "서울특별시 강남구 테헤란로 427",
#             "채권최고액": "300,000,000원",
#             "설정일자": "2024-01-15",
#         },
#     }
# else:
#     parsed_json = {
#         "file_name": os.path.basename(path),
#         "document_type": "기타 문서",
#         "content": {},
#     }

# 워크플로우 파일의 write_research_brief 함수 수정


def plan_legal_review(state: AgentState) -> dict:
    # LLM이 LegalReviewBrief 스키마에 맞춰 구조화된 답변을 생성하도록 설정합니다.
    structured_output_model = model.with_structured_output(ResearchQuestion)

    prompt = plan_legal_review_prompt.format(
        messages=get_buffer_string(state["messages"]),
        parsed_data=state.get("parsed_data", []),
        date=get_today_str(),
    )

    response = structured_output_model.invoke([HumanMessage(content=prompt)])

    return {
        "research_brief": response.dict(),
        "supervisor_messages": [HumanMessage(content=f"{response.research_brief}.")],
    }


# ===== 그래프 구성(GRAPH CONSTRUCTION) =====

# 법률 검토 에이전트의 워크플로우를 정의합니다.
workflow = StateGraph(AgentState)

# 워크플로우에 각 단계(노드)를 추가합니다.
workflow.add_node("clarify_with_user", clarify_with_user)
workflow.add_node("process_documents", process_documents)
workflow.add_node("plan_legal_review", plan_legal_review)

workflow.add_edge(START, "clarify_with_user")
workflow.add_edge("process_documents", "plan_legal_review")
workflow.add_edge("plan_legal_review", END)

# 워크플로우를 컴파일하여 실행 가능한 객체로 만듭니다.
law_research_agent = workflow.compile()


if __name__ == "__main__":
    from IPython.display import Image, display
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()
    scope = workflow.compile(checkpointer=checkpointer)

    # # Get the graph's PNG data as bytes
    # png_data = scope.get_graph(xray=True).draw_mermaid_png()

    # # Write the bytes to a file
    # with open("workflow_graph.png", "wb") as f:
    #     f.write(png_data)

    print("✅ Graph saved to 'workflow_graph.png'. You can now open this file.")

    from langchain_core.messages import HumanMessage

    # print("\n--- 실행 1: 정보 부족 (역할, 문서 모두 없음) ---")
    # thread1 = {"configurable": {"thread_id": "thread-1"}}
    # result1 = scope.invoke({"messages": [HumanMessage(content="내 계약서에 어떤 문제가 있을까?")]}, config=thread1)
    # print(result1['messages'][-1].content)
    # print("-" * 50)

    # print("\n--- 실행 2: 정보 부족 (문서 없음) ---")
    # # thread2 = {"configurable": {"thread_id": "thread-2"}}
    # result2 = scope.invoke({"messages": [HumanMessage(content="나는 임대인이야")]}, config=thread1)
    # print(result2['messages'][-1].content)
    # print("-" * 50)

    print("\n--- 실행 3: 모든 정보 제공됨 -> 전체 워크플로우 실행 ---")
    thread3 = {"configurable": {"thread_id": "thread-3"}}
    final_result = scope.invoke(
        {
            "messages": [
                HumanMessage(
                    content="임차인 입장이고, 여기 계약서랑 등기부등본이야. 분석해줘."
                )
            ],
            "document_paths": [
                "주택임대차표준계약서_test3.pdf",
                "등기부등본_clean.png",
            ],
        },
        config=thread3,
    )

    # 최종 결과인 research_brief 출력
    print("✅ 최종 검토 브리핑이 생성되었습니다:")
    print(json.dumps(final_result.get("research_brief"), indent=2, ensure_ascii=False))

    print(final_result["messages"])
