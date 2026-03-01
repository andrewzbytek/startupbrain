"""
Deterministic transcript generator for NuclearCompliance.ai integration tests.

Each function returns a dict with:
    transcript          (str)  — Wispr Flow-style post-session summary
    participants        (str)  — comma-separated names
    topic_hint          (str)  — rough topic label
    expected_claims_min (int)  — lower bound on extracted claim count
    expected_claims_max (int)  — upper bound on extracted claim count
    expected_contradictions (int) — minimum number of contradictions expected
"""


# ---------------------------------------------------------------------------
# Normal sessions
# ---------------------------------------------------------------------------

def session_01_initial_strategy() -> dict:
    """
    Sets the baseline for NuclearCompliance.ai.
    Target market: small UK nuclear plants. Compliance focus.
    Expected: 5-8 claims, 0 contradictions (first session, nothing to contradict).
    """
    transcript = """Session 1 — Initial Strategy and Target Market
Date: 2026-02-01
Participants: Alex, Jordan

We have decided to focus exclusively on small nuclear power plants in the United Kingdom
as our initial target market. By "small" we mean operators running fewer than three
reactors — these include sites like Heysham, Hartlepool, and Torness managed by
independent operators. The rationale for this focus is procurement cycle length: large
operators like EDF and national grid entities have 18-24 month procurement cycles, which
is too slow for a startup at our stage. Small independent nuclear operators typically
close compliance software contracts in 6-12 months.

The core problem we are solving is compliance document management. Nuclear plants are
drowning in PDFs — safety cases, maintenance logs, regulatory submissions, and operating
rules — and tracking version histories and compliance status across these documents is
entirely manual today. Operators use spreadsheets and shared drives. This is our beachhead.

Our primary compliance focus is nuclear safety case documentation. The regulatory
environment (Office for Nuclear Regulation in the UK) requires operators to maintain
detailed audit trails for all safety-critical documents. This creates a clear, repeatable
pain point that every UK nuclear operator shares.

We agreed that the MVP will be UK-only for the first twelve months. The UK nuclear sector
is small enough that we can realistically reach every relevant operator through direct
outreach. Post-MVP international expansion is possible but not a year-one priority.

We also confirmed that our first hire must be someone with nuclear domain expertise, not
a software developer. Domain access is the scarcer resource for us. We can build the
software; we need credibility with plant operators. A former ONR inspector or an EDF
compliance manager would be the ideal profile.

The name "NuclearCompliance.ai" is directional — it positions us as a specialist. We
discussed whether this is too narrow but agreed that specificity builds trust in a
regulated industry. We will revisit the name only if investor feedback consistently flags
it as a problem.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan",
        "topic_hint": "initial strategy and target market",
        "expected_claims_min": 5,
        "expected_claims_max": 8,
        "expected_contradictions": 0,
    }


def session_02_business_model() -> dict:
    """
    Additive session establishing pricing and go-to-market.
    £50K/year per facility, 10 facilities Y1.
    Expected: 6-8 claims, 0 contradictions (all additive to session 1).
    """
    transcript = """Session 2 — Business Model and Pricing
Date: 2026-02-05
Participants: Alex, Jordan

Following our initial strategy session, we have now finalised the business model.
We will use a per-facility annual SaaS licence. Each nuclear site is a single contract.
Billing is annual in advance. We are not using per-user pricing or usage-based billing.
The reason: nuclear budgets are allocated per facility, not per headcount. Annual contracts
give us predictable revenue, and VCs strongly prefer ARR over variable MRR.

Pricing anchor: £50,000 per facility per year for our initial customers. This puts us
comfortably in the enterprise software range while remaining a small line item relative to
the cost of a compliance failure. We will add a one-time implementation fee of £10,000 to
£15,000 to cover onboarding, document ingestion, and staff training.

After we have signed three customers at £50K, we will raise the standard price to £75,000.
The first three customers will be treated as reference customers and will be locked in at
the lower rate.

Our year-one go-to-market goal is 10 paying facilities, which equals £500,000 ARR. This
is achievable given that the entire UK small nuclear market is approximately 15-20
facilities. We are targeting 50-60% market penetration in the small-operator segment
within 24 months.

Direct sales only for year one. No channel partners, no resellers. We need to own the
customer relationship to learn from it. Channel partnerships may be appropriate for
international expansion post-Series A.

We also confirmed that seed round targeting will begin after we close our first paying
customer. The target raise is £1.5M-£2M seed, sufficient for 18 months of runway at
current burn.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan",
        "topic_hint": "business model and pricing",
        "expected_claims_min": 6,
        "expected_claims_max": 8,
        "expected_contradictions": 0,
    }


def session_03_contradiction() -> dict:
    """
    Contradicts session 1: pivot to BP/Shell enterprise (large oil & gas).
    This should trigger a Critical contradiction with the documented target market decision.
    Expected: 4-6 claims, 1+ contradictions.
    """
    transcript = """Session 3 — Revisiting Target Market
Date: 2026-02-10
Participants: Alex, Jordan

We had a long discussion today about whether our focus on small UK nuclear plants is the
right beachhead. We are now seriously considering pivoting to large enterprise oil and gas
companies — specifically BP and Shell — as our initial customers.

The rationale: BP and Shell have compliance teams of 50-100 people. Even a small deal with
BP would be £200K-£300K. They have dedicated budgets for digital transformation. The
procurement cycles are longer (12-18 months) but the contract values more than compensate.
We believe one BP deal is worth three or four small nuclear deals combined.

Our revised thesis is that we should position ourselves as a general industrial compliance
platform, starting with oil and gas, and expand into nuclear as a second vertical. This
is a significant shift from our earlier nuclear-first strategy, but we think it better
reflects where the largest budgets are.

We have identified a contact at BP's HSE digital team who is willing to have an initial
conversation. This is the trigger for re-evaluating our market prioritisation.

We also discussed the technical approach. For oil and gas we will need to handle a much
wider range of document types, including HAZOP studies, PSSR assessments, and COMAH
reports. This is different from the nuclear safety case focus we had before.

One concern: our domain expertise is in nuclear, not oil and gas. We would need to hire
into oil and gas expertise, which is a different hiring profile than the nuclear domain
expert we had planned as our first hire.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan",
        "topic_hint": "target market pivot consideration",
        "expected_claims_min": 4,
        "expected_claims_max": 6,
        "expected_contradictions": 1,
    }


def session_04_investor_feedback() -> dict:
    """
    Investor feedback session. Branding concerns, pricing pushback from Sarah Chen.
    Expected: 3-5 claims, 0 contradictions (feedback doesn't directly contradict decisions).
    """
    transcript = """Session 4 — Investor Feedback Debrief
Date: 2026-02-14
Participants: Alex, Jordan

We debriefed after three investor meetings this week. Two themes emerged consistently.

First, branding. Sarah Chen at Beacon Capital and Marcus Webb at Frontier Ventures both
independently raised concerns about the name "NuclearCompliance.ai". Sarah said it felt
like a government contractor brand. Marcus said the word "nuclear" creates anxiety in
investor circles outside the UK. Neither asked us to change it, but both flagged it as
something that could slow fundraising in the US market. We have decided to explore
alternative names before our next investor round, without committing to a change.

Second, pricing validation. Sarah questioned whether £50,000 per facility per year is
achievable for a first-time software vendor selling into regulated industries. She noted
that most enterprise software sold to nuclear operators starts at £20K-£30K because
procurement managers are evaluated on cost per vendor. This was pushback, not a rejection.
We are not changing our pricing based on one investor's view, but we should validate with
at least two plant managers before the next round.

Marcus asked specifically about our onboarding timeline. He wants to see evidence that
we can get a customer live within 90 days of contract signature. This is a metric we have
not tracked yet. We will add time-to-live as a KPI.

Positive signal: both investors expressed interest in seeing a live demo with real data
from a nuclear operator. We need a reference site to make progress in fundraising.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan",
        "topic_hint": "investor feedback and branding",
        "expected_claims_min": 3,
        "expected_claims_max": 5,
        "expected_contradictions": 0,
    }


def session_05_direct_correction() -> dict:
    """
    Direct correction: 'Implementation fee is £12,000 not £10-15K range'.
    Short, focused session with a single specific correction.
    Expected: 1-2 claims, 0 contradictions (correction is deliberate update).
    """
    transcript = """Session 5 — Pricing Correction
Date: 2026-02-18
Participants: Alex, Jordan

Quick correction to our pricing model. After speaking with two integration consultants,
we have fixed the implementation fee at £12,000 per site. The £10,000-£15,000 range we
had before was too vague for contract negotiations. Customers asked what determines
whether they pay £10K or £15K, and we did not have a clean answer.

Going forward, the implementation fee is a flat £12,000. This covers a four-week
onboarding: document ingestion (up to 500 PDFs), staff training (two sessions), and a
compliance index handover report. Any work beyond this scope is billed at £1,500 per day.

This change does not affect the annual licence price of £50,000 per facility per year.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan",
        "topic_hint": "implementation fee correction",
        "expected_claims_min": 1,
        "expected_claims_max": 2,
        "expected_contradictions": 0,
    }


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def edge_empty() -> dict:
    """Empty transcript — extraction should return zero claims."""
    return {
        "transcript": "",
        "participants": "",
        "topic_hint": "",
        "expected_claims_min": 0,
        "expected_claims_max": 0,
        "expected_contradictions": 0,
    }


def edge_long() -> dict:
    """
    5000+ word session covering many topics.
    Expected: 10-20 claims, 0 contradictions.
    """
    transcript = """Session 6 — Comprehensive Strategy Review
Date: 2026-02-20
Participants: Alex, Jordan, Rachel (advisor)

This was a full-day strategy review with our advisor Rachel, who previously ran business
development at a nuclear software company for eight years. We covered every major aspect
of the business.

MARKET SIZING AND OPPORTUNITY

We began with a detailed market sizing exercise. In the UK there are currently 15 active
nuclear power stations, of which approximately 11 are operated by small or independent
operators (fewer than 3 reactors). The remaining 4 are operated by EDF Energy, which we
are treating as a second-wave target due to their longer procurement cycles.

Each of these 11 small operators currently spends, by our estimates, £80,000-£120,000
per year on compliance administration — primarily through internal staff time and external
consultants reviewing documents. Our product replaces a significant fraction of this cost,
which means our £50,000 price point is defensible as a cost-saving play, not just a
productivity tool.

Beyond the UK, Rachel identified the following international markets as next priority:
France (58 reactors, operated primarily by EDF France — very long procurement cycles),
Finland (2 operators, short cycles, strong digital adoption culture), and South Korea
(24 reactors, aggressive modernisation programme, English documentation acceptable).
International expansion is post-Series A, but Finland in particular could be Year 2.

PRODUCT ROADMAP DISCUSSION

We have prioritised the MVP feature set. The MVP must do three things: ingest PDFs from
the operator's document management system (DMS), extract compliance metadata using LLM
processing, and display a searchable compliance index with version history.

Post-MVP features, in rough priority order:
1. Technical drawing handling (P&IDs, CAD exports as PDFs): required for full safety case
   coverage, scheduled for Version 1.5 (6 months post-MVP).
2. Automated gap analysis: compares the operator's document set against ONR regulatory
   requirements and flags missing or outdated documents. Estimated 9-12 months post-MVP.
3. Audit trail export: generates a compliance report formatted for ONR submissions. Highly
   requested by early prospects. 12 months post-MVP.
4. AI querying: natural language questions across the compliance index ("Show me all
   documents referencing the station blackout procedure"). 18 months post-MVP.
5. Multi-site dashboard: for operators managing multiple facilities. 18-24 months post-MVP.

We spent considerable time on the LLM approach. Claude is our primary model for extraction.
We use PyMuPDF for PDF text extraction, with a vision fallback for scanned documents where
OCR quality is poor. The MongoDB Atlas vector search provides the semantic retrieval layer.
We deliberately avoided LangChain and LlamaIndex — we want to own the extraction logic.

TECHNICAL INFRASTRUCTURE

Storage: Azure Blob Storage for raw documents. Nuclear operators predominantly run on
Microsoft infrastructure, and Azure security certifications (ISO 27001, Cyber Essentials
Plus) are expected prerequisites for data storage approval. AWS S3 is a fallback if Azure
creates procurement friction with a specific customer.

Compute: cloud-hosted, initially on Azure App Service. Containerised using Docker. We are
not doing on-premises deployment for MVP. If a nuclear operator requires on-premises, that
is a post-Series A engineering project.

Data security: all documents are encrypted at rest (AES-256) and in transit (TLS 1.3).
We are exploring whether to seek ISO 27001 certification before our second customer,
or whether Cyber Essentials Plus is sufficient. Rachel's view is that ISO 27001 will be
required for the third or fourth customer, so we should budget for the audit.

Database: MongoDB Atlas (cloud, managed). We use the M10 cluster tier for staging and
M30 for production. Vector search is enabled. We store raw document text, extracted
metadata, compliance index entries, and audit logs.

SALES AND GO-TO-MARKET STRATEGY

Rachel walked us through her experience at her previous company. Key learnings:
- First customer took 14 months from first meeting to contract. This is fast for nuclear.
- The decision to buy compliance software involves the Compliance Manager, the IT
  Director, and the Finance Director. All three must sign off. The Compliance Manager
  is typically the champion; the IT Director is the risk blocker.
- Nuclear operators rarely issue open tenders for software under £100K. They prefer to
  negotiate directly with a known vendor. This means relationship-led sales is essential.
- Industry events: the Nuclear Industry Association (NIA) annual conference is the most
  important event. The World Nuclear Association symposium is for larger operators.
  We should exhibit at NIA this year (cost: approximately £5,000 for a small stand).
- Reference customers are everything. One signed customer who speaks publicly about us
  is worth 20 cold outreach calls.

Our revised sales process:
1. Warm introduction via Rachel's network (she will introduce us to 3-4 compliance
   managers in the next 60 days).
2. Discovery call to confirm pain point and current workflow.
3. Proof of concept: we ingest a sample of their existing documents (100-200 PDFs) and
   show them the resulting compliance index. No charge for PoC. Maximum 2 weeks.
4. Commercial proposal: £50K licence + £12K implementation fee. 30-day close target.
5. Onboarding: 4-week project. Document ingestion, training, handover.

COMPETITIVE LANDSCAPE REVIEW

We reviewed three competitors in detail:

ComplianceDB (UK-based): Rule-based OCR and keyword tagging. No LLM extraction. Their
UI is outdated (built in 2016). Pricing: £30K-£45K per site. We win on extraction quality
and modern interface. Their main advantage: 8 years of nuclear-specific regulatory
templates built up.

TechSafe (German): Focused on HAZOP and COMAH documentation for oil and gas. They have
a nuclear module but it is not their core product. Pricing unknown. They operate in a
different regulatory context (German nuclear phase-out means their nuclear customer base
is declining). Not a primary competitor for UK market.

NuclearDocs Pro (US): US nuclear market focus (NRC regulations, not ONR). Pricing in USD,
contracts require US data residency. Not a competitor for UK market but relevant if we
expand to US. Their LLM extraction features are 12-18 months behind ours based on their
product blog.

Our moat: nuclear-specific LLM prompts trained on UK regulatory vocabulary (ONR, ALARP,
Safety Cases, LC documents). This is not replicable quickly. It took us 3 months to get
the extraction quality to 95%+ accuracy on safety case documents. A general compliance
platform would need 6-12 months to match our nuclear extraction quality.

FUNDRAISING AND FINANCIAL PLANNING

Current financial position: self-funded, approximately £180,000 remaining runway at
current burn rate (£25K/month including Alex and Jordan salaries). This gives us
approximately 7 months before we need external capital.

Target: close first customer within 4 months, which gives us revenue to extend runway.
If first customer slips past 4 months, we will need to either raise a small bridge or
reduce burn temporarily.

Seed round targets: £1.5M-£2M at a pre-money valuation of £5M-£8M. This implies a
pre-seed round in the traditional sense (we are too early for Series A terms). Rachel
introduced us to three nuclear-specialist investors: Breakthrough Energy Ventures
(Washington DC), Nucleation Capital (San Francisco), and a family office in London that
invests in nuclear technology.

The seed round will fund: engineering team hire (1 senior developer), first hire (nuclear
domain expert), sales and marketing (NIA conference, case study production), and 18 months
of runway.

KEY RISKS IDENTIFIED

1. LLM accuracy: extraction errors in safety-critical documents could be a liability issue.
   Mitigation: human confirmation step is mandatory — no document metadata is published
   to the compliance index without a staff member reviewing it.
2. Regulatory approval: we have not confirmed whether ONR requires any certification or
   approval for software used in compliance workflows. Rachel will check with her ONR
   contact this week. This could be a 6-12 month delay if certification is required.
3. Data residency: some nuclear operators require UK data residency. Azure UK South
   satisfies this for Azure-hosted data. MongoDB Atlas has a UK region. This should not
   be a blocker.
4. Procurement cycle risk: even 6-12 months is a long cycle for a startup. We may need
   to run multiple sales processes in parallel to ensure pipeline coverage.
5. Team concentration risk: the entire company is currently two people. The loss of either
   founder would be material. We need to distribute knowledge into documentation and
   the codebase before we hire.

OPEN QUESTIONS FROM THIS SESSION

- Should we seek ONR pre-approval for our extraction methodology? (Rachel to investigate)
- What is the right approach for multi-site operators — bundle pricing or per-site pricing?
- Do we need a formal data processing agreement (DPA) before handling nuclear safety
  documents, and what does that require?
- When should we incorporate a limited company (currently operating as a partnership)?
  Rachel recommends incorporating before signing any customer contracts.
- Channel partnership with a nuclear consultancy (e.g., Atkins, Jacobs) — Rachel thinks
  this could be transformative but cautions that channel partners are slow to onboard.

DECISIONS MADE TODAY

1. We will exhibit at the NIA annual conference this year (budget: £5,000).
2. Rachel will make 3-4 warm introductions to compliance managers within 60 days.
3. We will not pursue international expansion until we have 3 paying UK customers.
4. ISO 27001 certification will be pursued after customer #3 (not before).
5. We will incorporate as a limited company before signing the first customer contract.
6. The PoC process (free, 2-week ingestion demo) is now the standard first commercial step.

DETAILED PRODUCT SPECIFICATION SESSION

After the strategy review, we spent two hours going through the detailed product
specification with Rachel. This section captures the key decisions and questions from
that part of the session.

Document ingestion pipeline: The MVP ingestion pipeline has five stages. Stage one is
document upload — the operator uploads PDFs through a secure web interface. Stage two is
text extraction — PyMuPDF extracts text from all PDF pages, falling back to vision-based
OCR for pages where text extraction confidence is below 80%. Stage three is metadata
extraction — we send each document to Claude claude-sonnet-4-20250514 with a structured prompt
that asks for document type, revision number, approval date, applicable regulatory
licence conditions, and summary. Stage four is human confirmation — every extracted field
is presented to a compliance officer for review before publication. Stage five is
indexing — confirmed documents are written to the MongoDB Atlas compliance index.

The human confirmation step is non-negotiable. Rachel was emphatic about this: nuclear
operators will not accept any automated system that publishes compliance data without
human sign-off. The product must make human review fast (our target is under 2 minutes
per document) while ensuring nothing goes live without explicit approval. The UI must
make it easy to approve, reject, or edit individual fields.

We discussed what "reject" means in practice. If a compliance officer rejects the
extraction for a document, the document should be flagged for manual entry. We are not
trying to fully automate extraction — we are trying to make manual entry much faster by
providing an 80-90% complete pre-filled form. The extraction is a starting point, not a
final answer.

Document versioning: nuclear compliance requires complete version history. When a new
version of a document is uploaded, the system must link it to prior versions and preserve
the full history. The compliance index must show the currently approved version as well
as all prior versions with their approval timestamps. This is an ONR audit trail
requirement that has no flexibility.

Regulatory licence conditions: each nuclear site operates under a set of licence
conditions (LCs) issued by ONR. There are 36 standard LCs, and compliance documents
must be mapped to the LCs they relate to. Our extraction prompt asks Claude to identify
which LCs are relevant to each document. Rachel reviewed our LC mapping approach and
confirmed the extraction logic looks correct for Safety Cases (typically LC10, LC14,
LC19, LC23, LC26) and Operating Rules (typically LC24, LC25, LC27).

DETAILED FINANCIAL MODEL REVIEW

We built a detailed financial model with Rachel's input. Key assumptions:

Revenue model: £50,000 per facility per year, plus £12,000 one-time implementation fee.
Year 1: 3 facilities signed at £50K each = £150,000 ARR + £36,000 implementation fees.
Year 2: 7 additional facilities at £50K (total 10 facilities) = £500,000 ARR.
Year 3: 5 additional UK facilities + first international customer = £750,000 ARR.

Cost structure: Currently £25,000/month including Alex and Jordan salaries (£8K each,
below market deliberately) and infrastructure costs (MongoDB Atlas M30: ~£800/month,
Azure App Service: ~£600/month, Claude API at current usage: ~£400/month). Total
infrastructure: approximately £2,000/month. Total monthly burn: £25,000.

Unit economics at scale: each facility contributes £50,000 ARR. Customer acquisition
cost (CAC) estimate: £8,000-£15,000 per facility (direct sales time + conference costs
allocated across pipeline). Payback period: 2-4 months. Lifetime value assuming 5-year
customer life: £250,000 per facility. LTV:CAC ratio: approximately 20:1 at mature scale.

Cash position: £180,000 remaining. At current burn, approximately 7 months runway.
First revenue expected at month 4 (first customer signed, implementation fee received).
This extends runway to approximately 9 months. Seed round needed within 6 months.

Seed round use of funds: £1.5M-£2M.
- Engineering: hire one senior full-stack developer (£120K/year salary). £240K over 2 years.
- Domain expertise: hire one nuclear compliance expert (£90K/year). £180K over 2 years.
- Sales and marketing: NIA conference (£5K), case studies (£15K), travel (£20K). Total £40K.
- Infrastructure scaling: upgrade MongoDB Atlas, additional Claude API capacity. £30K.
- Legal and compliance: ISO 27001 audit (£25K), data processing agreements (£10K). £35K.
- Operating reserve: £1M for 24 months of extended runway.

Rachel flagged that nuclear sector investors typically want to see a clear path to
regulatory compliance (ISO 27001, Cyber Essentials Plus) before committing capital. We
should accelerate the Cyber Essentials Plus certification — it is achievable in 2-3 months
and costs approximately £3,000. ISO 27001 follows after customer #3.

CUSTOMER DISCOVERY INSIGHTS

Rachel facilitated a customer discovery review based on the 8 conversations Alex and
Jordan have had with nuclear compliance managers in the past 3 months. Key patterns:

Pain point severity: 7 out of 8 compliance managers rated compliance document tracking
as a "significant" or "major" pain point. The most common description: "I have 3,000
documents to track and I do it in Excel with broken VLOOKUP formulas." This is exactly
the problem we solve.

Current workarounds: all 8 contacts use spreadsheets as their primary tracking tool.
Six of the eight also use SharePoint for document storage, but without any structured
metadata — documents are stored by folder structure only, not by compliance attribute.
None of the eight had any AI or LLM-based tooling in use.

Willingness to pay: 5 of 8 contacts said £50,000/year was "reasonable" or "within our
budget." Two said it was "high for a new vendor" but did not rule it out. One said it
was "too expensive" — this was a site with only one compliance manager and limited budget.
The £50,000 price point is not a blocker for our target segment.

Decision timeline: all contacts indicated that a decision to buy new compliance software
would require IT Director and Finance Director sign-off in addition to the Compliance
Manager. Typical internal approval process: 3-6 months once a vendor is shortlisted. This
is consistent with Rachel's experience.

Proof of concept requirement: 6 of 8 contacts said they would want a proof of concept
before committing. Our 2-week PoC (100-200 document ingestion, no charge) maps directly
to this requirement. Rachel confirmed this is standard for nuclear software procurement.

LEGAL AND IP CONSIDERATIONS

We briefly discussed intellectual property. Our core IP is the extraction prompt library
— the set of nuclear-specific prompts that produce structured compliance metadata from
regulatory documents. These prompts have taken 3 months to develop and tune and represent
significant accumulated knowledge of ONR regulatory vocabulary and document structure.

We decided to treat the prompts as trade secrets rather than seeking patent protection.
Patent protection for software prompts is unclear and slow. Trade secret protection
requires keeping them confidential, which we already do. We will add confidentiality
provisions to employment contracts.

Data ownership: all compliance documents remain the property of the nuclear operator.
We do not train any models on customer data. We do not retain raw document content after
the contract ends (or use it for any purpose other than providing the service). These
are standard SaaS data ownership commitments, but in nuclear they need to be explicit in
the contract.

Liability limitation: our contracts will cap our liability at the annual licence fee
(£50,000) in the event of a service failure. Rachel noted that this is standard for SaaS
vendors in regulated industries, and nuclear operators will not typically push back on it
for software under £100K.

HIRING PLAN DEEP DIVE

We spent 45 minutes on the hiring plan with Rachel's guidance. The decisions:

First hire (nuclear domain expert): target profile is a former ONR inspector, a senior
compliance manager from a nuclear plant, or a nuclear safety case author from a
consultancy (e.g., Jacobs, Amec Foster Wheeler, Wood). Salary range: £80,000-£100,000.
Equity: 1-2% vesting over 4 years. This person's primary role is customer credibility
and domain validation, not engineering. They should be able to review extraction results,
identify errors in regulatory mapping, and contribute to prompt refinement.

Rachel offered to circulate a job description within her nuclear network. She has contacts
at three former colleagues who might be interested or be able to make introductions.

Second hire (senior developer): target profile is a full-stack developer with Python and
cloud experience. Nuclear domain expertise is not required. Salary range: £100,000-£130,000.
Equity: 0.5-1%. This person will own the ingestion pipeline and UI, freeing Alex and
Jordan to focus on sales and product strategy.

Third hire (sales): timing is post-seed round, after we have at least one reference
customer. Sales hire salary range: £70,000-£90,000 base plus commission. This hire
unlocks faster pipeline development.

CONFERENCE AND EVENTS STRATEGY

We mapped the nuclear industry conference calendar:

NIA Annual Conference (London, October): the most important event. All UK nuclear
operators attend. We will exhibit with a small stand. Demo station showing live ingestion
of a sample compliance document set. Target: 10 meaningful conversations with compliance
managers.

World Nuclear Association Symposium (London, September): larger, more international,
focused on reactor operators rather than compliance. Less relevant for our immediate
pipeline but useful for brand building. We will attend but not exhibit.

ONR Annual Conference: focused on regulators and safety professionals. Useful for
understanding regulatory direction. We will attend as observers in year one.

Nuclear Skills Organisation (NSO) events: smaller, focused on workforce development.
Rachel will attend on our behalf and report back.

PRODUCT PRICING SENSITIVITY ANALYSIS

We tested three alternative pricing scenarios with Rachel:

Scenario A (current): £50,000/year + £12,000 implementation. Pro: high margin, clear
value proposition. Con: some prospects balk at the price for a new vendor.

Scenario B (volume discount): £50,000/year for facilities 1-3, £40,000 for facilities
4+, at the operator level. Pro: encourages multi-site deals. Con: complicates contracts,
reduces ARR if one operator has multiple sites.

Scenario C (freemium pilot): 30-day free trial with full features, then £50,000/year.
Pro: dramatically reduces PoC friction. Con: operators may not have the bandwidth to
evaluate properly in 30 days; could devalue the product.

Rachel's recommendation: stick with Scenario A for the first 3 customers, then reassess
based on what objections we actually encounter. The PoC (which is already free) provides
sufficient trial period. Freemium is a consumer-grade motion that does not fit the
enterprise nuclear buying process.

We agreed with Rachel's recommendation. Current pricing model is confirmed: £50,000/year
per facility plus £12,000 one-time implementation fee.

AFTERNOON WRAP-UP AND ACTION ITEMS

Rachel summarised her key action items:
1. Make 3-4 warm introductions to compliance managers (within 60 days).
2. Circulate nuclear domain expert job description to her network (within 14 days).
3. Check with ONR contact about software certification requirements (within 30 days).
4. Review our data processing agreement template against nuclear sector norms (within 30 days).

Alex and Jordan action items:
1. Book NIA conference stand (deposit required within 30 days of booking).
2. File for Cyber Essentials Plus certification (engage a certifying body within 14 days).
3. Begin company incorporation process (engage a solicitor within 7 days).
4. Update investor deck with Rachel's market sizing data (by end of week).
5. Prepare PoC runbook: a repeatable playbook for running the 2-week document ingestion
   proof of concept, so that any team member can run it without Alex or Jordan.

Rachel will join us for a monthly advisor call going forward. She will not be a board
member at this stage but has agreed to a formal advisor agreement with 0.25% equity
vesting over 2 years in exchange for approximately 4 hours per month of structured
support.

Overall, this was the most productive session we have had. The market sizing and financial
modelling have given us much greater confidence in the business case. The customer
discovery patterns confirm we are solving a real problem at the right price point.
Rachel's network access is a significant asset that we expect to translate into our
first customer introduction within 60 days.

REGULATORY ENVIRONMENT DEEP DIVE

Rachel gave us a detailed overview of the UK nuclear regulatory framework that will shape
our product requirements for the next 12-18 months.

The Office for Nuclear Regulation (ONR) is the primary regulator. ONR issues site licences
under the Nuclear Installations Act 1965. Each licence comes with 36 standard licence
conditions (LCs) that define the safety management obligations of the site licensee.
Our product must help operators demonstrate compliance with these licence conditions.

The most compliance-document-intensive licence conditions are:
- LC10: Training — operators must maintain records of all staff training and competency
  assessments for safety-related roles. This generates large volumes of training records
  and competency frameworks.
- LC14: Safety documentation — operators must maintain up-to-date safety cases for all
  hazardous operations. Safety cases can be thousands of pages long.
- LC19: Construction and installation — operators must maintain records of all safety-
  significant modifications. Each modification requires a formal safety assessment.
- LC23: Operating rules — operators must maintain documented operating rules for all
  safety systems. These rules change frequently as equipment is modified.
- LC24 and LC25: Operating and maintenance instructions — formal procedures for all
  safety-critical operations. Must be version-controlled and regularly reviewed.
- LC26: Control and supervision — operators must ensure all safety-related work is
  properly authorised and supervised. Records include permit-to-work documentation.
- LC27: Safety mechanisms — records of all safety system tests and inspections.

Rachel explained that ONR conducts formal inspections at each nuclear site approximately
once per year, with additional targeted inspections following incidents or as part of
periodic safety review programmes. Our product needs to enable operators to rapidly
assemble documentary evidence for any LC on demand — the classic use case is an ONR
inspector walking into a site and asking "show me your LC14 safety case documentation
for the turbine hall." Our compliance index should make this answerable in minutes.

We also discussed the Periodic Safety Review (PSR) process. Every 10 years, operators
must conduct a comprehensive review of their safety case and demonstrate that the plant
remains safe to operate. PSRs are massive undertakings involving hundreds of thousands
of pages of documentation. Rachel has worked on two PSRs and believes our product could
provide significant value in PSR preparation — the compliance index makes it much easier
to identify documentation gaps and stale documents. PSR preparation is a potential
premium use case that we should keep in mind for Version 2.

TECHNICAL ARCHITECTURE DECISIONS

We finalised several technical architecture decisions that had been open:

LLM prompt versioning: we will version-control all extraction prompts alongside the
codebase. Each prompt has a version number (e.g., extraction_v1.2.md). When we update
a prompt, we record the version that produced each extraction in the compliance index.
This allows us to re-run extractions with newer prompts when prompt quality improves.

Extraction confidence scoring: for each extracted field, Claude returns a confidence
score (high, medium, low). Fields with low confidence are flagged for mandatory human
review. Fields with high confidence still require human sign-off but are pre-checked
in the UI to reduce friction. We estimate that 70-80% of fields will have high
confidence for well-structured safety case documents.

Failure mode handling: if Claude returns malformed output (XML parsing fails), the
document is flagged as "extraction failed" and sent to a manual entry queue. We never
silently drop a document. Every upload eventually reaches either a confirmed state
(extraction reviewed and approved) or a failed state (manual entry required).

API cost management: we track Claude API costs per customer. Each customer's document
ingestion is billed internally against their account. This allows us to monitor per-
customer API cost and adjust if a particular customer has an unusually large or complex
document set that drives costs above our £50K annual revenue threshold. At current token
prices, we estimate API cost per facility per year is approximately £800-£1,500 depending
on document volume.

Backup and recovery: the compliance index is backed up to Azure Blob Storage daily.
Point-in-time recovery is available for 30 days. For nuclear operators, we will offer
an annual data export in standard formats (CSV, JSON) so that operators can maintain
their own offline copy of the compliance index.

PARTNERSHIP AND ECOSYSTEM STRATEGY

Rachel raised the question of partnerships with nuclear consultancies. The major firms —
Jacobs, Amec Foster Wheeler (now Wood), Atkins, Lloyd's Register — all have nuclear
compliance practices and bill hundreds of engineers to nuclear operators. These firms
could be significant channel partners, and they could also be acquirers.

Rachel's view on channel partnerships: possible and potentially transformative, but slow.
A partnership with a major consultancy requires alignment at multiple levels — commercial,
technical, legal. These firms are large and risk-averse. A partnership agreement would
likely take 9-12 months to negotiate and implement. We should focus on direct sales for
the first 2 years and revisit partnerships after we have demonstrated product-market fit.

Alternative partnership approach: rather than a formal channel partnership, Rachel
suggested we should build relationships with individual consultants at these firms. A
nuclear compliance consultant who uses our product in their work becomes an informal
ambassador. When their client asks them for a recommendation, they recommend us. This
informal referral dynamic is faster to build than a formal partnership.

Technology partnerships: we are using Claude (Anthropic) as our primary LLM. We should
explore whether an Anthropic startup partnership programme is available — this could
provide API credits, go-to-market support, and co-marketing opportunities. Rachel is not
familiar with Anthropic's partnership programmes but suggested we investigate.

BRAND AND POSITIONING REFINEMENT

Rachel raised the brand issue again and pushed us harder than the investor feedback had.
Her view: "NuclearCompliance.ai" will be perceived by operators as a product built by
people who understand nuclear, which is positive. But it may be perceived by investors
as too narrow, and by non-nuclear potential acquirers as unappealing.

She suggested we consider a name that describes what the product does rather than the
vertical it serves. Examples she offered: ComplianceAtlas (indexes compliance documents),
SafetyIndex (searchable safety document index), RegulationIQ (intelligent regulatory
document management). None of these are necessarily better, but they illustrate the
direction: a name that hints at the function without being vertically locked.

We agreed to conduct a naming exercise before our next investor meetings. We will generate
20-30 candidate names, score them against criteria (memorable, domain-appropriate,
available as .ai domain, no trademark conflicts), and shortlist to 5 for investor feedback.

For now, "NuclearCompliance.ai" remains our operating name. We will not change it without
clear consensus that an alternative is better. The brand change is exploratory, not committed.

TECHNOLOGY RISK ASSESSMENT

We spent 30 minutes with Rachel on technology risk. Her questions probed areas we had
not fully thought through:

What happens if Anthropic significantly raises API prices or changes its terms of service?
Response: we are aware of model dependency risk. Our prompts are transferable to other
LLMs (GPT-4o, Gemini). We have tested GPT-4o briefly and extraction quality is comparable.
Switching costs are low — it is a configuration change, not a rewrite. We accept this
risk as manageable.

What happens if a customer's document management system (DMS) does not have an API for
document export? Response: most nuclear operators use SharePoint or a bespoke DMS. For
SharePoint, we have an integration path via the Microsoft Graph API. For bespoke systems,
we provide a bulk upload interface (zip file containing PDFs). We have not encountered a
case where document extraction was blocked by DMS access issues.

What is our disaster recovery plan if our primary cloud region goes down? Response:
Azure UK South is our primary region. We have not implemented multi-region failover for
MVP. The compliance index is read-heavy; operators can tolerate hours of read-only access
but need write access for active document ingestion. Post-seed, we will implement an
Azure UK West secondary region with asynchronous replication.

What is the security model for API access to the compliance index? Response: operators
access the index via a web application (username/password login with MFA). API access
for integration with other systems uses API key authentication. All API keys are per-user
and can be revoked. We log all API access for audit purposes.

Rachel's overall assessment: the technology risks are manageable for a seed-stage
company. The most significant risk she identified is not technology — it is people.
We are two people with deep product knowledge, and a significant proportion of the
business value is currently in our heads. The priority before hiring is to document
everything: architecture, prompts, customer conversations, regulatory knowledge.

COMPETITOR INTELLIGENCE UPDATE

Rachel provided updated competitor intelligence based on her recent industry conversations.

ComplianceDB has a new version in beta (ComplianceDB 4.0). It adds basic AI features —
natural language search across the document index — but the extraction is still rule-based
keyword tagging, not LLM-based metadata extraction. Rachel spoke to a compliance manager
at Sellafield who is currently evaluating ComplianceDB 4.0 and described the extraction
quality as "better than Excel, not good enough to trust without full manual review." This
validates our extraction-first approach.

A new entrant has appeared: SafetyFlow, a UK startup founded 8 months ago by former BP
engineers. Their focus is oil and gas HAZOP documentation, not nuclear. They have one
customer (a North Sea operator) and are funded by a Scottish Enterprise grant. They are
not a current competitor for our nuclear target segment, but their existence confirms that
the broader compliance document management market is attracting new entrants.

Rachel identified a potential acquisition risk we had not considered: large enterprise
software vendors (IBM, Oracle, SAP) occasionally acquire niche compliance tools. An
acquisition of ComplianceDB by a larger vendor with nuclear relationships would be a
material risk. Rachel's view: this is unlikely in the next 2 years because ComplianceDB
is still privately held and not obviously for sale. But we should move fast to establish
customer relationships before a well-funded acquirer could consolidate the market.

NEXT STEPS AND SESSION CLOSE

We closed the session at 6pm. Rachel summarised the key decisions and open items:

Confirmed decisions from today's session:
- Target market: UK small nuclear operators, nuclear-first, UK-only for first 12 months.
- Pricing: £50,000 per facility per year plus £12,000 implementation fee (confirmed, not
  changing based on investor feedback alone).
- First hire: nuclear domain expert, not a developer.
- Sales motion: direct sales, relationship-led, PoC-first.
- Conference: NIA Annual Conference, exhibit with a stand.
- Certification: Cyber Essentials Plus before first customer, ISO 27001 after customer #3.
- Company structure: incorporate as a limited company before first contract.
- Brand: exploratory naming exercise before next investor round, no committed change.

Open items requiring follow-up:
- ONR certification requirement for compliance software (Rachel to investigate).
- Data processing agreement template for nuclear sector (Rachel to review).
- Anthropic startup partnership programme (Alex to investigate).
- Multi-region cloud disaster recovery plan (post-seed priority).
- PoC runbook documentation (Alex and Jordan to prepare within 2 weeks).

The next full strategy session will be in 6 weeks. Monthly advisor calls with Rachel
begin next week. Overall, the session confirmed that our strategy is sound and that the
primary near-term priority is closing the first customer as quickly as possible.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan, Rachel",
        "topic_hint": "comprehensive strategy review",
        "expected_claims_min": 10,
        "expected_claims_max": 20,
        "expected_contradictions": 0,
    }


def edge_xml_injection() -> dict:
    """
    Transcript containing raw XML closing tags to test injection protection.
    Expected: 2-4 claims, 0 contradictions.
    """
    transcript = """Session 7 — Technical Architecture Note
Date: 2026-02-22
Participants: Alex

Quick note on the extraction approach. We use XML tags like </transcript> and </claim>
in our internal prompt templates. One concern is whether a malicious PDF could contain
content like </extraction_output> or </claim> that would confuse the parser.

We decided to escape all user-supplied content before embedding it in prompts. The
escape_xml() function in our claude_client handles this: it replaces < with &lt; and
> with &gt;. This means even if a PDF contains </transcript> the resulting XML remains
well-formed.

We also confirmed that the regex parser in ingestion.py handles DOTALL mode, so
multi-line claim text works correctly. Testing with a document containing </claim>
tags confirmed no parser confusion.

Our technical approach: LLM extraction from PDFs using Claude claude-sonnet-4-20250514.
MongoDB Atlas for storage. Azure Blob for raw documents.
"""
    return {
        "transcript": transcript,
        "participants": "Alex",
        "topic_hint": "XML injection protection and technical architecture",
        "expected_claims_min": 2,
        "expected_claims_max": 4,
        "expected_contradictions": 0,
    }


def edge_multiple_contradictions() -> dict:
    """
    Three contradictions in one session: target market, pricing, and technical approach.
    Expected: 3-5 claims, 3 contradictions.
    """
    transcript = """Session 8 — Strategic Pivot Discussion
Date: 2026-02-25
Participants: Alex, Jordan

After reflection, we want to make three major changes to our documented strategy.

First, target market: we are no longer focusing on small UK nuclear plants as our
beachhead. We have decided to pivot our primary focus to large enterprise pharmaceutical
companies — specifically GMP compliance documentation for FDA-regulated manufacturing
sites. Pharma is a larger market, has more standardised document types, and decision
makers are easier to reach than nuclear operators. This replaces our earlier nuclear-first
strategy entirely.

Second, pricing: we are abandoning the £50,000 per facility annual licence model. We have
decided to use usage-based pricing instead: £0.05 per document processed, with a minimum
monthly commitment of £2,000. This is a complete reversal of our earlier decision to use
per-facility annual licensing. We believe usage-based pricing will lower the barrier to
entry for new customers.

Third, technical approach: we are no longer using Claude as our primary LLM. We have
decided to switch to OpenAI GPT-4o for extraction. The reason is cost — GPT-4o is
approximately 40% cheaper per token for our extraction workloads. We will also replace
MongoDB Atlas with PostgreSQL and pgvector for vector search, as it is cheaper to operate
on standard cloud infrastructure.
"""
    return {
        "transcript": transcript,
        "participants": "Alex, Jordan",
        "topic_hint": "major strategic pivot with multiple contradictions",
        "expected_claims_min": 3,
        "expected_claims_max": 5,
        "expected_contradictions": 3,
    }


# ---------------------------------------------------------------------------
# Registry for easy iteration in tests
# ---------------------------------------------------------------------------

ALL_SESSIONS = [
    session_01_initial_strategy,
    session_02_business_model,
    session_03_contradiction,
    session_04_investor_feedback,
    session_05_direct_correction,
]

ALL_EDGE_CASES = [
    edge_empty,
    edge_long,
    edge_xml_injection,
    edge_multiple_contradictions,
]
