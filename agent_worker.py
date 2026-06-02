"""Agent Worker nodes - konkretne implementacje agentów z dziedziczeniem."""
from core.logging_setup import get_logger

log = get_logger(__name__)

class BaseWorker:
    def __init__(self, ctx):
        self.ctx = ctx
        self.name = "BaseWorker"
        
    def execute(self, task: str) -> str:
        log.info(f"{self.name} wykonuje: {task}")
        return f"{self.name} przetworzył zadanie."

class PlanningAgent(BaseWorker):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.name = "PlanningAgent"
        
    def execute(self, task: str) -> str:
        log.info(f"{self.name} planuje: {task}")
        # Można podpiąć wywoływanie modelu
        if self.ctx and self.ctx.has("ollama"):
            try:
                # Ograniczone wywołanie do planowania, np. zero-shot z promptem systemowym
                return self.ctx.ollama.generate(f"Rozłóż na kroki: {task}", system="Jesteś ekspertem planistą. Wypisz kroki realizacji.")
            except Exception as e:
                log.error(f"Błąd modelu w planowaniu: {e}")
        return f"Plan dla zadania '{task}'"

class ResearchAgent(BaseWorker):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.name = "ResearchAgent"
        
    def execute(self, task: str) -> str:
        log.info(f"{self.name} bada temat: {task}")
        if self.ctx and self.ctx.has("deep_research"):
            return self.ctx.deep_research.research(task)
        return f"Zebrano dostępne informacje o: {task}"

class CodingAgent(BaseWorker):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.name = "CodingAgent"

    def execute(self, task: str) -> str:
        log.info(f"{self.name} przygotowuje kod: {task}")
        if self.ctx and self.ctx.has("ollama"):
            try:
                router = getattr(self.ctx, "model_router", None)
                model = router.get_optimal_model("coding") if router else self.ctx.config.llm.model
                old_model = self.ctx.ollama.model
                self.ctx.ollama.model = model
                resp = self.ctx.ollama.generate(task, system="Jesteś programistą. Tylko wygeneruj kod bez opisu.")
                self.ctx.ollama.model = old_model
                return resp
            except Exception as e:
                log.error(f"Coding error: {e}")
        return "def generated_code():\n    return 'Hello World'"
