# Lumos — Under-18 Data Policy

**Status: DRAFT for the BCOLBD 2026 demo. Not legal advice, not reviewed by a
lawyer, and not sufficient for a public launch.**

This document exists because BLOCK-007 was blocking LUMOS-005, and because the
whitepaper already commits to "parental consent for under-18 accounts" and "no
student assessment profiles" without either being implemented or written down.
A draft that engineering can build against is better than a commitment nobody
has read. It is written to be *replaced* by a reviewed policy, not to stand in
for one.

Two things to be clear about before anything below is relied on. Bangladesh's
**Digital Security Act** and any successor data-protection legislation have not
been reviewed against this text. If Lumos is ever offered to students outside
Bangladesh, **GDPR Article 8** (EU) and **COPPA** (US) impose stricter and
different requirements, particularly on consent age and on verifiable parental
consent, and neither is satisfied here.

---

## 1. Who uses Lumos

The target user is an SSC student in Bangladesh. **Most are 14 to 16 years old.**
The Edexcel IAL demo scope reaches slightly older students, typically 16 to 18.

The design assumption is therefore inverted from most products: **assume a user
is a minor unless established otherwise**, and make the minor's experience the
default rather than the exception.

## 2. Minimum age

- **Minimum age to use Lumos at all: 13.**
- **Ages 13–17: permitted with a parent or guardian's acknowledgement** (§4).
- **Under 13: not permitted.** No account, no chat, no stored data.

13 is chosen because it is the floor COPPA and GDPR both build on, and because
below it the consent machinery required is materially heavier than a competition
project can honestly implement.

## 3. What is collected — and what is deliberately not

**Collected, because the product cannot work without it:**

| Data | Why | Retention |
|---|---|---|
| Display name (may be a nickname) | Addressing the student | Life of the account |
| Email address | Sign-in and recovery | Life of the account |
| Year of birth (not full date) | Age banding only | Life of the account |
| Curriculum, subject, level | Retrieval scope (ADR-006) | Life of the account |
| Preferred language | Bangla or English interface | Life of the account |

**Not collected. This list is a commitment, not an oversight:**

- No full date of birth. The year is enough to band an age.
- No phone number, address, school name, or photograph.
- No precise location. Country-level at most, and only if a real need appears.
- No third-party advertising or analytics identifiers. **No ad network, ever.**
- **No assessment profile.** Lumos does not build, store or infer a model of a
  student's ability, weaknesses or predicted grade. This is the whitepaper's own
  commitment, and the schema must not acquire the columns to break it quietly.
- No biometric data, no voice recordings retained after transcription.

## 4. Parental acknowledgement

Verifiable parental consent in the COPPA sense — a credit-card check, a signed
form, a video call — is **not implemented**, and pretending otherwise would be
the exact failure this project is built to avoid.

What the demo implements is weaker and is named accurately:

1. At sign-up, a student aged 13–17 supplies a parent or guardian's email.
2. Lumos sends that address a plain-language notice: what Lumos is, what it
   stores, how to see it, and how to delete the account.
3. The guardian can delete the account from a link in that email, with no
   account of their own and no login.
4. The student's account works meanwhile.

**This is acknowledgement, not verified consent**, and every user-facing string
must say so. Moving to verified consent is a launch requirement and is out of
scope for the competition demo.

## 5. Chat history

**Default: not retained.** A tutoring conversation is discarded when the session
ends. Retention is opt-in per student, off until chosen, and revocable — and
revoking it deletes what was already stored rather than only stopping new
writes.

This is stricter than most products and is deliberate. A retained conversation
between a fifteen-year-old and a tutor is a sensitive record with no clear owner,
and the feature it buys — resuming a chat — does not justify holding it by
default.

## 6. Retention and deletion

| Event | Effect |
|---|---|
| Student deletes their account | All personal data erased within **30 days** |
| Guardian uses the deletion link | Same |
| 24 months of inactivity | Account and data deleted after a warning email |
| Opt-in chat history revoked | Stored conversations erased immediately |

Deletion means deletion from the primary store and from backups on their normal
rotation, not a `deleted = true` flag. Anonymous, non-reversible aggregates —
"how many questions were asked this week" — may survive, and must never contain
anything that could re-identify a student.

## 7. What the tutor may and may not do

- It answers curriculum questions from the registered corpus, with citations.
- It **states a limitation when evidence is insufficient**, and never invents an
  answer to appear helpful (ADR-010).
- It does not offer medical, legal, or mental-health advice. A conversation that
  turns to self-harm is met with a signpost to a real service and a human, not
  with a generated response.
- It does not collect information about the student's family, home or school in
  the course of a conversation, and it does not ask.

## 8. Security

- Passwords hashed with a memory-hard function. No secret has a default, and a
  missing one aborts startup (ADR-012).
- Every resource authorised server-side on ownership, on every request.
- No student data reaches a model provider beyond the question text and the
  retrieved curriculum context. **No name, no email, no identifier is sent to a
  model.**
- Licensed curriculum material is never redistributed; the tutor explains and
  cites (ADR-026).

## 9. What is not resolved

Recorded here so nobody mistakes this draft for a finished policy.

- [ ] Review against Bangladeshi law by someone qualified to do it.
- [ ] Whether acknowledgement (§4) is legally sufficient in Bangladesh, and what
      verified consent would require.
- [ ] A data-processing agreement with Neon, Cloudflare and Hugging Face, each of
      which processes data on Lumos's behalf.
- [ ] Where data physically rests. Neon is currently `ap-southeast-1`
      (Singapore), which is a cross-border transfer from Bangladesh.
- [ ] A breach-notification procedure, with a named responsible person.
- [ ] Whether a school or teacher account may see a student's activity, which
      §3's no-assessment-profile commitment constrains sharply.

---

**Owner:** Hameem · **Drafted:** 2026-09-04 · **Blocker:** BLOCK-007
