# Entity catalog: positions by name, candidate sets by index

Status: done (2026-11-10). Stage B landed 2026-10-27 and stage C 2026-10-28;
the code of each was reviewed (adversarial workflow with a judge) and
measured (§6). Rev 6 (2026-10-27) dropped stage A and D18's tie-break (owner
ruling; the measurements behind it are in §11); the stage A code and its two
tests were written, then removed. Every item of the three plan reviews is
ruled or applied (§11); the plan text was last reviewed at rev 5. The
LIVE-pass bug found at step 0 was fixed by the link-layer session
(Semantic_Embedding `6d0ad1b`, 2026-11-01). Hashes and paths here are those
of the Isabelle2025-2 code, before the Isabelle2026 port. "The scratchpad"
below is the session scratchpad, archived as
`~/archive/claude-scratchpad/1595227b-scratchpad-2026-11-10.tar.zst`.
- RESUME HERE (last updated 2026-11-10): nothing left to do.
  - Owner's answers (2026-11-10): no memory write; Status line rewritten
    and this plan committed (Isabelle_RPC `87f8a24`, pushed); MLML's
    Isabelle_RPC pointer is neither committed nor pushed; Isa-Mini `19843e1`
    and MLML `da4778f9` were already on origin; `test_entity_mirror.py` stays
    uncommitted; the scratchpad archived (6,191 entries and 149,072,309
    bytes, matching the source, which was then deleted). The link-layer
    session was asked to update the status of
    `BUG_LIVE_PASS_INFRA_FILTER_CONTEXT.md` (it still reads "open").
  - REASSIGNED (2026-10-29, relayed by the link-layer session "Isabelle
    jEdit 语义搜索面板", quoting the owner "LIVE bug 由你负责"): that session
    owns the LIVE-pass bug and designs its fix together with retiring the
    infra filter's class_variant rule
    (`Semantic_Embedding/ai-artifacts/INFRA_FILTER_CLASS_VARIANT_PLAN.md`).
    Do not start a fix here. Answered it (23:46 +08): nothing pending here
    depends on the current behaviour; listed what the fix may make stale
    (§8.1's baseline and driver, `QueryLocalScore_PatternOnly`, the 5 goldens
    of `19843e1` if class_variant goes) and the probes in the scratchpad.
    Fixed there: Semantic_Embedding `6d0ad1b` (2026-11-01).
  - Formerly NEXT (owner, 2026-10-28 20:56): DISCUSS the LIVE-pass bug after
    the compaction; no code before the owner agrees. Note:
    `BUG_LIVE_PASS_INFRA_FILTER_CONTEXT.md` beside this file.
    - Re-explain from zero (the owner asked "remind me what it is", 20:50;
      that explanation is not in any file): `make_entity_callbacks` builds the
      infra filter once, keeping the build-time `fact_space`; the theorems
      LIVE pass and rules Source-2 find a fact that appeared later (e.g. a
      `have` noted as `local.h`); `accessible_entry_of_fact` passes it in the
      query context's space, then `infra_thm_rule`'s "hidden" rule interns
      it in the build-time space, which never saw it, so it is dropped. No
      enumeration returns `is_local = true`. Ranked AoA search is spared
      (`IsaMini.contextual_thms`); pattern-only search is not (golden
      `QueryLocalScore_PatternOnly` records 0 results). The constant rules
      use the build-time `const_space` the same way (not probed).
    - Fix directions in the note (not decided): skip the name-space rules
      for live facts, or evaluate them in the query context. Either may move
      goldens such as `QueryLocalScore_PatternOnly` and makes §8.1's baseline
      stale (harmless now: the driver is uncommitted). Bring a fix proposal;
      for a design change, the adversarial review per the owner's template.
  - Done (2026-10-28, 18:23–20:56): the 23 retrieval goldens re-run with
    real scores (18/23), the 5 failures diagnosed (owner asked: cause = the
    infra filter rework `a5fe5dc`, 08-25, after the goldens' `da03c7d`, see
    "Goldens on this machine" below) and re-recorded (owner-approved); 23/23
    pass. COMMITTED (owner-approved "批准提交"): Isa-Mini `19843e1` (the 5
    `Tests/*.yml` only), MLML `da4778f9` (only the Isa-Mini pointer,
    `e2d732f` → `19843e1`); on origin by 2026-11-10.
  - `test_entity_mirror.py` (§8.3 tests) stays uncommitted (owner,
    2026-10-27, confirmed 2026-11-10), although review item R2 noted that the
    lock and the two protocol checks have no committed direct test and that
    cross-call catalog reuse within a `by aoa` is covered by it only. Still
    passes on 2026-11-10.
  - Done (2026-10-28, 17:36 +08): §8.5 for stage C, the real runs; §6.2 holds
    the measured numbers. Run 17:04–17:30, all three proved, 4.90 USD; torn
    down (sampler.stop, stop_servers.sh, the Naproche orphan killed). Files in
    the scratchpad's `stageC_measure/run_claudecode/`. First unfiltered
    theorem sub-query 6.84 MB, later ones 11 KB; peak RSS 2.88 GB, from the
    vector store's mmap pages now that keys match (probe in §6.2).
    - Pure.thy check: daily moved from `30aab6e` to `7eb9137` at ≈14:40
      (another session, owner's order: `5826993` "Pure.thy back to stock",
      light_locale `f5b9f29`); Pure.thy is byte-identical to the hg tag;
      Pure's theory hash is `104565bf…` and HOL.HOL's `18e25ed3…`, the DB's.
    - The REPL first rebuilt `MathBench_ProverBase` (43.5 min) and
      `MathBench_Prover` (7.3 min); checked with `ps` beforehand that no other
      build ran (owner's rule, relayed 2026-10-28: never build in parallel
      with another build).
  - The steps that were run (record):
    1. Verify the owner's statement that Pure.thy is restored: diff
       `contrib/Isabelle2025-2/src/Pure/Pure.thy` against the scratchpad's
       `vector_probe/Pure.pristine.thy`; and check retrieval scores are no
       longer all 0.300 (e.g. one retrieval golden). If restored, the stage B
       run (all scores 0.300) is not like-for-like: say so when comparing.
    2. Run exactly as for stage B (record below, "Real run done"): copy the
       scripts of the scratchpad's `stageB_measure/` into a new
       `stageC_measure/`, change the paths only; ports 27184 (host under
       py-spy) and 6699 (REPL via tools/aoa_putnam_eval/start_servers.sh,
       CLAUDE* variables unset), driver ClaudeCode, cases.txt; monitor every
       ≤ 10 min; teardown: sampler.stop, stop_servers.sh, kill the orphans
       whose environ has RPC_Host=127.0.0.1:27184 (a Naproche one last time).
    3. Analyse with `query_windows.py`, `analyze.py`, `profile_summary.py`;
       count the unfiltered theorem sub-queries in this run's logs
       (`count_subqueries.py`); report bytes per case AND per unfiltered
       sub-query (after B: 86,664 entries ≈ 14.4 MB each). Write the numbers
       into §6.2 (measured) by hand.
  - All repositories PUSHED to origin (2026-10-28 ≈14:00, owner's order):
    Isabelle_RPC, Semantic_Embedding, Isa-Mini, and, because MLML's unpushed
    bumps referenced them, Performant_Isabelle_ML (df5d412) and light_locale
    (02f2694); then MLML (6734d096). Every submodule commit MLML references
    is on origin.
  - Stage C LANDED (2026-10-28): Isabelle_RPC `0b239b2`, Semantic_Embedding
    `b7e0133`, Isa-Mini `e2d732f`, MLML `6734d096` (was `cf75a135`; its
    message amended with --only, owner-approved, to name 394612c); reviewed (judge: landing
    conditions met) and re-reviewed (accepted). Details in "Stage C in
    progress" below.
  - Port check done (owner asked; wf_9e9fb92c-04f; saved as
    `ENTITY_CATALOG_CODE_REVIEW_C_portcheck.json`): accepted. The three
    commits are exactly the reviewed change ported onto HEAD; the only
    differences are the intended HEAD adaptations; no link-layer code, no
    compile risk found. Notes: rpc.py's (link layer's) field comment names
    "Semantic_Embedding's retrieval closure", which exists only once the link
    layer lands; MLML `cf75a135` also moves Isabelle_RPC across another
    session's `394612c` (unicode is_malformed, 10-27 23:39) without saying so
    in its message. Fixed: amended (message only) to `6734d096`.
  - Owner rulings (2026-10-28 ≈13:00): push every repository to origin;
    §8.5 for stage C = the real runs only (same three cases, ClaudeCode,
    the stage B scripts in the scratchpad's `stageB_measure/`); NO load
    simulation and NO re-count (owner agreed with my reasons: the fake
    Isabelle speaks only the old reply; the host is far from saturation; the
    count is agent behaviour, unchanged by C). Do it after the compaction.
    Compare per case AND per unfiltered theorem sub-query (≈14.4 MB each
    after B; expected ≈7 MB for the first per `by aoa`, ≈11 KB bitmap
    later), since how many the agent issues is random. The owner says
    Pure.thy has been restored, so retrieval scores should be normal again:
    verify (diff against the scratchpad's `vector_probe/Pure.pristine.thy`,
    and a retrieval golden or log showing scores other than 0.300) before
    comparing with the stage B run, which had all scores at 0.300. Then the LIVE-pass bug
    (`BUG_LIVE_PASS_INFRA_FILTER_CONTEXT.md`); its fix makes the §8.1
    baseline stale, which is now harmless (the driver is uncommitted).
  - Running: nothing. My REPL on 127.0.0.1:6666 (restarted 2026-10-28 18:23
    for the golden re-run) was stopped 2026-10-29 at the owner's order
    ("请关闭"); nothing listens on 6666 or 27182 since.
  - Done (2026-10-28, 18:25): the 23 retrieval goldens re-run with real
    scores, 18/23; see "Goldens on this machine" below.
  - Done: step 0 (baseline); stage B landed and accepted, including its code
    review fixes. The commits are listed below; pushed 2026-10-28.
  - Done (2026-10-27, 23:10 +08): §8.5 for stage B. §6 now holds the
    measured numbers (§6.1) and stage C's expectation (§6.2); §1's sub-query
    count is corrected. Both sweeps finished; nothing of this plan runs on
    cslh19 or on ports 6699/27184. Next: stage C, below.
  - §8.5 for stage B, as it was run (record):
    - Run the three PutnamBench cases under py-spy (main-thread CPU, bytes
      received, host peak RSS), the 20/40-load simulation, and a count of
      unfiltered sub-queries per case across drivers. Then replace §6 with the
      numbers.
    - On cslh19, work only under `/home/xero/tmp/aoa_sim/`. It holds `sim/`,
      `sampler.py`, `venv/`, `pyjit/` and an `Isabelle_RPC` copy from the §1
      measurements. Never touch `/home/xero/Current/MLML`.
    - Find out how the §1 measurements were run before rerunning them.
      Found (2026-10-27, 19:46 +08): the three real cases ran on THIS machine,
      not on cslh19, through `tools/aoa_putnam_eval` (REPL 6699, RPC host
      27184 under py-spy, driver ClaudeCode with its default model, 5.77 USD).
      Only the load simulation ran on cslh19. Record, scripts and summaries:
      `contrib/Theory-Agent-over-Trees/ai-artifacts/probes/cluster/`
      (`MEASUREMENTS.md`, `real_run/`, `simulation/`); raw data in the
      scratchpad of session a225873a (`aoa_python_load/run2_claudecode/`).
      The simulation models today's burst: 37–45 full theorem enumerations,
      each followed by one `command_at_position`; after stage B it needs a
      new burst model. Owner rulings (2026-10-27, 19:50 +08):
      - the real runs go on this machine, as in §1; only the simulation runs
        on cslh19 (§8.5 corrected);
      - driver ClaudeCode only, the same three cases;
      - post-B simulation model: a burst per `query` call is u full theorem
        enumerations (the unfiltered sub-queries) plus r small callbacks (one
        `command_at_position` per rendered result). u and r come from the logs,
        in two profiles: ClaudeCode (u = 0) and Codex (u ≈ 1.1 per call);
        r ≈ 14–19. Think time and N = 1/5/10/20/30/40 unchanged; CPU
        calibrated with §1's factor.
    - Running (started 2026-10-27, 19:59 +08 and 20:02 +08):
      - Real run: scripts copied from `real_run/` into the scratchpad's
        `stageB_measure/` (paths changed only); output in
        `stageB_measure/run_claudecode/`. The REPL start rebuilt the
        MathBench_Prover heap (≈5 min). Teardown when the evaluation exits:
        `touch run_claudecode/sampler.stop`, `tools/aoa_putnam_eval/stop_servers.sh`,
        then kill orphans whose environ has `RPC_Host=127.0.0.1:27184`; then
        `analyze.py`, `profile_summary.py`, `count_messages.py`,
        `tool_windows.py` as in §1.
      - Simulation, Codex profile: cslh19 `/home/xero/tmp/aoa_sim/sim_postB/`
        (a copy of `sim/` with MODE=postB; `analyze.py` also reports the
        small calls), host package = Isabelle_RPC `b633c2a`'s
        `Isabelle_RPC_Host` in `aoa_sim/pkg_stageB/` via PYTHONPATH, the old
        venv and `sim/payload.bin`. Output `sim_postB/sweep_codex/`. Profile
        `profile_codex_gpt6sol.json`: the 150 query calls of CodexAPI
        gpt6sol-high, mean u 1.07, mean r 13.7. CPU factor 2.19 = the §1
        sweep's 41 enumerations per burst / the 18.73 real enumerations per
        query call (281 rendered + 0 unfiltered over 15 calls).
      - Next: the ClaudeCode-profile sweep (`sweep_claudecode/`), with a
        profile from the §1 run's and this run's query calls.
    - Real run done (2026-10-27, 19:59–20:15 +08; all three proved, 3.92
      USD; torn down, the Naproche orphan killed). Measured with the §1
      scripts; `stageB_measure/query_windows.py` reproduces §1's 4045 / 4620
      MB and 132.7 s on §1's data.

      | | §1 (before stage B) | after stage B |
      |---|---|---|
      | main-thread CPU per case (b2, a5, b1) | 41, 46, 45 s | 4.5, 5.4, 3.3 s |
      | main thread, mean over the cases | 8.1% | 1.38% |
      | main thread, 1 s peak | 78% | 87% (one second in b2), else ≤ 39% |
      | bytes from Isabelle, whole run | 4620 MB | 87 MB |
      | of which in `query` calls | 4045 MB in 15 calls | 87 MB in 12 calls |
      | heaviest `query` call, main thread | 13–22 s | 1.8 s |
      | host peak RSS | 1.8 GB | 1.66 GB |
      | unfiltered theorem sub-queries | 0 of 38 | 6 of 35 |

      - All 87 MB are the 6 unfiltered sub-queries: each is one THEOREM
        enumeration of 86,664 entries (after `theories_not_include`), about
        14.4 MB. That is what stage C removes.
      - Peak RSS: in both runs the host jumps by ≈ 1.4 GB within 5 s of the
        first semantic lookup (vector store loading), so stage B barely moves
        it.
      - py-spy main thread now: `_call_thm` 1.0 s, `asyncio.streams.read`
        1.0 s, `get_user_only` 0.7 s, `ssl.create_default_context` 0.7 s.
      - Profile for the ClaudeCode sweep: `profile_claudecode.json`, the 27
        query calls of both runs, mean u 0.22, mean r 17.4.
    - Codex-profile sweep done (20:02–21:33 +08), results in
      `sim_postB/sweep_codex/sweep_all.json` on cslh19. Main thread; one
      `query` call (burst) p50 / p95; event-loop lag p95; host RSS max. In
      brackets: §1's sweep, before stage B.

      | N | main thread | burst p50 / p95 | lag p95 | RSS max |
      |---|---|---|---|---|
      | 1 | 0.8% (4.6%) | 0.4 / 1.6 s (10.4 / 11.0 s) | 1 ms (1 ms) | 117 MB (124 MB) |
      | 5 | 2.7% (25.6%) | 0.5 / 1.2 s (8.6 / 10.4 s) | 1 ms (59 ms) | 124 MB (207 MB) |
      | 10 | 4.0% (52.3%) | 0.4 / 1.1 s (9.6 / 21.1 s) | 1 ms (73 ms) | 163 MB (331 MB) |
      | 20 | 7.1% (99.2%) | 0.4 / 1.1 s (102 / 122 s) | 1 ms (386 ms) | 160 MB (916 MB) |
      | 30 | 11.0% (99.2%) | 0.4 / 1.3 s (191 / 219 s) | 3 ms (610 ms) | 268 MB (1460 MB) |
      | 40 | 14.6% (99.1%) | 0.4 / 1.4 s (261 / 294 s) | 38 ms (606 ms) | 339 MB (1725 MB) |

      No queueing up to 40 (burst latency as at N = 1); ≈ 0.37% of the main
      thread per run, so saturation near 270 runs by linear extrapolation.
      The simulated host has no vector store, so its RSS is not the real
      host's.
    - ClaudeCode-profile sweep done (21:33–23:04 +08), results in
      `sim_postB/sweep_claudecode/sweep_all.json`; numbers in §6.1. The owner
      had been offered cancelling it and did not answer, so it ran as
      approved.
    - The unfiltered count is done, from existing logs
      (`stageB_measure/count_subqueries.py` and `subquery_counts.json` in the
      scratchpad). Unfiltered: not `exact_name`/`exact_term`, and none of
      term_patterns, type_patterns, theories_include, name_contains,
      target_type. An `exact_term` sub-query enumerates nothing, so §1's
      "37 of 38" is really 35 filtered + 3 exact + 0 unfiltered.

      "lemma" counts the unfiltered sub-queries that ask for theorems (the
      ≈20 MB kind); "experience" ones enumerate no entity kind.

      | driver, log set | cases (with queries) | query calls | sub-queries | unfiltered (lemma) | cases with ≥1 | max per case |
      |---|---|---|---|---|---|---|
      | ClaudeCode, §1 run (10-24) | 3 (3) | 15 | 38 | 0 (0) | 0 | 0 |
      | Claude-API, miniF2F (09-24) | 73 (35) | 93 | 243 | 43 (43) | 10 | 21 |
      | CodexAPI gpt6sol-high, miniF2F (09-25) | 61 (39) | 150 | 282 | 178 (160) | 38 | 18 |
      | CodexAPI gpt6luna-xhigh, miniF2F | 5 (5) | 62 | 123 | 2 (0, experience) | 2 | 1 |
      | CodexAPI gpt5-6sol-high, miniF2F | 5 (1) | 1 | 3 | 1 (0, experience) | 1 | 1 |
      | CodexAPI gpt5-6luna-xhigh, miniF2F | 3 (3) | 16 | 38 | 3 (0, experience) | 2 | 2 |
      | DeepSeek.V4-pro, PutnamBench (06-17..21, older prompt) | 19 (18) | 1388 | 2272 | 1058 (980) | 18 | 238 |
      | PlainAgent, miniF2F (09-24) | 73 (24) | 74 | 189 | 16 (14) | 8 | 4 |
  - After that: stage C. It needs the link layer's uncommitted
    `request_state` (rpc.py). Owner rulings (2026-10-27, 20:25 +08):
    - Stage C's commit carries the link layer's `request_state` field and its
      reset at request start: rpc.py's two hunks and rpc.pyi's
      `request_state: dict[str, Any]` line (checked: that is all the link
      layer changed in those two files). The commit message says that part is the link-layer session's
      work, and that session is told before the commit.
    - Stage C starts only after the simulation sweeps finish and §6 holds the
      measured numbers, so the shared tree's ML stays unchanged meanwhile.
    Then follow §9 stage C.
  - Stage C in progress (started 2026-10-27, 23:10 +08), in the working tree:
    - Pre-C copies of every edited file:
      `/tmp/claude-1002/-home-qiyuan-Current-MLML/1595227b-511f-4ae1-9cd4-1d599bbc8344/scratchpad/stageC_pre/`
      (the diff from them is stage C; the link layer's hunks are older).
    - Written: `Tools/entity_catalog.ML` (new; needs the owner's approval
      at commit) and its `ML_file`; `context.ML` (tenth field, one reply,
      catalogs in the seven makers, positions out of ns_filter, the LIVE pass
      and the rule sources, `entry_def_pos` private, `cached_thm_entry`
      without `pos`); `rpc.py` (`finally` reset; comment); `context.py`
      (`_Mirror`, `_enumerate`, the `_CALLBACKS` table, `entities_of` →
      `(entries, warnings)`); `semantic_store.ML` (no positions in the
      caches, `make_entity_callbacks` with the keep predicate returning a
      list, `query_knn` builds per call); `semantics.py` (three sites);
      `test_resolve_notation_callback.py`; `agent_server.ML`,
      `plain_agent_app.ML` (`K false`); `model.py` (pattern-only path);
      the two fakes (`tests/test_link_layer.py`,
      `test_link_display_owner.py`, both the link layer's; tell that session);
      skill `modules.md` (also: the load order gains entity_catalog.ML, and
      the "≥ half docstring is stale" sentence goes with that docstring);
      `TACTIC_DESIGN.md` second note.
    - Passing so far: `tests/test_link_layer.py` (22),
      `test_link_display_owner.py` + `test_definition_position.py` (10),
      `test_def_pos.py`.
    - Compiled (REPL on 6666 restarted 23:3x; it reloads the edited
      theories from source when a theory imports them; Minilang_AoA loads).
    - (Superseded by review item R1, 2026-10-28: the differential moved to
      `ENTITY_CATALOG_BASELINE/run_differential.py`; this record is the first
      run.) §8.1 passes: `Test/test_resolve_notation_e2e.py` now also evaluates
      the step 0 theory (same name and entities, today's
      `make_entity_callbacks (K true)`) and the relay
      `test.entity_catalog_differential` (in
      `test_resolve_notation_callback.py`): all 45 sets equal
      `baseline.json`; the dropped reply is re-delivered; an index list and a
      bitmap (length not a multiple of 8, bits not a prefix) both occur.
      Test 5 now builds its constants callback per call_command. Needs an
      external host on 27182 started after the edits (mine was stopped
      before the goldens).
    - §8.2 passes: `test/Test_Entity_Catalog.thy` (new; ROOT lists it;
      needs approval at commit), run through the REPL. Four in-memory
      mutants (structure shadowing) each fail it: LSB-first bitmap, sorted
      index list, no protocol error, intern ignoring is_local.
    - §8.3 passes: `test_entity_mirror.py` (new; needs approval at commit):
      decoder, both encodings, one transfer for two concurrent calls, two
      gathered calls leave mirror = catalog, re-delivery, both protocol
      errors and an unchanged mirror after one. Four in-memory mutants each
      fail it (no lock, LSB-first, no gap check, no bitmap length check).
      `import Isabelle_RPC_Host` works in a venv holding only the five
      declared dependencies (`python -I`; numpy not importable).
    - §8.1 mutation check: a host whose mirror prepends instead of appending
      passes Tests 1–5 and fails the differential (many sets differ). (An
      LSB-first decoder already fails Test 5.)
    - Goldens (§8.4), 23 retrieval goldens: the same 16 pass. Of the 7 that
      already failed before stage B (remote_error), 4 give outputs identical
      to stage B's; 3 move, all by D18's tie order (every score is 0.300,
      the Pure.thy hash breakage): QueryNullFields and QueryScalarStringField
      render fewer entries, because a sibling sub-query's results, answered
      first, now lead the unfiltered sub-query's bitmap order, make its top
      k and are deduplicated against the sibling; QuerySearchSummary's
      no-filter sub-query now returns the 5 shown earlier. Not re-recorded:
      they fail for another reason.
    - PlainAgent: Test_Simple passes; Test_sqrt2's interaction is identical
      to stage B's run (the same scripted END failure). plain_agent_app.ML
      compiles.
    - Running processes (2026-10-27 23:50): only my REPL on 6666; no other
      REPL or RPC host on this machine.
    - Owner rulings (2026-10-27, ≈23:55 +08): new files approved for the
      commit: `Tools/entity_catalog.ML`, `test/Test_Entity_Catalog.thy`.
      `test_entity_mirror.py` is NOT approved: it stays uncommitted in the
      working tree. Code review before landing, with stage B's process
      (adversarial workflow: critics, one fresh defender per concern, judge;
      Opus, xhigh; English; report concerns and fix plan in Chinese; no
      code change before the owner agrees). The owner confirmed the object:
      the stage C code with the plan clauses it implements; the judge rules
      whether the landing conditions are met.
    - Review running: workflow `wf_89c937d1-918` (started ≈23:58 +08) over
      `stageC_review/stageC.diff` in the scratchpad (the exact stage C
      change: pre-C copies vs now, plus ROOT and the three new files). Save
      the result as `ENTITY_CATALOG_CODE_REVIEW_C_judge.json` beside this
      file (never committed).
    - Review done (wf_89c937d1-918; 8 raw, 5 kept, 5 dropped; saved as
      `ENTITY_CATALOG_CODE_REVIEW_C_judge.json`). Judge: landing conditions
      met; no correctness bug, no dirty hack; a short re-review of the delta
      after the fixes.
      - R1 (valid, owner): the §8.1 differential sits in the committed e2e
        test but reads the git-ignored baseline, which the LIVE-pass fix and
        any new lemma will make stale. Proposed relaxation of §8.1: move it to
        an uncommitted driver beside the baseline (run_differential.py, its
        own host, a frozen copy of the theory); the committed test keeps
        Test 5's per-call_command callback. Cost: no committed check then
        catches a mirror that prepends.
      - R2 (partially valid, no code change): after landing, the lock and
        both Python protocol checks have no direct committed test (only
        test_entity_mirror.py, not approved); indirect coverage by
        QueryNullFields/QueryScalarStringField once goldens pass again. The
        Run_Python-in-Test_Entity_Catalog proposal is rejected by the judge.
      - R3 (partially valid, owner, optional): one private helper
        `mk_enumeration_callback` owning catalog creation, the two schemas
        and the answer call; bodies keep their tuple10 pattern with `_` for
        synced_length. Changes §4.2 and D14 wording.
      - R4 (valid, author): put the §5.5 finally on the existing
        per-iteration try in rpc.py; undo the re-indent.
      - R5 (partially valid, author): semantic_store.ML "name/position" →
        "name"; reword make_entity_callbacks' signature comment so "the
        retrieval closure" names the whole list. Item 3 (old dead debug
        block in context.ML) rejected: outside the diff.
      - Owner rulings (2026-10-28): R1 relax §8.1 (approved); R3 adopt
        `mk_enumeration_callback` (approved; §4.2 and D14 reworded); R4 and
        R5 items 1-2 as the judge planned (approved). After the fixes: one
        short re-review of the delta (the judge's scope (a)-(d)).
      - Fixes done (2026-10-28, ≈10:00 +08): R4 (rpc.py: dispatch block
        byte-identical to pre-C, finally on the per-iteration try); R5 (two
        comments); R3 (`mk_enumeration_callback`; bodies back to pre-C
        except `_` for synced_length and the constants body's `entries`
        name); R1 (the committed e2e test and relay are pre-C plus Test 5 and
        the 2-tuple return only; `ENTITY_CATALOG_BASELINE/run_differential.py`
        and `Entity_Catalog_Differential.thy` (uncommitted) hold §8.1;
        `run_baseline.py` gained `serve` and `run_theory(theory)` for reuse).
        Plan text: D14, §4.2, §8.1, §9 stage C reworded by hand.
        The pre-C snapshot's semantic_store.ML got the link layer's pack_link
        line, so the stage C diff stays exact.
      - Re-run after the fixes, REPL restarted: §8.1 driver 45/45 equal, no
        failure (the relay checks re-delivery and both encodings; the theory
        raises on any failure); §8.2
        OK; e2e Tests 1–5 pass (fresh external host); test_entity_mirror,
        test_def_pos, test_attached_host (9), test_link_layer (23),
        AoA link-display + definition-position (10) pass; PlainAgent
        Test_Simple success.
      - The link layer also edited `tests/test_link_layer.py` after the
        snapshot (D65 rewrites); the snapshot was rebased onto it, so the
        diff holds only the FakeConnection change. Full diff after the fixes:
        `stageC_review/stageC_fixed.diff` (22 files, incl. the three
        uncommitted driver files under ENTITY_CATALOG_BASELINE/).
      - Re-review done (wf_f5d4327f-010; saved as
        `ENTITY_CATALOG_CODE_REVIEW_C_rereview.json`): accepted; two plan
        sentences fixed by hand (§8.1 bullet 1; the status re-run record).
      - Landing (2026-10-28): HEAD-based patches in the scratchpad's
        `stageC_land/` (`<repo>.stageC.patch`; for context.ML,
        semantic_store.ML, semantics.py, agent_server.ML, model.py the hunks
        were ported onto HEAD; HEAD+C plus the link layer's own patch
        reproduces the working tree except where its hunks collide with
        stage C's, all checked by eye). At HEAD, make_entity_callbacks
        returns the eleven callbacks (no links) and its comment omits links.
        Exported (git archive HEAD + git apply in `stageC_land/export/`;
        a temporary-index approach was declined by the owner): Python tests
        pass there (def_pos, mirror, definition_position 5); ML checked by
        name (no reader of removed names). The link-layer session was told
        before the commit.
      - LANDED (2026-10-28 ≈12:15 +08), staged with git apply --cached, each
        staged file checked equal to the tested export: Isabelle_RPC
        `0b239b2`, Semantic_Embedding `b7e0133`, Isa-Mini `e2d732f`, MLML
        bump `cf75a135`, amended to `6734d096` (only the three submodule paths; the other staged
        entries, .gitmodules and contrib/isabelle-base-features, were left
        staged). Not pushed. Uncommitted by ruling: test_entity_mirror.py,
        PlainAgent, the two link-layer fakes, the §8.1 driver files.
        Running after landing: only my REPL on 6666, which already holds the
        landed code (the working tree did not change); no other REPL or
        fixed-address RPC host.
    - The link-layer session (2026-10-28 ≈00:00) changes one line of its own
      `pack_link` in `semantic_store.ML` (rewrites: packTuple3 → packPair).
      Before computing any stage C diff again, make the same edit in
      `stageC_pre/Semantic_Embedding/Tools/semantic_store.ML`, so the diff
      stays exactly stage C. That session has been told what stage C does to
      its files (the list return, entities_of's shape, its two fakes, the
      request_state commit); tell it again right before the commit.
    - Then: land per §7
      (HEAD-based patches: the link layer's uncommitted hunks overlap in
      `context.ML`, `semantic_store.ML`, `rpc.py`; tell that session about
      its two fakes); §8.5.
  - For after this plan: the LIVE-pass bug
    (`BUG_LIVE_PASS_INFRA_FILTER_CONTEXT.md`); fixed by the link-layer
    session, Semantic_Embedding `6d0ad1b` (2026-11-01).
  - Running: nothing (my REPL on 6666 stopped 2026-10-29, owner's order).
  - Scratch work lives in the session scratchpad
    `/tmp/claude-1002/-home-qiyuan-Current-MLML/1595227b-511f-4ae1-9cd4-1d599bbc8344/scratchpad/`:
    `stageA_golden/` (golden runs, REPL logs), `stageB_land/` and
    `stageB_fix/` (HEAD-based patches), `stageB_repl/` (probes),
    `stageB_mutation/` (mutation plugins), `vector_probe/` (the theory-hash
    investigation), `blake2b_bench/` (sort timings).
- Stage B landed (2026-10-27): Isabelle_RPC `fabbefc`, Semantic_Embedding
  `caa179f`, Isa-Mini `fc916da`, MLML bump `ae04528b` (not pushed).
  - Code review of stage B, at the owner's request: workflow run
    `wf_749c941e-55c`. Two critic lenses, merge, one fresh defender per
    concern, judge; Opus, xhigh. The report will be saved as
    `ENTITY_CATALOG_CODE_REVIEW_B_judge.json` beside this file. No code change
    before the owner agrees. §8.5 (cslh19) waits for it.
  - The review is done. The judge says acceptance is not yet met, because
    of R1. 8 raw concerns, 5 kept, 3 dropped. The fixes wait for the owner's
    agreement.
    - R1 (valid, author): in `agent_server.ML`'s `reply`, the resolver call
      sits outside the per-item `try`. A non-ERROR exception from key hashing
      (Cannot_Hash, Read_Timeout, Remote_Calling_Failure) fails the whole
      batch. Fix: `Option.join (try (Context_Callbacks.entry_of_name gctx) e)`.
    - R2 (invalid): the `(uk, position)` shape is §5.3/P2 as ruled. No change.
    - R3 (partly valid, author): four comments. The resolver signature's "no
      dynamic-fact test"; the "(uk, pos) whenever displayed" claims in
      model.py and agent_server.ML; "entity callbacks" in
      Interpretation_Driver_Config_Test; the plural "by-name callbacks" in
      semantic_store.ML.
    - R4 (valid, author): the e2e test needs a `(file, offset)` ctxt row
      through interpret_file's list, and an iff check for the fixed-variable
      exemption.
    - R5 (valid, owner): in modules.md, move the by-name paragraph after the
      enumeration material and state its argument. Replace registry.md's stale
      wiring sentence; the owner approves the wording.
    The judge forwards no relaxation proposal, and rejected the critics' two.
    After the fixes, one narrow re-review of the fix diffs is needed, with no
    debate.
  - Fixes for R1, R3, R4 and R5 are in the working tree (owner: no comment
    needed, process approved). The R5 registry.md sentence is as the judge
    worded it; the owner was told and may veto.
    - After a REPL restart, Minilang_AoA compiles.
    - The e2e test passes with 24 names and 4 definitions.
    - Interpretation_Driver_Config_Test passes, and 10 unit tests pass.
    - A probe shows that a static unpacker cannot decode the new
      `(file, offset)` row ("Failed to unpack callback argument").
    - HEAD-based fix patches are in the scratchpad's `stageB_fix/`.
    - Narrow re-review (`wf_c81b7156-9b3`): accepted, with no new concern.
      Report: `ENTITY_CATALOG_CODE_REVIEW_B_rereview.json`.
    - Committed with only these hunks staged: Isabelle_RPC `b633c2a`,
      Semantic_Embedding `620d8b4`, Isa-Mini `39161b6`, MLML bump `fae22eda`
      (not pushed). Stage B is accepted.
    - Next: §8.5 on cslh19.
  - Only stage B's changes were staged. They were applied to each file's HEAD
    version and written with `git apply --cached`; the link layer's
    uncommitted hunks stay in the working tree.
  - The staged state was checked from an index export: its Python passed the
    decoder test, 128 AoA unit tests and the e2e test (against the REPL's
    working-tree ML).
  - Its ML was checked by name: it uses no link-layer identifier, and every
    caller matches the new signatures.
  - The staged ML was not compiled on its own. Isabelle_RPC and
    Semantic_Embedding are registered components, so an exported copy clashes
    by session name.
  - PlainAgent's edit lives in the working tree only.
  - The untracked `scratch_se_timing/SE_Timing_Thy.thy` (not this plan's)
    still calls `entry_def_pos` with an entry.
  Every §9 stage B bullet is done. Two changes go beyond the bullets:
  - `interpret_file_callbacks` keeps the link layer's `links` callback, now
    built directly with `make_links_callback (Context.proof_of context)`.
  - `test_link_display_owner.py`'s fakes return the new triple. Its session
    was told.
  Tests:
  - New files: `Semantic_Embedding/Test/test_entries_of_names_e2e.py` (the
    resolver differential over 24 names, and `_definition_of_name` through
    `interpret_file_callbacks` for a constant, a theorem and a collection),
    `Isabelle_RPC/test_def_pos.py` (the decoder), and
    `Isa-Mini/IsaMini/AoA/test_definition_position.py` (the Useful-lemmas
    path; the METHOD, THEOREM_COLLECTION and no-position skips). All pass.
    Each was mutation-checked in memory; every mutant fails.
  - The list check in `Interpretation_Driver_Config_Test.thy` passes.
  - Regressions:
    - Semantic_Embedding's three e2e tests and `tests/` pass.
    - Isa-Mini's AoA unit tests: 146 pass. 44 fail, all with "async def
      functions are not natively supported", because the venv lacks
      pytest-asyncio.
    - PlainAgent: `Test_Simple` passes. `Test_sqrt2`'s script fails at an
      `END` that cannot prove `∃m n. ¦sqrt 2¦ = real m / real n ∧ coprime m n`;
      that run made no query. It was not run before stage B.
    - The 23 retrieval goldens: the 16 that passed before still pass. The 7
      that failed before give outputs byte-identical to before stage B.
  - Running processes (2026-10-27 16:30): no foreign process mixes old and
    new code. The link-layer session's REPL (6731) and its attached host both
    started after the edits.
- Goldens on this machine: in the 23 retrieval goldens of `test_AoA.py`, every
  candidate scored the default 0.300. Cause (verified, 2026-10-27): the
  light_locale patch changed `Pure.thy`, so every theory hash changed.
  Resolved 2026-10-28: Pure.thy restored (daily `7eb9137`), keys match the DB
  again (§6.2).
  - Re-run with real scores (2026-10-28 18:24, owner's go; landed code plus
    the link layer's working tree, as before): 18/23 pass. The 16 still
    pass; AbbrevQuery and Query_BundleBareName now pass too (they failed only
    from the 0.300 scores).
  - The other 5 (QueryNullFields, QueryScalarStringField, QuerySearchSummary,
    SemanticKNN_induction_rule, SemanticKNN_patterns) differ from goldens
    recorded 2026-08-24, but not by tie order:
    - Their candidate sets differ. QuerySearchSummary: 132 entities match
      the filters, now 169; 976, now 1209. The same counts appear in every
      run since before stage B, at 0.300 too (counts do not depend on scores).
      The new candidates (`idom.square_eq_iff`,
      `linordered_ring.zero_le_square`, `equal.equal_eq`, `Rep_Nat_induct`,
      `Abs_Nat_induct`) are already in step 0's baseline.
    - Scores differ: `powr_def` 0.674, now 0.681; `log` 0.768, now 0.769.
      Cause not verified (the stored vectors, or the query's vector from the
      embedding API).
    - The run used the working tree, which also holds other sessions'
      uncommitted changes (the link layer in `retrieval.py`, `model.py`,
      `semantic_store.ML`, `context.ML`). Whether HEAD alone gives the same
      output was not checked.
    - So they went stale before this plan; stage C changes neither sets
      (§8.1) nor scores. Re-recording them is the owner's decision (none
      re-recorded).
    - Root cause (diagnosed 2026-10-28, owner asked): the goldens are
      `da03c7d` (2026-08-24 20:05), the infra filter plan's re-baseline to
      drifted scores. Semantic_Embedding `a5fe5dc` (08-25 14:23, infra filter
      step 2, owner rulings of 08-25) then deleted `abs_rep_name`, narrowed
      `class_infix` to `*_axioms`, and marked 40 theories, among them
      `HOL.SMT` and `HOL.Meson`. Probes (the 08-24 `infra_filter.ML`
      loaded renamed beside today's, same context; scratchpad
      `stageC_golden/diag/`):
      - With the old filter, QuerySearchSummary's six counts come out 132,
        976, 746, 549, 416, 467 (golden: 132, 976, 746, 549, 416, 460);
        with today's, 169, 1209, 966, 669, 419, 612, today's output.
      - Every added candidate is infra for the old filter by the cascade of
        `class.idom`, `class.linordered_ring`, `class.equal`, `class.ln`
        (`class_infix`) or `Rep_Nat`, `Abs_Nat`, `Abs_Integ`
        (`abs_rep_name`), and kept today. Every removed one is either kept
        by both (pushed out of the top k) or in a marked theory today
        (`Meson.iff_to_disjD`, `SMT.verit_connective_def`, `SMT.int_plus`,
        `SMT.nat_plus_as_int`).
      - The score shifts (`powr_def` +0.007, three constants +0.001; the
        other scores identical) and QueryNullFields' reorders (it prints no
        scores) are not explained; the records carry no `interpreted_at`.
    - Re-recorded (owner-approved 2026-10-28, after the diagnosis): the 5
      goldens from the working tree's output (two runs byte-identical; the
      old goldens kept in the scratchpad's `stageC_golden/diag/golden_before/`).
      All 23 retrieval goldens then pass. Committed (owner-approved), not
      pushed: Isa-Mini `19843e1`, MLML `da4778f9`.
- Landing: the files this plan edits hold the link layer of the session
  "Isabelle jEdit 语义搜索面板" (`Semantic_Embedding/ai-artifacts/LINK_LAYER_PLAN.md`):
  `Universal_Key.ML`, `context.ML`, `rpc.py`, `semantics.py`,
  `semantic_store.ML`, `model.py`, `retrieval.py`, `agent_server.ML`. That
  session commits it only at its §8 step 7, when the owner asks, so days from
  now. Its code imports the untracked `links.py`; committing a file whole would
  break HEAD. Owner ruling (2026-10-27), overriding Isa-Mini's AoA CLAUDE.md
  "never git add" for this plan: a stage lands by staging only this plan's
  changes. The change is applied to each file's HEAD version, and the result
  goes in with `git apply --cached`; the working tree is not touched. Before
  committing, the staged state, HEAD plus the patches, is exported to a
  scratch directory and tested there. Stage B does not depend on the link
  layer: the resolver uses `entry_of_fact` and `entry_def_pos`, both at HEAD.
  Stage C does depend on it: the mirror needs the link layer's uncommitted
  `request_state` in `rpc.py`.
- Step 0 is done (2026-10-27), in `ENTITY_CATALOG_BASELINE/` beside this file
  (uncommitted).
  - `corpus.json` holds 45 items and `Entity_Catalog_Baseline.thy` the theory.
    The theory declares entities of every kind, builds the callbacks once with
    `Semantic_Store.make_entity_callbacks` and a string-keyed unpacker, then
    runs the corpus in one relay request (`run_baseline.py`).
  - `baseline.json` holds each item's set and the heads of Isabelle_RPC,
    Semantic_Embedding and the distribution.
  - 43 items were identical across two runs; the remaining two are the ones
    that the third run changed.
  - Finding: no item has `is_local = true`. Today `make_entity_callbacks`
    yields none. A fact present at build time enters the cache with `false`. A
    fact noted later is dropped by the infra filter, which is built from the
    build context: `infra_thm_rule` answers "hidden" there, and keeps the fact
    when built from the fact's own context (probe, 2026-10-27, a theorem). The
    rule callbacks pass their live facts through the same filter (code
    reading, not probed). So §8.1's proof-local contexts record that their
    facts are absent; `is_local = true` is not exercised by §8.1, and §8.2
    covers it instead (owner, 2026-10-27). The owner rules this a bug, recorded
    in `BUG_LIVE_PASS_INFRA_FILTER_CONTEXT.md` beside this file and fixed after
    this plan (§10).
  - If the distribution's theories change before stage C, re-record the
    baseline from a `git archive` of the pre-stage-B commits.
Round 4 (review of rev 5; two critic lenses, merge, one fresh defender per
concern, judge; Opus, xhigh) is done: ready to implement; three minor
self-decidable gaps S1–S3, applied (§9 stage B Semantic_Embedding bullet; §7
landing rule and §9 stage C docs bullet; §5.2 scan), no re-review needed; no
owner item, no relaxation proposal. Report:
`ENTITY_CATALOG_REVIEW_4_judge.json` beside this file. During the review the
author's read-through also fixed §4.2 (the catalog is created in the seven
`mk_callback` functions; `make_rules_callback` creates none), §4.4(a)
(`entry_def_pos (#pos e)`), §8.3's heading and §9's stage A landing step.
Scope: Isabelle_RPC (`Tools/entity_catalog.ML` new, `Tools/context.ML`,
`Tools/Universal_Key.ML` (the six name-kind `key_of_*` also return the entry's
position), `Isabelle_RPC_Host/context.py`, `position.py`, `rpc.py`, the
isabelle-rpc skill references), Semantic_Embedding (`Tools/semantic_store.ML`,
`Isabelle_Semantic_Embedding/semantics.py`), Isa-Mini (`Agent/agent_server.ML`,
`IsaMini/AoA/model.py`, `retrieval.py`, `docs/TACTIC_DESIGN.md`, and the
untracked `PlainAgent/`). TAT is not touched.

## 0. Glossary (fixed terms; use these and nothing else)

- **entity enumeration callbacks**: the eleven callbacks `Context.theorems`,
  `Context.constants`, `Context.types`, `Context.classes`, `Context.locales`,
  `Context.theorem_collection`, `Context.methods`, `Context.introduction_rules`,
  `Context.elimination_rules`, `Context.induction_rules`,
  `Context.case_split_rules` (`Tools/context.ML`), reached from Python through
  `Isabelle_RPC_Host.context.entities_of`. Their reply is a **set**; the order of
  the entries carries no meaning (D18).
- **kind**: one of the eleven entity kinds (the kind tag is byte 16 of a
  universal key).
- **catalog** (目录): per entity enumeration callback, the append-only
  numbering of the **catalog entries** that its replies have returned so far.
  Its maker creates it empty; it lives as long as the callback, which is built
  for one `call_command` (D1). ML assigns the indices; Python holds a
  **mirror** (§5.1).
- **catalog entry**: `(uk, name, is_local)`; on the wire a tuple4 with its
  `index`. Positions are not part of it (D5).
- **index set encoding**: the first field of every enumeration reply: the
  indices of this call's results, as either a **bitmap** (msgpack `bin`,
  ⌈len/8⌉ bytes over the catalog `[0, len)`, MSB-first within a byte) or an
  **index list** (msgpack `array` of ints). ML sends whichever is smaller.
  Example: catalog length 10, indices {0..7, 9}: the bitmap bytes are `FF 40`
  (LSB-first would give `FF 02`).
- **synced_length**: request field `int`: the caller's mirror holds catalog
  entries `[0, synced_length)` of this kind.
- **resolver**: `entry_of_name` (§4.4), the one ML function that turns
  `(kind, name)` into `(uk, name, pos, is_local)` in a context, by name only and
  without touching any catalog. `pos : Context_Callbacks.def_pos = string * int
  * int` = (standard file path, line, symbol offset); an empty file or a zero
  offset means unknown (the resolver writes `("", 0, 0)`).
- **def_pos decoder**: `IsabellePosition.from_def_pos` (§5.3), the one Python
  function that turns a def_pos triple into `IsabellePosition | None`.

## 1. Problem, measured

Local profile of three PutnamBench AoA runs (ClaudeCode driver, py-spy 100 Hz,
RPC host main thread):

| where the main thread's time went | share |
|---|---|
| enumeration chain (`_call_thm` loop, asyncio stream reads, msgpack) | 89% |
| of which `_get_definition_with_pos` (one full enumeration per rendered result) | 99% |
| of which the search's own candidate enumeration | 1% |
| everything else (event loop, TLS, jsonschema, YAML logging, embedding glue) | 11% |

A full `Context.theorems` reply is ~111k entries × ~180 B ≈ 20 MB, of which
positions (an absolute file path per entry) are ~53%. Of the 38 measured
sub-queries, 35 are filtered (their enumeration is small), 3 are exact lookups
(no enumeration) and none is unfiltered (corrected 2026-10-27: the one first
counted unfiltered was an `exact_term` query, which enumerates nothing); but every
rendered result calls `_get_definition_with_pos`, which enumerates the whole
kind unfiltered to find one entry's position. 15 `query` calls → 38 sub-queries
→ 281 rendered results → ≈ 4 GB received; 14–22 s main-thread CPU per heavy call.

Two metrics matter, in this order:
1. **Bytes on the wire.** In the cluster the RPC host may sit on another machine
   with unknown bandwidth; a 20 MB reply per unfiltered sub-query is not
   acceptable there even if the local CPU could absorb it. This is why the
   catalog is built now and not deferred to a measurement.
2. **Host main-thread CPU.** Per-byte costs (local, 112k entries, 20 MB):
   pure-Python conversion loop 0.06 s without GC / 0.17 s with, msgpack C decode
   0.05 s, asyncio small-chunk reads ≈ 25% of the chain. Python 3.14's JIT
   changes none of this (cslh19: 0% on the loop).

History: positions were added to the enumeration reply (`0f852a7`) behind a
per-connection cache; AoA's `ctxt` argument bypassed that cache from `70d2cf0`
(2026-06-14); the cache was retired 2026-08-26 (INFRA_FILTER_REWORK_PLAN §18)
without a single-entity position lookup replacing it.

## 2. Decisions (owner rulings, 2026-10-25/26/27; final)

- D1 No cross-request catalog reuse. A catalog lives as long as its callback,
  which is built for one `call_command` (O1). The per-`by aoa` first unfiltered
  transfer (§6) is the remaining bandwidth item; reuse across `by aoa` on one
  connection is recorded in §10 as the next lever.
- D2 All kinds uniformly; proof-local facts are ordinary results with
  `is_local = true`, nothing else is special about them.
- D3 Only enumeration replies append to a catalog. Single-entity resolutions
  (§3.2, §3.3) never touch a catalog.
- D4 One reply shape for the eleven callbacks and one mode:
  `(index set encoding, catalog entries with index ≥ synced_length, warnings)`.
  Every caller keeps a catalog; there is no catalog-less mode (C13). Each
  delivered entry carries its index (C7 rejected: cheap, and the reply stays
  self-describing should RPC dispatch become parallel). ML chooses bitmap or
  index list by byte size.
- D5 Positions come only from `IsaMini.retrieve_entity` (§3.2) and
  `Context.entries_of_names` (§3.3), both through the resolver; never from an
  enumeration reply, never from a catalog. A resolver `NONE` means no
  definition source is rendered (today's outcome).
- D6 The same uk may occur several times in a catalog (another name, another
  `is_local`); the intern key is `(uk, name, is_local)`. Per-call dedup by uk
  stays where it is today (`key_seen` in the callback bodies).
- D7 `IsaMini.retrieve_entity` stays in Isa-Mini. Its body becomes one shared
  function in `agent_server.ML` (PlainAgent calls it instead of its copy) and
  calls the resolver to add `(uk, pos)` to each reply item. The uk costs no
  extra computation (the resolver builds it anyway) and is kept for possible
  later use (C14 rejected).
- D8 Hiding stays the post-ranking `??.` drop; `drop_declared`, the infra
  filters and `exclude` stay inside the callback bodies, unchanged.
- D9 (moot: order is meaningless, D18).
- D10 Python decodes both encodings in pure Python (no numpy in
  Isabelle_RPC_Host).
- D11 Catalog per kind, eleven index spaces, each starting empty and growing
  only with that kind's replies. Holds by construction: each callback owns one
  catalog (D13).
- D12 (merged into D8.)
- D13 Every entity enumeration callback owns its catalog: its maker creates it,
  and it is never optional (D4). There is no installation record (O1). The
  `interpret_file` callback list holds no enumeration callback: none of its
  tools enumerates once D5 lands (C16).
- D14 `Entity_Catalog`: one plain catalog type; the eleven callback bodies are
  unchanged and return their final result list to `mk_enumeration_callback`,
  which hands it to `Entity_Catalog.answer`, which interns it. No payloads, no
  `sources`, no frozen prefix. (Reworded 2026-10-28, owner ruling on review
  item R3.)
- D15 Python mirror = a plain list per kind guarded by an `asyncio.Lock`; no
  compact representation.
- D16 `type def_pos` stays in `Context_Callbacks`, which also exports
  `pack_pos`; `Entity_Catalog` knows nothing of positions (C15, first half).
- D17 Names: `Entity_Catalog`, `synced_length`, `entry_of_name`,
  `Context.entries_of_names`. There is no context wrapper class; `ctxt` stays
  the plain wire value everywhere.
- D18 The enumeration interface is a set. The two consumers that break ties
  by list order (`lookup`'s no-vector tiers, `model.py`'s pattern-only path)
  keep doing so, with no tie-break of their own (§5.4). From stage C on, the
  list is the mirror entries at the reply's indices, so the order of
  equal-score candidates depends on the earlier replies of the same
  `call_command`; the owner accepts this (2026-10-27). Rev 5's unkeyed
  `blake2b(uk, digest_size=8)` tie-break is dropped: it cost 79–84 ms per
  whole-kind candidate set on cslh19 (§11). Stage C goldens that move because
  of tie order are re-recorded once, with the owner's approval.
- D19 At render time, METHOD entities (like THEOREM_COLLECTION today) never get
  a definition source: an explicit skip beside the existing one in
  `_format_fetched_entity`, with the reason in a comment.
- D20 A rendered entity's definition comes from its own name's declaration
  (the resolver resolves by name); stage B goldens that move for that reason
  are re-recorded entry by entry, with the owner's approval (widened by O2,
  which the owner delegated to the author). Known cases: an entity the infra
  filter removes; a rule-kind exact_name hit on a fact that is not a member of
  that kind; a concealed constant that the infra filter keeps but the
  enumeration's accessibility check drops; a theorem the enumeration lists
  under another alias (`lemmas bar = foo`). In AoA, `_PROOF_COMMAND_RE` hides
  `lemma`-like sources, so for an alias of a `definition`-generated fact AoA
  may stop showing a definition it shows today. In show_defs,
  `query_by_name_raw` raises before `_append_definition` for an entity without
  an interpretation record, so for infra entities only the notation path
  (`_try_resolve_syntax_token`) changes.
- D21 PlainAgent (untracked `contrib/Isa-Mini/PlainAgent/`) is ported: its
  `IsaMini.retrieve_entity` copy is replaced by the shared body; its
  `make_entity_callbacks` call takes the new signature with the methods keep
  predicate `K false`, the same as AoA (owner ruling, C11-followup). Whether it
  enters git is not this plan's business.
- D22 Two stages, each landing whole with its own tests, measurement and
  golden rule (§7, §8, §9): B = positions (the measured 99%); C = the catalog
  (P4). Rev 5's stage A (D18's tie-break alone) is dropped with that
  tie-break; the names B and C stay. Measurement after a stage (§8.5) does not
  gate the next.
- D23 Positions leave the enumeration engines (C15, second half, stage C):
  `ns_filter`, the LIVE pass of `make_theorems_callback`, the live sources of
  the rule callbacks and `Thm_Cache` stop computing and storing `def_pos`;
  `entry_def_pos` becomes private to the resolver.

## 3. Wire schemas

`MessagePackBinIO` combinator notation. `ctxt_unpack` is unchanged (AoA:
`string option` = Minilang state name; PIDE: `(file, offset) option`; static:
`unit`).

### 3.1 The eleven entity enumeration callbacks (stage C; one shared schema)

```
arg_schema = unpackPair (ctxt_unpack,
  unpackTuple10 (unpackOption unpackString,   (* theory                      *)
                 unpackBool,                  (* the_theory_only             *)
                 unpackList unpackString,     (* exclude                     *)
                 unpackList unpackString,     (* term_patterns               *)
                 unpackList unpackString,     (* type_patterns               *)
                 unpackList unpackString,     (* theories_include            *)
                 unpackList unpackString,     (* name_contains               *)
                 unpackInt,                   (* limit, <0 = no limit        *)
                 unpackString,                (* target_type, "" = no filter *)
                 unpackInt))                  (* synced_length               *)

ret_schema = Entity_Catalog.pack_reply =
  packTriple (
    Entity_Catalog.pack_index_set,            (* bin = bitmap | array of int = index list *)
    packList (packTuple4 (pack_universal_key, packString, packBool, packInt)),
                                              (* (uk, name, is_local, index), index >= synced_length, ascending, contiguous *)
    packList packString)                      (* warnings *)
```

- The first nine request fields are today's nine; the tenth is new.
- The body computes today's result list in the queried context; `answer`
  interns each result, in order; the index set encoding covers `[0, len)` with
  `len` the catalog length after interning; the entries are
  `catalog[synced_length, len)`. Under the Python lock (§5.1) and ML's
  sequential dispatch these are the entries this call interned, plus any that
  an earlier call interned whose reply the caller did not apply (§5.1). Let
  `len0` be the catalog length before interning: `synced_length < len0` is
  legal and re-delivers `[synced_length, len0)`; ML rejects only
  `synced_length > len0`, before interning (protocol error).
- Positions are gone: the theorem kinds' tuple4 and the other kinds' tuple3
  become this one tuple4; `is_local` is `false` for non-theorem kinds.
- `limit`, `exclude`, filters, `key_seen`: unchanged, inside the bodies.

### 3.2 `IsaMini.retrieve_entity` (stage B; stays in Isa-Mini; reply extended)

```
arg_schema = unpackPair (ctxt_unpack,
               unpackList (unpackPair (Universal_Key.unpack_entity_kind, unpackString)))
ret_schema = packList (packTriple (
  packOption (packTuple5 (packString,            (* short_name (externed; "??." prefix when inaccessible) *)
                          packList packString,   (* propositions (theorem kinds) | [type] (constants) | [] *)
                          packList packString,   (* roles: simp / intro / elim tags *)
                          packList packString,   (* abbreviation constants' full names *)
                          packBool)),            (* is_local *)
  packOption (packPair (pack_universal_key, Context_Callbacks.pack_pos)),
                                                 (* NEW: (uk, pos); SOME iff the display is SOME and the resolver gives SOME *)
  packOption packString))                        (* diagnostic *)
```

Same length and order as the request. The shared body calls the resolver only
when the display is `SOME`; a single-theorem fact asked with an out-of-range
index therefore gives `(NONE, NONE, SOME diagnostic)`. The display body is
unchanged (same printer, same roles), so AoA's golden output moves only where
D20 says.

### 3.3 `Context.entries_of_names` (stage B; new, Isabelle_RPC)

```
arg_schema = unpackPair (ctxt_unpack,
               unpackList (unpackPair (Universal_Key.unpack_entity_kind, unpackString)))
ret_schema = packList (packOption (packTuple4 (pack_universal_key, packString,
                                               Context_Callbacks.pack_pos, packBool)))
```

Same length and order as the request; each item is the resolver's answer.
Built by `make_entries_of_names_callback : context_unpacker -> callback'`
(an unpacker only, so it cannot touch a catalog: D3 by construction).
Registered where its one caller, `_definition_of_name` (§5.3), runs: in
`interpret_file_callbacks` (`semantic_store.ML`), built from the PIDE unpacker,
in place of today's `make_entity_callbacks context pu` entries (P1). Any
connection that builds Semantic_Embedding's exported `query_by_name_tool` must
carry this callback, or definitions vanish silently, because
`_append_definition` swallows the error; the existing list check in
`Test/Interpretation_Driver_Config_Test.thy` asserts it for `interpret_file`
(§8.3).

### 3.4 Unchanged

`universal_key_of`, `key_of_theorems`, `pide_state.command_at_position`,
`Semantic_Store.excluded_theory_names`, `Context.loaded_theory_hashes`,
`Context.experiences`, everything else. `Context.entities_of_keys` of rev 2 is
not built.

## 4. ML side

### 4.1 `Tools/entity_catalog.ML` (stage C; after `Universal_Key.ML`, before `context.ML`)

```sml
signature ENTITY_CATALOG =
sig
  type entry = {uk : Universal_Key.universal_key, name : string, is_local : bool}

  type T                                   (* one callback's catalog: append-only; indices assigned here only *)
  val new : unit -> T                      (* empty; Dynamic_Array.empty 16, Bytehashtab.empty 16 *)

  val length       : T -> int
  val intern       : T -> entry -> int     (* index of the entry equal in (uk, name, is_local); appended when absent *)
  val entries_from : T -> int -> (entry * int) list      (* indices >= n, ascending *)

  datatype index_set = Bitmap of Word8Vector.vector | Indices of int list
  type reply = index_set * (entry * int) list * string list
  val answer : T -> int -> entry list -> string list -> reply
  (* n > length => protocol error; n < length re-delivers [n, length) (a reply
     the caller did not apply); intern each result in order; encode the
     indices as the smaller of Bitmap (ceil (length/8) bytes) and Indices (sum
     of msgpack int widths; in result order, never sorted); entries_from n. *)

  val pack_index_set : index_set MessagePackBinIO.Pack.packer
  val pack_reply : reply MessagePackBinIO.Pack.packer
end
```

Representation: `entries : entry Dynamic_Array.T` (index = position; no
storage until the first append) and `by_uk : (entry * int) list
Bytehashtab.table` for `intern` (one 16-slot array at creation); both from
Performant_Isabelle_ML, both grow by doubling. No locks: callbacks are served
one at a time per `call_command` (`dispatch_loop` runs each callback to
completion before reading the next request) and every enumeration callback is
built for exactly one `call_command` (§4.3). Memory: entries hold references
to names already in the ML heap; a few MB per `by aoa`.

### 4.2 The eleven callbacks (stage C)

Every maker keeps today's parameter list (its last parameter is still the
`context_unpacker`). The catalog is created where the callback record is
built, by one private helper that all seven makers of an entity enumeration
callback call (`make_constants_callback`, `make_types_callback`,
`make_classes_callback`, `make_locales_callback`,
`make_theorem_collection_callback`, `make_methods_callback`,
`make_thm_like_callback`): `mk_enumeration_callback name ctxt_unpack body`
evaluates `Entity_Catalog.new ()` once per application, outside the
callback's `function`, sets the two schemas, and hands the body's
`(entries, warnings)` to `Entity_Catalog.answer`. So the catalog is never at
structure level (one catalog for every request of the process, mutated from
several threads) and never inside `function` (a fresh catalog per call, so the
second call's `synced_length` is rejected), by construction: no body sees the
catalog. `make_thm_like_callback` builds `Context.theorems` (through
`make_theorems_callback`) and the four rule callbacks (through
`make_rules_callback`, which fully applies it in its body and creates no
catalog of its own); each application builds one callback, so each of the
five gets its own catalog. (Reworded 2026-10-28, owner ruling on review item
R3; rev 6 had each maker create its catalog.) Example:

```sml
fun mk_enumeration_callback name (ctxt_unpack : context_unpacker) body =
  let val catalog = Entity_Catalog.new ()
  in Remote_Procedure_Calling.mk_callback {
       name = name, ...,
       arg_schema = unpackPair (ctxt_unpack, arg_schema),
       ret_schema = Entity_Catalog.pack_reply,
       function = fn arg as (_, (_, _, _, _, _, _, _, _, _, synced_length)) =>
         let val (entries, warnings) = body arg
         in Entity_Catalog.answer catalog synced_length entries warnings end,
       ...}
  end
```

The bodies keep their tuple10 pattern, with `_` for `synced_length`, and are
otherwise unchanged.

Positions leave the engines (D23): `ns_filter`'s result triple drops its
position; the LIVE pass of `make_theorems_callback` and the live sources of the
rule callbacks drop `epos`; `cached_thm_entry` drops `pos`, so
`Semantic_Store`'s `process_facts_into_cache`, `classify_rule_entries`' retag
and the dynamic-member adoption (`entry`/`invented`) stop computing or copying
it. `entry_def_pos` leaves the `CONTEXT_CALLBACKS` signature; `def_pos` and
`pack_pos` stay exported (D16). The `Position.T` that the interpretation path
(`enumerate_entries`, the adoption tuple's `#pos e`) reads from name-space
entries is a different value and is untouched.

### 4.3 `make_entity_callbacks` (stage C)

```sml
(* Semantic_Store *)
val make_entity_callbacks : Context.generic -> (string -> bool) ->
      Context_Callbacks.context_unpacker -> Remote_Procedure_Calling.callback' list
```

returns the eleven callbacks plus `links`. The `string -> bool` argument is the
methods keep predicate, combined with `not o is_infra_method`; it is not an
option. Sites:

- AoA (`raw_AoA` in `agent_server.ML`): `K false`; the `methods = _`
  destructuring and the `make_methods_callback (SOME (K false))` override go.
- PlainAgent (`plain_agent_app.ML`): `K false` (D21).
- static: `K true`, called inside the function `query_knn` returns (C8), so
  each call builds fresh callbacks. Today they are built once per
  `query_knn (context)` application and shared by every later call of the
  returned function, each a separate `call_command`.

Every site builds its callbacks once per `call_command`; this is what gives
each catalog the lifetime of one request (D1). A callback reused across two
`call_command`s still answers correctly: the second request's mirror starts
at 0 and ML re-delivers `[0, len)` (§3.1).

`interpret_file_callbacks` no longer calls it (D13; stage B, §3.3). The
`IsaMini.query_by_name` RPC (`agent_server.ML`) installs no enumeration
callbacks.

### 4.4 The resolver `entry_of_name` (stage B)

```sml
val entry_of_name : Context.generic -> Universal_Key.entity_kind * string
                    -> {uk : universal_key, name : string, pos : def_pos, is_local : bool} option
```

In `context.ML`, catalog-free. Resolution is by name only, through the
functions `universal_key_of` dispatches to; there is no infra filter, no
rule-kind membership test, no methods filter and no dynamic-fact test of its
own (D20). The whole computation runs under `handle ERROR _ => NONE`.

- (a) Theorem kinds. `Universal_Key.key_of_theorem NONE` gives `(uk, thm,
  is_global, full_name, disp_name)` (it parses `foo(3)` with
  `parse_thm_xname`). A rule kind re-keys `thm` with its `key_of_*_rule'`, as
  `key_of''` does. `name = disp_name`; `is_local = not is_global`.
  `pos = ("", 0, 0)` when `Facts.is_dynamic facts full_name` holds, because a
  dynamic member has no declaration of its own (as with today's invented
  members in `semantic_store.ML`); otherwise `entry_def_pos (#pos e)` with `e`
  the entry `entry_of_fact` gives for `full_name`. This dynamic-fact rule
  applies to these five kinds only.
- (b) The six name kinds. `key_of_constant`, `key_of_type`, `key_of_class`,
  `key_of_locale`, `key_of_theorem_collection` and `key_of_method` give
  `(uk, name, position)` from one name-space lookup (below);
  `pos = entry_def_pos` of that position; `is_local = false`. For
  THEOREM_COLLECTION this is the collection's own declaration, which
  show_defs prints today.

`Universal_Key` change (stage B): `key_of_ns_entity` also returns
`SOME (#pos ns_entry)`, the position of the entry it already reads; the six
name-kind `key_of_*` functions return `(uk, name, Position.T option)`;
`key_of_constant`'s fixed-variable branch returns `NONE` for the position,
which the resolver maps to its own `NONE`. `universal_key_of`'s dispatch
projects to the pair; every other caller already takes `#1` (`context.ML`,
`key_of`, `key_of''`, `semantic_store.ML`, `agent_server.ML`,
`Tactic_Declaration_Test.thy`). The position is a `Position.T`, not the
`name_space_entry` record, because that record type is spelled out only in
`Context_Callbacks`, which loads after `Universal_Key`. `entry_def_pos` takes a
`Position.T` (its body reads only `#pos`); its stage B callers pass `#pos e`
until D23 removes them in stage C. The uk and the position thus come from one
lookup by construction.

So the resolver gives `SOME` exactly when `universal_key_and_name_of` succeeds,
except a fixed variable asked as ConstantK (no name-space entry), which is
`NONE`. Also `NONE`: an unknown name, a bare multi-theorem fact, an empty fact,
an out-of-range index into a multi-theorem fact, an undeclared
type/class/locale/method. `SOME` where today's enumeration has no such entry: a
single-theorem fact with any index (`foo(5)`), a static fact asked as
THEOREM_COLLECTION, a fact asked as a rule kind it is not a member of, an
infra-filtered entity. The static-fact-as-collection `SOME` is unobservable:
the §3.2 display gate gives that request no position (its display is `NONE`),
and show_defs never reaches a `0x06` key of a static fact.

Used by §3.2 (inside the shared retrieve body) and §3.3.

### 4.5 Preserved behaviour (acceptance, §8.1)

For every request of the §8.1 corpus, the set of `(uk[16:], name, is_local)`
that `entities_of` returns after stage C equals the baseline set recorded on
the unmodified tree (§9 step 0). `uk[16:]` is the kind tag followed by the full
internal name (name-space kinds) or the first 15 bytes of the proposition
digest `thm128` (theorem kinds); no theory hash enters it. Bytes 0–15 are a
theory-hash prefix that changes with the .thy text of the defining or
constituent theories and of their heap ancestors; stage C itself adds an
`ML_file` line to `Remote_Procedure_Calling.thy`, and other agents edit .thy
files in the shared tree. In one context a name has exactly one uk and the
prefix is computed by builders this plan does not change, so `uk[16:]` with
the name and `is_local` identifies an entry as completely as the whole uk.

## 5. Python side

### 5.1 The mirror (stage C)

Per kind, in a dict under a private key of `connection.request_state`:
`entries: list[tuple[bytes, str, bool]]` and `lock: asyncio.Lock`. The
container and each kind's pair are created on first use by `_enumerate`
(§5.2) with `setdefault`, with no `await` between the check and the creation,
so concurrent first calls share one (precedent: `links.py`'s retrieval
closure). `_enumerate` holds the kind's lock across three phases: read
`synced_length = len(entries)`, send, apply the reply. Applying: the first
delivered index must equal `synced_length` and the indices must be contiguous
(else protocol error); extend; after that a bitmap must be exactly
⌈len(entries)/8⌉ bytes (else protocol error). A lost reply leaves the mirror
unchanged; the next call re-sends the same `synced_length` and ML re-delivers
(§3.1). Memory: ~18 MB traced for a fully transferred theorem kind (measured
with plain lists); only the kinds and entries actually returned are ever held.

### 5.2 `entities_of` (stage C)

`context.py` keeps one sender, `_enumerate(connection, kind, ...filters...,
ctxt) -> (list[entity_entry], list[str])`, which owns §5.1 end to end: it
applies the reply, checks the bitmap length, decodes the index set (bitmap: a
256-entry table of set-bit positions per byte; list: as is) through a
module-private helper, and returns the mirror entries at those indices
together with the warnings. No other function reads or writes the mirror.

`_call`, `_call_thm`, the eleven per-kind functions and `_KIND_TO_FUNC` are
deleted; nothing outside `context.py` imports them.

`entities_of` loops over one table: kind → callback name, and which filters it
forwards; the table reproduces today's five branches. It concatenates the
per-kind lists and warnings and applies today's cross-kind theorem-face
suppression to that one list, unchanged except that its `is_local.pop` goes.
It returns `(entries, warnings)` with `entity_entry = (uk, name, is_local)`; the
separate is_local dict goes. Callers updated: `lookup` (two sites),
`embed_all_entities_in_theories`, the pattern-only path in `model.py`, the
relay in `test_resolve_notation_callback.py`. Test doubles updated:
`Semantic_Embedding/tests/test_link_layer.py`'s `FakeConnection`
(`Context.theorems`/`Context.introduction_rules` branch) and the `entities_of`
fake in `IsaMini/AoA/test_link_display_owner.py`. That inventory came from
this scan, to be re-run before landing stage C (it also lists documents that
name these callbacks, the definition of `entities_of`, and
`Semantic_Embedding/Test/Query_Tool_Test.thy`, which is in no session and stays
untouched, per the round 2 ruling):

```
/usr/bin/grep -rnI --exclude-dir=ai-artifacts --exclude-dir=archive --exclude-dir=build \
  --exclude-dir=.git --exclude-dir=.mypy_cache --exclude='*~' \
  -e 'Context\.\(theorems\|constants\|types\|classes\|locales\|theorem_collection\|methods\|introduction_rules\|elimination_rules\|induction_rules\|case_split_rules\)\b' \
  -e 'setattr(.*entities_of' -e 'entities_of(' contrib/Isabelle_RPC contrib/Semantic_Embedding contrib/Isa-Mini
```

`ctxt` is passed through untouched everywhere.

### 5.3 Positions and definitions (stage B)

- A def_pos triple becomes an `IsabellePosition | None` only through
  `IsabellePosition.from_def_pos(triple)`, a classmethod in `position.py` beside
  `from_s` and `unpack` (O3, decided by the author under the owner's
  delegation). It takes the wire triple `(file, line, offset)` whole, so no
  call site re-orders it into the constructor's `(line, raw_offset, file)`; an
  empty file or a zero offset gives `None`, as `_mk_pos` does today. Its readers
  are `retrieve_entities_with_diagnostics` (Isa-Mini) and `_definition_of_name`
  (Semantic_Embedding); `context.py`'s `_call` and `_call_thm` use it until
  stage C deletes them; `_mk_pos` is deleted; neither package has a copy.
- `retrieve_entities_with_diagnostics` returns per entity `(display | None,
  (uk, position) | None, diagnostic | None)`; the uk stops there (P2).
  `RetrievedEntity` gains `position: IsabellePosition | None` without a default
  (placed before the defaulted fields); `IsabelleEntity` and
  `IsabelleFact_Presented` are unchanged. Its two construction sites pass it by
  keyword: `semantic_knn`'s EXPERIENCE branch passes `None`;
  `_make_retrieved_entity` takes `position` as a required parameter, and
  `semantic_knn` passes each retrieve item's position.
  `retrieve_entities_by_name` (the Useful-lemmas path, feeding
  `_render_useful_lemmas`) calls `_retrieve_entity_with_diagnostics` instead of
  `_retrieve_entity` and passes each item's position on. `_retrieve_entity`
  keeps returning only the display tuple, for its callers that render nothing
  (`_try_resolve_as_named_fact` and the `test.py` tests). Callers and fakes
  updated: the callers of `_retrieve_entity_with_diagnostics` in `model.py`
  (FactByName resolution, `refresh_facts`, `semantic_knn_counted`,
  `retrieve_entities_by_name`), `_query_entity_core` in `retrieval.py` (only its
  two-value unpack changes), `_make_retrieved_entity` and the fakes in
  `IsaMini/AoA/test_link_display_owner.py`.
- `_definition_at(connection, pos)` (factored out of the second half of today's
  `_get_definition_with_pos`: `command_at_position`, `_strip_trailing_begin`,
  `pretty_unicode`, `cmd_pos`) is the only place turning a position into text.
  It lives in Semantic_Embedding's `semantics.py`, next to `_definition_of_name`,
  because Isa-Mini depends on Semantic_Embedding and not the other way round;
  `retrieval.py` imports it in place of `_get_definition_with_pos`.
  `_format_fetched_entity` calls it with the entity's position when present and
  the kind is not THEOREM_COLLECTION or METHOD (D19). `_get_def_for_fetched` is
  deleted; dropping its `try` adds no failure path, because
  `command_at_position` already swallows its own exceptions. The
  `QueryWholeFileDump` model test (`test.py`) moves its patch point to
  `retrieval._definition_at`, the imported name; its assertions and golden are
  unchanged.
- Semantic_Embedding: `_get_definition_with_pos(connection, kind, uk, ctxt)`
  becomes `_definition_of_name(connection, kind, name, ctxt)` =
  `Context.entries_of_names([(kind, name)])`, the decoder, then
  `_definition_at`; `_get_definition_source` and `_append_definition` pass the
  name they hold (callers: `query_by_name_tool`, `_try_resolve_syntax_token`).
  Nothing in Isa-Mini or Semantic_Embedding enumerates to find a position any
  more.

### 5.4 Order of equal-score candidates (D18)

No code. The two sites stay as they are: `model.py`'s pattern-only path
(`entries.sort(key=lambda e: _pat_score(e[0]), reverse=True)` before the
`entries[:k_fetch]` cut) and `lookup`'s no-vector loop (`for uk in
candidates:`). Both keep equal-score candidates in the order `entities_of`
returns them.

Up to stage C that order is ML's enumeration order, as today. From stage C on
it is the order of the reply's indices. For a bitmap that is ascending index
order: a catalog entry's index is fixed by the first reply of the
`call_command` that returned it, so an entity that an earlier query returned
comes before one first returned now. An index list keeps ML's result order
(§4.1): no sort on either side (owner ruling, 2026-10-27: no sort that serves
no purpose).

### 5.5 `request_state` lifetime (stage C)

`handle_client` resets `connection.request_state` at request start (today) and
in a `finally` covering the success, error, unknown-procedure and cancellation
exits, so the mirrors are dropped as soon as the reply or error is written
even while Isabelle keeps the connection pooled. One `call_command`, its
callbacks, one request on one connection and one `request_state` correspond
one to one: `call_command` takes the connection out of the pool for its whole
duration, and an RPC command issued by ML code running inside a callback takes
another connection.

## 6. Effect

### 6.1 Stage B, measured (§8.5, 2026-10-27)

Real runs: the §1 cases, driver (ClaudeCode) and scripts, on this machine.

| | §1, before stage B | after stage B |
|---|---|---|
| main-thread CPU per case (b2, a5, b1) | 41, 46, 45 s | 4.5, 5.4, 3.3 s |
| main thread, mean over the cases | 8.1% | 1.38% |
| bytes from Isabelle, whole run | 4620 MB | 87 MB |
| heaviest `query` call, main thread | 13–22 s | 1.8 s |
| host peak RSS | 1.8 GB | 1.66 GB |
| unfiltered theorem sub-queries | 0 of 38 | 6 of 35 |

- The 87 MB are exactly those 6 sub-queries: one THEOREM enumeration each,
  86,664 entries after `theories_not_include`, ≈ 14.4 MB. A `query` call
  without one receives ≈ 0.1 MB.
- Per rendered result: one small call (`command_at_position`); the position
  rides on `IsaMini.retrieve_entity`.
- Peak RSS: in both runs ≈ 1.4 GB arrives with the vector store at the first
  semantic lookup; enumeration does not set it.

Simulation (cslh19). §1's sweep modelled one `query` call as a burst of 37–45
full enumerations. Here a burst draws one measured call, with u unfiltered
theorem sub-queries and r rendered results, and makes 2.19·u full
enumerations (§1's calibration: 41 simulated per 18.73 real) and r small
calls. Think time, N and payload as in §1. Main thread; burst p50 / p95:

| N | before stage B (§1's sweep) | Codex profile (150 calls; u 1.07, r 13.7) | ClaudeCode profile (27 calls; u 0.22, r 17.4) |
|---|---|---|---|
| 1 | 4.6%; 10.4 / 11.0 s | 0.8%; 0.4 / 1.6 s | 0.4%; 0.0 / 0.5 s |
| 10 | 52.3%; 9.6 / 21.1 s | 4.0%; 0.4 / 1.1 s | 1.3%; 0.0 / 0.9 s |
| 20 | 99.2%; 102 / 122 s | 7.1%; 0.4 / 1.1 s | 2.0%; 0.0 / 0.8 s |
| 40 | 99.1%; 261 / 294 s | 14.6%; 0.4 / 1.4 s | 3.7%; 0.0 / 0.8 s |

Saturation moved from between 10 and 20 runs to beyond 40 in both profiles:
burst latency at N = 40 equals that at N = 1, event-loop lag p95 is 38 ms and
1 ms (606 ms before). Linear extrapolation: ≈ 270 runs (Codex), ≈ 1000
(ClaudeCode).

Unfiltered theorem sub-queries across drivers, from the evaluation logs:

| driver, log set | query calls | sub-queries | unfiltered theorem sub-queries | cases with one / with queries | max per case |
|---|---|---|---|---|---|
| ClaudeCode, PutnamBench, §1 run | 15 | 38 | 0 | 0 / 3 | 0 |
| ClaudeCode, PutnamBench, after stage B | 12 | 35 | 6 | 3 / 3 | 3 |
| Claude-API, miniF2F | 93 | 243 | 43 | 10 / 35 | 21 |
| CodexAPI gpt6sol-high, miniF2F | 150 | 282 | 160 | 38 / 39 | 17 |
| CodexAPI gpt6luna-xhigh, gpt5-6sol-high, gpt5-6luna-xhigh, miniF2F | 79 | 164 | 0 | 0 / 9 | 0 |
| DeepSeek.V4-pro, PutnamBench (2026-06, older prompt) | 1388 | 2272 | 982 | 18 / 18 | 213 |
| PlainAgent, miniF2F | 74 | 189 | 14 | 7 / 24 | 3 |

### 6.2 Stage C, measured (§8.5, 2026-10-28)

Real runs as in §6.1: the same three cases, driver and scripts, on this
machine, 17:04–17:30 +08; all three proved.

The two runs differ in retrieval, so the comparison is not like-for-like. In
§6.1's run every retrieval score was the default 0.300: the light_locale patch
had changed `Pure.thy`, so no entity key matched the DB. `Pure.thy` was
restored before this run (daily `7eb9137`). Retrieval found vectors and DB
descriptions again: none of the 188 rendered results of §6.1's run carries a DB
description, 10 of b2's 22 here do. The agent therefore saw other lemmas and
behaved differently.

| | after stage B (§6.1) | after stage C |
|---|---|---|
| case wall time (b2, a5, b1) | 227, 431, 304 s | 109, 983, 473 s |
| main-thread CPU per case (b2, a5, b1) | 4.5, 5.4, 3.3 s | 4.2, 12.1, 6.0 s |
| main thread, mean over the cases | 1.38% | 1.42% |
| main thread, 1 s peak | 87% | 82% |
| bytes from Isabelle over the cases | 87 MB | 7.1 MB |
| of which in `query` calls | 87 MB in 12 calls | 7 MB in 10 calls |
| heaviest `query` call, main thread | 1.8 s | 1.15 s |
| host peak RSS | 1.66 GB | 2.88 GB |
| unfiltered theorem sub-queries | 6 of 35 | 3 of 32 |
| cost | 3.92 USD | 4.90 USD |

Per call, after stage B, expected for stage C, and measured:

| call | after stage B | stage C, expected | stage C, measured |
|---|---|---|---|
| filtered sub-query | matching entries × ≈ 180 B | new entries only + index set | everything else from Isabelle in a case: 30 KB (b2), 127 KB (a5), 74 KB (b1) |
| first unfiltered theorem sub-query in a `by aoa` | ≈ 14.4 MB | ≈ 7 MB once (the same entries without positions, §1's 53%) | 6.84 MB |
| later unfiltered theorem sub-queries | ≈ 14.4 MB each | ≈ 11 KB bitmap + new entries | 11.0 KB each |
| per rendered result | 1 small call | unchanged | unchanged |

- All three unfiltered sub-queries are in one `query` call of a5 (17:07:06),
  each a THEOREM enumeration of 86,664 entries. The host's socket counters,
  sampled every 2 s, show 6,847,630 B in the window holding the first and the
  second, and 10,991 B in the window holding the third. So the first carries
  ≈ 6.84 MB (≈ 79 B per entry, 47% of stage B's 14.4 MB), and each later one
  ≈ 11 KB (86,664 bits = 10,833 B, plus framing).
- No `by aoa` of this run has unfiltered sub-queries in two `query` calls, so
  the run shows the catalog reused within one call only.
- Main-thread CPU per case follows the case's length: 1.1–3.8% of its wall
  time in both runs. a5 ran 2.3 times longer than in §6.1's run, with the
  same 37 tool calls. So per-case CPU does not compare across the runs; the
  mean and the peak do, and are unchanged.
- Peak RSS: the host grows from 0.2 to 2.8 GB at 17:07:07–22, during that
  call, and is back at 0.24 GB by 17:23:45. The vector scan (`_topk_sync`)
  reads the candidates' vectors in place from the LMDB mmap, so every page it
  touches counts as the host's file-backed RSS. Probe (offline, read-only): one
  scan of 86,664 theorem vectors maps 1.25 GB of file pages, with anonymous
  memory unchanged; a second scan of the same keys adds nothing. In §6.1's run
  no key matched, so the scan touched no vectors. Stage C does not cause this;
  the rest of the 2.6 GB (twice the probe) was not decomposed.
- py-spy: the vector gather `get_user_only` (worker threads) takes 12 s, 1.2 s
  in §6.1's run, since vectors are found now.
- Before the cases, the REPL rebuilt `MathBench_ProverBase` (43.5 min) and
  `MathBench_Prover` (7.3 min) for the restored Pure, with the host already up.
  Totals from host start therefore do not compare; the table uses the cases'
  windows.

The first unfiltered transfer per `by aoa` per kind remains; §10 records the
lever for it.

## 7. Notes (no decision pending)

- Evaluations (cluster, cslh19) run from the working tree, so a stage takes
  effect for them when it lands. Releasing is not this plan's business.
- Landing rule, per stage. A stage lands whole, in one sitting, after its §8
  tests: one commit in each touched submodule, followed by one MLML commit that
  bumps all of them. No MLML commit holds half a stage: within stage B,
  Isa-Mini's `retrieval.py` imports the `_get_definition_with_pos` that
  Semantic_Embedding deletes; within stage C, `semantic_store.ML` writes the
  `pos` field of `cached_thm_entry`, which Isabelle_RPC removes, and calls
  `entry_def_pos`, which Isabelle_RPC makes private; and Isa-Mini's `raw_AoA`
  calls `make_entity_callbacks` with its old arguments.
- Stages B and C change ML and a wire shape. Before landing either, tell the
  owner that until it lands any agent restarting a Minilang_AoA or
  Semantic_Embedding REPL in the shared tree fails. Right after it lands, every
  fixed-address RPC host (`RPC_Host` set) and every running REPL that loads a
  touched session must be restarted together; tell the owner which ones are
  running. An old host with new ML fails every retrieval in stage B or every
  `by aoa` in stage C; a new host with an old REPL loses definitions silently
  in stage B (the REPL answers "Unknown callback" and `_append_definition`
  swallows it). The §8 tests that use an externally started host
  (`test_resolve_notation_e2e.py`) run against one started after the edits.
- Should callback dispatch ever become parallel, `answer` must run as one
  critical section per catalog; the reply rule and the per-entry index need no
  change (D4).
- PlainAgent is untracked; its edits live only in the working tree. PlainAgent
  never queries METHOD (its query schema has no "proof tactic" label,
  `_kind_of_label` rejects "proof method", its default kinds are
  constant/theorem), so D21's port changes no PlainAgent output.

## 8. Acceptance and measurement

1. ML differential test (stage C), a driver beside the step 0 baseline in
   `Isabelle_RPC/ai-artifacts/ENTITY_CATALOG_BASELINE/`, uncommitted like the
   baseline (2026-10-28, owner ruling on review item R1: rev 6 extended the
   committed `test_resolve_notation_e2e.py`, which would then read git-ignored
   data that the LIVE-pass fix and any new lemma make stale; that test keeps
   only the last bullet below):
   - the driver's theory imports no Minilang, so it builds the callbacks once,
     with a custom `context_unpacker` that maps
     strings to proof contexts noting local facts after the callbacks are
     built (this stands for "several proof states with proof-local facts");
   - the corpus (unfiltered, each filter alone, combined, with `limit`,
     proof-local facts, a dynamic collection mutated between calls, every kind)
     runs in one relay request on those callbacks, so `synced_length > 0`
     occurs, and every reconstructed set must equal the baseline (§4.5);
   - the relay records each reply's encoding; the test asserts at least one
     index list, and at least one bitmap whose catalog length is not a
     multiple of 8 and whose set bits are not a prefix;
   - re-delivery is made deterministic: inside the same request, call
     `connection.callback` directly with `synced_length = len(mirror)` on a
     query whose results are not yet in the catalog and discard the reply; the
     next `entities_of` call of that kind must accept the re-delivered entries
     and match the baseline;
   - callbacks are built once per `call_command`, as at the production sites
     (today one constants callback serves two `call_command`s there).
2. ML unit test of `Entity_Catalog.answer` (stage C): the §0 example gives
   `Bitmap FF 40`; `n < length` re-delivers `[n, length)`; `n > length` raises;
   the same uk interned with `is_local = false` and with `is_local = true`
   gives two entries (D6). The last case is here because §8.1 cannot produce
   `is_local = true` today (step 0's finding in the status block).
   Its theory in the `Isabelle_RPC_Test` session (`test/`) is a new file and
   needs the owner's approval when it is committed; it is run through the REPL
   (`isabelle build` needs the owner's command).
3. Tests per stage (Python unless marked ML):
   - stage B: the def_pos decoder maps `("", 0, 0)` and `(file, n, 0)` to `None`
     and `(file, line, offset)` to `IsabellePosition(line, offset, file)`;
     a differential test over a corpus of `(kind, name)`: every resolver `SOME`
     agrees with `universal_key_and_name_of` on uk and name, and every success
     of `universal_key_and_name_of` is `SOME` except a fixed variable asked as
     ConstantK; the `SOME` cases with their fields (a singleton fact, bare and
     as `foo(5)`; an indexed member of a multi-theorem fact; a dynamic member
     `coll(i)` with pos `("", 0, 0)`; a collection asked as THEOREM_COLLECTION,
     with its declaration pos; a proof-local fact with `is_local = true`); the
     `NONE` cases (a bare multi-theorem name, an empty fact, an out-of-range
     index into a multi-theorem fact, a fixed variable asked as ConstantK, an
     undeclared type/class/locale/method, an unknown name); METHOD and
     THEOREM_COLLECTION skip; the Useful-lemmas path (with a faked
     `IsaMini.retrieve_entity` reply carrying a position, an entity from
     `retrieve_entities_by_name` rendered through `_render_fetched_entities`
     reaches a patched `_definition_at` with that position; no existing test or
     golden covers this block); `_definition_of_name` end to end through
     `interpret_file_callbacks`'s actual list, including one theorem
     collection; (ML) the list check in
     `Test/Interpretation_Driver_Config_Test.thy` asserts
     `Context.entries_of_names` is on it;
   - stage C: both encodings decode to the same set; the Python decoder turns
     `FF 40` with length 10 into {0..7, 9}; two concurrent same-kind calls on an
     empty mirror cause exactly one transfer (lock); two same-kind calls
     started with `asyncio.gather`, as `retrieval.py` does, leave the mirror
     equal to ML's catalog prefix and both sets equal the baseline; the two
     Python protocol errors (a first index other than `synced_length` or a
     gap; a bitmap of the wrong length); `import Isabelle_RPC_Host` with only
     its declared dependencies.
4. AoA golden tests (`test_AoA.py`), per stage: stage B may move only
   definitions that change because the position now comes from the rendered
   name instead of from the kind's enumeration entry with the same uk, i.e.
   D20's four known cases; stage C only the order of equal-score candidates
   (D18), in a case whose earlier query of the same kind returned some of
   them. Moved goldens are re-recorded once, entry by entry, after the owner's
   approval.
   PlainAgent's `Test/` passes after each stage that touches it.
5. After each stage: the three PutnamBench cases under py-spy on this
   machine, as in §1 (main-thread CPU, bytes received, host peak RSS); the
   20/40-load simulation on cslh19; and a count of unfiltered sub-queries per
   case across drivers. Replace §6 with the numbers.

## 9. Work order (two stages, D22)

0. Baseline, before any edit: freeze the §8.1 corpus as an ai-artifacts data
   file; record each item's set of `(uk[16:], name, is_local)` (§4.5) through a
   relay calling today's `entities_of`. Uncommitted.
1. **Stage B** (D5, D7, D19, D20, the `interpret_file` half of D13 (C16), the
   retrieve part of D21; the eleven callbacks untouched and still carrying
   positions):
   - Isabelle_RPC ML: `entry_of_name`; `make_entries_of_names_callback`;
     `pack_pos` exported; `key_of_ns_entity` and the six name-kind `key_of_*`
     return the entry's `Position.T option`; `entry_def_pos` takes a
     `Position.T`.
   - Isabelle_RPC Python: `IsabellePosition.from_def_pos`; `_call` and
     `_call_thm` use it; `_mk_pos` deleted.
   - Isabelle_RPC skill (owner-approved): `references/registry.md` gains the row
     `Context.entries_of_names` → `Context_Callbacks.make_entries_of_names_callback`;
     `references/modules.md`'s `Context_Callbacks` section gains the resolver
     `entry_of_name` and the new callback; its Python positions paragraph names
     `IsabellePosition.from_def_pos` as the one decoder of the triple.
   - Semantic_Embedding: `interpret_file_callbacks` registers
     `Context.entries_of_names` instead of `make_entity_callbacks context pu`,
     with its signature comment and the `pu` comment, both of which describe
     the list stage B replaces; `_definition_at` and `_definition_of_name` in
     `semantics.py`; `_get_definition_with_pos` deleted; `process_facts_into_cache`
     and the dynamic-member adoption's `entry` in `semantic_store.ML` pass
     `entry_def_pos (#pos e)` (§4.4).
   - Isa-Mini: the shared retrieve body with `(uk, pos)` behind the display
     gate; `MINILANG_AGENT_AoA` exports `make_retrieve_entity_callback` and
     `make_thm_roles`; `RetrievedEntity.position`; `_make_retrieved_entity`'s
     `position` parameter; `retrieve_entities_by_name` on
     `_retrieve_entity_with_diagnostics`; METHOD skip; `retrieval.py` imports
     `_definition_at`; `_get_def_for_fetched` deleted; fakes and tests of §5.3;
     `docs/TACTIC_DESIGN.md:152` keeps its text and gets a dated note that the
     definition skip for tactics is now D19's explicit METHOD skip
     (owner-approved).
   - PlainAgent: `plain_agent_app.ML` deletes its copied `make_thm_roles` /
     `make_retrieve_entity_callback` block and calls the exported ones at its
     two use sites.
   - §8.3 stage B tests; goldens per §8.4; land per §7; §8.5.
2. **Stage C** (D4, D11, the rest of D13, D14–D17, D23, the rest of D21):
   - Isabelle_RPC ML: `entity_catalog.ML`; each maker creates its catalog
     through `mk_enumeration_callback`, which also owns the schemas and the
     `answer` call (§4.2); positions out of
     the engines and `cached_thm_entry`; `entry_def_pos` private to the
     resolver.
   - Isabelle_RPC Python: the mirror and `_enumerate`; `entities_of`'s new
     return; `_call`, `_call_thm`, the per-kind functions and `_KIND_TO_FUNC`
     deleted; `request_state` `finally`; pure-Python bitmap decode.
   - Semantic_Embedding: `make_entity_callbacks`' new signature (§4.3); the
     static callbacks built inside `query_knn`'s returned function;
     `Thm_Cache` without positions; `lookup` and
     `embed_all_entities_in_theories` on the new `entity_entry`.
   - Isa-Mini: `raw_AoA`'s `make_entity_callbacks` call; the pattern-only path
     on the new `entity_entry`; PlainAgent's `make_entity_callbacks` call.
   - Docs and comments: `context.ML`'s header (the tenth payload field,
     `synced_length`); `make_thm_like_callback`'s comment (the LIVE candidate has no
     pos); the `ret_schema_thm` comment and the def_pos sentences of the
     adoption comment in `semantic_store.ML` go with their code; the
     isabelle-rpc skill's `references/modules.md` `Context_Callbacks` argument,
     return and trap text rewritten (ten fields; one reply shape; no 2-tuple
     trap; catalog and `synced_length`) and its stale "Python caches only the
     fully default query" bullet deleted (owner-approved);
     `docs/TACTIC_DESIGN.md:152` gets a second dated note that the override is
     now `make_entity_callbacks`' methods keep predicate `K false`
     (owner-approved).
   - §8.1, §8.2, §8.3 stage C tests; land per §7; §8.5.

## 10. Out of scope (recorded)

Cross-`by aoa` catalog reuse on one connection (would remove the first
unfiltered transfer per `by aoa` and kind, ≈ 7 MB for theorems (§6.2); needs a
content identity, see D1); a file
table for positions should positions ever return to a bulk reply; an iNet index
over cached propositions for pattern queries (ML-side fold cost);
`jsonschema.validate` cost in the mcp library (33 ms per tool call on cslh19);
Python 3.14 / JIT (measured: no gain); numpy in Isabelle_RPC_Host. The LIVE
pass bug (`BUG_LIVE_PASS_INFRA_FILTER_CONTEXT.md`): fixed after this plan, by
the owner's ruling (2026-10-27), so §8.1's baseline stays valid for stage C
(fixed in Semantic_Embedding `6d0ad1b`, 2026-11-01).

## 11. Review history

- Reports beside this file: `ENTITY_CATALOG_REVIEW_1_judge.json` (rev 2),
  `ENTITY_CATALOG_REVIEW_2_judge.json` (rev 3), `ENTITY_CATALOG_REVIEW_3_judge.json`
  (rev 4; merged concerns R1–R15, defenses, judge). Journals:
  `~/.claude/projects/-home-qiyuan-Current-MLML/1595227b-511f-4ae1-9cd4-1d599bbc8344/subagents/workflows/wf_99d04464-dc1/journal.jsonl`
  (round 2) and `.../wf_acb72a38-931/journal.jsonl` (round 3).
- Round 2 owner rulings: C1 adopted with an unkeyed hash (D18); C7 rejected,
  the index stays (D4); C13 adopted (D4, D17, §5.1); C14 rejected, `(uk, pos)`
  stays (D7); C15 adopted, both halves (D16, D23); C16 adopted (D13, §3.3);
  PlainAgent's methods filter `K false` (D21).
- Round 2 items left to the author, applied: C2 (§4.4, §3.2, §8.3, the
  `key_of_ns_entity` step); C3 (§4.3); C4 (§5.3, §8.3, the def_pos decoder); C5
  (§0 example, §4.5, §8.1, §8.2, §9 step 0); C6 (§7 landing and restart
  rules; the staging is D22); C8 (§3.1, §4.1, §4.3, §8.1); C10 (§5.2,
  including the recorded scan); C11 (§9 stage B); C12 (§5.2; the skill
  reference via O4); the protocol checks (§3.1, §5.1, §8.2, §8.3); C15-a
  (§3.2, §3.3).
- Round 3 owner rulings: O1 adopted, each callback owns its catalog and there
  is no installation record (D1, D11, D13, §4.1–4.3; `new ()` allocates
  minimally, the author's recommendation acknowledged by the owner); O2
  delegated to the author and adopted (D20, §8.4); O3 delegated to the author:
  `IsabellePosition.from_def_pos` (§5.3); O4 approved, all three document
  edits (§9); P1 adopted (§3.3); P2 adopted (§5.3); P3 the author's call,
  adopted with R12's `(digest, uk)` shape (§0, §5.4); P4 adopted (D22).
  Releasing is not this plan's business.
- Round 3 items left to the author, applied: R1 (§4.5, §9 step 0); R2 (§3.2,
  §4.4, §8.3); R3 (§4.4, §9 stage B); R4 (§5.3, §8.3); R5 (§0, §5.3, §8.3, §9
  stage B); R6 (§0, §8.1, §8.2, §8.3); R7 (§3.1, §4.1); R8 (§7); R9 (§7, §8.4);
  R11 (§5.2); R12 (§0, §5.4, §8.5); R13 (§5.4, §6); R14 (§5.2, §9); R15 (D13,
  §4.3, §9 stage headers); J1 (§5.3). Decided this round: the resolver returns
  `SOME`, not C2's `NONE`, for a static fact asked as THEOREM_COLLECTION
  (unobservable, §4.4); PlainAgent never queries METHOD (§7).
- Rejected by the round 2 judge: index-range validation (no producer of a bad
  index; failures already loud); `_derived_topk` order dependence
  (hypothetical); a per-reply catalog length (equals `synced_length +
  len(entries)`); a lazy uk in the resolver (splits one SOME/NONE rule in two);
  deleting `Query_Tool_Test.thy` (out of scope, owner's call).
- Rejected by the round 3 judge: PlainAgent's METHOD display (PlainAgent
  cannot request METHOD); concealed and hidden names as a separate cause
  (already covered by the infra filter; the remaining kept-constant case is in
  D20); an explicit `Facts.is_dynamic` check making a static fact asked as
  THEOREM_COLLECTION `NONE` (unobservable, and it breaks the equivalence with
  `universal_key_and_name_of` that §8.3 tests); six new exported by-name
  functions instead of extending the existing six (same behaviour, doubled
  API); a nested sort key `(-score, tie_break_key(uk))` (replaced by the
  two-pass shape; measured 45–50% slower than a flat key at the site that
  sorts every entry); the evidence that `Minilang_AoA.thy` defines a locale,
  lemmas and a constant (lines 79–272 are one nested comment).
- Rev 6 (owner ruling, 2026-10-27): stage A and D18's tie-break are dropped;
  the history-dependent order of equal-score candidates after stage C is
  accepted (D18, D22, §5.4, §8.4); an index list keeps ML's result order and
  is never sorted (§4.1, §5.4). Stage A had been implemented and tested;
  it was removed from the working tree before landing. The measurements on
  cslh19 (Python 3.13, load ≈ 7.6; 111,467 theorem keys; minimum of 9 runs):
  - `sorted(candidates, key=tie_break_key)`: 79–84 ms. Of this, the blake2b
    digests take 27 ms, the key calls and tuples 6 ms more, and sorting the
    ready tuples 35 ms. A plain `sorted(uks)` takes 20 ms.
  - The pattern-only path's extra tie sort: 83–87 ms, beside 8 ms for today's
    score sort.
  - Alternatives measured: a `digest + uk` bytes key, 57 ms (same order); a
    tie-break order kept in the mirror, 61 ms once per kind per `call_command`
    and 5 ms per whole-kind query; `heapq.nsmallest(20, …)`, 31 ms.
  On this machine (Python 3.12) the full sort took 146–166 ms.
