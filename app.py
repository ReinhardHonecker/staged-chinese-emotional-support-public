from __future__ import annotations

import json
from html import escape
from pathlib import Path

import streamlit as st

from config import LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS
from modules.conversation_state import apply_understanding_feedback
from modules.llm_client import (
    LLMGateway,
    LLMRuntimeConfig,
    ProviderType,
    is_llm_configured,
)
from modules.models import (
    ConversationState,
    DialogueStage,
    Emotion,
    SafetyStatus,
    UserIntent,
)
from modules.pipeline import UserInputError, process_message
from modules.strategy_selector import strategy_model_status


def bilingual(english: str, chinese: str) -> str:
    return f"{english} / {chinese}"


FULL_TITLE = bilingual(
    "A Staged Chinese Emotional-support Dialogue System with Intent-driven Multidimensional State Modeling",
    "基于意图驱动与多维状态建模的分阶段中文情感支持对话系统",
)
DISPLAY_TITLE = bilingual("Staged Chinese Emotional Support", "心语 · 分阶段情感支持")
ASSET_DIR = Path(__file__).resolve().parent / "assets"

SUPPORT_MODES = ["我想先说说", "帮我理清楚", "一起想办法", "先帮我稳一下"]
MODE_LABELS = {
    "我想先说说": bilingual("💬 Talk first", "倾诉"),
    "帮我理清楚": bilingual("🧭 Organize", "梳理"),
    "一起想办法": bilingual("🪴 Plan action", "行动"),
    "先帮我稳一下": bilingual("🌿 Stabilize", "稳定"),
}
MODE_HINTS = {
    "我想先说说": bilingual(
        "Start with what matters most. This turn will not rush into analysis or advice.",
        "先把最在意的部分说出来。这一轮不急着分析，也不急着给建议。",
    ),
    "帮我理清楚": bilingual(
        "Separate facts, worries, feelings, and the point where you feel stuck.",
        "一起区分事实、担心、感受和真正卡住你的地方。",
    ),
    "一起想办法": bilingual(
        "Compare possible directions with your consent, then turn one choice into a small step.",
        "在你愿意的前提下比较方向，再把选择变成一个小步骤。",
    ),
    "先帮我稳一下": bilingual(
        "Reduce the immediate confusion and tension before handling a complex problem.",
        "先降低此刻的混乱和紧绷，暂时不处理复杂问题。",
    ),
}
MODE_PLACEHOLDERS = {
    "我想先说说": bilingual(
        "Please enter Chinese text, starting with what you most want to say…",
        "请使用中文，从你最想说的那一部分开始……",
    ),
    "帮我理清楚": bilingual(
        "In Chinese, describe what happened and what feels most confusing…",
        "请使用中文，告诉我发生了什么，以及哪里最让你混乱……",
    ),
    "一起想办法": bilingual(
        "In Chinese, describe one problem you most want to address…",
        "请使用中文，说说你现在最想解决的一个问题……",
    ),
    "先帮我稳一下": bilingual(
        "In Chinese, describe the strongest feeling in your body or mind right now…",
        "请使用中文，告诉我你此刻身体或心里最明显的感受……",
    ),
}

PROVIDER_OPTIONS = {
    ProviderType.OPENAI_COMPATIBLE.display_name: ProviderType.OPENAI_COMPATIBLE,
    ProviderType.ANTHROPIC.display_name: ProviderType.ANTHROPIC,
}
PROVIDER_DEFAULT_URLS = {
    ProviderType.OPENAI_COMPATIBLE.display_name: "https://api.openai.com/v1",
    ProviderType.ANTHROPIC.display_name: "https://api.anthropic.com",
}

STAGE_ORDER = [
    DialogueStage.EXPRESS,
    DialogueStage.ORGANIZE,
    DialogueStage.SUPPORT,
    DialogueStage.STRATEGIZE,
    DialogueStage.ACT,
]
STAGE_ICONS = {
    DialogueStage.EXPRESS: "01",
    DialogueStage.ORGANIZE: "02",
    DialogueStage.SUPPORT: "03",
    DialogueStage.STRATEGIZE: "04",
    DialogueStage.ACT: "05",
}
STAGE_LABELS = {
    DialogueStage.EXPRESS: bilingual("Express", "表达"),
    DialogueStage.ORGANIZE: bilingual("Organize", "梳理"),
    DialogueStage.SUPPORT: bilingual("Support", "支持"),
    DialogueStage.STRATEGIZE: bilingual("Strategize", "协商"),
    DialogueStage.ACT: bilingual("Act", "行动"),
    DialogueStage.SAFETY: bilingual("Safety", "安全"),
}
EMOTION_LABELS = {
    Emotion.ANXIETY: bilingual("Anxiety / fear", "焦虑/恐惧"),
    Emotion.SADNESS: bilingual("Sadness / loss", "悲伤/失落"),
    Emotion.ANGER: bilingual("Anger", "愤怒"),
    Emotion.GRIEVANCE: bilingual("Grievance / frustration", "委屈/受挫"),
    Emotion.LONELINESS: bilingual("Loneliness / exclusion", "孤独/被排斥"),
    Emotion.SHAME: bilingual("Shame / guilt", "羞耻/内疚"),
    Emotion.STRESS: bilingual("Stress / exhaustion", "压力/耗竭"),
    Emotion.CONFUSION: bilingual("Confusion / conflict", "困惑/矛盾"),
    Emotion.POSITIVE: bilingual("Positive / hopeful", "积极/希望"),
    Emotion.NEUTRAL: bilingual("Neutral", "中性"),
}
INTENT_LABELS = {
    UserIntent.VENT: bilingual("Wants to vent", "只想倾诉"),
    UserIntent.BE_UNDERSTOOD: bilingual("Wants to be understood", "想被理解"),
    UserIntent.CLARIFY: bilingual("Wants clarity", "想理清问题"),
    UserIntent.ADVICE: bilingual("Wants advice", "想听建议"),
    UserIntent.CHOOSE: bilingual("Wants to choose", "想做选择"),
    UserIntent.STABILIZE: bilingual("Wants to stabilize first", "想先缓下来"),
    UserIntent.UNKNOWN: bilingual("Uncertain", "不确定"),
    UserIntent.SAFETY: bilingual("Safety-related", "安全相关"),
}
STRATEGY_ENGINE_LABELS = {
    "学习权重": bilingual("Learned artifact", "学习权重"),
    "规则基线": bilingual("Rule baseline", "规则基线"),
}
STRATEGY_LABELS = {
    "邀请表达": bilingual("Invite expression", "邀请表达"),
    "具体复述": bilingual("Specific reflection", "具体复述"),
    "澄清问题": bilingual("Clarifying question", "澄清问题"),
    "总结问题地图": bilingual("Problem-map summary", "总结问题地图"),
    "情绪反映": bilingual("Emotion reflection", "情绪反映"),
    "情绪验证": bilingual("Emotion validation", "情绪验证"),
    "力量确认": bilingual("Strength affirmation", "力量确认"),
    "短时稳定": bilingual("Brief stabilization", "短时稳定"),
    "征求建议许可": bilingual("Ask permission for advice", "征求建议许可"),
    "提供信息": bilingual("Provide information", "提供信息"),
    "比较方案": bilingual("Compare options", "比较方案"),
    "最小行动": bilingual("Minimal action", "最小行动"),
    "回顾调整": bilingual("Review and adjust", "回顾调整"),
    "受控安全协议": bilingual("Controlled safety protocol", "受控安全协议"),
}
FEEDBACK_LABELS = {
    "理解准确": bilingual("Accurate", "理解准确"),
    "部分准确": bilingual("Partly accurate", "部分准确"),
    "不准确": bilingual("Inaccurate", "不准确"),
}
ACTION_STATUS_LABELS = {
    "待确认": bilingual("Pending confirmation", "待确认"),
    "准备尝试": bilingual("Ready to try", "准备尝试"),
    "已完成": bilingual("Completed", "已完成"),
    "遇到困难": bilingual("Encountered difficulty", "遇到困难"),
    "暂不执行": bilingual("Not now", "暂不执行"),
}


st.set_page_config(
    page_title=DISPLAY_TITLE,
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="auto",
)


def load_theme() -> None:
    css_path = ASSET_DIR / "app.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def initialize_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_state" not in st.session_state:
        st.session_state.conversation_state = ConversationState()
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "feedback_submitted_turn" not in st.session_state:
        st.session_state.feedback_submitted_turn = -1
    default_provider = ProviderType.OPENAI_COMPATIBLE.display_name
    defaults = {
        "llm_gateway": None,
        "llm_provider_label": default_provider,
        "llm_base_url_input": PROVIDER_DEFAULT_URLS[default_provider],
        "llm_model_input": "",
        "llm_api_key_draft": "",
        "llm_data_consent": False,
        "llm_config_error": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sync_provider_defaults() -> None:
    label = st.session_state.llm_provider_label
    st.session_state.llm_base_url_input = PROVIDER_DEFAULT_URLS[label]
    st.session_state.llm_api_key_draft = ""
    st.session_state.llm_data_consent = False
    st.session_state.llm_gateway = None
    st.session_state.llm_config_error = ""


def active_llm_gateway() -> LLMGateway | None:
    """Treat consent as a live requirement, even if stale configuration exists."""
    if not st.session_state.get("llm_data_consent", False):
        return None
    return st.session_state.get("llm_gateway")


def on_llm_consent_change() -> None:
    if not st.session_state.llm_data_consent:
        st.session_state.llm_gateway = None
        st.session_state.llm_api_key_draft = ""
        st.session_state.llm_config_error = ""


def apply_llm_config() -> None:
    draft_key = st.session_state.llm_api_key_draft
    st.session_state.llm_api_key_draft = ""
    if not st.session_state.llm_data_consent:
        st.session_state.llm_gateway = None
        st.session_state.llm_config_error = bilingual(
            "Confirm the third-party data-transfer notice before enabling online mode.",
            "启用在线模式前，请先确认第三方数据传输提示。",
        )
        return
    try:
        config = LLMRuntimeConfig(
            provider=PROVIDER_OPTIONS[st.session_state.llm_provider_label],
            base_url=st.session_state.llm_base_url_input,
            api_key=draft_key,
            model=st.session_state.llm_model_input,
            timeout_seconds=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )
        st.session_state.llm_gateway = LLMGateway(config)
    except Exception:
        st.session_state.llm_gateway = None
        st.session_state.llm_config_error = bilingual(
            "Invalid configuration. Check the API URL, API Key, and model name.",
            "配置无效，请检查 API 地址、API Key 和模型名。",
        )
        return
    st.session_state.llm_config_error = ""


def clear_llm_config() -> None:
    default_provider = ProviderType.OPENAI_COMPATIBLE.display_name
    st.session_state.llm_gateway = None
    st.session_state.llm_provider_label = default_provider
    st.session_state.llm_base_url_input = PROVIDER_DEFAULT_URLS[default_provider]
    st.session_state.llm_model_input = ""
    st.session_state.llm_api_key_draft = ""
    st.session_state.llm_data_consent = False
    st.session_state.llm_config_error = ""


def reset_conversation() -> None:
    """Clear conversation data while preserving the chosen model and support mode."""
    st.session_state.messages = []
    st.session_state.conversation_state = ConversationState()
    st.session_state.last_result = None
    st.session_state.feedback_submitted_turn = -1


def natural_safety_text(status: SafetyStatus) -> str:
    return {
        SafetyStatus.S0: bilingual(
            "Continue with ordinary supportive dialogue",
            "当前按普通支持对话继续",
        ),
        SafetyStatus.S1: bilingual(
            "Prioritize acknowledgement and continue monitoring strong distress",
            "听到较强困扰，优先承接并持续关注",
        ),
        SafetyStatus.S2: bilingual(
            "Clarify the meaning and current safety first",
            "先确认表达的具体含义和当前安全",
        ),
        SafetyStatus.S3: bilingual(
            "Confirm safety step by step and connect to real-world support",
            "正在逐步确认安全并连接现实支持",
        ),
        SafetyStatus.S4: bilingual(
            "Prioritize immediate real-world emergency support",
            "当前优先连接现实中的紧急支持",
        ),
    }[status]


def render_header() -> None:
    st.markdown(
        f"""
        <section class="hero-shell" aria-labelledby="app-title">
          <div class="hero-eyebrow"><span class="hero-mark">✦</span> NLP COURSE PROJECT</div>
          <h1 id="app-title" class="hero-title">{DISPLAY_TITLE}</h1>
          <p class="hero-subtitle">
            {FULL_TITLE}<br>
            Listen first, organize together, acknowledge the feeling, and then find one next step.<br>
            先听你说，陪你理清，接住你的感受，再和你一起找到下一步。
          </p>
          <div class="hero-tags">
            <span class="soft-tag">Intent-driven / 意图驱动</span>
            <span class="soft-tag">Multidimensional state / 多维状态</span>
            <span class="soft-tag">Staged support / 分阶段支持</span>
            <span class="soft-tag">Safety routing / 安全分流</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_support_selector() -> str:
    st.markdown(
        '<div class="section-kicker">How would you like support this time? / 这次，你希望我怎么陪你？</div>',
        unsafe_allow_html=True,
    )
    selected = st.segmented_control(
        bilingual("Choose a support mode", "选择支持方式"),
        SUPPORT_MODES,
        selection_mode="single",
        default=SUPPORT_MODES[0],
        required=True,
        format_func=lambda value: MODE_LABELS[value],
        key="support_mode",
        label_visibility="collapsed",
        width="stretch",
    )
    selected = selected or SUPPORT_MODES[0]
    st.markdown(
        f'<div class="mode-hint"><span>✦</span><span>{escape(MODE_HINTS[selected])}</span></div>',
        unsafe_allow_html=True,
    )
    return selected


def render_stage_tracker(state: ConversationState) -> None:
    current = state.current_stage
    if current == DialogueStage.SAFETY:
        status = state.last_analysis.safety.status if state.last_analysis else SafetyStatus.S2
        st.markdown(
            f'<div class="safety-route">Safety first / 安全优先 · {escape(natural_safety_text(status))}</div>',
            unsafe_allow_html=True,
        )
        return

    current_index = STAGE_ORDER.index(current) if current in STAGE_ORDER else 0
    steps = []
    for index, stage in enumerate(STAGE_ORDER):
        css_class = "active" if index == current_index else "done" if index < current_index else ""
        steps.append(
            f'<div class="stage-step {css_class}">{STAGE_ICONS[stage]} · {STAGE_LABELS[stage]}</div>'
        )
    st.markdown(f'<div class="stage-tracker">{"".join(steps)}</div>', unsafe_allow_html=True)


def _insight_row(label: str, value: str) -> str:
    return (
        '<div class="insight-row">'
        f'<span class="insight-label">{escape(label)}</span>'
        f'<span class="insight-value">{escape(value)}</span>'
        "</div>"
    )


def render_sidebar() -> str:
    state: ConversationState = st.session_state.conversation_state
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand"><h2>Support console / 心语控制台</h2>'
            '<p>Model, state, and current understanding / 模型、状态与本轮理解</p></div>',
            unsafe_allow_html=True,
        )

        with st.expander(
            bilingual("Model API configuration", "模型 API 配置"),
            expanded=not is_llm_configured(active_llm_gateway()),
        ):
            st.selectbox(
                bilingual("Protocol", "接口协议"),
                list(PROVIDER_OPTIONS),
                key="llm_provider_label",
                on_change=sync_provider_defaults,
            )
            st.text_input("API URL", key="llm_base_url_input")
            st.text_input(
                bilingual("Model name", "模型名"),
                key="llm_model_input",
                placeholder=bilingual(
                    "Enter a model identifier provided by the selected service",
                    "输入所选服务实际提供的模型标识",
                ),
            )
            st.text_input(
                "API Key",
                type="password",
                key="llm_api_key_draft",
                placeholder=bilingual(
                    "Held only in current-session memory",
                    "仅保存在当前会话内存中",
                ),
            )
            st.checkbox(
                bilingual(
                    "I understand that online mode sends the current input, limited conversation history, and structured state derived from the conversation to the selected third party.",
                    "我了解：在线模式会把本轮输入、有限对话历史以及由对话派生的结构化状态发送至所选第三方服务。",
                ),
                key="llm_data_consent",
                on_change=on_llm_consent_change,
            )
            apply_col, clear_col = st.columns(2)
            with apply_col:
                st.button(
                    bilingual("Apply for this session", "应用本次会话配置"),
                    use_container_width=True,
                    type="primary",
                    on_click=apply_llm_config,
                )
            with clear_col:
                st.button(
                    bilingual("Clear API configuration", "清除 API 配置"),
                    use_container_width=True,
                    on_click=clear_llm_config,
                )
            if st.session_state.llm_config_error:
                st.error(st.session_state.llm_config_error)
            st.caption(
                bilingual(
                    "Offline by default; nothing is written to .env, logs, or downloads. HTTP is allowed only for local addresses.",
                    "默认离线运行；不写入 .env、日志或下载文件。HTTP 仅允许本机地址。",
                )
            )

        gateway = active_llm_gateway()
        if is_llm_configured(gateway):
            provider = gateway.config.provider.display_name
            runtime_html = (
                '<div class="runtime-pill"><span class="runtime-dot"></span>'
                f'<span><b>Online / 在线运行</b><br>{escape(provider)} · {escape(gateway.config.model)}</span></div>'
            )
        else:
            runtime_html = (
                '<div class="runtime-pill offline"><span class="runtime-dot"></span>'
                '<span><b>Offline demo / 离线演示</b><br>'
                'Local rules and controlled templates / 当前使用本地规则与受控模板</span></div>'
            )
        st.markdown(runtime_html, unsafe_allow_html=True)

        with st.expander(bilingual("Strategy-artifact experiment", "策略权重实验"), expanded=False):
            model_status = strategy_model_status()
            deployed = bool(model_status.get("accepted", False))
            strategy_label = st.radio(
                bilingual("Strategy engine", "策略引擎"),
                ["学习权重", "规则基线"],
                index=0 if deployed else 1,
                horizontal=True,
                format_func=lambda value: STRATEGY_ENGINE_LABELS[value],
                key="strategy_engine_label",
            )
            strategy_mode = "learned" if strategy_label == "学习权重" else "rule"
            if model_status.get("available"):
                if deployed:
                    st.caption(
                        bilingual(
                            f"Local artifact: {model_status.get('model_version', 'loaded')} · deployment threshold passed",
                            f"本地权重：{model_status.get('model_version', '已加载')} · 已通过部署门槛",
                        )
                    )
                else:
                    st.caption(
                        bilingual(
                            "The experimental artifact did not meet the deployment threshold. Rules remain the default; explicit A/B selection is available.",
                            "实验权重未通过部署门槛，默认使用规则；可显式切换做 A/B 演示。",
                        )
                    )
            else:
                st.caption(
                    bilingual(
                        "The local artifact is unavailable; learned mode falls back to the rule baseline.",
                        "本地权重尚不可用；学习模式会自动回退规则基线。",
                    )
                )
            last_plan = st.session_state.last_result.plan if st.session_state.last_result else None
            if last_plan:
                learned_result = last_plan.strategy_source in {"learned", "learned_experimental"}
                summary = (
                    f"**Turn source / 本轮来源:** {last_plan.strategy_source}  \n"
                    f"**Primary strategy / 主策略:** {STRATEGY_LABELS.get(last_plan.primary_strategy, last_plan.primary_strategy)}"
                )
                if learned_result:
                    summary += f"  \n**Learned-model confidence / 学习模型置信度:** {last_plan.strategy_confidence:.3f}"
                else:
                    summary += (
                        "  \n**Probability note / 概率说明:** Deterministic rules do not produce "
                        "logistic-regression class probabilities. / 确定性规则不产生逻辑回归类别概率。"
                    )
                st.markdown(summary)
                if learned_result:
                    for name, score in list(last_plan.strategy_scores.items())[:3]:
                        st.progress(
                            min(1.0, max(0.0, float(score))),
                            text=f"{STRATEGY_LABELS.get(name, name)} · {float(score):.3f}",
                        )
                elif last_plan.strategy_decision_basis:
                    st.caption(
                        f"Rule basis / 规则依据: {last_plan.strategy_decision_basis}"
                    )
                if last_plan.strategy_fallback_reason:
                    st.caption(
                        f"Fallback reason / 回退原因: {last_plan.strategy_fallback_reason}"
                    )

        last_result = st.session_state.last_result
        if last_result:
            with st.container(border=True, key="sidebar_status"):
                if last_result.used_fallback:
                    detail = last_result.error_code or bilingual(
                        "Response-quality audit triggered fallback",
                        "回复质量检查触发兜底",
                    )
                    st.markdown("**Turn status: fallback enabled / 本轮状态：已启用兜底**")
                    st.caption(detail)
                else:
                    seconds = last_result.latency_ms / 1000
                    st.markdown("**Turn status: complete / 本轮状态：完整生成**")
                    st.caption(
                        f"{last_result.provider_used} · {last_result.model_used} · {seconds:.1f} s / 秒"
                    )

        with st.container(border=True, key="understanding_card"):
            analysis = state.last_analysis
            st.markdown("#### What I currently understand / 我目前听到的")
            if analysis:
                emotions = [EMOTION_LABELS[analysis.primary_emotion]] + [
                    EMOTION_LABELS[item] for item in analysis.secondary_emotions
                ]
                emotion_tags = "".join(
                    f'<span class="emotion-tag">{escape(item)}</span>' for item in emotions
                )
                content = "".join(
                    [
                        _insight_row(
                            bilingual("Main concern", "主要困扰"),
                            state.problem_map.core_problem,
                        ),
                        f'<div class="insight-row"><span class="insight-label">Possible feelings / 可能的感受</span>{emotion_tags}</div>',
                        _insight_row(
                            bilingual("Possible need", "你可能更需要"),
                            INTENT_LABELS[analysis.user_intent],
                        ),
                        _insight_row(
                            bilingual("Current stage", "当前阶段"),
                            STAGE_LABELS[state.current_stage],
                        ),
                    ]
                )
                st.markdown(content, unsafe_allow_html=True)
                st.caption(natural_safety_text(analysis.safety.status))
                if analysis.certainty.value == "较低":
                    st.caption(
                        bilingual(
                            "Confidence in the current understanding is low; use the calibration control below.",
                            "当前理解置信度较低，建议使用下方校准功能。",
                        )
                    )
            else:
                st.markdown(
                    '<div class="sidebar-copy">After the conversation starts, this area shows a tentative understanding of the problem, feelings, and support intent.<br>'
                    '开始对话后，这里会显示系统对问题、感受和支持意图的暂定理解。</div>',
                    unsafe_allow_html=True,
                )

        with st.expander(bilingual("Project scope and boundaries", "项目说明与边界"), expanded=False):
            st.markdown(
                bilingual(
                    "The system completes one primary task per turn and enters advice or action only with your consent.",
                    "本系统每轮只完成一个主要任务，并在你愿意时才进入建议和行动阶段。",
                )
            )
            st.caption(
                bilingual(
                    "Course prototype; not a substitute for qualified counseling, medical diagnosis, or emergency services.",
                    "课程设计原型，不能替代专业心理咨询、医疗诊断或紧急服务。",
                )
            )

        if st.button(
            bilingual("Clear conversation", "清空当前对话"),
            use_container_width=True,
            type="secondary",
        ):
            reset_conversation()
            st.rerun()

        st.markdown(
            '<div class="sidebar-footnote">Online configuration applies only to the current browser session; switching protocols or clearing configuration returns immediately to the offline demo.<br>'
            '在线配置只对当前浏览器会话生效；切换协议或清除配置后立即回到离线演示。</div>',
            unsafe_allow_html=True,
        )
    return strategy_mode


def render_welcome() -> None:
    st.markdown(
        """
        <div class="welcome-card">
          <div class="welcome-copy">
            <h3>You do not need to explain everything at once / 不用一次把所有事情说清楚</h3>
            <p>Start with the part taking up most of your attention. The system first considers what you need now, then chooses one task for this turn.<br>
            从最占据你注意力的那一部分开始就好。系统会先理解你此刻需要什么，再决定这一轮应该做什么。</p>
          </div>
          <div class="starter-grid" aria-label="Chinese input examples / 中文输入示例">
            <div class="starter-item">Chinese input example / 中文输入示例<br>考试结束了，我轻松但又担心成绩。</div>
            <div class="starter-item">Chinese input example / 中文输入示例<br>我已经很努力，却觉得没有被看到。</div>
            <div class="starter-item">Chinese input example / 中文输入示例<br>脑子很乱，帮我把事情理一理。</div>
            <div class="starter-item">Chinese input example / 中文输入示例<br>我现在很慌，先帮我缓下来。</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_message(message: dict) -> None:
    role = message.get("role", "assistant")
    with st.chat_message(role):
        st.markdown(message.get("content", ""))
        meta = message.get("meta") or {}
        if role == "assistant" and meta:
            stage_value = str(meta.get("stage", ""))
            stage_display = next(
                (
                    label
                    for stage, label in STAGE_LABELS.items()
                    if stage.value == stage_value
                ),
                bilingual("Unknown stage", "未知阶段"),
            )
            parts = [
                f"<span>{escape(str(meta.get('model', bilingual('Unknown model', '未知模型'))))}</span>",
                f"<span>{escape(stage_display)}</span>",
            ]
            latency_ms = meta.get("latency_ms")
            if latency_ms is not None:
                parts.append(f"<span>{float(latency_ms) / 1000:.1f} s / 秒</span>")
            if meta.get("fallback"):
                parts.append("<span>Fallback enabled / 已启用兜底</span>")
            if meta.get("strategy"):
                strategy = str(meta.get("strategy"))
                parts.append(
                    f"<span>{escape(STRATEGY_LABELS.get(strategy, strategy))} · "
                    f"{escape(str(meta.get('strategy_source', 'rule')))}</span>"
                )
            st.markdown(
                f'<div class="message-meta">{"".join(parts)}</div>',
                unsafe_allow_html=True,
            )


def render_understanding_feedback() -> None:
    state: ConversationState = st.session_state.conversation_state
    analysis = state.last_analysis
    if not analysis or st.session_state.feedback_submitted_turn == state.turn_index:
        return

    with st.container(border=False, key="feedback_panel"):
        with st.expander(
            bilingual("✦ Calibrate this turn", "校准这轮理解"),
            expanded=False,
        ):
            st.caption(
                bilingual(
                    "The system’s understanding is tentative; your confirmation takes priority.",
                    "系统的理解只是暂定判断，以你的确认为准。",
                )
            )
            feedback = st.segmented_control(
                bilingual("Understanding accuracy", "理解程度"),
                ["理解准确", "部分准确", "不准确"],
                default="理解准确",
                required=True,
                format_func=lambda value: FEEDBACK_LABELS[value],
                key=f"feedback_choice_{state.turn_index}",
                width="stretch",
            )
            with st.form(f"feedback_form_{state.turn_index}"):
                primary = None
                secondary = None
                intent = None
                corrected_issue = None
                if feedback != "理解准确":
                    emotion_values = [item.value for item in Emotion]
                    primary = st.selectbox(
                        bilingual("More accurate primary feeling", "更准确的主要感受"),
                        emotion_values,
                        index=emotion_values.index(analysis.primary_emotion.value),
                        format_func=lambda value: EMOTION_LABELS[Emotion(value)],
                    )
                    secondary = st.multiselect(
                        bilingual(
                            "Other feelings (up to two)",
                            "还包括哪些感受（最多两个）",
                        ),
                        emotion_values,
                        default=[item.value for item in analysis.secondary_emotions],
                        max_selections=2,
                        format_func=lambda value: EMOTION_LABELS[Emotion(value)],
                    )
                    intent_values = [item.value for item in UserIntent]
                    intent = st.selectbox(
                        bilingual("What do you need now?", "你现在更需要什么"),
                        intent_values,
                        index=intent_values.index(analysis.user_intent.value),
                        format_func=lambda value: INTENT_LABELS[UserIntent(value)],
                    )
                    corrected_issue = st.text_input(
                        bilingual(
                            "What did the system misunderstand?",
                            "系统把哪一部分理解错了",
                        ),
                        value=(
                            state.problem_map.core_problem
                            if state.problem_map.core_problem != "尚未明确"
                            else ""
                        ),
                    )
                submitted = st.form_submit_button(
                    bilingual("Save calibration", "保存校准"),
                    use_container_width=True,
                )
                if submitted:
                    st.session_state.conversation_state = apply_understanding_feedback(
                        state,
                        feedback,
                        primary_emotion=primary,
                        secondary_emotions=secondary,
                        intent=intent,
                        corrected_issue=corrected_issue,
                    )
                    st.session_state.feedback_submitted_turn = state.turn_index
                    st.rerun()


def render_action_card() -> None:
    # Explicitly replace the entire card block, including nested form/download
    # widgets, when a rerun changes its visibility or preceding chat messages.
    card_slot = st.empty()
    state: ConversationState = st.session_state.conversation_state
    if state.current_stage == DialogueStage.SAFETY:
        return
    action = state.action_plan
    if not action:
        return

    with card_slot.container(border=True, key="action_card"):
        st.markdown(
            f"""
            <div class="action-summary">
              <h3>🪴 Small action for this turn / 本轮小行动</h3>
              <p>{escape(action.action)}</p>
            </div>
            <div class="action-metrics">
              <div class="action-metric"><b>When / 时间</b><span>{escape(action.when)}</span></div>
              <div class="action-metric"><b>Duration / 预计用时</b><span>{action.duration_minutes} min / 分钟</span></div>
              <div class="action-metric"><b>Status / 状态</b><span>{escape(ACTION_STATUS_LABELS.get(action.status, action.status))}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            f"Possible obstacle / 可能障碍: {action.obstacle} · "
            f"Fallback plan / 备用方案: {action.fallback}"
        )

        with st.expander(bilingual("Edit action card", "编辑行动卡"), expanded=False):
            with st.form("action_plan_form"):
                action_text = st.text_input(
                    bilingual("Action", "动作"), value=action.action
                )
                when = st.text_input(bilingual("When", "时间"), value=action.when)
                duration = st.number_input(
                    bilingual("Estimated minutes", "预计分钟数"),
                    min_value=1,
                    max_value=120,
                    value=action.duration_minutes,
                )
                obstacle = st.text_input(
                    bilingual("Possible obstacle", "可能障碍"),
                    value=action.obstacle,
                )
                fallback = st.text_input(
                    bilingual("Fallback plan", "备用方案"), value=action.fallback
                )
                statuses = ["待确认", "准备尝试", "已完成", "遇到困难", "暂不执行"]
                status = st.selectbox(
                    bilingual("Status", "状态"),
                    statuses,
                    index=statuses.index(action.status if action.status in statuses else "待确认"),
                    format_func=lambda value: ACTION_STATUS_LABELS[value],
                )
                if st.form_submit_button(
                    bilingual("Update action card", "更新行动卡"),
                    use_container_width=True,
                ):
                    updated = state.model_copy(deep=True)
                    updated.action_plan.action = action_text
                    updated.action_plan.when = when
                    updated.action_plan.duration_minutes = int(duration)
                    updated.action_plan.obstacle = obstacle
                    updated.action_plan.fallback = fallback
                    updated.action_plan.status = status
                    st.session_state.conversation_state = updated
                    st.rerun()

        action_json = json.dumps(
            st.session_state.conversation_state.action_plan.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        st.download_button(
            bilingual("Download action card JSON", "下载行动卡 JSON"),
            data=action_json,
            file_name="emotion_support_action_plan.json",
            mime="application/json",
            use_container_width=False,
        )


def build_pipeline_history(messages: list[dict]) -> list[dict]:
    """Keep only the local Safety marker alongside the bounded role/content history."""
    history = []
    for item in messages[-12:]:
        entry = {"role": item["role"], "content": item["content"]}
        meta = item.get("meta")
        if (
            item.get("role") == "assistant"
            and isinstance(meta, dict)
            and meta.get("stage") == DialogueStage.SAFETY.value
        ):
            entry["meta"] = {"stage": DialogueStage.SAFETY.value}
        history.append(entry)
    return history


def process_user_input(
    user_input: str,
    selected_mode: str,
    selected_strategy_mode: str,
) -> None:
    history_before_current = build_pipeline_history(st.session_state.messages)
    with st.chat_message("user"):
        st.markdown(user_input)
    try:
        with st.chat_message("assistant"):
            with st.spinner(
                bilingual(
                    "Determining the most useful task for this turn…",
                    "正在判断这一轮最需要做什么……",
                )
            ):
                result = process_message(
                    user_input,
                    history_before_current,
                    st.session_state.conversation_state,
                    selected_mode=selected_mode,
                    selected_strategy_mode=selected_strategy_mode,
                    llm_gateway=active_llm_gateway(),
                )
                st.markdown(result.response)
                st.caption(
                    f"{result.provider_used} · {result.model_used} · "
                    f"{STAGE_LABELS[result.plan.stage]} · {result.latency_ms / 1000:.1f} s / 秒"
                )
        assistant_meta = {
            "provider": result.provider_used,
            "model": result.model_used,
            "stage": result.plan.stage.value,
            "latency_ms": result.latency_ms,
            "fallback": result.used_fallback,
            "strategy": result.plan.primary_strategy,
            "strategy_source": result.plan.strategy_source,
        }
        st.session_state.messages.extend(
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": result.response, "meta": assistant_meta},
            ]
        )
        st.session_state.conversation_state = result.state
        st.session_state.last_result = result
        st.session_state.feedback_submitted_turn = -1
        st.rerun()
    except UserInputError as exc:
        st.warning(f"Input notice / 输入提示: {exc}")
    except Exception:
        st.error(
            bilingual(
                "This turn could not be completed. Try again later; internal errors and credentials will not be displayed.",
                "这一轮处理没有完成。请稍后重试；系统不会展示内部错误或密钥信息。",
            )
        )


load_theme()
initialize_state()

selected_strategy_mode = render_sidebar()
render_header()
selected_mode = render_support_selector()
render_stage_tracker(st.session_state.conversation_state)

with st.container(border=False, key="conversation_shell"):
    st.markdown(
        '<div class="conversation-heading"><span>Conversation space / 对话空间</span>'
        '<span>One primary task per turn / 每轮只完成一个主要任务</span></div>',
        unsafe_allow_html=True,
    )
    # Keep later form/card slots stable as the number of chat messages grows.
    # This prevents a new chat block from inheriting an old card's nested widgets
    # during the internal rerun that completes a turn.
    with st.container(border=False, key="chat_history"):
        if not st.session_state.messages:
            render_welcome()
        else:
            for message in st.session_state.messages:
                render_message(message)

    render_understanding_feedback()
    render_action_card()

user_input = st.chat_input(MODE_PLACEHOLDERS[selected_mode])
if user_input:
    process_user_input(user_input, selected_mode, selected_strategy_mode)
