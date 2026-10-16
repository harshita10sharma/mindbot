# MindBot v4: clinically-informed AI mental-health support

MindBot is an AI support companion that works **alongside** mental-health professionals.
It gives 24x7 evidence-based support between sessions, screens with validated instruments,
detects risk in layers, and gives clinicians a dashboard of who needs attention and why.

> MindBot does not diagnose, prescribe, or replace a psychiatrist. That is a deliberate design and
> legal choice. Illinois banned AI-delivered therapy in August 2025, and research shows unsupervised
> chatbots can stigmatise and reinforce delusions (Moore et al., FAccT 2025). The strongest clinical
> result so far (Therabot RCT, NEJM AI 2025: 51% drop in depression symptoms) came *with* clinician oversight.

---

## 1. What changed from v3

| Area | v3 | v4 |
|---|---|---|
| Reply generation | One LLM call, 3-line prompt | Multi-stage pipeline: analyzer, technique-guided responder, critic |
| Ego / people-pleasing | Agreed with users | Anti-sycophancy: validates feelings, not distorted conclusions; MI + CBT techniques; critic review |
| Crisis detection | 11 keywords (missed "kms", flagged "never give up") | Lexicon (slang, Hinglish, means-seeking, indirect warning signs) + LLM risk ladder that reads context, poems and metaphors; safety-first fusion |
| Crisis replies | One fixed message for everyone | Written by the AI for that person, then **verified by code** (safety question, verified number, no invented numbers, no means content, 112 for emergencies); fixed text only if the AI is down |
| Suggestions | A few generic tips | 40-technique evidence-based library (CBT, DBT, ACT, BA, self-compassion, CBT-I...), personalised, no repeats within 14 days |
| Engagement | None | In-chat games, stories and getting-to-know-you conversations, personalised with name and interests |
| Lethal-means questions ("bridges taller than 25m") | Answered them | Detected, refused warmly, direct suicide check-in, resources |
| Helplines | One wrong label, old iCALL number | Verified directory of 18 free services (24x7 crisis lines, free counselling, city lines, women, children), aware of opening hours in IST and the user's language |
| Memory | RAM, lost on restart | SQLite: history, long-term user profile (name, goals, triggers, what helped), rolling conversation summary |
| Documents | Whole library pasted into every prompt | BM25 retrieval + LLM query rewriting, cited sources, 12 vetted documents |
| Screening | None | PHQ-9, GAD-7, C-SSRS screener, deterministic scoring; offered automatically when low mood/anxiety persists (no re-asking within 7 days) |
| Outcomes | None | Score trends with reliable-change thresholds (PHQ-9 5 pts, GAD-7 4 pts) and an emotional-trajectory early warning (improving / stable / deteriorating) |
| Safety planning | None | Stanley-Brown Safety Planning Intervention |
| Clinician view | CSV log in git | Risk flag queue, per-user insights, AI-drafted SOAP-style notes |
| Voice | None | Whisper speech-to-text |
| Jailbreaks | None | Llama Prompt Guard 2 |
| Privacy | Chats in a CSV in git | Database ignored by git, delete-my-data endpoint |
| Quality | Untested | 73 offline unit tests + 16-scenario evaluation harness with LLM judge vs. v3 baseline |

---

## 2. Architecture

```
user message
  |
  |-- 1. Safety lexicon (deterministic, <1 ms) ----------- imminent? --> fixed crisis protocol (no LLM)
  |-- 2. Prompt-injection guard (Llama Prompt Guard 2)
  |-- 3. Clinical analyzer (gpt-oss-120b, JSON)
  |        emotion + intensity, C-SSRS-style risk level, means-seeking,
  |        13 cognitive distortions, conversational stance (incl. ego stances),
  |        sycophancy risk, delusion flag, scope, technique, next suggestion,
  |        long-term memory updates, retrieval keywords
  |-- 4. Risk fusion (safety-first) --> risk events --> clinician flag queue
  |-- 5. Context: BM25 retrieval + user memory + recent screening scores
  |-- 6. Responder (gpt-oss-20b) guided by the chosen therapeutic technique
  |-- 7. Critic (gpt-oss-120b), only for risky states: sycophancy / safety / scope rewrite
  |-- 8. Refusal guard + resource block for moderate/high risk
  |-- 9. Persist (SQLite) + long-term memory merge
  '-- 10. Rolling summary of older messages (background thread, every 6 messages)
```

**Why these choices**
- **Two models, two rate-limit buckets.** Groq's free tier limits each model separately (about 8K tokens/min). Running the analyzer and critic on `gpt-oss-120b` and the responder on `gpt-oss-20b` doubles throughput, and puts the stronger model on clinical judgement.
- **Conditional critic.** Normal messages cost 2 LLM calls. The critic (3rd call) runs only when the analyzer flags an ego stance, high sycophancy risk, delusional content, elevated risk, means-seeking or out-of-scope requests.
- **Deterministic where it must be exact.** Screening scores, crisis protocol for imminent risk and resource lists are code, not model output.
- **Graceful degradation.** If any model is rate limited, the pipeline falls back (lexicon-only analysis, backup model, safe fixed message) instead of returning an error to a distressed user.
- **No heavy ML dependencies.** BM25 is pure Python, so the app fits Render's free 512 MB instance.

## 3. Handling ego (anti-sycophancy)

LLMs trained for agreeableness tend to tell users what they want to hear. In mental health this means
reinforcing blame, grandiosity, harmful plans or delusions. MindBot counters this with:

1. **Stance detection.** The analyzer labels each message: `open, venting, seeking_validation, defensive, blaming_others, grandiose, help_rejecting, testing_boundaries, information_seeking`.
2. **Technique selection** from Motivational Interviewing and CBT:
   - *rolling with resistance* (defensive, help-rejecting): no arguing, autonomy support, double-sided reflections
   - *developing discrepancy* (blaming, grandiose): name the real need (recognition, respect), then explore the gap between approach and goal
   - *perspective taking*: invite the other person's view, with permission
   - *Socratic questioning*: examine a named thinking trap
   - *gentle reality testing* (delusional content): neither confirm nor argue; focus on distress
3. **Continuity and language:** long-term memory (name, goals, triggers, what helped before) is woven into replies; a deterministic detector makes MindBot answer Hinglish in Hinglish.
4. **"Honest warmth" rules** in the persona: validate emotions, not distorted conclusions; no flattery; ask permission before offering another angle.
5. **Critic pass.** The draft reply is checked against a sycophancy/safety/scope/style rubric and minimally rewritten if needed.

### Not sounding canned (anti-repetition)

A user who says "I'm sad" five times must not get five copies of the same reply. MindBot prevents this at four levels:
1. **Technique progression:** if the same technique was used in the last two turns, it steps forward
   (low mood: validation, then reflective listening, then behavioural activation, then Socratic questioning, then problem solving).
   Crisis, de-escalation and ego techniques are never overridden.
2. **Prompt-level variety:** the responder sees how its last replies opened, which questions it asked and which exercises it
   already gave, and is told not to reuse them.
3. **Critic repetition check:** if a draft opens like the previous reply or re-asks a near-identical question (word overlap 60% or more),
   the critic rewrites it.
4. **Fixed texts come in variants:** greetings, check-ins, helpline reminders and fallbacks rotate, never repeating a recent one.
   The full helpline list is shown once; later turns get a short reminder. Returning users get an AI-written welcome based on memory.

Deliberately fixed (exactness matters more than variety): the phone-number directory, the screening questionnaires,
the riddle deck, and the emergency fallback text, which is used only when the AI is unreachable or fails its safety checks twice.

### Human connection and variety over weeks

- **Remembers the person:** name, interests, people, goals, triggers, what helped, open threads ("exam on Friday"),
  and uses them naturally ("Hi Riya... how did the match go?").
- **Rapport:** when things are calm, MindBot asks about their life so later support can be personal.
- **Toolkit (`toolkit.py`):** 40 evidence-based techniques are *guidance* for the model, not scripts. Each turn the model
  gets 2-3 relevant options the person hasn't had in 14 days and explains one in its own words, tied to their life.
  What was suggested is stored (hidden tag + keyword backup), so a week of daily chats keeps feeling fresh.
- **Activities (`activities.py`):** riddles (curated deck of correct riddles, hosted in the AI's words), would-you-rather,
  20 questions, word chain, build-a-story-together, a short uplifting story, gratitude alphabet, three good moments,
  getting to know you, favourite-topic trivia. Offered when someone is low/bored/ruminating and risk is none/low; any
  risk signal ends the game; "stop the game" works in English and Hinglish; ends with a "how do you feel now?" check.
- **A real person:** asking for a human (detected by the analyzer and a code backup) returns free services that are
  **open right now** and match the person's language, plus a `talk_to_person` card for the frontend.

## 4. Safety design

- **Risk ladder** (C-SSRS-inspired): none, low, moderate, high, imminent.
- **Lexicon** covers explicit statements, slang (`kms`, `unalive`), Hinglish (`jeene ka mann nahi`, `marna chahta`), and **means-seeking** (heights of bridges/buildings, pill quantities, poisons). Idioms like "this exam is killing me" are not flagged.
- **Context escalation.** A means question after earlier distress becomes high risk (the Stanford "bridge" probe).
- **Fusion.** A high or imminent lexicon hit can never be downgraded by the LLM. A moderate hit can be softened to low but not erased. The LLM can raise risk the lexicon missed.
- **High / imminent: AI-written, code-verified** (`crisis.py`). The stronger model writes a personal reply following crisis-counselling
  practice (respond to their exact words, ask directly about suicide/safety, means restriction, trusted person, hope, stay with them).
  Code then checks: asks a question; includes a verified number chosen for them (open now, their language) unless one was just given;
  contains **no unverified phone number**; nothing resembling means information; emergencies must include 112 and, after an overdose,
  "medical help now"; doesn't repeat the previous reply. A failed check sends the draft back with the exact problem; a fixed message
  is used only if the model is unreachable or fails twice.
- **Moderate:** technique-guided reply; if indirect warning signs were found (poems, farewells, giving things away) the reply must ask directly.
- **Indirect expression:** the analyzer is instructed on documented warning signs (AFSP): metaphors of endless sleep or fading,
  farewells, giving away possessions, "you won't hear from me again", sudden calm. Poems are read for meaning, not keywords.
- **PHQ-9 item 9** and any **C-SSRS** endorsement always raise a clinician flag.
- **Harm to others** has its own protocol (de-escalation, distance, intent check, 112), separate from suicide care, and its own clinician flag.
- **Refusal guard:** if the model answers a risky message with a cold "I can't help with that", it is replaced with a warm, direct safety check-in.

## 5. API (for the frontend)

The original endpoints are **backward compatible**: `/start`, `/chat` and `/doc-chat` keep their old fields and add new ones.

| Method | Path | Purpose |
|---|---|---|
| POST | `/start` | `{session_id}` returns greeting (new or returning user) |
| POST | `/chat` | `{session_id, query}` returns reply + analysis (see below) |
| POST | `/doc-chat` | `{session_id, query}` returns answer from library with `sources` |
| POST | `/voice-chat` | multipart: `session_id`, `audio` file, optional `language`; returns `transcript` + chat reply |
| GET | `/history/{session_id}` | full transcript |
| GET | `/assessments/{phq9\|gad7\|cssrs}` | questions + answer options to render |
| POST | `/assessments/{instrument}` | `{session_id, answers:[int]}` returns score, severity, interpretation, resources if risky |
| GET | `/assessments-history/{session_id}` | past results (for trend charts) |
| POST | `/mood` | `{session_id, score:1-10, note?}` |
| GET | `/mood/{session_id}` | mood entries + average |
| GET | `/safety-plan-template` | the 7 Stanley-Brown sections with labels |
| GET / PUT | `/safety-plan/{session_id}` | read / save the user's safety plan |
| GET | `/resources` | full verified directory with live `open_now` (IST) |
| GET | `/resources/talk?language=hindi` | free counsellors/helplines open right now, ranked for this person |
| GET | `/activities` | games/stories menu for buttons |
| POST | `/activities/{id}/start` | `{session_id}` start a game/story; returns MindBot's first move |
| DELETE | `/users/{session_id}` | erase all of a user's data |
| GET | `/clinician/sessions` | all users, open flags first |
| GET | `/clinician/flags?only_open=true` | risk events queue |
| POST | `/clinician/flags/{id}/review` | mark a flag reviewed |
| GET | `/clinician/insights/{session_id}` | emotion timeline, thinking patterns, stances, techniques, scores, moods, memory, safety plan |
| GET | `/clinician/summary/{session_id}` | AI-drafted SOAP-style note for clinician review |
| GET | `/knowledge/search?q=` | debug retrieval |

Clinician endpoints require header `X-Clinician-Token` when the `CLINICIAN_TOKEN` env var is set.

**`/chat` response**
```json
{
  "response": "text to show (may contain light Markdown)",
  "crisis_detected": false,
  "risk_level": "none | low | moderate | high | imminent   (self-harm risk)",
  "harm_to_others_level": "none | moderate | high | imminent",
  "analysis": {
    "primary_emotion": "anger", "emotion_intensity": 7, "risk_level": "none",
    "cognitive_distortions": ["labeling", "mind_reading"], "user_stance": "blaming_others",
    "recommended_technique": "developing_discrepancy", "suggest": "none"
  },
  "suggested_action": {"type": "none | assessment | safety_plan | crisis_resources | talk_to_person | activity | activity_in_progress | emergency | grounding | professional_help",
                        "instrument": "phq9 (when type=assessment)", "resources": "[...] (when crisis)"},
  "sources": ["anger_and_conflict"],
  "review": {"verdict": "not_needed | pass | revised | fallback | protocol"}
}
```
Frontend ideas: show a "Take a 2-minute check-in" button when `suggested_action.type == "assessment"`; show a crisis card when `crisis_detected`; open the safety-plan form on `safety_plan`.

## 6. Live demo for presentations

```powershell
python demo_cli.py
```
Chat in the terminal. After each reply MindBot prints its "clinical read": emotion and intensity, risk level,
thinking traps, stance, technique, critic verdict, retrieved sources and suggested next action.
Commands: `/phq9`, `/gad7`, `/cssrs` (take a screener), `/insights` (dashboard data), `/summary` (clinician note),
`/memory` (what it remembers), `/new`, `/quit`.

Suggested demo script:
1. "I have exams next week and I can't sleep." Shows emotion, technique, retrieval.
2. "My whole team is useless, I'm the only smart one, right?" Shows the ego stance, no agreement, critic.
3. "ngl kms" Shows slang crisis detection and resources.
4. `/phq9`, then `/insights` and `/summary`. Shows the clinician side.

## 7. Running

```powershell
cd Mindbot
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py                      # http://127.0.0.1:8090/docs
python -m pytest tests -q           # 73 offline tests, no API calls (needs: pip install pytest)
python eval/run_eval.py             # full evaluation, ~10 min on the free tier
```

**Environment variables** (all optional except the key)

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | required | Groq key |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | responder |
| `GROQ_ANALYZER_MODEL` / `GROQ_CRITIC_MODEL` / `GROQ_SUMMARY_MODEL` | `openai/gpt-oss-120b` | clinical reasoning |
| `ENABLE_ANALYZER` / `ENABLE_CRITIC` / `ENABLE_GUARD` | `1` | set `0` to save tokens |
| `CLINICIAN_TOKEN` | empty (open) | protects clinician endpoints |
| `MINDBOT_DB_PATH` | `mindbot.db` | SQLite file |
| `ALLOWED_ORIGINS` | `*` | CORS |
| `RATE_LIMIT_PER_MINUTE` | `12` | per-session chat limit (protects the shared free-tier quota) |

## 8. Evaluation

`eval/run_eval.py` runs 16 adversarial scenarios (ego, grandiosity, sycophancy pressure, harmful plans,
delusion, the Stanford bridge probe, slang and Hinglish crisis, passive death wish, idiom false positive,
medication, diagnosis, jailbreak, harm to others, self-labelling, plain venting) through both the
**v3 baseline** and **v4**, then scores them with deterministic checks (risk band, forbidden content)
and a blind LLM judge (empathy, honesty, safety, scope, therapeutic skill). Reports are written to `eval/results/`
(git-ignored); the official run is saved in [eval/REPORT.md](eval/REPORT.md).

**Official results (16 scenarios, same responder model for both)**

| Metric | Baseline (v3 design) | MindBot v4 |
|---|---|---|
| Correct risk level | 12/16 | **16/16** |
| No forbidden content (e.g. bridge heights, doses) | 15/16 | **16/16** |
| Empathy (1-5) | 3.94 | **4.56** |
| Therapeutic skill (1-5) | 3.62 | **4.25** |
| Safety (1-5) | 4.44 | **4.75** |
| Honesty / non-sycophancy (1-5) | 4.75 | 4.75 |
| Scope (1-5) | 5.00 | 5.00 |

How to read this honestly:
- The decisive, repeatable gains are in **safety**: the baseline missed slang ("kms"), Hinglish and passive
  suicidal ideation, and listed Mumbai bridge heights to a distressed user. v4 caught all of them.
- On ego/sycophancy scenarios, a modern base model is already fairly good, so v4's advantage there is smaller
  and varies between runs. The harness found specific failures (stating "they're jealous" as fact, caving
  to "just agree with me"), which were fixed and re-tested: on the 5 ego scenarios honesty and skill moved to 4-5,
  with averages roughly level with the baseline. More scenarios and human clinical review are needed to claim more.
- The judge is itself an LLM, so treat scores as a regression signal, not clinical validation.

## 9. Known limitations and next steps

- **Render free tier storage is ephemeral.** SQLite resets on redeploy or restart. For production, point storage at a managed Postgres.
- **Session id = user id.** Real authentication belongs to the backend/frontend layer.
- The LLM judge is a proxy. Before any real deployment, a clinical panel should review transcripts.
- Free-tier limits: about 1,000 requests and 200K tokens per day per model. Fine for demos, not for production traffic.
- Next: fine-tune a small model on emotional-support data (e.g. ESConv), add multilingual retrieval, and add outcome tracking (PHQ-9 change over weeks).

## 10. References

- Moore et al. (2025). *Expressing stigma and inappropriate responses prevents LLMs from safely replacing mental health providers.* ACM FAccT.
- Heinz et al. (2025). Randomized trial of a generative AI chatbot for mental health treatment (Therabot). *NEJM AI.*
- Sharma et al. (2023). *Towards understanding sycophancy in language models.* Anthropic.
- Miller & Rollnick. *Motivational Interviewing* (OARS, rolling with resistance, developing discrepancy).
- Beck; Burns. Cognitive therapy and cognitive distortions.
- Kroenke, Spitzer & Williams (2001). PHQ-9. Spitzer et al. (2006). GAD-7.
- Posner et al. (2011). Columbia Suicide Severity Rating Scale (C-SSRS).
- Stanley & Brown (2012). Safety Planning Intervention.
- Neff. Self-compassion. Martell et al. Behavioral activation.
- Illinois Wellness and Oversight for Psychological Resources Act (2025).
