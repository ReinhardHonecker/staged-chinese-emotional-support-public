# Staged Chinese Emotional Support Dialogue System

**An NLP course project built around one question: what should this turn of the conversation actually do?**

[简体中文](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md) · [Evaluation](EVALUATION.md) · [Q&A](docs/Q_AND_A.md) · [Local demo](docs/DEMO.md)

> This project is intended for education, research, and local demonstration. It is not a therapy service, crisis hotline, medical device, or clinically validated risk-assessment system.

This is the **public source snapshot of an offline course prototype**, exported from the reviewed private baseline `98dea9a8ecc889687031da09b79977aecd007295` into a new repository without the private Git history. The experimental `joblib` weight, raw corpus, teacher-label caches, local reports, and personal evidence are not distributed. Publishing this code does not establish permission to redistribute the omitted weight, validate a live provider, or authorize a public emotional-support service.

## Overview / 项目概述

Emotional-support dialogue involves more than detecting an emotion and producing a sympathetic sentence. In a multi-turn conversation, the system first has to understand what the user wants from the current exchange and what task the next reply should perform.

Sometimes the user wants to keep talking without receiving advice. Sometimes they want help separating what has happened from what they fear may happen. In other cases, they have already chosen one of several directions and want to turn it into a concrete next step. A reply can be fluent and still miss the point if the system fails to distinguish these situations.

This project makes the decision process explicit. It analyzes the user’s current situation, emotions, and support intent; selects a dialogue stage and response strategy; generates a reply and, when appropriate, an action card; checks the complete result; and only then updates the session state. The user can also inspect and correct the system’s interpretation so that later responses are based on information that has actually been confirmed.

The application is implemented with Python, Pydantic, and Streamlit. Its default offline path uses local rules and controlled Chinese templates, so no model API is required. After explicit consent to data transfer, the user may also connect a compatible online model provider; this optional path has not received live-provider acceptance. The repository preserves code and historical results for a lightweight strategy-classification experiment, but not its trained weight. The recorded model did not meet the activation threshold, and this public package uses rules when that weight is absent.

## Why staged dialogue control

A sentence such as “everything feels messy right now” can mean several different things. The user may be inviting the system to listen, asking for help organizing the situation, or saying that they first need a lower-effort response. Treating all three cases as the same generation task makes premature advice and misplaced problem solving more likely.

The project therefore separates interpretation from response policy:

1. **State analysis** organizes reported events, worries or interpretations, feelings, support intent, readiness for advice, evidence spans, and safety-related context.
2. **Stage control** selects the main task for the turn: Express, Organize, Support, Strategize, Act, or Safety.
3. **Strategy planning** determines how to carry out that task and sets limits such as whether advice is allowed, how many alternatives may be offered, and how many main questions may be asked.
4. **Response generation** realizes the plan through local templates or an optional online model.
5. **Response checking** evaluates the reply and action card together before the selected result is stored in the session.

The field named `facts` does **not** mean that the application has independently verified a real-world fact. It stores event information reported by the user. For example:

> 项目截止是周五，我担心做不完，脑子很乱，帮我区分事实和担心。<br>
> The project is due on Friday. I am worried that I will not finish, my thoughts feel scattered, and I want help separating facts from worries.

| Part of the input | How the system treats it |
| --- | --- |
| The deadline is Friday | Event information reported by the user |
| I worry that I will not finish | A feared future outcome, not a confirmed result |
| My thoughts feel scattered | A self-reported feeling |
| Help me separate facts from worries | The request for this turn |

When information is missing, the relevant field may remain empty or be left for clarification. The program does not copy an entire message into several incompatible fields simply to avoid an empty value. This is still bounded rule-based processing, not a general Chinese semantic parser.

## Dialogue stages and support modes

The interface offers four support modes—Talk first, Organize, Stabilize, and Plan action—while the internal dialogue policy uses six stages.

| Stage | Main task |
| --- | --- |
| Express | Stay with what the user has just shared instead of moving immediately to a solution. |
| Organize | Separate reported events, worries, feelings, and requests, then invite confirmation. |
| Support | Respond to the user’s feelings and offer a brief, low-effort response when they want to slow down first. |
| Strategize | Compare no more than three possible directions when the user is willing to discuss advice. |
| Act | Turn a confirmed choice or explicit action request into one small step and an action card. |
| Safety | Pause ordinary problem solving and switch to a controlled local safety path. |

These stages are not a mandatory sequence. The user can choose the kind of support needed for the current turn, while safety-related information takes priority. Selecting Plan action also does not authorize the system to decide on the user’s behalf: the conversation may first compare options and wait for a clear choice before creating an action.

The normal interface always supplies a support mode and defaults to Talk first. A separate no-mode evaluation deliberately removes that hint to examine the rule-based stage selector under a different condition. The two results should therefore not be treated as the same task.

## Key capabilities / 主要能力

### Correctable state analysis

The system represents more than a single emotion label. It tracks the main issue, primary and secondary emotions, support intent, readiness for advice, problem structure, safety context, and evidence taken from the user’s text.

Users can correct the interpretation through the interface or in the conversation itself—for example, “I am not sad; I am angry.” For the explicit forms covered by the current tests, the correction is applied after automatic inference. Rejected emotions and duplicates of the confirmed primary emotion are removed from the secondary list. A later turn is still analyzed again, so one correction does not permanently define the user’s state.

### Grounded option selection

The system stores only options that appeared in the final previous reply and that the local parser could preserve completely. When the user says “I choose the second one,” the program first checks whether that phrase maps unambiguously to the still-active list.

If no valid list exists, the number is out of range, the choice is negated, the reference is ambiguous, or an important qualifier cannot be preserved, the system asks for clarification. Unsupported duration expressions such as `1.5 minutes` or “two and a half minutes” are not silently converted into an integer.

### Editable action cards

An Act turn can produce a structured card containing the action, time and place, expected duration, success criterion, likely obstacle, fallback action, review prompt, and current status. The card can be edited in the interface and downloaded as JSON.

The visible reply and its card are checked as one result, preventing the page from displaying one candidate while saving the card from another. During Safety, an ordinary action card is hidden from the interface but retained in the current session. It can reappear after ordinary dialogue resumes.

### Offline by default, online by choice

The default offline path uses local rules for analysis, stage selection, and strategy selection, followed by controlled Chinese response templates. It requires no model credentials and supports reproducible testing and local demonstration.

The optional online path supports OpenAI-compatible Chat Completions and Anthropic Messages. On ordinary turns, a configured provider may assist with state analysis, response generation, and review. If a call fails or returns an invalid structure, the application follows its existing validation and fallback rules.

Online generation and the learned strategy selector are separate settings. An online model may follow a rule-selected strategy, while the local classifier only predicts a strategy label and never generates reply text. Provider-facing tests currently use mocks; the final code version has not completed a live-provider acceptance run.

### Safety routing and output checks

The complete cleaned input is scanned locally for safety-related language before the ordinary length limit is applied. Turns recognized as S2–S4 remain on the controlled local path instead of entering ordinary online analysis. The implemented paths also distinguish first-person, third-party, self-harm, and other-harm contexts.

S0–S4 are internal routing states, not clinical risk grades. Recognition is rule-based and finite, so it cannot guarantee that every real-world expression will be detected or handled correctly.

## Processing flow

```text
User input + current session
  -> clean the input and run a local full-text safety precheck
  -> apply the ordinary length limit and filter provider-bound history
  -> analyze locally, or use an online provider after consent
  -> choose the stage and strategy; resolve any active option reference
  -> generate a reply and optional action card
  -> check and select the complete result
  -> update session state and render the reply, corrections, and card
```

See [Architecture](docs/ARCHITECTURE.md) for the full control flow and module responsibilities.

## Installation and launch / 安装与运行

Use **Python 3.12**. Clone the public source repository; no model credentials are needed for offline operation. Do not place credentials in a clone URL.

```bash
git clone https://github.com/ReinhardHonecker/staged-chinese-emotional-support-public.git
cd staged-chinese-emotional-support-public
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

### macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Open the localhost address printed by Streamlit. For a first run, leave the provider fields empty, choose a support mode, and use synthetic text. No `.env` file or separate generative-model download is required.

“Offline” means that the application does not call an external model. Installing dependencies still requires network access, and the operating system is not placed in a network-isolated environment.

To try the online path, enter the protocol, API endpoint, model identifier, and API key in the sidebar. Read the data-transfer notice and give explicit consent before applying the configuration. Do not use sensitive personal material when testing a third-party provider. See [Local demo](docs/DEMO.md) for guided examples.

## Tests and evaluation

Run the checks from the repository root with the same virtual environment:

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/evaluate_scenarios.py
.\.venv\Scripts\python.exe -m pip check
```

### macOS / Linux

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate_scenarios.py
.venv/bin/python -m pip check
```

The weight-free public snapshot passed **319 automated tests** locally on 2026-10-14, plus offline evaluation and `pip check`, without provider credentials. The suite includes module tests, offline pipeline tests, Streamlit AppTest coverage, and mock-provider checks. One AppTest explicitly checks the missing-weight fallback instead of requiring unavailable model scores. See [public CI](https://github.com/ReinhardHonecker/staged-chinese-emotional-support-public/actions/workflows/ci.yml) and [Evaluation](EVALUATION.md) for versioned evidence and the distinction from private historical runs.

| Evidence | Recorded result | How to read it |
| --- | ---: | --- |
| Public snapshot, local automated suite | 319 passed | The weight-free snapshot satisfies the tested contracts; the suite does not cover every semantic failure |
| Synthetic scenarios | 60 scenarios / 180 turns | Engineering fixtures, not a real-user study or expert gold standard |
| Explicit-mode adherence | 180/180 | The expected stage supplies the UI mode; this measures adherence, not blind classification |
| No-mode stage routing | 116/180 (64.44%) | Results are imbalanced: Organize is 4/43 and Support is 0/15 |
| Exact repeated-response rate | 20/180 (11.11%) | Exact string repetition, not semantic similarity or response quality |

See [Evaluation](EVALUATION.md) for definitions, class-level results, historical comparisons, and the limits of each evidence source.

## Experimental strategy classifier

The repository preserves the code, provenance, and historical metrics of an experiment based on character-level TF-IDF, structured features, and logistic regression. Its task was to predict a support strategy for the current turn, not generate text or decide safety routing. **The trained weight is not included in this public repository.** The following results describe the earlier private experiment, not a retraining or a public-package learned-model run.

| Metric | Result |
| --- | ---: |
| Accuracy | 0.5929 |
| Macro-F1 | 0.4973 |
| Weighted-F1 | 0.6530 |
| Top-2 Accuracy | 0.8490 |

The project’s Macro-F1 activation threshold is 0.55; the recorded result of 0.4973 did not pass it. The higher Top-2 Accuracy and small artifact size do not override that gate. With no weight bundled, learned selection falls back to rules under the existing loader behavior. The omission avoids claiming redistribution rights that have not been established. Data provenance, annotation method, class imbalance, and artifact checks are documented in the [model card](MODEL_CARD.md).

## Project structure

| Path | Responsibility |
| --- | --- |
| `app.py` | Streamlit UI, session configuration, correction controls, and action-card editing |
| `modules/models.py` | Pydantic contracts for analysis, plans, responses, and session state |
| `modules/pipeline.py` | Main processing flow for one message |
| `modules/state_analyzer.py` | State analysis, evidence extraction, and explicit corrections |
| `modules/stage_controller.py` | Dialogue-stage selection |
| `modules/response_planner.py` | Strategy, advice permission, and response constraints |
| `modules/strategy_selector.py` | Rule-based and experimental learned strategy selection |
| `modules/choices.py` | Option storage, lifetime, and reference resolution |
| `modules/response_generator.py`, `modules/response_composer.py` | Online generation and local templates |
| `modules/response_guard.py` | Reply and action-card checks |
| `modules/conversation_state.py` | Session-state updates |
| `tests/` | Automated test suite |
| `scripts/evaluate_scenarios.py` | Synthetic-scenario evaluation |

## Compliance, provenance, and citation / 合规、来源与引用

The application does not persist raw dialogue to disk by default. Online configuration is scoped to the current Streamlit session and requires explicit data-transfer consent. Withdrawing consent clears the stored gateway and API-key draft. An ordinary online request may still contain the length-limited current input, filtered recent history, and structured state derived from the conversation. See [Privacy and safety](PRIVACY_AND_SAFETY.md) for the full data flow.

Known limitations include:

- finite coverage for complex negation, reported speech, irony, implicit intent, and long-range references;
- conservative option parsing that may require an extra clarification turn;
- strongly imbalanced no-mode stage routing;
- a learned strategy classifier that has not passed its activation threshold;
- no final-version live-provider acceptance, real-user outcome study, or clinical validation;
- synthetic tests and deterministic checks that cannot establish that every reply is appropriate.

The maintainer **ReinhardHonecker** has confirmed sole authorship of the original project and the right to publish it. Development, testing, and documentation used AI assistance; sole authorship does not mean every line was manually typed. The public attribution uses the existing account handle, without adding a real name or private contact details. See [Contributions and AI assistance](docs/CONTRIBUTIONS.md).

The project uses the [PolyForm Noncommercial License 1.0.0](LICENSE), a source-available license with non-commercial restrictions rather than an OSI-approved open-source license. The official `LICENSE` text remains unchanged. 官方 `LICENSE` 正文保持原样。

Third-party material is listed in [Third-party notices](THIRD_PARTY_NOTICES.md), and citation metadata is available in [CITATION.cff](CITATION.cff). The [public-release checklist](PUBLIC_RELEASE_CHECKLIST.md) distinguishes this authorized code-only publication from unverified artifact redistribution and future deployment work. Historical browser checks retain their original version attribution; this export does not claim a new browser or live-provider acceptance run.

## Documentation

- [Architecture](docs/ARCHITECTURE.md): processing flow, module responsibilities, state lifetime, and key design decisions;
- [Q&A](docs/Q_AND_A.md): operation, design choices, and evaluation questions;
- [Local demo](docs/DEMO.md): guided examples using synthetic input;
- [Evaluation](EVALUATION.md): protocols, metrics, historical results, and evidence boundaries;
- [Model card](MODEL_CARD.md): the lightweight strategy-classification experiment;
- [Privacy and safety](PRIVACY_AND_SAFETY.md): online data flow and safety routing;
- [Contributions and AI assistance](docs/CONTRIBUTIONS.md): confirmed authorship, publication scope, and the recorded AI-assisted workflow;
- [Documentation status](docs/PORTFOLIO_REVIEW.md): the current documentation scope and remaining work.
