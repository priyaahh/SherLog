"""
Multi-agent orchestrator using LangGraph
Coordinates execution flow between specialized agents
"""

import logging
import re
import uuid
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


class InvestigationState(TypedDict, total=False):
    """State object for investigation workflow"""
    investigation_id: str
    incident_id: str
    logs: List[str]
    alerts: List[str]
    context: str
    
    # Intermediate results
    parsed_logs: Dict[str, Any]
    anomalies: List[Dict[str, Any]]
    relevant_runbooks: List[Dict[str, Any]]
    root_cause: str
    risk_assessment: Dict[str, Any]
    recommendations: List[str]
    
    # Metadata
    status: str
    errors: List[str]


class AIOrchestrator:
    """Orchestrates multi-agent incident investigation"""
    
    def __init__(self, settings, rag_retriever=None):
        """Initialize orchestrator with settings and optional RAG retriever"""
        self.settings = settings
        self.investigations: Dict[str, InvestigationState] = {}
        
        # Inject or initialize RAG retriever
        self.rag_retriever = rag_retriever
        if self.rag_retriever is None:
            try:
                from rag.retriever import RAGRetriever
                self.rag_retriever = RAGRetriever(settings)
            except Exception as e:
                logger.warning(f"Could not initialize default RAGRetriever: {e}")
                self.rag_retriever = None

        # Initialize LLM conditionally
        if getattr(settings, 'google_api_key', None):
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model=settings.llm_model,
                    temperature=settings.llm_temperature,
                    google_api_key=settings.google_api_key
                )
            except Exception as e:
                logger.warning(f"LLM initialization warning: {e}")
                self.llm = None
        else:
            self.llm = None
            logger.warning("GOOGLE_API_KEY not configured. Running orchestrator in rule/fallback mode.")
        
        # Build graph
        self.graph = self._build_graph()
        logger.info("AIOrchestrator initialized")
    
    def _build_graph(self):
        """Build LangGraph state graph"""
        workflow = StateGraph(InvestigationState)
        
        # Add nodes for each agent phase
        workflow.add_node("parse_logs", self._parse_logs_agent)
        workflow.add_node("detect_anomalies", self._detect_anomalies_agent)
        workflow.add_node("retrieve_context", self._retrieve_context_agent)
        workflow.add_node("root_cause_analysis", self._root_cause_agent)
        workflow.add_node("risk_assessment", self._risk_assessment_agent)
        workflow.add_node("generate_report", self._generate_report_agent)
        
        # Define edges (workflow execution order)
        workflow.add_edge("parse_logs", "detect_anomalies")
        workflow.add_edge("detect_anomalies", "retrieve_context")
        workflow.add_edge("retrieve_context", "root_cause_analysis")
        workflow.add_edge("root_cause_analysis", "risk_assessment")
        workflow.add_edge("risk_assessment", "generate_report")
        workflow.add_edge("generate_report", END)
        
        # Set entry point
        workflow.set_entry_point("parse_logs")
        
        return workflow.compile()
    
    def _parse_logs_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 1: Parse and normalize logs"""
        inv_id = state.get("investigation_id", "unknown")
        logger.info(f"[{inv_id}] Parsing logs...")
        try:
            logs = state.get("logs", [])
            state["parsed_logs"] = {
                "entries": len(logs),
                "time_range": "parsed",
                "sources": ["syslog", "application"],
                "sample_head": logs[:3] if logs else []
            }
        except Exception as e:
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(f"Log parsing failed: {e}")
            logger.error(f"Log parsing error: {e}")
        return state
    
    def _detect_anomalies_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 2: Detect anomalies via pattern matching across log lines"""
        inv_id = state.get("investigation_id", "unknown")
        logger.info(f"[{inv_id}] Detecting anomalies...")
        try:
            logs = state.get("logs", [])
            pattern_map: Dict[str, Dict[str, Any]] = {}

            rules = [
                ("db_pool_exhausted", r"(?i)(ERR_DB_POOL_EXHAUSTED|cannot acquire connection|connection pool.*exhausted|pool.*timeout)", "critical"),
                ("out_of_memory", r"(?i)(OutOfMemoryError|OOM|heap space|memory limit exceeded|cgroup out of memory)", "critical"),
                ("request_timeout", r"(?i)(request timeout|timeout after|timed out|deadline exceeded|504 Gateway)", "high"),
                ("connection_failure", r"(?i)(connection refused|connection reset|ECONNREFUSED|network unreachable|broken pipe)", "high"),
                ("database_error", r"(?i)(database|sql|postgres|mysql|mongo|psql).*error", "high"),
                ("http_server_error", r"(?i)(HTTP (500|502|503|504)|Internal Server Error|Bad Gateway|Service Unavailable)", "high"),
                ("auth_failure", r"(?i)(401 Unauthorized|403 Forbidden|authentication failed|permission denied)", "medium"),
                ("general_error", r"(?i)\b(ERROR|FATAL|CRITICAL|FAIL|EXCEPTION|Traceback)\b", "medium"),
            ]

            for line in logs:
                for p_type, regex, sev in rules:
                    if re.search(regex, line):
                        if p_type not in pattern_map:
                            pattern_map[p_type] = {
                                "type": p_type,
                                "severity": sev,
                                "count": 0,
                                "examples": []
                            }
                        pattern_map[p_type]["count"] += 1
                        if len(pattern_map[p_type]["examples"]) < 3:
                            pattern_map[p_type]["examples"].append(line.strip())
                        break

            anomalies = list(pattern_map.values())
            state["anomalies"] = anomalies
            logger.info(f"[{inv_id}] Detected {len(anomalies)} anomaly types")
        except Exception as e:
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(f"Anomaly detection failed: {e}")
            logger.error(f"Anomaly detection error: {e}")
            state["anomalies"] = []
        return state
    
    def _retrieve_context_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 3: Retrieve relevant runbooks and context using hybrid RAG search"""
        inv_id = state.get("investigation_id", "unknown")
        logger.info(f"[{inv_id}] Retrieving context...")
        try:
            query_parts = []
            if state.get("context"):
                query_parts.append(state["context"])

            for anom in state.get("anomalies", []):
                examples = anom.get("examples", [])
                if examples:
                    query_parts.extend(examples[:2])
                else:
                    query_parts.append(anom.get("type", "").replace("_", " "))

            if not query_parts:
                query_parts = state.get("logs", [])[:3]

            search_query = " ".join(query_parts) if query_parts else "database error failure incident"
            
            top_k = getattr(self.settings, 'rag_top_k', 3)
            if self.rag_retriever:
                results = self.rag_retriever.hybrid_search(query=search_query, top_k=top_k)
                state["relevant_runbooks"] = results
                logger.info(f"[{inv_id}] Retrieved {len(results)} relevant runbooks via hybrid search")
            else:
                logger.warning(f"[{inv_id}] RAG retriever not available, skipping retrieval")
                state["relevant_runbooks"] = []

        except Exception as e:
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(f"Context retrieval failed: {e}")
            logger.error(f"Context retrieval error: {e}")
            state["relevant_runbooks"] = []
        return state
    
    def _deterministic_root_cause(self, anomalies: List[Dict[str, Any]], logs: List[str]) -> str:
        """Fallback root cause synthesis when LLM is offline or not configured"""
        types = [a.get("type") for a in anomalies if a.get("type")]
        if "db_pool_exhausted" in types or any("ERR_DB_POOL_EXHAUSTED" in l for l in logs):
            return "Database connection pool exhausted. Active workers could not acquire connections within the timeout threshold, leading to cascaded request timeouts."
        elif "out_of_memory" in types:
            return "Java Virtual Machine (JVM) heap space exhaustion causing pod eviction and unresponsiveness."
        elif "request_timeout" in types:
            return "Upstream request timeout. Target service dependencies failed to respond within latency thresholds."
        elif "connection_failure" in types:
            return "Network connection failure. Unable to establish TCP socket connection to target service."
        elif anomalies:
            return f"Service failure triggered by {anomalies[0].get('type', 'system anomaly')} leading to degraded performance."
        elif logs:
            return f"Error detected in service logs: {logs[0][:120]}"
        return "System failure identified from log errors."

    def _root_cause_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 4: Analyze root cause using Gemini LLM and context"""
        inv_id = state.get("investigation_id", "unknown")
        logger.info(f"[{inv_id}] Analyzing root cause...")
        try:
            logs = state.get("logs", [])
            runbooks = state.get("relevant_runbooks", [])
            anomalies = state.get("anomalies", [])
            context = state.get("context", "")

            logs_text = "\n".join(logs[:50]) if logs else "No logs provided"
            
            runbooks_text = "\n".join([
                f"- Document ID: {rb.get('id', 'N/A')}\n  Title: {rb.get('title', 'N/A')}\n  Content: {rb.get('content', '')[:300]}"
                for rb in runbooks
            ]) if runbooks else "No runbooks matched"

            anomalies_text = "\n".join([
                f"- Anomaly: {a.get('type')}, Severity: {a.get('severity')}, Occurrences: {a.get('count')}\n  Sample: {a.get('examples', [''])[0]}"
                for a in anomalies
            ]) if anomalies else "No anomalies detected"

            prompt = (
                "You are an expert Site Reliability Engineer analyzing an IT system incident.\n"
                f"Incident Context: {context}\n\n"
                f"Detected Anomalies:\n{anomalies_text}\n\n"
                f"Log Entries:\n{logs_text}\n\n"
                f"Matched Runbooks / Reference:\n{runbooks_text}\n\n"
                "Task: Provide a concise, highly specific root cause analysis in 2-3 sentences. "
                "Explicitly identify the core failure mechanism, why it occurred, and its direct impact. "
                "Do not include conversational filler or markdown headers."
            )

            if self.llm:
                try:
                    response = self.llm.invoke(prompt)
                    content = response.content if hasattr(response, "content") else str(response)
                    if isinstance(content, list):
                        rc = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
                    else:
                        rc = str(content)
                    state["root_cause"] = rc.strip()
                except Exception as llm_err:
                    logger.error(f"LLM root cause invocation failed: {llm_err}")
                    if "errors" not in state or not isinstance(state["errors"], list):
                        state["errors"] = []
                    state["errors"].append(f"LLM invocation error: {llm_err}")
                    state["root_cause"] = self._deterministic_root_cause(anomalies, logs)
            else:
                state["root_cause"] = self._deterministic_root_cause(anomalies, logs)

        except Exception as e:
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(f"Root cause analysis failed: {e}")
            logger.error(f"Root cause analysis error: {e}")
            state["root_cause"] = self._deterministic_root_cause(state.get("anomalies", []), state.get("logs", []))

        return state
    
    def _risk_assessment_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 5: Assess risk and impact derived from detected anomalies"""
        inv_id = state.get("investigation_id", "unknown")
        logger.info(f"[{inv_id}] Assessing risk...")
        try:
            anomalies = state.get("anomalies", [])
            sev_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            max_sev = "low"
            max_score = 1
            total_occurrences = 0

            for a in anomalies:
                s = a.get("severity", "low").lower()
                score = sev_weights.get(s, 1)
                total_occurrences += a.get("count", 1)
                if score > max_score:
                    max_score = score
                    max_sev = s

            if len(anomalies) >= 2 or total_occurrences >= 5:
                confidence = 0.95
            elif len(anomalies) == 1:
                confidence = 0.85
            else:
                confidence = 0.60

            if max_score >= 4:
                blast_radius = "Critical service degradation impacting transaction workflows"
            elif max_score >= 3:
                blast_radius = "Multiple upstream services impacted by latency"
            else:
                blast_radius = "Isolated component degradation"

            state["risk_assessment"] = {
                "severity": max_sev,
                "confidence": confidence,
                "blast_radius": blast_radius,
                "impact_summary": f"Identified {len(anomalies)} anomaly types across {total_occurrences} log instances."
            }
        except Exception as e:
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(f"Risk assessment failed: {e}")
            logger.error(f"Risk assessment error: {e}")
            state["risk_assessment"] = {
                "severity": "medium",
                "confidence": 0.5,
                "blast_radius": "Unknown"
            }
        return state
    
    def _generate_report_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 6: Generate final recommendations and complete investigation"""
        inv_id = state.get("investigation_id", "unknown")
        logger.info(f"[{inv_id}] Generating report...")
        try:
            recs = []
            for a in state.get("anomalies", []):
                a_type = a.get("type", "")
                if a_type == "db_pool_exhausted":
                    recs.append("Increase database connection pool max size and ensure connection checkout timeouts are enforced.")
                    recs.append("Audit active queries to identify unreleased connections and connection leaks.")
                elif a_type == "out_of_memory":
                    recs.append("Increase container memory allocation and inspect heap dumps for memory leaks.")
                elif a_type == "request_timeout":
                    recs.append("Inspect downstream latency metrics and review gateway timeout thresholds.")
                elif a_type == "connection_failure":
                    recs.append("Verify downstream service health, DNS routing, and security group network ACLs.")
                elif a_type == "auth_failure":
                    recs.append("Validate API credentials, token expiry, and IAM access policies.")

            for rb in state.get("relevant_runbooks", []):
                title = rb.get("title") or rb.get("id")
                if title:
                    recs.append(f"Apply remediation runbook: '{title}'")

            if not recs:
                recs = [
                    "Inspect service telemetry and recent deployment changes.",
                    "Verify dependent service health and network connectivity."
                ]

            state["recommendations"] = recs[:5]
            state["status"] = "completed"
        except Exception as e:
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(f"Report generation failed: {e}")
            logger.error(f"Report generation error: {e}")
            state["status"] = "completed"
        return state
    
    def start_investigation(self, incident_data: Dict[str, Any]) -> str:
        """Start a new investigation"""
        investigation_id = str(uuid.uuid4())
        
        state: InvestigationState = {
            "investigation_id": investigation_id,
            "incident_id": incident_data.get("incident_id", "unknown"),
            "logs": incident_data.get("logs", []),
            "alerts": incident_data.get("alerts", []),
            "context": incident_data.get("context", ""),
            "parsed_logs": {},
            "anomalies": [],
            "relevant_runbooks": [],
            "root_cause": "",
            "risk_assessment": {},
            "recommendations": [],
            "status": "in_progress",
            "errors": []
        }
        
        try:
            # Execute graph
            result = self.graph.invoke(state)
            self.investigations[investigation_id] = result
            logger.info(f"Investigation {investigation_id} started")
        except Exception as e:
            logger.error(f"Investigation failed: {e}")
            state["status"] = "failed"
            if "errors" not in state or not isinstance(state["errors"], list):
                state["errors"] = []
            state["errors"].append(str(e))
            self.investigations[investigation_id] = state
        
        return investigation_id
    
    def get_investigation_result(self, investigation_id: str) -> Dict[str, Any]:
        """Get investigation results"""
        state = self.investigations.get(investigation_id)
        if not state:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        return {
            "investigation_id": investigation_id,
            "status": state.get("status", "completed"),
            "root_cause": state.get("root_cause", ""),
            "risk_assessment": state.get("risk_assessment", {}),
            "recommendations": state.get("recommendations", []),
            "anomalies": state.get("anomalies", []),
            "errors": state.get("errors", [])
        }
