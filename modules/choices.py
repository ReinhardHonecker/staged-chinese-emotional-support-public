"""One-turn references to options actually displayed in this session."""
import re

from modules.models import ConversationState, DialogueStage, TurnPlan

_QUOTES = re.compile(r'“[^”]*”|‘[^’]*’|"[^"]*"|\x27[^\x27]*\x27|`[^`]*`')
_NUMBERED = re.compile(r"(?:^|[：:；;\n])\s*(\d+)[.、．)）]\s*")
_ORDINAL = re.compile(r"第\s*(\d+|[一二三四五六七八九十两]+)\s*(?:个|项|条|种|点|方案|方向)")
_SHORT_SELECTION = re.compile(r"(?:选|选择)\s*(\d+|[一二三四五六七八九十两]+)(?=\s*(?:个|项|号|[，,。！!\s]|$))")
_NEGATED_SELECTION = re.compile(
    r"(?:不(?:想|愿意|打算|准备|要)?|不要|别|没(?:有)?)"
    r"(?:再|去|先|急着|马上|直接|现在)?"
    r"(?:选择|选|做|用|试|按|定|采用|执行|行动)"
)
# Explicit list-level closing markers used by the bounded comparison format.
# An unknown continuation could still qualify the final action: do not guess.
_LIST_CLOSINGS = (
    "这轮只选", "可以按可行性、代价和可逆性", "先判断哪一个", "你可以先排除",
    "你想先选哪一项", "每项都可以调整", "每个选项都可以继续调整",
)


def option_duration(option: str) -> int | None:
    """Respect an explicit simple minute limit; ambiguous limits need clarification."""
    if re.search(r"(?:半|\d+|[一二三四五六七八九十两百]+)\s*(?:小时|秒钟?|天|周)", option):
        return None
    if re.search(r"[\d一二三四五六七八九十两百]+\s*(?:到|至|[-~～—])\s*[\d一二三四五六七八九十两百]+\s*分钟", option):
        return None
    # Capture the complete numeric expression before interpreting it. Matching
    # an integer suffix would turn 1.5 into 5; 分半钟 is explicit, not absent.
    mentions = re.findall(
        r"([\d一二三四五六七八九十两百零〇点.．半几多]+)\s*(分钟|分半钟?)", option
    )
    if not mentions:
        return None if re.search(r"分钟|分半", option) else 5
    if len(mentions) != 1:
        return None
    raw, unit = mentions[0]
    if unit != "分钟" or not re.fullmatch(r"\d+|[一二三四五六七八九十两百]+", raw):
        return None
    digits = {"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
    if raw.isdigit():
        minutes = int(raw)
    elif raw in digits:
        minutes = digits[raw]
    elif raw.count("十") == 1 and "百" not in raw:
        tens, units = raw.split("十")
        minutes = (digits.get(tens, 1) * 10 + digits.get(units, 0)) if len(tens)<=1 and len(units)<=1 else 0
    else:
        return None
    return minutes if 1 <= minutes <= 120 else None


def displayed_options(response: str) -> list[str]:
    """Only store complete numbered clauses, not quoted lists or partial tails."""
    quoted = [(match.start(), match.end()) for match in _QUOTES.finditer(response)]
    markers = [match for match in _NUMBERED.finditer(response)
               if not any(start <= match.end()-1 < end for start, end in quoted)]
    if not 2 <= len(markers) <= 3:
        return []
    if [int(match.group(1)) for match in markers] != list(range(1, len(markers)+1)):
        return []
    values = []
    for index, marker in enumerate(markers):
        end = markers[index+1].start() if index+1 < len(markers) else len(response)
        tail = response[marker.end():end]
        # The final item needs a visible terminator; a clipped final option is
        # not safe to turn into an executable reference.
        terminator = re.search(r"[；;。\n]", tail)
        if index == len(markers)-1 and terminator is None:
            return []
        remainder = tail[terminator.end():].strip(" ；;。\n\r\t") if terminator else ""
        if remainder:
            # Internal sentences may qualify the action (e.g. draft only).
            # Only a recognized closing can delimit the final item; otherwise
            # reject the whole list rather than storing a truncated action.
            if index < len(markers)-1 or not remainder.startswith(_LIST_CLOSINGS):
                return []
        value = tail[:terminator.start()] if terminator else tail
        value = value.strip()
        if not value or len(value) > 100 or "…" in value:
            return []
        values.append(value)
    return values if len(set(values)) == len(values) else []


def record_presented_options(state: ConversationState, response: str, plan: TurnPlan) -> None:
    # Called only after the final response is chosen, and after turn_index is
    # incremented. Any intervening turn (including Safety) expires the offer.
    state.pending_options = displayed_options(response) if (
        plan.stage == DialogueStage.STRATEGIZE and plan.primary_strategy == "比较方案"
    ) else []
    state.options_turn = state.turn_index if state.pending_options else None


def resolve_choice(text: str, state: ConversationState) -> tuple[bool, str | None]:
    """Return (has_reference, unique_current_choice); never reconstruct history."""
    unquoted = _QUOTES.sub("", text)
    matches = list(_ORDINAL.finditer(unquoted)) + list(_SHORT_SELECTION.finditer(unquoted))
    vague = bool(re.search(r"(?:选|就|按|用|试试).{0,4}(?:那个|这个|前面那个|后面那个|上一个)", unquoted))
    choosing = bool(re.search(r"(?:^|[，,。；;！？!?\n])\s*(?:我(?:决定|想)?|就|先)(?:选择|选)", unquoted))
    quoted_reference = any(_ORDINAL.search(match.group()) for match in _QUOTES.finditer(text))
    if not matches and not vague and not choosing and not quoted_reference:
        return False, None
    active = (state.current_stage == DialogueStage.STRATEGIZE and bool(state.pending_options)
              and state.options_turn == state.turn_index)
    if not active or vague or len(matches) > 1:
        return True, None
    if _NEGATED_SELECTION.search(unquoted) or re.search(r"不是|还是|或者|或是|可能|也许|吗|？|\?", unquoted):
        return True, None
    if not re.search(r"选|选择|就|按|用|试|做|定", unquoted):
        return True, None
    if matches:
        # The decision verb must govern this ordinal in its own clause. An
        # unrelated "做" later in the turn cannot activate an earlier mention.
        if matches[0].re is _ORDINAL:
            prefix = re.split(r"[，,。；;！？!?\n]", unquoted[:matches[0].start()])[-1]
            if not re.search(r"(?:选择|选|就|按|用|试试|试|做|定)\s*$", prefix):
                return True, None
        value = matches[0].group(1)
        numbers = {"一":1, "二":2, "两":2, "三":3}
        index = int(value) if value.isdigit() else numbers.get(value, 0)
        if not 1 <= index <= len(state.pending_options):
            return True, None
        selected = state.pending_options[index-1]
    else:
        # Exact operation/object references are allowed only with an actual
        # selection verb outside quotations. No fuzzy matching or history guess.
        candidates = [option for option in state.pending_options if choosing and (
            option in unquoted or re.sub(r"^(?:我)?(?:可以|能够|能|愿意)?(?:先)?", "", option) in unquoted
        )]
        if len(candidates) != 1:
            return True, None
        selected = candidates[0]
    return (True, selected) if option_duration(selected) is not None else (True, None)
