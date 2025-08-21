"""Multi-agent supervisor for coordinating research across multiple specialized agents.

This module implements a supervisor pattern where:
1. A supervisor agent coordinates research activities and delegates tasks
2. Multiple researcher agents work on specific sub-topics independently
3. Results are aggregated and compressed for final reporting

The supervisor uses parallel research execution to improve efficiency while
maintaining isolated context windows for each research topic.
"""

import os
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from typing_extensions import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    HumanMessage, 
    BaseMessage, 
    SystemMessage, 
    ToolMessage,
    filter_messages
)
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from lawdeepresearch.prompts import lead_researcher_prompt
from lawdeepresearch.research_agent import researcher_agent
from lawdeepresearch.state_multi_agent_supervisor import (
    SupervisorState, 
    ConductResearch, 
    ResearchComplete
)
from lawdeepresearch.utils import get_today_str, think_tool

def get_notes_from_tool_calls(messages: list[BaseMessage]) -> list[str]:
    """Extract research notes from ToolMessage objects in supervisor message history.
    
    This function retrieves the compressed research findings that sub-agents
    return as ToolMessage content. When the supervisor delegates research to
    sub-agents via ConductResearch tool calls, each sub-agent returns its
    compressed findings as the content of a ToolMessage. This function
    extracts all such ToolMessage content to compile the final research notes.
    
    Args:
        messages: List of messages from supervisor's conversation history
        
    Returns:
        List of research note strings extracted from ToolMessage objects
    """
    return [tool_msg.content for tool_msg in filter_messages(messages, include_types="tool")]

# Ensure async compatibility for Jupyter environments
try:
    import nest_asyncio
    # Only apply if running in Jupyter/IPython environment
    try:
        from IPython import get_ipython
        if get_ipython() is not None:
            nest_asyncio.apply()
    except ImportError:
        pass  # Not in Jupyter, no need for nest_asyncio
except ImportError:
    pass  # nest_asyncio not available, proceed without it


# ===== CONFIGURATION =====

supervisor_tools = [ConductResearch, ResearchComplete, think_tool]
# supervisor_model = init_chat_model(model="anthropic:claude-sonnet-4-20250514")
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
supervisor_model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    api_key = API_KEY,
    temperature=0,
    convert_system_message_to_human=True 
)
supervisor_model_with_tools = supervisor_model.bind_tools(supervisor_tools)

# System constants
# Maximum number of tool call iterations for individual researcher agents
# This prevents infinite loops and controls research depth per topic
max_researcher_iterations = 6 # Calls to think_tool + ConductResearch

# Maximum number of concurrent research agents the supervisor can launch
# This is passed to the lead_researcher_prompt to limit parallel research tasks
max_concurrent_researchers = 3

# ===== SUPERVISOR NODES =====

async def supervisor(state: SupervisorState) -> Command[Literal["supervisor_tools"]]:
    """Coordinate research activities.
    
    Analyzes the research brief and current progress to decide:
    - What research topics need investigation
    - Whether to conduct parallel research
    - When research is complete
    
    Args:
        state: Current supervisor state with messages and research progress
        
    Returns:
        Command to proceed to supervisor_tools node with updated state
    """
    supervisor_messages = state.get("supervisor_messages", [])
    
    # Prepare system message with current date and constraints
    system_message = lead_researcher_prompt.format(
        date=get_today_str(), 
        max_concurrent_research_units=max_concurrent_researchers,
        max_researcher_iterations=max_researcher_iterations
    )
    messages = [SystemMessage(content=system_message)] + supervisor_messages
    
    # Make decision about next research steps
    response = await supervisor_model_with_tools.ainvoke(messages)
    
    return Command(
        goto="supervisor_tools",
        update={
            "supervisor_messages": [response],
            "research_iterations": state.get("research_iterations", 0) + 1
        }
    )

async def supervisor_tools(state: SupervisorState) -> Command[Literal["supervisor", "__end__"]]:
    """Execute supervisor decisions - either conduct research or end the process.
    
    Handles:
    - Executing think_tool calls for strategic reflection
    - Launching parallel research agents for different topics
    - Aggregating research results
    - Determining when research is complete
    
    Args:
        state: Current supervisor state with messages and iteration count
        
    Returns:
        Command to continue supervision, end process, or handle errors
    """
    supervisor_messages = state.get("supervisor_messages", [])
    research_iterations = state.get("research_iterations", 0)
    most_recent_message = supervisor_messages[-1]
    
    # Initialize variables for single return pattern
    tool_messages = []
    all_raw_notes = []
    next_step = "supervisor"  # Default next step
    should_end = False
    
    # Check exit criteria first
    exceeded_iterations = research_iterations >= max_researcher_iterations
    no_tool_calls = not most_recent_message.tool_calls
    research_complete = any(
        tool_call["name"] == "ResearchComplete" 
        for tool_call in most_recent_message.tool_calls
    )
    
    if exceeded_iterations or no_tool_calls or research_complete:
        should_end = True
        next_step = END
    
    else:
        # Execute ALL tool calls before deciding next step
        try:
            # Separate think_tool calls from ConductResearch calls
            think_tool_calls = [
                tool_call for tool_call in most_recent_message.tool_calls 
                if tool_call["name"] == "think_tool"
            ]
            
            conduct_research_calls = [
                tool_call for tool_call in most_recent_message.tool_calls 
                if tool_call["name"] == "ConductResearch"
            ]

            # Handle think_tool calls (synchronous)
            for tool_call in think_tool_calls:
                observation = think_tool.invoke(tool_call["args"])
                tool_messages.append(
                    ToolMessage(
                        content=observation,
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"]
                    )
                )

            # Handle ConductResearch calls (asynchronous)
            if conduct_research_calls:
                # Launch parallel research agents
                coros = [
                    researcher_agent.ainvoke({
                        "researcher_messages": [
                            HumanMessage(content=tool_call["args"]["research_topic"])
                        ],
                        "research_topic": tool_call["args"]["research_topic"]
                    }) 
                    for tool_call in conduct_research_calls
                ]

                # Wait for all research to complete
                tool_results = await asyncio.gather(*coros)

                # Format research results as tool messages
                # Each sub-agent returns compressed research findings in result["compressed_research"]
                # We write this compressed research as the content of a ToolMessage, which allows
                # the supervisor to later retrieve these findings via get_notes_from_tool_calls()
                research_tool_messages = [
                    ToolMessage(
                        content=result.get("compressed_research", "Error synthesizing research report"),
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"]
                    ) for result, tool_call in zip(tool_results, conduct_research_calls)
                ]
                
                tool_messages.extend(research_tool_messages)

                # Aggregate raw notes from all research
                all_raw_notes = [
                    "\n".join(result.get("raw_notes", [])) 
                    for result in tool_results
                ]
                
        except Exception as e:
            print(f"Error in supervisor tools: {e}")
            should_end = True
            next_step = END
    
    # Single return point with appropriate state updates
    if should_end:
        return Command(
            goto=next_step,
            update={
                "notes": get_notes_from_tool_calls(supervisor_messages),
                "research_brief": state.get("research_brief", "")
            }
        )
    else:
        return Command(
            goto=next_step,
            update={
                "supervisor_messages": tool_messages,
                "raw_notes": all_raw_notes
            }
        )

# ===== GRAPH CONSTRUCTION =====

# Build supervisor graph
supervisor_builder = StateGraph(SupervisorState)
supervisor_builder.add_node("supervisor", supervisor)
supervisor_builder.add_node("supervisor_tools", supervisor_tools)
supervisor_builder.add_edge(START, "supervisor")
supervisor_agent = supervisor_builder.compile()


if __name__ == "__main__":
    from IPython.display import Image, display
    from lawdeepresearch.multi_agent_supervisor import supervisor_agent

    # Show the agent
    # display(Image(supervisor_agent.get_graph(xray=True).draw_mermaid_png()))

    # # 1. 그래프의 PNG 이미지 데이터를 바이트(bytes) 형태로 가져옵니다.
    # png_data = supervisor_agent.get_graph(xray=True).draw_mermaid_png()

    # # 2. 'wb' (write binary) 모드로 파일을 열고, 이미지 데이터를 씁니다.
    # file_path = "supervisor_agent_graph.png"
    # with open(file_path, "wb") as f:
    #     f.write(png_data)
        
    # print(f"✅ 그래프 이미지가 '{file_path}' 파일로 저장되었습니다.")


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

    async def main():
        # 2. '특수 장비(await)'를 암실 안에서 사용합니다.
        # 초기 입력값으로 research_brief를 supervisor_messages가 아닌 research_brief 필드에 전달합니다.
        result = await supervisor_agent.ainvoke({
            "research_brief": research_brief,
            "supervisor_messages": [HumanMessage(content=research_brief)]
        })
        print(result)

    # 3. asyncio.run()으로 '암실' 전체 작업을 실행합니다.
    asyncio.run(main())