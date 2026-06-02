"""Multi Agent Orchestrator - zarządzanie flotą agentów w celu realizacji złożonych zadań"""
from typing import Dict, Any, Optional

from core.logging_setup import get_logger
from agent_worker import BaseWorker, PlanningAgent, ResearchAgent, CodingAgent

log = get_logger(__name__)

class Orchestrator:
    def __init__(self, ctx):
        self.ctx = ctx
        self.agents: Dict[str, BaseWorker] = {
            "plan": PlanningAgent(ctx),
            "research": ResearchAgent(ctx),
            "code": CodingAgent(ctx),
            "default": BaseWorker(ctx)
        }
        
    def dispatch(self, task: str) -> str:
        """Kieruje zadanie do odpowiedniego Agenta w zależności od słów kluczowych (lub przy uzyciu LLM)."""
        log.info(f"Routing task w systemie agentów: {task}")
        
        lower_task = task.lower()
        if "zaplanuj" in lower_task or "rozpisz" in lower_task or "plan" in lower_task:
            return self.agents["plan"].execute(task)
        elif "wyszukaj" in lower_task or "research" in lower_task or "zbadaj" in lower_task:
            return self.agents["research"].execute(task)
        elif "napisz kod" in lower_task or "kod" in lower_task or "program" in lower_task:
            return self.agents["code"].execute(task)
        else:
            # Domyślnie wykonuje ogólne zadanie
            return self.agents["default"].execute(task)
            
    def orchestrated_workflow(self, task: str) -> str:
        """Autonomiczny wieloetapowy workflow - np. najpierw research, potem plan, potem kod."""
        log.info(f"Start workflow dla: {task}")
        
        research_result = self.agents["research"].execute(f"Zbadaj tematykę: {task}")
        plan_result = self.agents["plan"].execute(f"Na podstawie wiedzy: {research_result}, stwórz plan dla zadania: {task}")
        
        # Opcjonalnie mozna przekazac the plan to the code agent
        return f"WORKFLOW ZAKOŃCZONY.\n\nKROK 1 (Research):\n{research_result}\n\nKROK 2 (Plan):\n{plan_result}"
