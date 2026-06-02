"""Model Orchestrator - wybór optymalnego modelu (Vision/Coding itp)"""
from core.logging_setup import get_logger
log = get_logger(__name__)

class ModelRouter:
    def get_optimal_model(self, task_type: str) -> str:
        models = {
            "vision": "llama3-vision",
            "coding": "qwen2.5-coder",
            "chat": "llama3.1"
        }
        chosen = models.get(task_type, "llama3.1")
        log.info(f"Router wybrał model: {chosen} dla {task_type}")
        return chosen
