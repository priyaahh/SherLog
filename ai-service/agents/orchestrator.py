"""
Multi-agent orchestrator using LangGraph
Coordinates execution flow between specialized agents
"""

import logging
import uuid
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class InvestigationState(BaseModel):
    """State object for investigation workflow"""
    investigation_id: str
    incident_id: str
    logs: List[str]
    alerts: List[str]
    context: str
    
    # Intermediate results
    parsed_logs: Dict[str, Any] = {}
    anomalies: List[Dict[str, Any]] = []
    relevant_runbooks: List[Dict[str, Any]] = []
    root_cause: str = ""
    risk_assessment: Dict[str, Any] = {}
    recommendations: List[str] = []
    
    # Metadata
    status: str = "in_progress"
    errors: List[str] = []


class AIOrchestrator:
    """Orchestrates multi-agent incident investigation"""
    
    def __init__(self, settings):
        """Initialize orchestrator with settings"""
        self.settings = settings
        self.investigations: Dict[str, InvestigationState] = {}
        
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
        logger.info(f"[{state.investigation_id}] Parsing logs...")
        try:
            # TODO: Implement log parsing logic
            state.parsed_logs = {
                "entries": len(state.logs),
                "time_range": "parsed",
                "sources": ["syslog", "audit"]
            }
        except Exception as e:
            state.errors.append(f"Log parsing failed: {e}")
            logger.error(f"Log parsing error: {e}")
        return state
    
    def _detect_anomalies_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 2: Detect anomalies in logs"""
        logger.info(f"[{state.investigation_id}] Detecting anomalies...")
        try:
            # TODO: Implement anomaly detection logic
            state.anomalies = [
                {"type": "unusual_process", "severity": "high", "count": 5}
            ]
        except Exception as e:
            state.errors.append(f"Anomaly detection failed: {e}")
            logger.error(f"Anomaly detection error: {e}")
        return state
    
    def _retrieve_context_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 3: Retrieve relevant runbooks and context"""
        logger.info(f"[{state.investigation_id}] Retrieving context...")
        try:
            # TODO: Implement RAG retrieval
            state.relevant_runbooks = [
                {"id": "rb_001", "title": "Process Anomaly Response"}
            ]
        except Exception as e:
            state.errors.append(f"Context retrieval failed: {e}")
            logger.error(f"Context retrieval error: {e}")
        return state
    
    def _root_cause_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 4: Analyze root cause"""
        logger.info(f"[{state.investigation_id}] Analyzing root cause...")
        try:
            # TODO: Implement root cause analysis with LLM
            state.root_cause = "Unauthorized process execution detected"
        except Exception as e:
            state.errors.append(f"Root cause analysis failed: {e}")
            logger.error(f"Root cause analysis error: {e}")
        return state
    
    def _risk_assessment_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 5: Assess risk and impact"""
        logger.info(f"[{state.investigation_id}] Assessing risk...")
        try:
            # TODO: Implement risk assessment logic
            state.risk_assessment = {
                "severity": "high",
                "confidence": 0.95,
                "blast_radius": "10+ systems",
                "attack_pattern": "T1059 (Command and Scripting Interpreter)"
            }
        except Exception as e:
            state.errors.append(f"Risk assessment failed: {e}")
            logger.error(f"Risk assessment error: {e}")
        return state
    
    def _generate_report_agent(self, state: InvestigationState) -> InvestigationState:
        """Phase 6: Generate report"""
        logger.info(f"[{state.investigation_id}] Generating report...")
        try:
            state.recommendations = [
                "Isolate affected systems immediately",
                "Review process execution logs",
                "Initiate IR protocol section 3.2"
            ]
            state.status = "completed"
        except Exception as e:
            state.errors.append(f"Report generation failed: {e}")
            logger.error(f"Report generation error: {e}")
        return state
    
    def start_investigation(self, incident_data: Dict[str, Any]) -> str:
        """Start a new investigation"""
        investigation_id = str(uuid.uuid4())
        
        state = InvestigationState(
            investigation_id=investigation_id,
            incident_id=incident_data.get("incident_id", "unknown"),
            logs=incident_data.get("logs", []),
            alerts=incident_data.get("alerts", []),
            context=incident_data.get("context", "")
        )
        
        try:
            # Execute graph
            result = self.graph.invoke(state)
            self.investigations[investigation_id] = result
            logger.info(f"Investigation {investigation_id} started")
        except Exception as e:
            logger.error(f"Investigation failed: {e}")
            state.status = "failed"
            state.errors.append(str(e))
            self.investigations[investigation_id] = state
        
        return investigation_id
    
    def get_investigation_result(self, investigation_id: str) -> Dict[str, Any]:
        """Get investigation results"""
        state = self.investigations.get(investigation_id)
        if not state:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        return {
            "investigation_id": investigation_id,
            "status": state.status,
            "root_cause": state.root_cause,
            "risk_assessment": state.risk_assessment,
            "recommendations": state.recommendations,
            "anomalies": state.anomalies,
            "errors": state.errors
        }
