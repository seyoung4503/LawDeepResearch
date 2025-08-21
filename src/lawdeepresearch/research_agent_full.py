"""
Full Multi-Agent Research System

This module integrates all components of the research system:
- User clarification and scoping
- Research brief generation  
- Multi-agent research coordination
- Final report generation

The system orchestrates the complete research workflow from initial user
input through final report delivery.
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

from lawdeepresearch.utils import get_today_str
from lawdeepresearch.prompts import final_report_generation_prompt
from lawdeepresearch.state_scope import AgentState, AgentInputState
from lawdeepresearch.research_agent_scope import clarify_with_user, process_documents, plan_legal_review
from lawdeepresearch.multi_agent_supervisor import supervisor_agent

# ===== Config =====

from langchain.chat_models import init_chat_model
# writer_model = init_chat_model(model="openai:gpt-4.1", max_tokens=32000) # model="anthropic:claude-sonnet-4-20250514", max_tokens=64000
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
writer_model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    api_key = API_KEY,
    temperature=0,
    convert_system_message_to_human=True,
    max_output_tokens = 32000
)

# ===== FINAL REPORT GENERATION =====

from lawdeepresearch.state_scope import AgentState

async def final_report_generation(state: AgentState):
    """
    Final report generation node.
    
    Synthesizes all research findings into a comprehensive final report
    """
    
    notes = state.get("notes", [])
    
    findings = "\n".join(notes)

    final_report_prompt = final_report_generation_prompt.format(
        research_brief=state.get("research_brief", ""),
        findings=findings,
        date=get_today_str()
    )
    
    final_report = await writer_model.ainvoke([HumanMessage(content=final_report_prompt)])
    
    return {
        "final_report": final_report.content, 
        "messages": ["Here is the final report: " + final_report.content],
    }

# ===== GRAPH CONSTRUCTION =====
# Build the overall workflow
deep_researcher_builder = StateGraph(AgentState)

# Add workflow nodes
deep_researcher_builder.add_node("clarify_with_user", clarify_with_user)
deep_researcher_builder.add_node("process_documents", process_documents)
deep_researcher_builder.add_node("plan_legal_review", plan_legal_review)
deep_researcher_builder.add_node("supervisor_subgraph", supervisor_agent)
deep_researcher_builder.add_node("final_report_generation", final_report_generation)

# Add workflow edges
deep_researcher_builder.add_edge(START, "clarify_with_user")
deep_researcher_builder.add_edge("process_documents", "plan_legal_review")
deep_researcher_builder.add_edge("plan_legal_review", "supervisor_subgraph")
deep_researcher_builder.add_edge("supervisor_subgraph", "final_report_generation")
deep_researcher_builder.add_edge("final_report_generation", END)

# Compile the full workflow
agent = deep_researcher_builder.compile()


if __name__ == "__main__":
    from IPython.display import Image, display
    from langgraph.checkpoint.memory import InMemorySaver

    checkpointer = InMemorySaver()
    scope = deep_researcher_builder.compile(checkpointer=checkpointer)
    
    # # Get the graph's PNG data as bytes
    # png_data = scope.get_graph(xray=True).draw_mermaid_png()

    # # Write the bytes to a file
    # with open("workflow_graph.png", "wb") as f:
    #     f.write(png_data)
    
    print("✅ Graph saved to 'workflow_graph.png'. You can now open this file.")


    
    from langchain_core.messages import HumanMessage
    import json
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
    from .tools.utils import format_messages
    def main():
        thread3 = {"configurable": {"thread_id": "thread-3"}}
        final_result = await scope.ainvoke({
            "messages": [HumanMessage(content="임차인 입장이고, 여기 계약서랑 등기부등본이야. 분석해줘.")],
            "document_paths": ["mock/path/to/my_contract.pdf", "mock/path/to/building_registration.pdf"]
        }, config=thread3)
        
        format_messages(final_result['messages'])

    # # 최종 결과인 research_brief 출력
    # print("✅ 최종 검토 브리핑이 생성되었습니다:")
    # print(json.dumps(final_result.get("research_brief"), indent=2, ensure_ascii=False))
    import asyncio
    asyncio.run(main())

    # print(final_result['messages'])
