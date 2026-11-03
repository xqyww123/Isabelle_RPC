(*
  Parts 1-2: the two measurements the fix plan (§A.9) requires to be re-derived
  rather than quoted.  Part 3: a theory from a heap carries no constituents cache.
  Part 4: experience_constituents keeps only the maximal constituent, here the
  unfinished theory.  All are pinned as assertions: batch output is not shown by
  `isabelle build`, so a number that is only printed is a number nobody reads.
*)
theory Test_Name_Spaces
  imports Isabelle_RPC.Remote_Procedure_Calling "HOL-Library.Multiset"
begin

definition rpc_test_dep :: "nat \<Rightarrow> nat" where "rpc_test_dep n = Suc n"

ML \<open>
local

val context = Context.Theory \<^theory>

(* 1. hash_of_long prefers Build's registry; key_of_ns_entity keeps using
      resolve_theory.  Over Main's cone the two must name the same theory value —
      if they ever did not, one long name would carry two content hashes.
      Measured 2026-08-12: 99 theories, 0 disagreements. *)
val main_cone = Theory.nodes_of \<^theory>\<open>Main\<close> |> map Context.theory_long_name

val disagreements =
  filter (fn long =>
    case Build.lookup_theory long of
      NONE => true
    | SOME thy =>
        Context.theory_identifier thy
          <> Context.theory_identifier (Theory_Hash.resolve_theory context long))
  main_cone

val _ =
  if null disagreements then ()
  else error ("Test_Name_Spaces: Build and resolve_theory disagree on " ^
              string_of_int (length disagreements) ^ " of " ^
              string_of_int (length main_cone) ^ " theories of Main's cone: " ^
              commas_quote disagreements)

(* 2. compute_constituents keeps one `seen` table per name space.  A single shared
      table would be wrong for any name carried by both spaces: whichever the walk
      met first would suppress the other.  Measured 2026-08-12 over
      HOL-Library.Multiset: Quickcheck_Exhaustive.unknown, Product_Type.prod,
      Sum_Type.sum, Int.int. *)
val multiset = \<^theory>\<open>Multiset\<close>
val shared =
  inter (op =)
    (Name_Space.get_names (Consts.space_of (Sign.consts_of multiset)))
    (Name_Space.get_names (Sign.type_space multiset))

val _ =
  if length shared = 4 then ()
  else error ("Test_Name_Spaces: " ^ string_of_int (length shared) ^
              " names are carried by both the constant and the type space of " ^
              "HOL-Library.Multiset, not the 4 measured: " ^ commas_quote shared)

(* 3. A theory from a pre-built heap must carry NO constituents cache.  This is
      what Cache_Scope's `empty = No_Cache` buys: THEORY_DATA'_ARGS' empty is one
      shared value, so a Cache-valued default would hand every theory of the image
      the same unpartitioned cache. *)
val _ =
  if is_none (Universal_Key.cache_scope_id \<^theory>\<open>List\<close>) then ()
  else error "Test_Name_Spaces: a theory loaded from the heap carries a constituents cache"

(* 4. experience_constituents keeps only the maximal constituent theories, resolved
      against the context.  The unfinished theory is in no registry (Build commits
      a theory only when its ROOT theories section finishes, build.ML:185-187 in
      schedule_theories), so a registry lookup cannot place it above HOL.Nat and
      keeps both. *)
val _ =
  (case Context_Callbacks.experience_constituents (Context.Proof \<^context>)
          ["rpc_test_dep (Suc ?n)"] of
    [(name, _)] =>
      if name = Context.theory_long_name \<^theory> then ()
      else error ("Test_Name_Spaces: the maximal constituent is " ^ quote name)
  | cs => error ("Test_Name_Spaces: not one maximal constituent: " ^ commas_quote (map #1 cs)))

in
val _ = writeln "Test_Name_Spaces: all checks passed"
end
\<close>

text \<open>Part 5: entry_of_name keeps an entity's raw position, so a caller can resolve a
  position that carries only a PIDE command id; pack_pos flattens it on the wire, and never
  raises while a reply is written, whatever file the position names.\<close>

ML \<open>
local

fun assert msg b = if b then () else error ("Test_Name_Spaces, part 5: " ^ msg)

(* facts at chosen positions; not visible, so no report names a command id that does not exist *)
val context5 =
  let
    fun note (name, pos) ctxt =
      #2 (Proof_Context.note_thms "" ((Binding.make (name, pos), []), [([@{thm refl}], [])]) ctxt)
  in
    Context_Position.set_visible false \<^context>
    |> fold note
      [("rpc_pos_id", Position.id "4711"),
       ("rpc_pos_id_only", Position.id_only "4712"),
       ("rpc_pos_undef_var", Position.file "$NO_SUCH_VAR/A.thy"),
       ("rpc_pos_colon", Position.file "/tmp/run:1/A.thy")]
    |> Context.Proof
  end

(* 5a. the raw position survives the resolver *)
val _ =
  (case Context_Callbacks.entry_of_name context5 (Universal_Key.TheoremK, "rpc_pos_id") of
    SOME {pos, ...} =>
      assert ("the command id is kept, not " ^ \<^make_string> (Position.id_of pos))
        (Position.id_of pos = SOME "4711")
  | NONE => assert "rpc_pos_id resolves" false)

(* the dynamic-fact case must really be one *)
val _ =
  assert "algebra_simps is a dynamic fact"
    (Facts.is_dynamic (Proof_Context.facts_of (Context.proof_of context5))
      (Name_Space.intern (Facts.space_of (Proof_Context.facts_of (Context.proof_of context5)))
        "algebra_simps"))

(* 5b. the round trip through Python: one line per item, "None" or "file|line|offset" *)
val unpack5 : Context_Callbacks.context_unpacker = fn src =>
  let val (_, src') = MessagePackBinIO.Unpack.unpackInt src in (context5, src') end

val items =
  [(1, \<^const_name>\<open>rpc_test_dep\<close>), (2, \<^unchecked_name>\<open>HOL.refl\<close>),
   (2, "algebra_simps(1)"), (2, "rpc_pos_id"), (2, "rpc_pos_id_only"),
   (2, "rpc_pos_undef_var"), (2, "rpc_pos_colon"), (2, "rpc_pos_no_such_fact")]

val replies =
  Run_Python.run_with [Context_Callbacks.make_entries_of_names_callback unpack5]
    (cat_lines
      ["items = [" ^ commas (map (fn (k, n) => "(" ^ string_of_int k ^ ", " ^ quote n ^ ")") items) ^ "]",
       "es = await connection.callback('Context.entries_of_names', (0, items))",
       "return '\\n'.join('None' if e is None else f'{e[2][0]}|{e[2][1]}|{e[2][2]}' for e in es)"])
  |> the_default "" |> split_lines

val _ = assert ("one reply per item: " ^ commas_quote replies) (length replies = length items)
val reply = nth replies
val (dep, refl, simp_member, at_id) = (reply 0, reply 1, reply 2, reply 3)
val (at_id_only, undef_var, colon, no_such) = (reply 4, reply 5, reply 6, reply 7)

fun fields s =
  (case space_explode "|" s of
    [f, l, o'] => (f, the_default ~1 (Int.fromString l), the_default ~1 (Int.fromString o'))
  | _ => error ("Test_Name_Spaces, part 5: not a position reply: " ^ quote s))

(* an absolute, expanded file (no ~~ and no $), a real line and offset, checked by shape *)
fun is_resolved suffix s =
  let val (f, l, o') = fields s
  in String.isPrefix "/" f andalso not (String.isSubstring "$" f) andalso
     String.isSuffix suffix f andalso l > 0 andalso o' > 0 end

in
val _ = assert ("this theory's constant: " ^ dep) (is_resolved "/Test_Name_Spaces.thy" dep)
val _ = assert ("HOL.refl: " ^ refl) (is_resolved "/src/HOL/HOL.thy" refl)
val _ = assert ("a dynamic-fact member has no position: " ^ simp_member) (simp_member = "|0|0")
val _ = assert ("an id position packs with no file: " ^ at_id) (#1 (fields at_id) = "")
val _ = assert ("an id-only position packs as unknown: " ^ at_id_only) (at_id_only = "|0|0")
val _ = assert ("an undefined variable packs as no file: " ^ undef_var) (#1 (fields undef_var) = "")
val _ = assert ("an illegal character packs as no file: " ^ colon) (#1 (fields colon) = "")
val _ = assert ("an unresolved name gives None: " ^ no_such) (no_such = "None")
val _ = writeln "Test_Name_Spaces, part 5: all checks passed"
end
\<close>

end
