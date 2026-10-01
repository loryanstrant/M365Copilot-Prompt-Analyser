# Demo guide — M365 Copilot Prompt Analyser

**For a stand-in presenter at the Avanade booth, 6DAI Sydney, Thursday 15 October 2026.**
You do not need to know this product. Read section 2, then follow section 3 in order.

---

## 1. The 60-second pitch

Everyone in this room has run Copilot training. Almost nobody can tell you whether it worked.
You get an adoption number — people are using it — and then a complete blank where the quality
should be. So the next move is always the same: another training deck, for everybody, whether
they need it or not.

This measures the thing that actually determines whether Copilot pays for itself, which is how
well your people ask. It reads prompts out of Microsoft Graph, sends each conversation to your
own Azure OpenAI deployment to be scored, and gives you a dashboard that says how good your
prompting is, which part of it people are worst at, who needs help by name, and what to say to
them. It also flags where somebody has pasted a person's name or something sensitive into a
prompt — not as a compliance tool, but so you can coach them.

It replaces the Power BI and Power Platform version of the same report, so there is no Power BI
licence and no Power Platform to maintain. The scoring runs on your own Azure OpenAI resource,
which means the prompts never leave your subscription and you control what model does the
scoring and what it costs — you can switch to a cheaper or larger model in the settings page
without redeploying anything. The rest is a small managed database and two small containers,
deployed from one button. Free, open source, MIT licence, no Microsoft support agreement.

It is for whoever owns Copilot enablement and is tired of guessing.

---

## 2. Before you start

**● Open this five minutes before you need it.** The demo instance is set to sleep when nobody
is using it, so the **first page load takes 30 to 60 seconds** and looks like a hung browser.
Once it is awake it stays quick. When this was last checked on 1 October 2026 a cold start took
15 seconds. Load it, leave the tab open, and do not close it between visitors.

- **URL:** https://prompts-api-7jgmhewq.delightfulplant-4d403f7f.australiaeast.azurecontainerapps.io
- **Also linked from:** https://copilotreports.strant.com — the landing page with all four
  products as cards. It is being set up now and the name may still be propagating, so use the
  long URL above as your reliable route in.
- **Username:** `admin`
- **Password:** in Vaultwarden, item **"Copilot demo AZURE — M365 Copilot Prompt Analyser
  admin"** (organisation *Strant Family*, collection *LS Development*).

Have the password open on your phone before the conference starts. Do not write it anywhere.

---

## 3. The click path

The left sidebar is grouped into **You**, **Organisation**, **Administration** and **Help**.
All the figures below were read off the live demo instance on 1 October 2026. If a number on
screen differs, say the number on screen — it is the real one.

**One bit of vocabulary before you start.** The product scores four things about every prompt:
whether it states a **goal**, gives enough **context**, points at a **source**, and says what
it **expects** back. The dashboard labels those four together with an acronym. Do not read the
acronym aloud — say "goal, context, source and expectation". That phrasing is the pitch.

**You land on "Your coaching", not the dashboard.** The demo binds the admin login to one of
the fictional employees, so the first page is one person's own coaching view.

### 1. Your coaching (`/me`)

Point at **How you compare** — their four scores against their team and against the whole
organisation.

> "This is what every one of your people gets. Their own prompting, scored, against their team.
> Nobody sees anybody else's numbers — and if the team is too small to compare without
> identifying someone, it refuses to show the comparison at all and tells you why."

**Say out loud: 183 prompts, averaging 5.5 out of 10.**

### 2. Overview (`/overview`)

Six cards across the top. Point at **Avg prompt quality**.

> "Four thousand prompts, scored one to ten. The average is five point six."

**Say out loud: 5.6 out of 10 — and only 38 per cent of prompts rate as high quality.** Then
point at **Weakest GCSE lever**, and say the words rather than the label:

> "And look at this — of the four things that make a prompt work, the one they're worst at is
> stating what they actually want. That's a four point seven out of ten. Which means your next
> enablement session isn't 'Copilot training', it's one specific habit, for everybody."

### 3. Executive briefing (`/briefing`)

Scroll it. Do not read it out.

> "The last thirty days against the thirty before, in sentences. And this is the important
> part — there's no AI anywhere in this page. Every figure is a database query and every
> sentence is assembled from fixed thresholds. The product has a language model configured, and
> it is deliberately kept out of here, because this is the page that gets read aloud to a
> board."

**Say out loud: no language model writes any of this.**

### 4. Prompt quality (`/quality`)

The per-prompt table, searchable and sortable, with each prompt's four scores and the
governance flags beside it.

> "Every prompt, scored, with the ones most in need of help at the top."

**Say out loud: 83 per cent of these prompts were written by the person — not accepted from a
suggestion.** That is the number that tells you whether people are actually engaging or just
clicking what Copilot offered them.

### 5. Conversations (`/conversations`)

Click into one. You get the full thread, each prompt's scores, a suggested improvement, and a
better starter prompt.

> "And this is the coaching itself — not 'you scored four', but 'here's what you should have
> asked instead'."

### 6. People coaching (`/coaching`)

Pick a person by name.

> "A manager or an enablement lead can see what anyone's coaching view looks like. Picked by
> name, not by editing a web address — and the personal view genuinely cannot be reached that
> way, because there's no user parameter in it at all."

**Say out loud: 7.2 against 3.2.** In the demo data, Grace Mbeki in Marketing averages 7.2 out
of 10 and Jo Whitcombe in Technology averages 3.2, on a near-identical number of prompts.

> "Same company, same licence, same training. One of those two is getting four times the value.
> That's the gap you can't see today."

### 7. Tenant users (`/users`)

Licence held or not, shown as a shape and a word, ● or ○, never colour alone. People with no
activity are listed rather than hidden.

---

## 4. Three questions executives will ask

**"Where does our prompt text go?"**
To your own Azure OpenAI deployment, inside your own subscription, and nowhere else. There is
no vendor service in the middle and no third party involved. Be precise about the one real
trade-off: unlike the Usage Reporter, this product does retain conversation text, because it
has to be able to show you *why* something scored as it did. If that is not acceptable in your
tenant, you restrict who can open the report to a named security group — and that answer is
usually enough for a risk team, but have the conversation honestly rather than glossing it.

**"What does it cost to run?"**
Two parts, and they are different in kind. The hosting is small and predictable — the cheapest
burstable database tier and two small containers. The scoring costs Azure OpenAI tokens, and
that is the part that scales with your prompt volume. It is designed down: it makes one model
call per conversation rather than one per prompt, it only ever scores prompts it has not
already scored, and the model is a setting rather than code, so you can run a smaller and
cheaper model and switch without redeploying. Your own team should price it against their own
prompt volume — do not quote them a figure.

**"Do we need Power BI, Fabric or the Power Platform?"**
No. None of the three. That is exactly what this replaces. It is one container and one database
and the dashboard is part of the application. It does need an Azure OpenAI deployment, which is
a different thing and most organisations in this room already have one.

---

## 5. If it breaks

**◐ Cold start — the normal case.** The page sits blank or spinning for up to a minute, then
loads completely and is quick from then on. Say, honestly:

> "These demos are set to sleep when nobody's on them, so it's just waking up — give it thirty
> seconds. In your own tenant it would be running all the time."

Then keep talking. Do not refresh repeatedly; it does not help.

**○ Genuinely down — rare.** You waited a full two minutes, refreshed twice, and you are
getting an error page or a connection failure rather than a slow load. Do not debug at the
booth. Switch to the fallback:

> "The live one's not cooperating — let me show you the actual screens instead, they're the
> same thing."

**The fallback, in this repo:**

- **Screenshots:** `docs/screenshots/` — `executive-summary.png`, `executive-briefing.png`,
  `prompt-quality.png`, `conversation-detail.png`, `personal-coaching.png`,
  `people-coaching.png`, `tenant-users.png`, `usage-breakdown.png`, `settings.png`,
  `scan-history.png`, plus dark-mode versions of every one. Walk these in the same order as
  section 3.
- **Video:** the 30-second video for this product belongs at
  `docs/videos/M365 Copilot Prompt Analyser - 30s.mp4`. **As of 1 October 2026 it is not yet
  committed** — check the folder before the event, and if it is empty, the screenshots are your
  fallback.

Have the screenshots open in a second browser tab before the doors open.

---

## 6. What NOT to promise

- **Production scoring needs your own Azure OpenAI deployment.** This is the big one for this
  product. The demo you are showing has pre-computed scores in its database and **no Azure
  OpenAI resource behind it at all** — nothing is being scored live while you click. In a real
  tenant, the scoring stage simply does not run without an endpoint, a deployment name and a
  key. If a customer has not got Azure OpenAI, say "then you'd need to stand that up first",
  and do not imply it is included.
- **It needs admin-consented Microsoft Graph application permissions** — two of them, reading
  Copilot interaction history and reading the directory, approved by a Global Administrator.
  Without those it collects nothing.
- **The governance flags are not data loss prevention.** They flag prompts that look like they
  contain a name or something sensitive, so you can coach the person. They are not a substitute
  for Microsoft Purview and must never be sold as one.
- **Conversation text is retained.** See the first executive question above. Do not let anyone
  leave believing it works like the Usage Reporter, which stores no text at all.
- **It is a desktop dashboard.** No phone layout, none planned.
- **There is no support contract.** MIT licence, community project, no service level agreement,
  no Microsoft backing.
- **Do not quote a dollar figure.** Not for hosting and especially not for token spend.

---

## 7. Everything on screen is fake

Say this before anybody has to ask:

> "Just so you know up front — everything you're about to see is invented. It's a fictional
> company called Avanoso, with made-up people and made-up prompts. There's no real tenant
> connected to this and never has been."

Every name, department, prompt and score is synthetic data created by a seeding script in this
repository. There are no real people, no real organisation and no real prompts anywhere in it.
Given that this product's whole subject is what employees typed, saying so unprompted is not
optional — it is the first thing out of your mouth.

---

## Shutting the demo down after the event

The four demos live in the **MVP 1k** Azure subscription, in four resource groups:
`rg-copilot-usage-demo`, `rg-copilot-prompts-demo`, `rg-copilot-agents-demo`,
`rg-copilot-cowork-demo`, plus `rg-copilot-demos-site` for the landing page.

The container apps are already set to `minReplicas: 0`, so they cost nothing while
nobody is looking at them. **The Postgres flexible servers are not** — they bill
whether or not anyone visits.

◐ **Stopping a Postgres flexible server is not permanent.** Azure automatically
starts a stopped server again after **7 days**. If you stop them and forget, they
quietly resume billing a week later.

● **The durable option is to delete the resource groups** once the event is over.
Everything is reproducible — each repo ships its own one-click template, so standing
the demo back up later is a template deployment and a `seed-demo` call, not a rebuild.

Ask Loryan before deleting anything: the same subscription hosts unrelated work.
