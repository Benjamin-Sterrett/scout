# Scout Discovery Research Prompt

Use this prompt with Claude (separate session), Gemini, or ChatGPT to research the freelance arbitrage landscape. Bring findings back to synthesize.

---

## The Prompt

I'm building a system called Scout — a freelance job arbitrage engine. It scores freelance job listings against a defined ROI model, filters out low-value work, and converts winners into structured tickets that feed into an automated development workflow (Claude Code + Linear + CI/CD).

The system has an unfair advantage: deterministic execution via an AI-orchestrated dev-workflow that turns messy specs into shipped code faster than manual freelancers. The goal is to consistently select jobs where this system has a structural edge — clear enough to scope, technical enough to automate, messy enough that competitors underprice or avoid them.

**I need research on these 10 topics. For each, give me concrete findings, not general advice.**

---

### 1. Platform Access & APIs

For each platform, tell me:
- Is there an official API? What does it expose (job listings, bidding, messaging)?
- What are the ToS restrictions on automated access, scraping, or bot-assisted bidding?
- Are there partner programs or approved integrations?
- What's the realistic path to automated intake (API, RSS, scraping, browser automation)?

Also cover:
- How does each platform's **search algorithm** rank freelancers? What triggers visibility vs burial?
- What are the **payment timelines** and escrow mechanics? How long from delivery to cash in hand?
- Can you operate on **multiple platforms simultaneously** with the same identity/portfolio?

**Platforms:**
- Upwork
- Fiverr
- Toptal
- Freelancer.com
- Reddit (r/forhire, r/slavelabour, r/webdev)
- X / Twitter (job posts, DM outreach)
- Discord (dev/freelance servers)
- We Work Remotely
- PeoplePerHour
- Gun.io
- Arc.dev

---

### 2. Job Categories With Highest Arbitrage Potential

Which categories of freelance work have the biggest gap between perceived difficulty (by the client or average freelancer) and actual difficulty (for an AI-assisted workflow)?

Think about:
- Web scraping / data extraction
- API integrations
- Bug fixes on existing codebases
- MVP builds from specs
- Migration work (framework upgrades, database migrations)
- Automation scripts
- Landing pages / marketing sites
- WordPress/Shopify customization

For each category, estimate:
- Typical price range
- Typical delivery time (manual freelancer vs AI-assisted)
- Clarity of typical specs (1-5)
- Risk of scope creep (1-5)

Also identify the **high-signal search queries** that surface these jobs on each platform. Examples:
- "fix", "bug", "error", "not working"
- "quick", "urgent", "today", "ASAP"
- "API issue", "integration", "webhook", "form not submitting"
- "migration", "upgrade", "convert"

Which query patterns consistently surface high-arbitrage listings vs noise?

---

### 3. Pricing Strategy

- What are the going rates for the categories above on each platform?
- How should I price: per-project, hourly, or value-based?
- What's the sweet spot where I can deliver fast (AI advantage) but price isn't so low it signals amateur?
- How do top-rated freelancers on Upwork/Fiverr price similar work?
- Is there a "speed premium" market (pay more, get it in 24h)?
- What **effective hourly rate** do top performers actually achieve in each category? (Not listed rate — actual earnings / actual hours)
- What's the minimum viable price point where clients still take you seriously? Below what threshold do you attract bad clients?

---

### 4. Legal & Compliance

- Do any platforms prohibit AI-assisted delivery? What's the current enforcement?
- Are there disclosure requirements (must I tell clients AI is involved)?
- What about IP assignment — if AI generates the code, who owns it?
- Any platform-specific rules about automated bidding or proposal generation?
- Tax implications of multi-platform freelance income (US context)
- **Dispute/chargeback risk** — how does each platform handle disputes? What's the freelancer's actual protection?
- If a client asks for a refund after delivery, what recourse exists?

---

### 5. Profile & Reputation Building

- What's the cold-start problem on each platform? How long to build credibility?
- Which platforms have the lowest barrier to first job?
- Are there strategies for bootstrapping ratings quickly?
- How important are platform-specific certifications or tests?
- Which platforms allow portfolio/case study showcasing?
- What **bid/proposal styles** convert best? Short and direct vs detailed breakdown?
- How much does response time matter? (e.g., first-to-bid advantage on Upwork)

---

### 6. Competitive Landscape

- Are other people/companies doing AI-assisted freelancing at scale?
- What tools exist for freelance job aggregation or automated bidding?
- Is anyone selling "AI freelancing" as a service or course?
- What's the market trajectory — is this arbitrage window closing or opening?

---

### 7. Client Red Flags & Qualification

- What are the proven indicators of a bad client? (vague scope, "quick and easy", no budget listed, history of disputes)
- Which client behaviors predict scope creep, non-payment, or endless revisions?
- Are there tools or heuristics for screening clients on Upwork/Fiverr before accepting? (review history, spend history, hire rate)
- What's the optimal way to structure a **fixed-scope agreement** that protects against "just one more thing"?

---

### 8. Communication & Delivery Patterns

- How do top freelancers minimize back-and-forth during execution? (async updates, loom videos, structured check-ins)
- What delivery format do clients respond best to? (PR link, deployed preview, zip file, walkthrough video)
- How much hand-holding is typical? What level of "done" do clients actually expect vs what they say?
- What's the fastest path from "job accepted" to "payment released" on each platform?

---

### 9. Portfolio & Social Proof at Scale

- How do you build a portfolio when AI did the work? What's ethical, what's standard practice?
- What does a high-converting Upwork/Fiverr profile actually look like? (structure, not vibes)
- Are **before/after case studies** effective for getting hired? Where do you publish them?
- How important are platform-specific metrics (Job Success Score on Upwork, response time on Fiverr)?

---

### 10. Freestyle — What Else Should I Know?

This is the open-ended section. Tell me anything important that I didn't ask about. Things like:

- Hidden costs or gotchas on specific platforms
- Emerging platforms or channels I'm not considering
- Non-obvious failure modes for AI-assisted freelancing
- Psychological/behavioral patterns in freelance clients that affect job selection
- Tools, browser extensions, or services that experienced freelancers use
- Seasonal patterns in freelance demand
- Whether this model works better as a solo operator or with a small team
- Adjacent business models that could layer on top (e.g., productized services, templates, SaaS)
- Anything that would change my scoring model or hard gates
- What you'd do differently if you were building this system yourself

**Don't hold back.** If it's relevant to running a freelance arbitrage operation at scale with AI-assisted execution, I want to hear it. This section is explicitly for things I don't know I don't know.

---

## Output Format

For each topic, give me:
1. **Key findings** (bullet points, be specific — names, numbers, URLs)
2. **Go/no-go assessment** per platform (for topic 1)
3. **Recommendations** (what should I do first?)
4. **Risks** (what could go wrong?)
5. **Sources** (where you found this — I'll verify)

Keep it dense. I don't need caveats or hedging. I need signal.
