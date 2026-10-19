"""检索响应归一化；保留各接口的来源提取逻辑，不执行网络请求。"""
from __future__ import annotations
from typing import Any
from datetime import datetime,timezone
PREAMBLE="只提供可核对材料与直接来源，同时寻找支持和反证；未知不补造。问题："
def utc_now():return datetime.now(timezone.utc).isoformat(timespec="seconds")
def provider_value(provider,key):return provider.get(key)

def build_payload(provider: dict[str, Any], query: str) -> dict[str, Any]:
    adapter = provider["adapter"]
    model = provider_value(provider, "model")
    prompt = PREAMBLE + query
    if adapter == "deepseek_search":
        if not query.strip() or len(query)>128:raise ValueError('invalid_search_query')
        count=provider.get('top_k',10)
        if not isinstance(count,int) or not 1<=count<=50:raise ValueError('invalid_search_count')
        return {'query':query,'count':count,'need_content':False}
    if adapter in {"responses_annotations", "responses_action_sources"}:
        return {
            "model": model,
            "input": prompt,
            "tools": provider.get("tools", [{"type": "web_search"}]),
        }
    if adapter == "qianfan_ai_search":
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "search_source": provider.get("search_source", "baidu_search_v2"),
            "resource_type_filter": [
                {"type": "web", "top_k": int(provider.get("top_k", 10))}
            ],
            "enable_deep_search": bool(provider.get("deep_search", False)),
            "enable_corner_markers": True,
            "enable_followup_query": False,
        }
    if adapter == "gemini_grounding":
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }
    raise ValueError(f"unsupported request adapter: {adapter}")

def add_source(
    sources: list[dict[str, Any]],
    seen: set[str],
    url: Any,
    title: Any = "",
    site: Any = "",
    snippet: Any = "",
    published_at: Any = "",
) -> None:
    clean_url = str(url or "").strip()
    if not clean_url or clean_url in seen:
        return
    seen.add(clean_url)
    sources.append(
        {
            "title": str(title or "").strip(),
            "url": clean_url,
            "site": str(site or "").strip(),
            "snippet": str(snippet or "").strip(),
            "published_at": str(published_at or "").strip(),
        }
    )

def normalize_response(
    provider: dict[str, Any], query: str, raw: dict[str, Any]
) -> dict[str, Any]:
    adapter = provider["adapter"]
    answer_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    search_call_seen = False

    if adapter == 'deepseek_search':
        for source in raw.get('results',[]) or []:
            add_source(sources,seen,source.get('url'),source.get('title'),source.get('site_name'),source.get('summary') or source.get('snippet'),source.get('date'))
        answer_parts=[s['snippet'] or s['title'] for s in sources]
        search_call_seen=bool(sources)
    elif adapter in {"responses_annotations", "responses_action_sources"}:
        for output in raw.get("output", []) or []:
            output_type = output.get("type")
            if output_type == "web_search_call":
                search_call_seen = True
                action = output.get("action", {}) or {}
                action_query = str(action.get("query", "")).strip()
                for source in action.get("sources", []) or []:
                    add_source(
                        sources,
                        seen,
                        source.get("url"),
                        source.get("title") or (f"检索命中：{action_query[:30]}" if action_query else "检索命中"),
                        source.get("site_name") or provider.get("label"),
                        source.get("snippet") or source.get("content"),
                        source.get("published_at") or source.get("date"),
                    )
            if output_type != "message":
                continue
            for content in output.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get('text'),str):
                    answer_parts.append(content['text'])
                for annotation in content.get("annotations", []) or []:
                    add_source(
                        sources,
                        seen,
                        annotation.get("url"),
                        annotation.get("title"),
                        annotation.get("site_name"),
                        annotation.get("snippet"),
                        annotation.get("published_at"),
                    )
        search_call_seen = search_call_seen or bool(sources)

    elif adapter == "qianfan_ai_search":
        choices = raw.get("choices", []) or []
        if choices:
            content=(choices[0].get("message", {}) or {}).get("content", "")
            if isinstance(content,str):answer_parts.append(content)
        for source in raw.get("references", []) or []:
            add_source(
                sources,
                seen,
                source.get("url"),
                source.get("title"),
                source.get("type") or "baidu_search_v2",
                source.get("content") or source.get("snippet"),
                source.get("date") or source.get("published_at"),
            )
        search_call_seen = bool(sources)

    elif adapter == "gemini_grounding":
        candidates = raw.get("candidates", []) or []
        if candidates:
            candidate = candidates[0]
            for part in (candidate.get("content", {}) or {}).get("parts", []) or []:
                if isinstance(part.get("text"),str) and not part.get('thought'):
                    answer_parts.append(part["text"])
            grounding = candidate.get("groundingMetadata", {}) or {}
            raw_queries = grounding.get("webSearchQueries", []) or []
            search_call_seen = bool(
                raw_queries
                or grounding.get("groundingChunks")
                or grounding.get("searchEntryPoint")
            )
            for chunk in grounding.get("groundingChunks", []) or []:
                web = chunk.get("web", {}) or {}
                add_source(
                    sources,
                    seen,
                    web.get("uri"),
                    web.get("title"),
                    "gemini-grounding",
                    "",
                    "",
                )

    answer = "".join(answer_parts).strip()
    has_error = bool(raw.get("error"))
    if has_error:
        status = "api_error"
    elif answer and search_call_seen and sources:
        status = "success"
    elif answer:
        status = "search_unconfirmed"
    else:
        status = "empty_response"
    record = {
        "provider": provider["id"],
        "label": provider.get("label", provider["id"]),
        "role": provider.get("role", ""),
        "status": status,
        "model": raw.get("model") or provider_value(provider, "model"),
        "requested_at": "",
        "completed_at": utc_now(),
        "query": query,
        "web_search_requested": True,
        "web_search_confirmed": bool(search_call_seen and sources),
        "answer": answer,
        "sources": sources,
        "usage": raw.get("usage") or {},
        "limitations": [] if status == "success" else ["未取得可用于核验的结构化来源"],
        "evidence_eligible": status == "success" and bool(sources) and adapter != "gemini_grounding",
    }
    if adapter == "gemini_grounding":
        candidate = (raw.get("candidates", []) or [{}])[0]
        grounding = candidate.get("groundingMetadata", {}) or {}
        record["queries"] = grounding.get("webSearchQueries", []) or []
        record["provider_ui"] = {
            "search_suggestions_html": ((grounding.get("searchEntryPoint", {}) or {}).get("renderedContent", ""))
        }
    return record
