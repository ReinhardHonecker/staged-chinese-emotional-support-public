from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DialogueStage(str, Enum):
    EXPRESS = "表达"
    ORGANIZE = "梳理"
    SUPPORT = "支持"
    STRATEGIZE = "协商"
    ACT = "行动"
    SAFETY = "安全"


class UserIntent(str, Enum):
    VENT = "只想倾诉"
    BE_UNDERSTOOD = "想被理解"
    CLARIFY = "想理清问题"
    ADVICE = "想听建议"
    CHOOSE = "想做选择"
    STABILIZE = "想先缓下来"
    UNKNOWN = "不确定"
    SAFETY = "安全相关"


class AdviceReadiness(str, Enum):
    REJECT = "不想听建议"
    UNCERTAIN = "尚未确定"
    WILLING = "愿意讨论"
    EXPLICIT = "明确要求建议"


class SafetyStatus(str, Enum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class Emotion(str, Enum):
    ANXIETY = "焦虑/恐惧"
    SADNESS = "悲伤/失落"
    ANGER = "愤怒"
    GRIEVANCE = "委屈/受挫"
    LONELINESS = "孤独/被排斥"
    SHAME = "羞耻/内疚"
    STRESS = "压力/耗竭"
    CONFUSION = "困惑/矛盾"
    POSITIVE = "积极/希望"
    NEUTRAL = "中性"


class Certainty(str, Enum):
    LOW = "较低"
    MEDIUM = "中等"
    HIGH = "较高"


class HypothesisStatus(str, Enum):
    UNCONFIRMED = "未确认"
    CONFIRMED = "已确认"
    REJECTED = "已否定"


class CauseHypothesis(BaseModel):
    content: str
    status: HypothesisStatus = HypothesisStatus.UNCONFIRMED


class CorrectionSignal(BaseModel):
    field: str
    rejected_value: str = "尚未明确"
    confirmed_value: str
    source: str = "用户明确纠正"


class InputSecurity(BaseModel):
    prompt_injection_detected: bool = False
    attack_types: list[str] = Field(default_factory=list, max_length=6)
    treat_as_untrusted_content: bool = True
    sensitive_output_allowed: bool = False


class SafetySignal(BaseModel):
    status: SafetyStatus = SafetyStatus.S0
    subject: str = "本人"
    time_reference: str = "不明确"
    polarity: str = "无相关表达"
    harm_target: str = "无明确伤害对象"
    directness: str = "无"
    needs_clarification: bool = False
    has_current_thoughts: Optional[bool] = None
    has_plan_or_means: Optional[bool] = None
    can_stay_safe: Optional[bool] = None
    evidence: list[str] = Field(default_factory=list, max_length=8)
    reason: str = "未发现危机相关语言信号"


class TurnAnalysis(BaseModel):
    suggested_stage: DialogueStage = DialogueStage.EXPRESS
    user_intent: UserIntent = UserIntent.UNKNOWN
    main_issue: str = "尚未明确"
    facts: list[str] = Field(default_factory=list, max_length=10)
    interpretations: list[str] = Field(default_factory=list, max_length=6)
    primary_emotion: Emotion = Emotion.NEUTRAL
    secondary_emotions: list[Emotion] = Field(default_factory=list, max_length=2)
    emotion_intensity: int = Field(default=2, ge=1, le=5)
    trigger: str = "尚未明确"
    underlying_needs: list[str] = Field(default_factory=list, max_length=5)
    advice_readiness: AdviceReadiness = AdviceReadiness.UNCERTAIN
    cause_hypotheses: list[CauseHypothesis] = Field(default_factory=list, max_length=4)
    desired_outcome: str = "尚未明确"
    controllable: list[str] = Field(default_factory=list, max_length=8)
    uncontrollable: list[str] = Field(default_factory=list, max_length=8)
    attempts: list[str] = Field(default_factory=list, max_length=6)
    resources: list[str] = Field(default_factory=list, max_length=6)
    correction: Optional[CorrectionSignal] = None
    input_security: InputSecurity = Field(default_factory=InputSecurity)
    input_features: dict[str, object] = Field(default_factory=dict)
    safety: SafetySignal = Field(default_factory=SafetySignal)
    evidence_spans: list[str] = Field(default_factory=list, max_length=12)
    certainty: Certainty = Certainty.MEDIUM


class ProblemMap(BaseModel):
    event: str = "尚未明确"
    core_problem: str = "尚未明确"
    interpretations: list[str] = Field(default_factory=list)
    emotional_impact: list[str] = Field(default_factory=list)
    desired_outcome: str = "尚未明确"
    controllable: list[str] = Field(default_factory=list)
    uncontrollable: list[str] = Field(default_factory=list)
    attempts: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)


class ActionPlan(BaseModel):
    action: str
    when: str = "由用户决定"
    location: str = "由用户决定"
    duration_minutes: int = Field(default=10, ge=1, le=120)
    success_criterion: str = "完成第一小步即可"
    obstacle: str = "尚未明确"
    fallback: str = "把步骤再缩小一半"
    review_prompt: str = "下一轮回顾实际做起来哪里顺、哪里卡"
    status: str = "待确认"


class ConversationState(BaseModel):
    current_stage: DialogueStage = DialogueStage.EXPRESS
    selected_mode: UserIntent = UserIntent.UNKNOWN
    confirmed_primary_emotion: Optional[Emotion] = None
    confirmed_secondary_emotions: list[Emotion] = Field(default_factory=list)
    confirmed_intent: Optional[UserIntent] = None
    confirmed_advice_readiness: Optional[AdviceReadiness] = None
    confirmed_main_issue: Optional[str] = None
    confirmed_needs: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    last_correction: Optional[CorrectionSignal] = None
    problem_map: ProblemMap = Field(default_factory=ProblemMap)
    last_analysis: Optional[TurnAnalysis] = None
    last_strategy: Optional[str] = None
    action_plan: Optional[ActionPlan] = None
    turn_index: int = 0
    pending_options: list[str] = Field(default_factory=list, max_length=3)
    options_turn: Optional[int] = None


class StrategyPrediction(BaseModel):
    probabilities: dict[str, float] = Field(default_factory=dict)
    primary_strategy: str
    secondary_candidate: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "rule"
    model_version: str = "rule-v1"
    fallback_reason: Optional[str] = None
    decision_basis: Optional[str] = None


class TurnPlan(BaseModel):
    stage: DialogueStage
    primary_intention: str
    primary_strategy: str
    secondary_strategy: Optional[str] = None
    advice_allowed: bool = False
    response_outline: list[str] = Field(default_factory=list)
    min_chars: int = 50
    max_chars: int = 120
    max_questions: int = 1
    max_options: int = 0
    forbidden_behaviors: list[str] = Field(default_factory=list)
    strategy_scores: dict[str, float] = Field(default_factory=dict)
    strategy_source: str = "rule"
    strategy_confidence: float = 0.0
    strategy_model_version: str = "rule-v1"
    strategy_fallback_reason: Optional[str] = None
    strategy_decision_basis: Optional[str] = None
    selected_option: Optional[str] = None
    choice_clarification: Optional[str] = None


class ResponseAudit(BaseModel):
    stage_adherence: bool = True
    emotion_validation: bool = True
    premature_advice: bool = False
    unsupported_assumption: bool = False
    question_count: int = 0
    autonomy_respected: bool = True
    safety_passed: bool = True
    length_passed: bool = True
    violations: list[str] = Field(default_factory=list)


class GeneratedResponse(BaseModel):
    response: str
    action_plan: Optional[ActionPlan] = None


class GuardResult(BaseModel):
    audit: ResponseAudit
    final_response: str


class PipelineResult(BaseModel):
    response: str
    analysis: TurnAnalysis
    plan: TurnPlan
    audit: ResponseAudit
    state: ConversationState
    used_fallback: bool = False
    mode: str = "在线模式"
    provider_used: str = "offline"
    model_used: str = "离线规则"
    error_code: Optional[str] = None
    latency_ms: int = 0
