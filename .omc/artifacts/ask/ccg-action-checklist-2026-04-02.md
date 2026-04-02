# CCG Action Checklist — Meeting Intelligence Project

## Date: 2026-04-02

### Agreed Recommendations (Claude + Gemini Consensus)

- [x] Extract structured data from all 53 meetings
- [x] Build chronological timeline with impact categorization (CRITICAL/MAJOR/DISRUPTIVE/REDIRECT)
- [x] Analyze marketing sentiment trajectory
- [x] Map Vinnie-Michael relationship patterns (decisions, tensions, direction changes)
- [x] Map Joe-Michael relationship patterns (mediation, alignment, 1-on-1 dynamics)
- [x] Generate AI expertise scores (individual + organizational)
- [x] Create decision influence graph (Mermaid)
- [x] Identify 5 structural dysfunctions
- [x] Produce strategic recommendations
- [x] Generate risk assessment

### Conflicting Recommendations

| Area                     | Claude's Position                       | Gemini's Position                                    | Chosen Direction                                                                                      |
| ------------------------ | --------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| AI as org capability     | Real strength, needs own track          | Distraction from basics                              | **Hybrid:** Separate AI innovation from operations. AI is real but is consuming operational bandwidth |
| Root cause framing       | Structural authority mismatch (fixable) | Leadership dysfunction (requires personality change) | **Claude's:** Frame as structural — more actionable, less personal                                    |
| Severity of Michael risk | High but addressable with changes       | Imminent, nearly certain departure                   | **Gemini's intensity, Claude's framing:** Treat as urgent (30 days) but solvable                      |

### Final Action Checklist for Stakeholders

**Week 1 (Immediate):**

- [ ] Review baseline report HTML dashboard
- [ ] Read CCG synthesis — especially dysfunction cycle and risk assessment
- [ ] Share Vinnie-Michael and Joe-Michael pattern reports with appropriate stakeholders
- [ ] Identify 3 abandoned action items that should be either formally killed or reactivated

**Week 2-4 (Short-term):**

- [ ] Define decision authority boundaries (WHAT vs HOW)
- [ ] Implement action item tracking with deadlines and follow-up checkpoints
- [ ] Address Michael's staffing and resource concerns
- [ ] Create separate AI innovation meeting track (monthly, with Perry Evans)

**Month 2-3 (Medium-term):**

- [ ] Reduce recurring meetings by 30%
- [ ] Enforce max 3 action items per meeting
- [ ] Establish 90-day strategy lock (no direction changes without formal review)
- [ ] Measure: action item completion rate target 50%+

**Quarter 2 (Validation):**

- [ ] Re-run extraction pipeline on new meetings to track improvement
- [ ] Compare sentiment trajectory — target positive sentiment recovery
- [ ] Measure direction change frequency — target <10 per quarter
- [ ] Assess retention risk indicators

### Deliverables Produced

| #   | Deliverable                        | Location                                     | Status |
| --- | ---------------------------------- | -------------------------------------------- | ------ |
| 1   | Extraction pipeline (TypeScript)   | `pipeline/src/extract.ts`                    | Done   |
| 2   | Normalizer                         | `pipeline/src/normalize.ts`                  | Done   |
| 3   | Report generator                   | `pipeline/src/report.ts`                     | Done   |
| 4   | Baseline HTML dashboard            | `pipeline/output/baseline-report.html`       | Done   |
| 5   | Chronological topic categorization | `pipeline/output/chronological-topics.md`    | Done   |
| 6   | Marketing sentiment analysis       | `pipeline/output/marketing-sentiment.md`     | Done   |
| 7   | Vinnie-Michael patterns            | `pipeline/output/vinnie-michael-patterns.md` | Done   |
| 8   | Joe-Michael patterns               | `pipeline/output/joe-michael-patterns.md`    | Done   |
| 9   | AI expertise scoring               | `pipeline/output/ai-expertise-score.md`      | Done   |
| 10  | CCG tri-model synthesis            | `pipeline/output/ccg-synthesis.md`           | Done   |
| 11  | Pattern flags (machine-readable)   | `pipeline/output/pattern-flags.json`         | Done   |
| 12  | Gemini advisory artifact           | `.omc/artifacts/ask/gemini-*.md`             | Done   |
| 13  | Claude advisory artifact           | `.omc/artifacts/ask/claude-*.md`             | Done   |
| 14  | Normalized data (JSON)             | `pipeline/data/normalized/`                  | Done   |
| 15  | Raw extractions (53 JSONs)         | `pipeline/data/extracted/`                   | Done   |

### CCG Workflow Status: COMPLETE

- [x] Phase 1: Decompose request into advisor prompts
- [x] Phase 2: Invoke advisors (Gemini MCP — Codex fallback noted)
- [x] Phase 3: Collect artifacts
- [x] Phase 4: Synthesize with agreed/conflicting/chosen direction + action checklist
