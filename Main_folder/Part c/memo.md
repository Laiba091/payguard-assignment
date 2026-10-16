# Memo: Taking complaint triage to production

**To:** CTO, PayGuard
**From:** Laiba
**Re:** How to put the LLM complaint-triage prototype into production safely

## Recommendation

Put complaint triage into production in four phases over about 4–5 months. It must start as **assistance to agents, not automation**. The model suggests the queue, urgency and summary; a person confirms. Automation is widened only for low-risk categories once measured accuracy earns it.

Fraud allegations, legal threats and vulnerable customers always go to a person. The model can never close a complaint.

Because of the in-country data rule, the LLM must run **inside the country**, as an open-weights model on in-country infrastructure. That decision drives the cost: about $1.5–3k/month for GPUs at 50,000 complaints/month, against about $20/month of tokens (measured in the prototype) on a foreign API that we are not allowed to use.

## 1. Architecture

![How a complaint flows through the system](images/triage_flow.png)

*Every box runs on in-country infrastructure. The diagram source is `images/triage_flow.html`.*

**Key design choices:**
- **Asynchronous batch processing.** Complaints are not real-time, so a queue with retries is simpler and more robust than a synchronous API. The target is triage within 5 minutes of receipt.
- **Version pinning.** The model weights, the prompt and the taxonomy are versioned together, and every output records the versions that produced it. Any change is a release: it is re-run on the labelled test set and must not get worse on `requires_human` recall.
- **Rules run outside the model.** The validator and guardrails are deterministic code outside the LLM. A prompt injection can at worst make a wrong but valid suggestion, and the injection rule then sends that complaint to a person. The model has no tools or write access.
- **Fail closed.** If the model is unavailable, or the output is invalid after retries, the complaint goes to the normal manual queue. Nothing is lost or auto-actioned.

## 2. Monitoring, including silent failures

Loud failures (errors, timeouts) are easy to catch. The dangerous failures are silent, where the system keeps producing valid-looking records that are wrong:

| Silent failure | How we detect it |
|---|---|
| Accuracy drifts (new products, new scam types, seasonal topics) | Agent **re-route** and **urgency-change** rates per category, with weekly trend alerts; a weekly audit of 100 random items labelled by senior agents |
| Category collapse (everything to `other` or one queue) | Category distribution compared with a 4-week baseline; alert when any share moves by more than 50% relative |
| A sensitive case is missed (fraud or legal complaint auto-routed) | A complaint that later becomes a fraud case, chargeback or legal matter is joined back to its triage record; **every miss is an incident**; monthly review of auto-routed items |
| Summaries invent facts | A monthly faithfulness review of 50 summaries; agents can flag a bad summary with one click |
| Guardrail rules stop matching (language change, new channel) | Keyword-hit rate per channel and language; rate of LLM-flagged complaints with no keyword hit |
| A model or library update changes behaviour | Pinned versions; the labelled test set is run in CI before every deploy |
| Cost or latency creep | Tokens and seconds per complaint, compared with a baseline |

The **owner** is the support operations lead, who gets a weekly dashboard. Engineering is on call for loud failures.

## 3. Privacy, data residency and retention

- **Residency.** Complaint text, model inputs and outputs, logs and backups stay on in-country infrastructure. That rules out foreign hosted LLM APIs, including their "zero data retention" modes, unless the regulator explicitly approves one. The plan is an open-weights instruction model (7–30B class), served on in-country cloud GPUs or on-premise. Data residency must be confirmed for every subprocessor: hosting, logging and monitoring.
- **Minimisation.** A redaction step removes card numbers, account numbers, national IDs, phone numbers and emails before the model sees the text. Triage does not need them.
- **Retention.**
  - Complaint records follow the regulator's complaint-handling retention period.
  - Model inputs and outputs in the audit store: 12 months (for disputes and audits), then deleted.
  - Debug logs: 30 days, with no raw text.
  - No customer data is used to train any model without a separate legal basis.
- **Access.** Only the triage service and named reviewers can read raw narratives; all access is logged.
- **Paperwork.** A privacy impact assessment (DPIA) is needed before Phase 2. The customer privacy notice must mention automated assistance in complaint handling.

## 4. Phased rollout

| Phase | Duration | What happens | Gate to move on |
|---|---|---|---|
| **0. Offline validation** | 3–4 weeks | Run on 2,000 past PayGuard complaints with known final routing; 300 double-labelled by senior agents | Strict category accuracy ≥ 85%; `requires_human` recall ≥ 98%; agreement between the two labellers measured |
| **1. Shadow** | 4 weeks | Runs on live complaints; output hidden from agents; compared with what agents actually do | Same targets met on live data; no missed sensitive case; latency within 5 minutes |
| **2. Human-in-the-loop** | 6–8 weeks | Agents see the suggested queue, urgency and summary, and accept or correct them; corrections are logged | Agent acceptance ≥ 90% per category; handling time measurably lower; no incidents |
| **3. Partial automation** | ongoing | Auto-route (not auto-close) only categories that passed Phase 2 **and** where `requires_human = false`; 5% random audit continues; fraud, legal and vulnerable cases are always human | Reviewed monthly; one-switch rollback to Phase 2 |

## 5. What we need from PayGuard

1. **Taxonomy and owners.** Confirm the routing queues, a named owner for each, and the SLA for each urgency level.
2. **Historical data.** About 2,000 recent complaints with their final routing and outcome, plus any fraud or legal flags added later. These are used for the Phase 0 evaluation.
3. **Labelling time.** Two senior agents for about 3 days to double-label 300 complaints, plus 2 hours a week for the ongoing audit.
4. **Regulatory clarity.** The exact residency requirement: does it cover derived data and logs, and could an in-country region of a global cloud qualify? Also any rules on automated decisions in complaint handling.
5. **Infrastructure.** An in-country GPU host (cloud or on-premise), budget approval (~$1.5–3k/month), and a security review.
6. **Integration.** API access to the CRM to read complaints and write suggestions, and a way for agents to correct a suggestion in one click.
7. **Risk sign-off.** Compliance and legal must approve the "never auto-close" list and the incident process for a missed sensitive case.

## Risks and open questions

- **Prototype evidence is limited.** It used US CFPB complaints and 60 hand labels. The prototype routed 83–90% of complaints to the exact queue (97% counting a reasonable second queue) and sent 25 of 27 sensitive complaints to a human; both misses were identity-theft letters that cited "FCRA 605B" without saying "identity theft". PayGuard's complaints (language, products, local terms) may behave differently, which is why Phase 0 uses PayGuard's own data.
- **Smaller self-hosted models may be weaker** than the hosted model used in the prototype. Phase 0 must compare two or three candidate models on the same labelled set before we commit.
- **Recall-first rules will over-flag at first.** In the prototype, 86% of complaints were sent to a human and only half of those needed one. Agent time saved in Phase 2 may therefore be smaller than hoped; tightening the rules is the main Phase 0 task, and any change needs compliance approval.
