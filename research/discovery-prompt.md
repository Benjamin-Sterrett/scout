# Scout Discovery Research Prompt

Use this prompt with Claude (separate session), Gemini, or ChatGPT to research the freelance arbitrage landscape. Bring findings back to synthesize.

---

## The Prompt

I'm building a system called Scout — a freelance job arbitrage engine. It scores freelance job listings against a defined ROI model, filters out low-value work, and converts winners into structured tickets that feed into an automated development workflow (Claude Code + Linear + CI/CD).

The system has an unfair advantage: deterministic execution via an AI-orchestrated dev-workflow that turns messy specs into shipped code faster than manual freelancers. The goal is to consistently select jobs where this system has a structural edge — clear enough to scope, technical enough to automate, messy enough that competitors underprice or avoid them.

**I need research on these 6 topics. For each, give me concrete findings, not general advice.**

---

### 1. Platform Access & APIs

For each platform, tell me:
- Is there an official API? What does it expose (job listings, bidding, messaging)?
- What are the ToS restrictions on automated access, scraping, or bot-assisted bidding?
- Are there partner programs or approved integrations?
- What's the realistic path to automated intake (API, RSS, scraping, browser automation)?

**Platforms:**
- Upwork
- Fiverr
- Toptal
- Freelancer.com
- Reddit (r/forhire, r/slavelabour, r/webdev)
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

---

### 3. Pricing Strategy

- What are the going rates for the categories above on each platform?
- How should I price: per-project, hourly, or value-based?
- What's the sweet spot where I can deliver fast (AI advantage) but price isn't so low it signals amateur?
- How do top-rated freelancers on Upwork/Fiverr price similar work?
- Is there a "speed premium" market (pay more, get it in 24h)?

---

### 4. Legal & Compliance

- Do any platforms prohibit AI-assisted delivery? What's the current enforcement?
- Are there disclosure requirements (must I tell clients AI is involved)?
- What about IP assignment — if AI generates the code, who owns it?
- Any platform-specific rules about automated bidding or proposal generation?
- Tax implications of multi-platform freelance income (US context)

---

### 5. Profile & Reputation Building

- What's the cold-start problem on each platform? How long to build credibility?
- Which platforms have the lowest barrier to first job?
- Are there strategies for bootstrapping ratings quickly?
- How important are platform-specific certifications or tests?
- Which platforms allow portfolio/case study showcasing?

---

### 6. Competitive Landscape

- Are other people/companies doing AI-assisted freelancing at scale?
- What tools exist for freelance job aggregation or automated bidding?
- Is anyone selling "AI freelancing" as a service or course?
- What's the market trajectory — is this arbitrage window closing or opening?

---

## Output Format

For each topic, give me:
1. **Key findings** (bullet points, be specific — names, numbers, URLs)
2. **Go/no-go assessment** per platform (for topic 1)
3. **Recommendations** (what should I do first?)
4. **Risks** (what could go wrong?)
5. **Sources** (where you found this — I'll verify)

Keep it dense. I don't need caveats or hedging. I need signal.
