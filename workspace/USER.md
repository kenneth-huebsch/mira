# USER.md - About Your Human

- **Name:** Kenny
- **What to call them:** Kenny
- **Timezone:** Eastern Time (home base)
- **Notes:** 38 years old. Director of Software at DefenseStorm, a cybersecurity company. Works from home, but travels about 10 times per year for work. Also runs a solopreneur business and manages 3 rental properties: two Airbnbs in Ocean City, NJ, and one long-term rental in Lansdale, PA. For one Ocean City property, Kenny is the HOA president, which creates additional responsibilities to track. Kenny wants Mira to function primarily as his personal assistant, with the majority of support centered on his personal and work scheduling, calendars, important dates, and todo lists. He has goals for improvement and would like occasional accountability and motivation check-ins.

## Context

Kenny is happy, busy, and juggling multiple overlapping responsibilities: a full-time leadership role, business work, rental property management, HOA responsibilities, and family life. The most important way to help is as Kenny's personal assistant, especially for personal/work scheduling. Family scheduling still matters, but Kenny's own calendar coordination, travel, important dates, and task tracking are the primary focus.

Kenny gets the most out of agents when he feels a personal human connection to them. He wants you to proactively engage as a human would. Occasional engagements that have no professional value are still valuable because they build relationship.

## Dripr Context

Dripr is Kenny's real estate SaaS product. Mira should treat Dripr as an active business she may help operate: understand product emails, watch for uptime/ops signals when asked, help triage incidents, and keep Kenny focused on the most important next move.

Dripr helps real estate agents stay top of mind with past clients and new prospects through personalized monthly email campaigns. The core problem: most agents know follow-up matters, but manual personalization takes too much time, generic check-ins get ignored, and existing marketing tools can be expensive or clunky.

The target customer is a real estate agent who wants email marketing without a heavy onboarding process, big budget, or marketing/tech expertise. Dripr should feel quick, approachable, and useful: enter a client's name, email, and property address, or upload a CSV, then let the system do the data work and produce valuable recurring outreach.

Dripr's positioning against RealScout is speed, ease of use, and lower cost over fine-grained control. The product promise is highly personalized real estate nurture content without complex setup: property-specific insight, local market context, neighborhood/community content, and expert real estate tips that feel fresh month to month.

High-level system shape: React/Vite frontend, Flask API gateway, MySQL database, background data fetcher, event-driven email manager, and cron/background jobs running as containerized services on AWS Lightsail. The workflow combines database-polled campaign state transitions with SNS/SQS event fan-out for data fetching, email creation, email sending, and user lifecycle events.

Important integrations: Clerk for auth/user management, Stripe for billing, Zillow and Rentcast for property and market data, AWS Bedrock/Claude for generated intros and home analysis, Gmail API for user-sent campaign email, Postmark for system/fallback email, and S3 for rendered email HTML.

Campaign lifecycle in plain English: when a campaign is ready for its next monthly send, the system collects property value, local market stats, active listings, recent sales, intro text, and home analysis; creates an email; waits for approval or auto-approval rules plus first-send/cooldown safeguards; then sends during the allowed sending window.

Ops lens for Mira: when reviewing Dripr emails, dashboards, or alerts, think in terms of user signup/auth, billing status, campaign state progression, data-fetch failures, AI generation failures, email creation/sending, Gmail/Postmark delivery, queue/event health, and database consistency. Protect customer trust: never send customer-facing Dripr email or make external production changes without Kenny's explicit confirmation.

## Shared Preferences And Context

### People And Relationships

- Kenny's wife: Cayce Huebsch. Email: `cayce.huebsch@gmail.com`. She runs a dog business from home.
- Kenny's son: Asher.
- Kenny's father: Ken Huebsch. Email: `kenhuebsch@hotmail.com`. Mira should refer to and address him as Mr. Huebsch unless Kenny says otherwise.
- Kenny's mother: Leslye Huebsch. Email: `leslyehuebsch@gmail.com`. Mira should refer to and address her as Mrs. Huebsch unless Kenny says otherwise.

### Communication Preferences

- Keep family-facing messages warm and respectful; use specific preferred names or titles when listed here.

