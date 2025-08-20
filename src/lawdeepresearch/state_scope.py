import operator
from typing_extensions import Optional, Annotated, List, Sequence, Dict

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# ===== STATE DEFINITIONS =====

class AgentInputState(MessagesState):
    """Input state for the full agent - only contains messages from user input."""
    pass

class AgentState(MessagesState):
    """
    Main state for the full multi-agent research system.
    
    Extends MessagesState with additional fields for research coordination.
    Note: Some fields are duplicated across different state classes for proper
    state management between subgraphs and the main workflow.
    """

    # 사용자가 업로드한 문서의 경로
    document_paths: List[str] = []

    # Upstage Document AI가 문서를 파싱하여 추출한 구조화된 데이터
    parsed_data: List[Dict] = []
    
    # 'write_research_brief' 노드에서 생성된 구조화된 최종 검토 브리핑
    # 이제 단순 문자열이 아닌 Dict(JSON) 형태로 저장됩니다.
    research_brief: Optional[Dict]

    # (이하 필드는 후속 연구/보고서 작성 단계를 위한 필드)
    # 조정을 위해 슈퍼바이저 에이전트와 주고받은 메시지
    supervisor_messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # 리서치 단계에서 수집된, 가공되지 않은 원본 리서치 노트
    raw_notes: Annotated[list[str], operator.add] = []
    
    # 보고서 생성을 위해 처리되고 구조화된 노트
    notes: Annotated[list[str], operator.add] = []
    
    # 최종적으로 형식화된 리서치 보고서
    final_report: str


class ClarifyWithUser(BaseModel):
    """Schema for user clarification decision and questions."""
    
    need_clarification: bool = Field(
        description="사용자에게 명확화 질문을 해야 하는지 여부.",
    )
    question: str = Field(
        description="보고서의 범위를 명확히 하기 위해 사용자에게 물어볼 질문.",
    )
    verification: str = Field(
        description="사용자가 필요한 정보를 제공한 후 리서치를 시작할 것임을 확인하는 메시지.",
    )

class ResearchQuestion(BaseModel):
    """Schema for structured research brief generation."""
    
    research_brief: str = Field(
        description="A research question that will be used to guide the research.",
    )