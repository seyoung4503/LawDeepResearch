from pathlib import Path
from datetime import datetime
from typing_extensions import Annotated, List, Literal
import os
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model 
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool, InjectedToolArg
from tavily import TavilyClient
from langchain_google_genai import ChatGoogleGenerativeAI

from lawdeepresearch.state_research import Summary
from lawdeepresearch.prompts import summarize_webpage_prompt

# ===== UTILITY FUNCTIONS =====

def get_today_str() -> str:
    """Get current date in a human-readable format."""
    return datetime.now().strftime("%a %b %-d, %Y")

def get_current_dir() -> Path:
    """Get the current directory of the module.

    This function is compatible with Jupyter notebooks and regular Python scripts.

    Returns:
        Path object representing the current directory
    """
    try:
        return Path(__file__).resolve().parent
    except NameError:  # __file__ is not defined
        return Path.cwd()

# ===== CONFIGURATION =====

# summarization_model = init_chat_model(model="openai:gpt-4.1-mini")
import os
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
summarization_model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", 
    api_key = API_KEY,
    temperature=0,
    convert_system_message_to_human=True 
)
tavily_client = TavilyClient()

# ===== SEARCH FUNCTIONS =====

def tavily_search_multiple(
    search_queries: List[str], 
    max_results: int = 3, 
    topic: Literal["general", "news", "finance"] = "general", 
    include_raw_content: bool = True, 
) -> List[dict]:
    """Perform search using Tavily API for multiple queries.

    Args:
        search_queries: List of search queries to execute
        max_results: Maximum number of results per query
        topic: Topic filter for search results
        include_raw_content: Whether to include raw webpage content

    Returns:
        List of search result dictionaries
    """
    
    # Execute searches sequentially. Note: yon can use AsyncTavilyClient to parallelize this step.
    search_docs = []
    for query in search_queries:
        result = tavily_client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic
        )
        search_docs.append(result)

    return search_docs

def summarize_webpage_content(webpage_content: str) -> str:
    """Summarize webpage content using the configured summarization model.
    
    Args:
        webpage_content: Raw webpage content to summarize
        
    Returns:
        Formatted summary with key excerpts
    """
    try:
        # Set up structured output model for summarization
        structured_model = summarization_model.with_structured_output(Summary)
        
        # Generate summary
        summary = structured_model.invoke([
            HumanMessage(content=summarize_webpage_prompt.format(
                webpage_content=webpage_content, 
                date=get_today_str()
            ))
        ])
        
        # Format summary with clear structure
        formatted_summary = (
            f"<summary>\n{summary.summary}\n</summary>\n\n"
            f"<key_excerpts>\n{summary.key_excerpts}\n</key_excerpts>"
        )
        
        return formatted_summary
        
    except Exception as e:
        print(f"Failed to summarize webpage: {str(e)}")
        return webpage_content[:1000] + "..." if len(webpage_content) > 1000 else webpage_content

def deduplicate_search_results(search_results: List[dict]) -> dict:
    """Deduplicate search results by URL to avoid processing duplicate content.
    
    Args:
        search_results: List of search result dictionaries
        
    Returns:
        Dictionary mapping URLs to unique results
    """
    unique_results = {}
    
    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = result
    
    return unique_results

def process_search_results(unique_results: dict) -> dict:
    """Process search results by summarizing content where available.
    
    Args:
        unique_results: Dictionary of unique search results
        
    Returns:
        Dictionary of processed results with summaries
    """
    summarized_results = {}
    
    for url, result in unique_results.items():
        # Use existing content if no raw content for summarization
        if not result.get("raw_content"):
            content = result['content']
        else:
            # Summarize raw content for better processing
            content = summarize_webpage_content(result['raw_content'])
        
        summarized_results[url] = {
            'title': result['title'],
            'content': content
        }
    
    return summarized_results

def format_search_output(summarized_results: dict) -> str:
    """Format search results into a well-structured string output.
    
    Args:
        summarized_results: Dictionary of processed search results
        
    Returns:
        Formatted string of search results with clear source separation
    """
    if not summarized_results:
        return "No valid search results found. Please try different search queries or use a different search API."
    
    formatted_output = "Search results: \n\n"
    
    for i, (url, result) in enumerate(summarized_results.items(), 1):
        formatted_output += f"\n\n--- SOURCE {i}: {result['title']} ---\n"
        formatted_output += f"URL: {url}\n\n"
        formatted_output += f"SUMMARY:\n{result['content']}\n\n"
        formatted_output += "-" * 80 + "\n"
    
    return formatted_output

# ===== RESEARCH TOOLS =====

@tool(parse_docstring=True)
def tavily_search(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 3,
    topic: Annotated[Literal["general", "news"], InjectedToolArg] = "general",
) -> str:
    """Fetch results from Tavily search API with content summarization.

    Args:
        query: A single search query to execute
        max_results: Maximum number of results to return
        topic: Topic to filter results by ('general', 'news')

    Returns:
        Formatted string of search results with summaries
    """
    # Execute search for single query
    search_results = tavily_search_multiple(
        [query],  # Convert single query to list for the internal function
        max_results=max_results,
        topic=topic,
        include_raw_content=True,
    )

    # Deduplicate results by URL to avoid processing duplicate content
    unique_results = deduplicate_search_results(search_results)

    # Process results with summarization
    summarized_results = process_search_results(unique_results)

    # Format output for consumption
    return format_search_output(summarized_results)




@tool(parse_docstring=True)
def verify_identity_assumptions(lessor_name: str, owner_name: str) -> str:
    """
    Compares the lessor's name from the lease agreement with the owner's name from the property registration to identify potential fraud risks.
    This tool does not prove legal identity but states assumptions based on the provided names.

    Args:
        lessor_name: The name of the lessor as written in the lease agreement.
        owner_name: The name of the owner as listed in the property registration.

    Returns:
        A string with a clear statement about the name match and associated risks.
    """
    print(f"--- 임대인-소유자 명의 비교: 임대인({lessor_name}), 소유자({owner_name}) ---")
    
    if lessor_name == owner_name:
        return (
            "✅ **가정: 소유자 명의 일치.**\n"
            "계약서상 임대인과 등기부등본상 소유자의 이름이 일치하는 것으로 확인됩니다. "
            "이는 계약의 신뢰도를 높이는 긍정적인 요소입니다. "
            "단, 최종적인 동일인물 확인은 계약 현장에서 신분증을 통해 반드시 대조해야 합니다."
        )
    else:
        return (
            "🚨 **치명적 위험: 소유자 명의 불일치.**\n"
            f"계약서상 임대인은 '{lessor_name}'이지만, 등기부등본상 실제 소유자는 '{owner_name}'입니다. "
            "이는 대리 계약이거나, 최악의 경우 전세 사기일 수 있습니다. "
            "위임장, 인감증명서 등 적법한 대리인임을 증명하는 서류를 즉시 확인해야 하며, 확인 불가 시 계약을 진행해서는 안 됩니다."
        )

def _filter_legal_search_results(results: dict) -> dict:
    """Filters out irrelevant URLs from legal search results."""
    filtered_results = {'results': []}
    irrelevant_patterns = ['download', 'login', 'javascript', 'error']
    
    for result in results.get('results', []):
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        
        # Check if any irrelevant pattern is in the URL or title
        if not any(pattern in url for pattern in irrelevant_patterns) and '안내' not in title:
            filtered_results['results'].append(result)
            
    return filtered_results


@tool(parse_docstring=True)
def statute_search(query: str) -> str:
    """Searches for Korean statutes and laws exclusively from the National Law Information Center (law.go.kr).

    Use this tool to find the exact text of laws, articles, and regulations.

    Args:
        query: The legal keyword or article number to search for (e.g., "주택임대차보호법 제3조").

    Returns:
        A formatted string of search results with summaries from law.go.kr.
    """
    # Prepend the 'site:' operator to restrict the search to the authoritative source.
    search_query = f"{query} site:law.go.kr"
    print(f"--- 법령 검색 실행: {search_query} ---")
    
    # 1. Tavily로 검색 실행
    raw_results = tavily_client.search(search_query, include_raw_content=True, max_results=5)
    
    # 2. (NEW) 의미 없는 URL 필터링
    filtered_results = _filter_legal_search_results(raw_results)
    
    # 3. 기존 파이프라인 재사용
    unique_results = deduplicate_search_results([filtered_results]) # Note: Wrap in a list
    summarized_results = process_search_results(unique_results)
    
    return format_search_output(summarized_results)

@tool(parse_docstring=True)
def case_law_search(query: str) -> str:
    """Searches for South Korean court precedents exclusively from the Supreme Court legal database (glaw.scourt.go.kr).

    Use this tool to find court cases and legal precedents related to a specific situation.

    Args:
        query: The legal situation or keyword to search for precedents (e.g., "전세보증금 미반환 대항력 판례").

    Returns:
        A formatted string of search results with summaries from glaw.scourt.go.kr.
    """
    # Prepend the 'site:' operator to restrict the search.
    search_query = f"{query} site:glaw.scourt.go.kr"
    print(f"--- 판례 검색 실행: {search_query} ---")
    
    # 1. Tavily로 검색 실행 (더 많은 결과를 가져와서 필터링)
    raw_results = tavily_client.search(search_query, include_raw_content=True, max_results=5)
    
    # 2. (NEW) 의미 없는 URL 필터링
    filtered_results = _filter_legal_search_results(raw_results)
    
    # 3. 기존 파이프라인 재사용
    unique_results = deduplicate_search_results([filtered_results])
    summarized_results = process_search_results(unique_results)
    
    return format_search_output(summarized_results)


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - When assessing research gaps: What specific information am I still missing?
    - Before concluding research: Can I provide a complete answer now?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps.

    Returns:
        Confirmation that reflection was recorded for decision-making.
    """
    output = f"Reflection recorded: {reflection}"
    return output


if __name__ == "__main__":
    # --- 1. statute_search (법령 검색) 테스트 ---
    print("\n" + "="*50)
    print("⚖️  'statute_search' 도구 테스트")
    print("="*50)
    statute_query = "주택임대차보호법 제8조 소액임차인 최우선변제권"
    print(f"질의: {statute_query}\n")
    # @tool로 데코레이트된 함수는 .invoke() 메소드로 호출할 수 있습니다.
    statute_result = statute_search.invoke({"query": statute_query})
    print("\n--- 결과 ---")
    print(statute_result)
    print("="*50)


    # --- 2. case_law_search (판례 검색) 테스트 ---
    print("\n" + "="*50)
    print("🏛️  'case_law_search' 도구 테스트")
    print("="*50)
    case_law_query = "전입신고 다음날 은행 근저당 설정 대항력"
    print(f"질의: {case_law_query}\n")
    case_law_result = case_law_search.invoke({"query": case_law_query})
    print("\n--- 결과 ---")
    print(case_law_result)
    print("="*50)