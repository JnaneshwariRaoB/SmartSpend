# SmartSpend — AI-Powered Affordability Engine

## The Real Problem

Every day, people make financial decisions with incomplete information.

Someone checks their bank balance, sees ₹80,000, and thinks they can afford a ₹50,000 laptop.
What they don't see:
- ₹18,000 rent is due in 4 days
- ₹12,000 EMI on 10th
- Electricity and internet bills totalling ₹3,500 on 15th
- They prefer to keep ₹10,000 as an emergency buffer

Their real available money is ₹36,500 — not ₹80,000.

A simple balance check fails them. This project builds the system that doesn't.

---

## What This Project Is

**SmartSpend** is an AI-powered affordability engine — a backend decision service that a
fintech app, neobank, or personal finance tool can call to answer one question:

> "Is it safe for this user to spend this amount right now, and if not, when and how?"

This is the core intelligence behind features like:
- Cleo's "Roast me" / budget warnings
- YNAB's "You have money available" logic
- Paytm / PhonePe's smart spend nudges
- Credit card apps that suggest EMI vs. full pay

---

## Business Context

### Who uses this?

| User | What they ask |
|---|---|
| A salaried employee | "Can I book this trip for ₹40,000 before my salary comes in?" |
| A freelancer with irregular income | "Is it safe to send ₹15,000 to family this week?" |
| A student | "Can I pay the course fee now or should I wait?" |
| A small business owner | "Can I invest ₹1.3L without affecting payroll?" |

### Why not just check balance?

Because balance is a snapshot. Affordability is a forecast.

The engine must project:
- Cash coming in (salary, freelance payments, rent received)
- Cash going out (EMIs, subscriptions, utility bills, rent paid)
- User's non-negotiable safety buffer
- Flexibility in discretionary spending

Only then can it make a responsible recommendation.

---

## What the Engine Decides

For every request, the engine produces:

### 1. `amount_safe_to_pay`
The maximum the user can pay **today** without any future risk.
Calculated as:
```
available = current_balance - minimum_balance_preference
net_forecast = available + confirmed_income - essential_expenses (over forecast window)
amount_safe_to_pay = min(net_forecast, requested_amount)
```

### 2. `affordability_status`
| Status | Meaning |
|---|---|
| `affordable_now` | Pay today, all bills still covered, buffer intact |
| `affordable_with_plan` | Can't pay all today, but installments make it safe |
| `affordable_later` | Salary/income arriving soon makes it feasible — wait |
| `not_affordable` | Cannot safely cover this within the deadline |

### 3. `recommended_payment_method`
| Method | When |
|---|---|
| `pay_in_full` | Full amount safe today |
| `pay_partial` | Partial payment safe today, rest deferred |
| `installments` | Split across future income dates |
| `wait` | Defer entirely to a safe future date |
| `do_not_proceed` | Not feasible within deadline |

### 4. `payment_plan`
Concrete schedule: e.g., `[{"date": "2025-10-01", "amount": 20000}, {"date": "2025-11-01", "amount": 20000}]`

### 5. `earliest_date_for_full_payment`
The earliest date the full amount can be paid safely.

### 6. `spending_changes_needed`
Which flexible expenses to pause or reduce to unlock funds.
e.g., `[{"category": "streaming_subscriptions", "action": "stop"}]`

### 7. `decision_explanation`
Plain-language, personalised reasoning. Not generic. References actual numbers.
e.g., *"Your balance of ₹80,000 looks healthy, but with ₹33,500 in committed expenses before October 15th and your ₹10,000 buffer, you can safely pay ₹36,500 today. Your next salary on October 1st will cover the remaining ₹13,500."*

---

## Architecture

This is built as a **modular Python service** — each component has a single responsibility and can be tested independently.

```
smartspend/
├── agent/
│   ├── main.py                  # Orchestrator: reads input, writes output
│   ├── profile_loader.py        # Parses user financial profile (JSON + CSV)
│   ├── vision_extractor.py      # Extracts figures from invoices/screenshots (VLM)
│   ├── cash_flow_forecaster.py  # Projects balance day-by-day over forecast window
│   ├── decision_engine.py       # Applies safety rules, selects recommendation
│   ├── plan_builder.py          # Constructs installment schedules
│   └── explanation_writer.py    # LLM writes personalised explanation
├── evaluate.py                  # Scores predictions against reference answers
├── requirements.txt
└── log.txt                      # Full agent reasoning transcript
```

### Data Flow

```
Request CSV
    │
    ▼
profile_loader     ── reads ──►  profile.json
                                 transactions.csv
                                 messages/ images
                                     │
                               vision_extractor (VLM)
                                     │
                                     ▼
cash_flow_forecaster  ──────►  14–90 day balance projection
                                     │
                                     ▼
decision_engine       ──────►  affordability_status + safe amount
                                     │
                                     ▼
plan_builder          ──────►  payment_plan + earliest_date
                                     │
                                     ▼
explanation_writer    ──────►  decision_explanation (LLM)
                                     │
                                     ▼
                              output.csv
```

---

## User Financial Profile

Each user profile contains:

```json
{
  "user_id": "user_26",
  "currency": "IDR",
  "current_balance": 28500000,
  "minimum_balance_preference": 5000000,
  "emergency_buffer": 2000000,
  "income": [
    {"source": "salary", "amount": 12000000, "frequency": "monthly", "next_date": "2025-09-01"}
  ],
  "recurring_expenses": [
    {"category": "rent", "amount": 4500000, "due_day": 1, "essential": true},
    {"category": "internet", "amount": 350000, "due_day": 5, "essential": true},
    {"category": "netflix", "amount": 180000, "due_day": 12, "essential": false}
  ],
  "pending_payments": [
    {"description": "car service", "amount": 1200000, "due_date": "2025-08-20"}
  ]
}
```

---

## What Makes This Industry-Relevant

### Safety-first design
A recommendation is only valid if:
- Balance never drops below `minimum_balance_preference` at any point
- Every essential expense is covered on its due date
- Every instalment in the plan is feasible on that specific date

### Personalisation
Same balance, different recommendations:
- User A has stable monthly salary → installment plan is safe
- User B has irregular freelance income → waiting is safer
- User C explicitly wants to keep a large buffer → more conservative amounts

### Multi-currency, Multi-language
Handles IDR, INR, EUR, USD, ZAR. Request text can be in any language (English, Indonesian, Hindi, etc.). The LLM handles translation and parsing transparently.

### Vision capability
Users often have invoices, bank screenshots, or payment receipts as images. The engine uses a vision LLM to extract amounts and due dates from these files and incorporates them into the decision.

### Auditability
Every decision traces back to specific numbers from the user's profile. No black-box outputs.

---

## Privacy & Compliance (Real-world considerations)

In production, this system would require:

| Requirement | Implementation |
|---|---|
| User consent | Explicit opt-in before reading financial data |
| Data encryption | AES-256 at rest, TLS 1.3 in transit |
| Access control | Per-user data isolation, role-based access |
| Audit logging | Every data access logged with timestamp and purpose |
| Regulatory compliance | GDPR (EU), DPDP Act (India), PSD2 (Open Banking) |
| Data minimisation | Only fetch data needed for the specific request |

> This project uses **fully synthetic, AI-generated data** for development. No real user financial data is used.

---

## Evaluation

The evaluation script (`evaluate.py`) scores predictions on:

| Metric | Method |
|---|---|
| `affordability_status` | Exact match accuracy |
| `recommended_payment_method` | Exact match accuracy |
| `amount_safe_to_pay` | Within ±5% of expected |
| `earliest_date_for_full_payment` | Within ±7 days of expected |
| Overall score | Weighted average across all fields |

---

## Why This Project Stands Out in Interviews

- **Real problem:** Every fintech company needs affordability logic
- **Full stack of AI:** LLM reasoning + VLM extraction + rule-based forecasting
- **Clean architecture:** Each module is testable and replaceable
- **Handles edge cases:** Missing data, multiple currencies, image inputs, non-English text
- **Production mindset:** Privacy, safety constraints, audit trails baked in from the start
- **Measurable output:** Quantitative evaluation with accuracy scores

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM / VLM | OpenAI GPT-4o (or Anthropic Claude) |
| Orchestration | Python — LangChain or direct API calls |
| Data parsing | pandas, pydantic |
| Image extraction | GPT-4o Vision / Claude Vision |
| Output | CSV via pandas |
| Evaluation | scikit-learn metrics + custom tolerance checks |
| Logging | Python logging → log.txt |
