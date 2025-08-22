import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing_extensions import Literal
from langchain_google_genai import ChatGoogleGenerativeAI

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, filter_messages
from langchain.chat_models import init_chat_model

from lawdeepresearch.state_research import ResearcherState, ResearcherOutputState
from lawdeepresearch.utils import tavily_search, get_today_str, think_tool, case_law_search, statute_search, verify_identity_assumptions
from lawdeepresearch.prompts import research_agent_prompt, compress_research_system_prompt, compress_research_human_message

# ===== CONFIGURATION =====

# Set up tools and model binding
tools = [tavily_search, think_tool, case_law_search, statute_search, verify_identity_assumptions]
tools_by_name = {tool.name: tool for tool in tools}

# Initialize models

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    api_key = API_KEY,
    temperature=0,
    convert_system_message_to_human=True 
)
# model = init_chat_model(model="anthropic:claude-sonnet-4-20250514")
model_with_tools = model.bind_tools(tools)
# summarization_model = init_chat_model(model="openai:gpt-4.1-mini")
# compress_model = init_chat_model(model="openai:gpt-4.1", max_tokens=32000) # model="anthropic:claude-sonnet-4-20250514", max_tokens=64000
compress_model = model

# ===== AGENT NODES =====

def llm_call(state: ResearcherState):
    """Analyze current state and decide on next actions.
    
    The model analyzes the current conversation state and decides whether to:
    1. Call search tools to gather more information
    2. Provide a final answer based on gathered information
    
    Returns updated state with the model's response.
    """
    return {
        "researcher_messages": [
            model_with_tools.invoke(
                [SystemMessage(content=research_agent_prompt)] + state["researcher_messages"]
            )
        ]
    }

def tool_node(state: ResearcherState):
    """Execute all tool calls from the previous LLM response.
    
    Executes all tool calls from the previous LLM responses.
    Returns updated state with tool execution results.
    """
    tool_calls = state["researcher_messages"][-1].tool_calls
 
    # Execute all tool calls
    observations = []
    for tool_call in tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observations.append(tool.invoke(tool_call["args"]))
            
    # Create tool message outputs
    tool_outputs = [
        ToolMessage(
            content=observation,
            name=tool_call["name"],
            tool_call_id=tool_call["id"]
        ) for observation, tool_call in zip(observations, tool_calls)
    ]
    
    return {"researcher_messages": tool_outputs}

def compress_research(state: ResearcherState) -> dict:
    """Compress research findings into a concise summary.
    
    Takes all the research messages and tool outputs and creates
    a compressed summary suitable for the supervisor's decision-making.
    """
    
    system_message = compress_research_system_prompt.format(date=get_today_str())
    messages = [SystemMessage(content=system_message)] + state.get("researcher_messages", []) + [HumanMessage(content=compress_research_human_message)]
    response = compress_model.invoke(messages)
    
    # Extract raw notes from tool and AI messages
    raw_notes = [
        str(m.content) for m in filter_messages(
            state["researcher_messages"], 
            include_types=["tool", "ai"]
        )
    ]
    
    return {
        "compressed_research": str(response.content),
        "raw_notes": ["\n".join(raw_notes)]
    }

# ===== ROUTING LOGIC =====

def should_continue(state: ResearcherState) -> Literal["tool_node", "compress_research"]:
    """Determine whether to continue research or provide final answer.
    
    Determines whether the agent should continue the research loop or provide
    a final answer based on whether the LLM made tool calls.
    
    Returns:
        "tool_node": Continue to tool execution
        "compress_research": Stop and compress research
    """
    messages = state["researcher_messages"]
    last_message = messages[-1]
    
    # If the LLM makes a tool call, continue to tool execution
    if last_message.tool_calls:
        return "tool_node"
    # Otherwise, we have a final answer
    return "compress_research"

# ===== GRAPH CONSTRUCTION =====

# Build the agent workflow
agent_builder = StateGraph(ResearcherState, output_schema=ResearcherOutputState)

# Add nodes to the graph
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)
agent_builder.add_node("compress_research", compress_research)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "tool_node": "tool_node", # Continue research loop
        "compress_research": "compress_research", # Provide final answer
    },
)
agent_builder.add_edge("tool_node", "llm_call") # Loop back for more research
agent_builder.add_edge("compress_research", END)

# Compile the agent
researcher_agent = agent_builder.compile()


if __name__ == "__main__":
    # from lawdeepresearch.research_agent import researcher_agent

    # # 1. 그래프의 PNG 이미지 데이터를 바이트(bytes) 형태로 가져옵니다.
    # png_data = researcher_agent.get_graph(xray=True).draw_mermaid_png()

    # # 2. 'wb' (write binary) 모드로 파일을 열고, 이미지 데이터를 씁니다.
    # file_path = "research_agent_graph.png"
    # with open(file_path, "wb") as f:
    #     f.write(png_data)
        
    # print(f"✅ 그래프 이미지가 '{file_path}' 파일로 저장되었습니다.")

    # from utils import format_messages
    from langchain_core.messages import HumanMessage

    # Example brief
    research_brief = """As the lessee, 성춘향, I need a comprehensive legal risk analysis of 
    my residential lease agreement for the property at 서울특별시 강남구 테헤란로 427. 
    My primary concerns are the security of my 500,000,000원 security deposit and any 
    potentially disadvantageous terms in the contract. Specifically, 
    please investigate the following points: 
    - Verify if the lessor, '홍길동', named in my lease agreement, is indeed the same 
    person as the owner, '홍길동', listed in the building registration document for 
    서울특별시 강남구 테헤란로 427. - Assess the financial risk to my security deposit of 
    500,000,000원. Specifically, analyze this amount in relation to the existing secured 
    debt (채권최고액) of 300,000,000원, which was set on 2024-01-15, on the property. 
    Please consider the implications of this debt on the recoverability of my deposit 
    in a potential foreclosure scenario, acknowledging that the current market value of 
    the property is unknown and should be considered a critical missing piece of information for a complete assessment. - 
    Thoroughly review the '특약사항' (Special Clauses) section of my lease agreement, 
    particularly the clause stating '임차인은 반려동물을 키울 수 없다.' 
    (The lessee cannot keep pets). Identify any other clauses that might be unusually 
    restrictive, unfair, or disadvantageous to me as the tenant, and explain their 
    potential legal implications. - Beyond the specific points, identify any other 
    common legal risks associated with residential lease agreements, considering the 
    contract period from 2025-09-01 to 2027-08-31, 
    that I, as the lessee, should be aware of."""

    result = researcher_agent.invoke({"researcher_messages": [HumanMessage(content=f"{research_brief}.")]})
    print(result['researcher_messages'])