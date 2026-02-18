"""Response generation and sending for Slack mentions."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ultrawork.config import ResponseConfig, get_config
from ultrawork.models.polling import PendingResponse, ResponseIntent, ResponseType
from ultrawork.models.thread import ThreadRecord
from ultrawork.slack.state import PollingStateManager

# Localized response templates
RESPONSE_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Hello! How can I help you?",
        "acknowledge": "Got it. I'll take a look.",
        "issue": "Issue received. I'm analyzing the details.\nI'll update you on the progress shortly.",
        "status": "Checking the current status. I'll share the details shortly.",
        "simple_query": "Got your question. I'll look into it and get back to you.",
        "action": "Request received. I'll register this as a task and work on it.\nI'll post progress updates in this thread.",
        "default": "Message received. I'll analyze the context and prepare an appropriate response.",
    },
    "ko": {
        "greeting": "안녕하세요! 무엇을 도와드릴까요?",
        "acknowledge": "확인했습니다. 살펴볼게요.",
        "issue": "이슈를 접수했습니다. 세부 사항을 분석 중입니다.\n진행 상황을 곧 업데이트해 드리겠습니다.",
        "status": "현재 상태를 확인 중입니다. 곧 자세한 내용을 공유드리겠습니다.",
        "simple_query": "질문 확인했습니다. 확인 후 답변드리겠습니다.",
        "action": "요청을 접수했습니다. 작업으로 등록하고 진행하겠습니다.\n이 스레드에 진행 상황을 업데이트하겠습니다.",
        "default": "메시지를 확인했습니다. 컨텍스트를 분석하고 적절한 응답을 준비하겠습니다.",
    },
    "ja": {
        "greeting": "こんにちは！何かお手伝いできますか？",
        "acknowledge": "了解しました。確認いたします。",
        "issue": "問題を受け付けました。詳細を分析中です。\n進捗状況をすぐにお知らせします。",
        "status": "現在の状況を確認中です。詳細をすぐに共有いたします。",
        "simple_query": "ご質問を確認しました。調べてご返答いたします。",
        "action": "リクエストを受け付けました。タスクとして登録し、作業を進めます。\nこのスレッドで進捗を更新いたします。",
        "default": "メッセージを受け付けました。コンテキストを分析し、適切な回答を準備いたします。",
    },
    "zh": {
        "greeting": "你好！有什么可以帮助你的吗？",
        "acknowledge": "收到，我来看看。",
        "issue": "已收到问题报告。正在分析详细信息。\n稍后会更新进展。",
        "status": "正在检查当前状态。稍后会分享详细信息。",
        "simple_query": "收到你的问题。我查看后会回复你。",
        "action": "已收到请求。我会将此注册为任务并开始处理。\n会在此线程中发布进展更新。",
        "default": "已收到消息。我会分析上下文并准备适当的回复。",
    },
    "es": {
        "greeting": "¡Hola! ¿En qué puedo ayudarte?",
        "acknowledge": "Entendido. Lo revisaré.",
        "issue": "Problema recibido. Estoy analizando los detalles.\nTe actualizaré sobre el progreso pronto.",
        "status": "Verificando el estado actual. Compartiré los detalles pronto.",
        "simple_query": "Recibí tu pregunta. Lo revisaré y te responderé.",
        "action": "Solicitud recibida. Registraré esto como tarea y trabajaré en ello.\nPublicaré actualizaciones en este hilo.",
        "default": "Mensaje recibido. Analizaré el contexto y prepararé una respuesta adecuada.",
    },
    "fr": {
        "greeting": "Bonjour ! Comment puis-je vous aider ?",
        "acknowledge": "Bien reçu. Je vais regarder.",
        "issue": "Problème reçu. J'analyse les détails.\nJe vous tiendrai informé de l'avancement.",
        "status": "Vérification de l'état actuel. Je partagerai les détails bientôt.",
        "simple_query": "J'ai reçu votre question. Je vais vérifier et vous répondre.",
        "action": "Demande reçue. Je vais enregistrer cela comme tâche et y travailler.\nJe publierai les mises à jour dans ce fil.",
        "default": "Message reçu. Je vais analyser le contexte et préparer une réponse appropriée.",
    },
    "de": {
        "greeting": "Hallo! Wie kann ich Ihnen helfen?",
        "acknowledge": "Verstanden. Ich schaue mir das an.",
        "issue": "Problem erhalten. Ich analysiere die Details.\nIch werde Sie bald über den Fortschritt informieren.",
        "status": "Überprüfe den aktuellen Status. Ich teile die Details bald mit.",
        "simple_query": "Ihre Frage erhalten. Ich werde es prüfen und mich melden.",
        "action": "Anfrage erhalten. Ich registriere dies als Aufgabe und arbeite daran.\nIch poste Updates in diesem Thread.",
        "default": "Nachricht erhalten. Ich analysiere den Kontext und bereite eine passende Antwort vor.",
    },
    "pt": {
        "greeting": "Olá! Como posso ajudar?",
        "acknowledge": "Entendido. Vou dar uma olhada.",
        "issue": "Problema recebido. Estou analisando os detalhes.\nAtualizarei sobre o progresso em breve.",
        "status": "Verificando o status atual. Compartilharei os detalhes em breve.",
        "simple_query": "Recebi sua pergunta. Vou verificar e retornar.",
        "action": "Solicitação recebida. Vou registrar isso como tarefa e trabalhar nela.\nPostarei atualizações nesta thread.",
        "default": "Mensagem recebida. Vou analisar o contexto e preparar uma resposta adequada.",
    },
}


def _get_response_lang() -> str:
    """Get the configured response language code."""
    try:
        return get_config().language.default
    except Exception:
        return "en"


def _get_templates(lang: str | None = None) -> dict[str, str]:
    """Get response templates for the configured language."""
    lang = lang or _get_response_lang()
    return RESPONSE_TEMPLATES.get(lang, RESPONSE_TEMPLATES["en"])


@dataclass
class ResponseCandidate:
    """A candidate response with confidence score."""

    text: str
    response_type: ResponseType
    intent: ResponseIntent
    confidence: float


class SlackResponder:
    """Generates and manages responses to Slack mentions."""

    def __init__(
        self,
        data_dir: Path,
        config: ResponseConfig | None = None,
    ):
        """Initialize the responder.

        Args:
            data_dir: Base data directory
            config: Response configuration
        """
        self.data_dir = Path(data_dir)
        self.config = config or ResponseConfig()
        self.state_manager = PollingStateManager(data_dir)

    def analyze_intent(self, text: str) -> ResponseIntent:
        """Analyze the intent of a message.

        Args:
            text: Message text to analyze

        Returns:
            Detected intent
        """
        text_lower = text.lower()

        # Question patterns
        question_patterns = [
            "?",
            "how",
            "what",
            "why",
            "when",
            "where",
            "who",
            "which",
            "can you explain",
            "could you tell",
        ]
        if any(p in text_lower for p in question_patterns):
            return ResponseIntent.QUESTION

        # Issue report patterns
        issue_patterns = [
            "bug",
            "error",
            "broken",
            "not working",
            "issue",
            "problem",
            "fix",
            "crash",
            "fail",
        ]
        if any(p in text_lower for p in issue_patterns):
            return ResponseIntent.ISSUE_REPORT

        # Request patterns
        request_patterns = [
            "please",
            "can you",
            "could you",
            "would you",
            "help me",
            "need",
            "want",
        ]
        if any(p in text_lower for p in request_patterns):
            return ResponseIntent.REQUEST

        # Status query patterns
        status_patterns = [
            "status",
            "progress",
            "update",
        ]
        if any(p in text_lower for p in status_patterns):
            return ResponseIntent.STATUS_QUERY

        # Greeting patterns
        greeting_patterns = [
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
        ]
        if any(p in text_lower for p in greeting_patterns):
            return ResponseIntent.GREETING

        return ResponseIntent.GENERAL

    def determine_response_type(
        self,
        intent: ResponseIntent,
        message_length: int,
        thread_length: int,
    ) -> ResponseType:
        """Determine the type of response needed.

        Args:
            intent: Detected message intent
            message_length: Length of the original message
            thread_length: Number of messages in thread

        Returns:
            Response type to use
        """
        # Simple acknowledgments
        if intent == ResponseIntent.GREETING:
            return ResponseType.ACKNOWLEDGE

        # Status queries are usually simple
        if intent == ResponseIntent.STATUS_QUERY:
            return ResponseType.SIMPLE_QUERY

        # Short questions are usually simple
        if intent == ResponseIntent.QUESTION and message_length < 100:
            return ResponseType.SIMPLE_QUERY

        # Issue reports need action
        if intent == ResponseIntent.ISSUE_REPORT:
            return ResponseType.ACTION

        # Complex requests need manual review
        if intent == ResponseIntent.REQUEST:
            if message_length > 200 or thread_length > 10:
                return ResponseType.COMPLEX
            return ResponseType.ACTION

        # Long threads are usually complex
        if thread_length > 15:
            return ResponseType.COMPLEX

        # Default to defer for uncertain cases
        if intent == ResponseIntent.GENERAL:
            return ResponseType.DEFER

        return ResponseType.SIMPLE_QUERY

    def generate_response(
        self,
        message: dict,
        thread: ThreadRecord | None = None,
        context_summary: str = "",
    ) -> ResponseCandidate:
        """Generate a response for a mention.

        Args:
            message: Slack message dict with 'text', 'ts', etc.
            thread: Thread record with context
            context_summary: Summary of explored context

        Returns:
            Response candidate with text and metadata
        """
        text = message.get("text", "")
        intent = self.analyze_intent(text)

        thread_length = thread.message_count if thread else 1
        response_type = self.determine_response_type(
            intent=intent,
            message_length=len(text),
            thread_length=thread_length,
        )

        # Generate response text based on intent
        response_text = self._generate_response_text(
            intent=intent,
            response_type=response_type,
            message=message,
            thread=thread,
            context_summary=context_summary,
        )

        # Calculate confidence
        confidence = self._calculate_confidence(
            intent=intent,
            response_type=response_type,
            thread_length=thread_length,
        )

        return ResponseCandidate(
            text=response_text,
            response_type=response_type,
            intent=intent,
            confidence=confidence,
        )

    def _generate_response_text(
        self,
        intent: ResponseIntent,
        response_type: ResponseType,
        message: dict,
        thread: ThreadRecord | None,
        context_summary: str,
    ) -> str:
        """Generate the actual response text.

        Args:
            intent: Detected intent
            response_type: Type of response
            message: Original message
            thread: Thread record
            context_summary: Context summary

        Returns:
            Response text
        """
        templates = _get_templates()

        # Simple acknowledgments
        if response_type == ResponseType.ACKNOWLEDGE:
            if intent == ResponseIntent.GREETING:
                return templates["greeting"]
            return templates["acknowledge"]

        # Issue reports
        if intent == ResponseIntent.ISSUE_REPORT:
            return templates["issue"]

        # Status queries
        if intent == ResponseIntent.STATUS_QUERY:
            return templates["status"]

        # Simple questions
        if response_type == ResponseType.SIMPLE_QUERY:
            return templates["simple_query"]

        # Action required (will create task)
        if response_type == ResponseType.ACTION:
            return templates["action"]

        # Complex or defer
        return templates["default"]

    def _calculate_confidence(
        self,
        intent: ResponseIntent,
        response_type: ResponseType,
        thread_length: int,
    ) -> float:
        """Calculate confidence score for the response.

        Args:
            intent: Detected intent
            response_type: Type of response
            thread_length: Thread length

        Returns:
            Confidence score (0.0 to 1.0)
        """
        base_confidence = 0.5

        # Simple acknowledgments are high confidence
        if response_type == ResponseType.ACKNOWLEDGE:
            return 0.95

        # Clear intents boost confidence
        if intent in (ResponseIntent.GREETING, ResponseIntent.STATUS_QUERY):
            base_confidence += 0.3

        # Questions are moderately confident
        if intent == ResponseIntent.QUESTION:
            base_confidence += 0.2

        # Long threads reduce confidence
        if thread_length > 10:
            base_confidence -= 0.15
        elif thread_length > 5:
            base_confidence -= 0.05

        # Complex and defer types are low confidence
        if response_type in (ResponseType.COMPLEX, ResponseType.DEFER):
            base_confidence -= 0.3

        return max(0.0, min(1.0, base_confidence))

    def should_auto_send(self, candidate: ResponseCandidate) -> bool:
        """Check if the response should be automatically sent.

        Args:
            candidate: Response candidate

        Returns:
            True if should auto-send
        """
        # Check response type against config
        type_allowed = candidate.response_type.value in self.config.auto_types

        # Check confidence threshold
        confidence_ok = candidate.confidence >= self.config.confidence_threshold

        return self.config.auto_respond and type_allowed and confidence_ok

    def create_pending_response(
        self,
        message: dict,
        candidate: ResponseCandidate,
        thread: ThreadRecord | None = None,
        context_summary: str = "",
        exploration_id: str | None = None,
    ) -> PendingResponse:
        """Create a pending response for manual review.

        Args:
            message: Original Slack message
            candidate: Generated response candidate
            thread: Thread record
            context_summary: Summary of context
            exploration_id: Linked exploration ID if any

        Returns:
            Pending response object
        """
        channel_info = message.get("channel", {})
        channel_id = (
            channel_info.get("id", "") if isinstance(channel_info, dict) else str(channel_info)
        )

        user_info = message.get("user", "")
        user_id = user_info.get("id", "") if isinstance(user_info, dict) else str(user_info)
        user_name = user_info.get("name", "") if isinstance(user_info, dict) else ""

        return PendingResponse(
            message_id=message.get("ts", ""),
            channel_id=channel_id,
            thread_ts=message.get("thread_ts", message.get("ts", "")),
            sender_id=user_id,
            sender_name=user_name,
            original_message=message.get("text", ""),
            proposed_response=candidate.text,
            response_type=candidate.response_type,
            intent=candidate.intent,
            confidence=candidate.confidence,
            created_at=datetime.now(),
            context_summary=context_summary,
            thread_message_count=thread.message_count if thread else 0,
            exploration_id=exploration_id,
        )

    def handle_mention(
        self,
        message: dict,
        thread: ThreadRecord | None = None,
        context_summary: str = "",
        exploration_id: str | None = None,
    ) -> tuple[PendingResponse, bool]:
        """Handle a mention and generate response.

        Args:
            message: Slack message dict
            thread: Thread record with context
            context_summary: Summary of explored context
            exploration_id: Linked exploration ID

        Returns:
            Tuple of (PendingResponse, should_auto_send)
        """
        # Generate response
        candidate = self.generate_response(
            message=message,
            thread=thread,
            context_summary=context_summary,
        )

        # Create pending response
        pending = self.create_pending_response(
            message=message,
            candidate=candidate,
            thread=thread,
            context_summary=context_summary,
            exploration_id=exploration_id,
        )

        # Determine if should auto-send
        should_send = self.should_auto_send(candidate)

        if not should_send:
            # Save to pending for manual review
            self.state_manager.add_pending_response(pending)

        return pending, should_send
