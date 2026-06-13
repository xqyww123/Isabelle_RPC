(*
  Universal Keys
  ==============

  A universal key is a Word8Vector.vector that uniquely identifies an Isabelle
  entity (theory, constant, theorem, type, class, or locale) across sessions.
  Keys are used as persistent identifiers in external stores (e.g. embedding
  databases) so that entries survive Isabelle restarts.

  Key format
  ----------

  Theory keys are just the 16-byte theory hash from Theory_Hash.hash_of.

  Entity keys have the layout:

    <theory_hash (16 bytes)> <tag (1 byte)> <entity (variable)>

  - theory_hash: 16-byte hash from Theory_Hash.hash_of, identifying the
    theory that defines the entity.  Works for both heap and non-heap theories.
    Exception: for theorem/rule entities the defining theory is in general
    unrecoverable (empirically: the name hint may be absent, the certificate
    theory is overwritten by whoever retrieves the thm, the derivation id is
    <none>, the tags carry no provenance).  Their theory_hash is instead the
    XOR of the theory hashes of the proposition's *constituent* theories —
    the defining theories of all constants and type constructors occurring in
    Thm.prop_of (the same term thm128 digests) — making the key computable
    from the thm alone and stable along whatever path the thm is reached.
    See "Constituent theories" in the implementation.
  - tag: 1-byte entity kind discriminator:
      0x01 = Constant, 0x02 = Theorem,
      0x03 = Type, 0x04 = Class, 0x05 = Locale,
      0x06 = Theorem_Collection, 0x07 = Method,
      0x12 = Introduction_Rule, 0x22 = Elimination_Rule,
      0x32 = Induction_Rule, 0x42 = Case_Split_Rule
  - entity: variable-length payload identifying the entity within its theory.

  Key sizes
  ---------

  - Theory keys:           16 bytes  (hash only)
  - Namespace entity keys: 17 + |name| bytes  (constant, type, class, locale,
                                                named_theorems, method)
  - Theorem keys:          32 bytes  (16 + 1 + 15, always)
  - Intro/Elim rule keys:  32 bytes  (same layout as theorem keys)
  - Induct/Cases rule keys: 32 bytes (same layout as theorem keys)

  Theorem keys (and introduction/elimination rule keys) use the first 15 bytes
  of the 128-bit term digest (Term_Digest.thm128) as entity payload,
  guaranteeing a fixed 32-byte key.

  Theorem/rule theory keys: the XOR scheme
  -----------------------------------------

  This is the one place where the 16-byte prefix is NOT a real theory hash, so
  the consequences are spelled out here:

  - Constituent theories.  The prefix is the XOR of the theory hashes of the
    proposition's constituent theories — the defining theory of every constant
    and type constructor in Thm.prop_of.  A constant/type's defining theory is
    taken as the LEADING QUALIFIER of its fully qualified name (HOL.conj -> HOL,
    Groups.plus_class.plus -> Groups); Pure's primitive types (fun, prop, ...)
    carry no qualifier and belong to Pure.  No name-space lookup is involved, so
    the key depends only on the thm, not on the context it is reached from.
    (See compute_constituents / theory_short_of below.)

  - LSB / WIP.  Hashes are XORed in full; the result's byte-0 LSB is then OR'd
    with the constituents' LSBs, so a key is WIP iff any constituent theory is
    WIP.  (Masking byte 0 before XOR would be redundant: the final OR dominates
    its parity.)  An empty constituent set yields the all-zero prefix.

  - Addressing (load-bearing for the Python store).  A namespace entity's prefix
    IS its defining theory's hash, so "which theory owns this entry" is read off
    the prefix.  A theorem/rule prefix is an XOR PSEUDO-theory that matches no
    real theory, so theory membership — for deletion and for hash-change
    migration — must instead be decided from the constituent list stored in the
    record (carried out of ML as build_entries' provenance).  Prefix range scans
    (e.g. migrating a theory's entries) must therefore SKIP theorem/rule keys and
    handle them by recomputing the XOR from the constituent list.

  - Degeneration.  A thm with a single constituent theory T has a prefix equal
    to T's hash byte-for-byte, indistinguishable by prefix alone from T's own
    keys.  Operations that range over a theory's keys by prefix must therefore
    discriminate theorem/rule keys (by tag/length), never trust the prefix.
*)
signature UNIVERSAL_KEY = sig

type context_unpacker = Context.generic MessagePackBinIO.Unpack.unpacker
val static_context_unpacker : Context.generic -> context_unpacker

eqtype universal_key
type fully_quantified_name = string
type theory_long_name = string

datatype entity_kind = ConstantK | TheoremK | TypeK | ClassK | LocaleK
                     | Theorem_CollectionK | MethodK
                     | IntroductionRuleK | EliminationRuleK
                     | InductionRuleK | CaseSplitRuleK

datatype entity =
      Constant of fully_quantified_name
    | Theorem  of thm
    | Named_Theorem of fully_quantified_name
    | Type     of fully_quantified_name
    | Class    of fully_quantified_name
    | Locale   of fully_quantified_name
    (* NB: Theorem_Collection is a named-collection entity (tag 0x06) covering
       any dynamic fact (named_theorems and raw add_thms_dynamic collections
       like derivative_eq_intros), distinct from Named_Theorem (singular) above
       which is the name-carrying variant of a Theorem (tag 0x02). *)
    | Theorem_Collection of fully_quantified_name
    | Method   of fully_quantified_name
    | Introduction_Rule of thm
    | Named_Introduction_Rule of fully_quantified_name
    | Elimination_Rule of thm
    | Named_Elimination_Rule of fully_quantified_name
    | Induction_Rule of thm
    | Named_Induction_Rule of fully_quantified_name
    | Case_Split_Rule of thm
    | Named_Case_Split_Rule of fully_quantified_name

val hasher : universal_key -> word

structure UK_Table : HASH_TABLE where type key = universal_key

val key_of_theory'  : theory -> universal_key
val key_of_theory   : Context.generic -> xstring -> universal_key * string
val key_of_constant : Context.generic -> xstring -> universal_key * string
type thm_uk_cache
val new_thm_uk_cache : unit -> thm_uk_cache
val key_of_theorem  : thm_uk_cache option -> Context.generic -> xstring
                    -> universal_key * thm * bool * string
val key_of_theorem' : thm_uk_cache option -> Context.generic -> thm -> universal_key
val key_of_type     : Context.generic -> xstring -> universal_key * string
val key_of_class    : Context.generic -> xstring -> universal_key * string
val key_of_locale   : Context.generic -> xstring -> universal_key * string
val key_of_theorem_collection : Context.generic -> xstring -> universal_key * string
val key_of_method   : Context.generic -> xstring -> universal_key * string
val key_of_introduction_rule  : thm_uk_cache option -> Context.generic -> xstring
                              -> universal_key * string
val key_of_introduction_rule' : thm_uk_cache option -> Context.generic -> thm -> universal_key
val key_of_elimination_rule   : thm_uk_cache option -> Context.generic -> xstring
                              -> universal_key * string
val key_of_elimination_rule'  : thm_uk_cache option -> Context.generic -> thm -> universal_key
val key_of_induction_rule     : thm_uk_cache option -> Context.generic -> xstring
                              -> universal_key * string
val key_of_induction_rule'    : thm_uk_cache option -> Context.generic -> thm -> universal_key
val key_of_case_split_rule    : thm_uk_cache option -> Context.generic -> xstring
                              -> universal_key * string
val key_of_case_split_rule'   : thm_uk_cache option -> Context.generic -> thm -> universal_key
val key_of          : thm_uk_cache option -> Context.generic -> entity -> universal_key
(* key_of'' pre-captures name spaces from the context, returning a closure.
   Use when computing keys for many entities from the same context. *)
val key_of''        : thm_uk_cache option -> Context.generic -> entity -> universal_key

(* The 15-byte entity payload of theorem keys (tag 0x02), as a standalone
   content fingerprint: thm_digest15 computes it for an arbitrary thm (no name
   hint or theory resolution involved), theorem_key_digest extracts it back
   from a theorem universal key (NONE for any other key shape).  Two keys'
   payloads agree iff the underlying propositions have equal thm128 prefixes.
   The payload compares cleanly across theories; the 16-byte prefix does not
   (it is an XOR pseudo-theory — use constituents_of for theory membership).
   Single source of truth for the payload layout; keep in sync with
   build_key/ent_digest128_15 below. *)
val thm_digest15        : thm -> Word8Vector.vector
val theorem_key_digest  : universal_key -> Word8Vector.vector option

(* Constituent theories of a thm's proposition: the XOR theory hash (the
   16-byte theory-key component of theorem/rule keys) together with the
   sorted (theory long name, theory hash) list it was XORed from. *)
type constituent = theory_long_name * Theory_Hash.hash
val thm_constituents : Context.generic -> thm -> Theory_Hash.hash * constituent list
(* Constituent list of a theorem/rule key built earlier in this session
   (populated as a side effect of key construction); NONE for any other key
   shape, or a thm/rule key not yet built in this session. *)
val constituents_of : universal_key -> constituent list option

val make_universal_key_callback  : context_unpacker -> Remote_Procedure_Calling.callback'
val make_universal_key_callback' : thm_uk_cache option -> context_unpacker -> Remote_Procedure_Calling.callback'

val pack_universal_key : universal_key MessagePackBinIO.Pack.packer
val unpack_universal_key : universal_key MessagePackBinIO.Unpack.unpacker

val pack_entity_kind : entity MessagePackBinIO.Pack.packer
val pack_entity_kind' : entity_kind MessagePackBinIO.Pack.packer
val unpack_entity_kind : entity_kind MessagePackBinIO.Unpack.unpacker
val pack_entity : entity MessagePackBinIO.Pack.packer
val unpack_entity : entity MessagePackBinIO.Unpack.unpacker

end

structure Universal_Key : UNIVERSAL_KEY = struct

type context_unpacker = Context.generic MessagePackBinIO.Unpack.unpacker

fun static_context_unpacker (ctx: Context.generic) : context_unpacker =
  fn src => let val (_, src') = MessagePackBinIO.Unpack.unpackUnit src
            in (ctx, src') end

type fully_quantified_name = string
type theory_long_name = string
datatype entity_kind = ConstantK | TheoremK | TypeK | ClassK | LocaleK
                     | Theorem_CollectionK | MethodK
                     | IntroductionRuleK | EliminationRuleK
                     | InductionRuleK | CaseSplitRuleK
datatype entity =
      Constant of fully_quantified_name
    | Theorem  of thm
    | Named_Theorem of fully_quantified_name
    | Type     of fully_quantified_name
    | Class    of fully_quantified_name
    | Locale   of fully_quantified_name
    (* NB: Theorem_Collection is a named-collection entity (tag 0x06) covering
       any dynamic fact (named_theorems and raw add_thms_dynamic collections
       like derivative_eq_intros), distinct from Named_Theorem (singular) above
       which is the name-carrying variant of a Theorem (tag 0x02). *)
    | Theorem_Collection of fully_quantified_name
    | Method   of fully_quantified_name
    | Introduction_Rule of thm
    | Named_Introduction_Rule of fully_quantified_name
    | Elimination_Rule of thm
    | Named_Elimination_Rule of fully_quantified_name
    | Induction_Rule of thm
    | Named_Induction_Rule of fully_quantified_name
    | Case_Split_Rule of thm
    | Named_Case_Split_Rule of fully_quantified_name
type caching_key = entity * theory_long_name
type universal_key = Word8Vector.vector
val hasher = Hashers.bitvec

val resolve_theory = Theory_Hash.resolve_theory

(* --- Cache --- *)

structure CacheTab = Hash_Table(struct
  type key = caching_key
  fun hash (Constant name, thy) =
        Word.xorb (0w1, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Theorem thm, thy) =
        Word.xorb (Term_Digest.digest128_hasher (Term_Digest.thm128 thm),
                   Hashers.string thy)
    | hash (Named_Theorem name, thy) =
        Word.xorb (0w3, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Type name, thy) =
        Word.xorb (0w4, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Class name, thy) =
        Word.xorb (0w5, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Locale name, thy) =
        Word.xorb (0w6, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Theorem_Collection name, thy) =
        Word.xorb (0w7, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Method name, thy) =
        Word.xorb (0w8, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Introduction_Rule thm, thy) =
        Word.xorb (0wx12, Word.xorb (Term_Digest.digest128_hasher (Term_Digest.thm128 thm),
                   Hashers.string thy))
    | hash (Named_Introduction_Rule name, thy) =
        Word.xorb (0wx13, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Elimination_Rule thm, thy) =
        Word.xorb (0wx22, Word.xorb (Term_Digest.digest128_hasher (Term_Digest.thm128 thm),
                   Hashers.string thy))
    | hash (Named_Elimination_Rule name, thy) =
        Word.xorb (0wx23, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Induction_Rule thm, thy) =
        Word.xorb (0wx32, Word.xorb (Term_Digest.digest128_hasher (Term_Digest.thm128 thm),
                   Hashers.string thy))
    | hash (Named_Induction_Rule name, thy) =
        Word.xorb (0wx33, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Case_Split_Rule thm, thy) =
        Word.xorb (0wx42, Word.xorb (Term_Digest.digest128_hasher (Term_Digest.thm128 thm),
                   Hashers.string thy))
    | hash (Named_Case_Split_Rule name, thy) =
        Word.xorb (0wx43, Word.xorb (Hashers.string name, Hashers.string thy))
  fun eq ((Constant n1, t1), (Constant n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Theorem thm1, t1), (Theorem thm2, t2)) =
        Thm.eq_thm (thm1, thm2) andalso t1 = t2
    | eq ((Named_Theorem n1, t1), (Named_Theorem n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Type n1, t1), (Type n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Class n1, t1), (Class n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Locale n1, t1), (Locale n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Theorem_Collection n1, t1), (Theorem_Collection n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Method n1, t1), (Method n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Introduction_Rule thm1, t1), (Introduction_Rule thm2, t2)) =
        Thm.eq_thm (thm1, thm2) andalso t1 = t2
    | eq ((Named_Introduction_Rule n1, t1), (Named_Introduction_Rule n2, t2)) =
        n1 = n2 andalso t1 = t2
    | eq ((Elimination_Rule thm1, t1), (Elimination_Rule thm2, t2)) =
        Thm.eq_thm (thm1, thm2) andalso t1 = t2
    | eq ((Named_Elimination_Rule n1, t1), (Named_Elimination_Rule n2, t2)) =
        n1 = n2 andalso t1 = t2
    | eq ((Induction_Rule thm1, t1), (Induction_Rule thm2, t2)) =
        Thm.eq_thm (thm1, thm2) andalso t1 = t2
    | eq ((Named_Induction_Rule n1, t1), (Named_Induction_Rule n2, t2)) =
        n1 = n2 andalso t1 = t2
    | eq ((Case_Split_Rule thm1, t1), (Case_Split_Rule thm2, t2)) =
        Thm.eq_thm (thm1, thm2) andalso t1 = t2
    | eq ((Named_Case_Split_Rule n1, t1), (Named_Case_Split_Rule n2, t2)) =
        n1 = n2 andalso t1 = t2
    | eq _ = false
end)

structure UK_Table = Hash_Table(struct
  type key = universal_key
  val hash = hasher
  val eq = op = : universal_key * universal_key -> bool
end)

(* --- Key cache --- *)

val cache : universal_key CacheTab.table = CacheTab.empty 1024
val cache_lock = Synchronized.var "Universal_Key.cache" ()

fun cached_key ck compute =
  Synchronized.change_result cache_lock (fn () =>
    case CacheTab.lookup cache ck of
      SOME k => (k, ())
    | NONE => let val k = compute ()
              in CacheTab.update cache (ck, k); (k, ()) end)

(* --- Thm prop cache (for theorems without derivation_id) --- *)

type thm_uk_cache = (term * universal_key) Net.net Synchronized.var

fun new_thm_uk_cache () : thm_uk_cache =
  Synchronized.var "thm_uk_cache" Net.empty

(* Entries are discriminated by the key's tag byte as well as the prop: the
   same proposition may legitimately be keyed as a theorem (0x02) and as one
   or more rule kinds (0x12/0x22/0x32/0x42) in the same cache. *)
fun inet_lookup (cache : thm_uk_cache) (tag : Word8.word) (prop : term) : universal_key option =
  List.find (fn (p, k) => Word8Vector.sub (k, 16) = tag andalso p aconv prop)
    (Net.match_term (Synchronized.value cache) prop)
  |> Option.map snd

fun inet_store (cache : thm_uk_cache) (prop : term) (k : universal_key) : unit =
  Synchronized.change cache
    (Net.insert_term_safe
       (fn ((p1, k1), (p2, k2)) =>
          p1 aconv p2 andalso Word8Vector.sub (k1, 16) = Word8Vector.sub (k2, 16))
       (prop, (prop, k)))

fun cached_thm_key (cache : thm_uk_cache option) (tag : Word8.word) (thm : thm)
                   (compute : unit -> universal_key) =
  case cache of
    NONE => compute ()
  | SOME c =>
      let val prop = Thm.prop_of thm
      in case inet_lookup c tag prop of
           SOME k => k
         | NONE => let val k = compute ()
                   in inet_store c prop k; k end
      end

(* --- Key construction helpers --- *)

type entity_writer = int * (Word8Array.array -> int -> unit)

fun ent_string (s : string) : entity_writer =
  (String.size s, fn buf => fn off =>
    Word8Array.copyVec {src = Byte.stringToBytes s, dst = buf, di = off})

fun ent_digest128_15 (d : Term_Digest.digest128) : entity_writer =
  (15, fn buf => fn off =>
    let val tmp = Term_Digest.digest128_to_array d
    in Word8ArraySlice.copy {
         src = Word8ArraySlice.slice (tmp, 0, SOME 15),
         dst = buf, di = off}
    end)

fun build_key (thy_hash : Theory_Hash.hash) (tag : Word8.word)
              ((ent_len, write_ent) : entity_writer) : universal_key =
  let val buf = Word8Array.array (16 + 1 + ent_len, 0w0)
  in
    Word8Array.copyVec {src = thy_hash, dst = buf, di = 0};
    Word8Array.update (buf, 16, tag);
    write_ent buf 17;
    Word8Array.vector buf
  end

(* Standalone theorem-key payload (see signature comment): the first 15 bytes
   of thm128, i.e. bytes 17..31 of a full theorem key, without prefix or tag. *)
fun thm_digest15 thm : Word8Vector.vector =
  let val arr = Term_Digest.digest128_to_array (Term_Digest.thm128 thm)
  in Word8Vector.tabulate (15, fn i => Word8Array.sub (arr, i)) end

fun theorem_key_digest (uk : universal_key) : Word8Vector.vector option =
  if Word8Vector.length uk = 32 andalso Word8Vector.sub (uk, 16) = 0wx02
  then SOME (Word8Vector.tabulate (15, fn i => Word8Vector.sub (uk, 17 + i)))
  else NONE

(* Proof-local facts have theory_long_name = "" in their name space entry.
   Fall back to the context's theory in that case. *)
fun default_thy_long_name context "" = Context.theory_long_name (Context.theory_of context)
  | default_thy_long_name _ name = name

(* --- Constituent theories of a theorem (XOR theory key) ---

   The defining theory of a thm is in general unrecoverable (see the signature
   header).  Instead, the 16-byte theory-key component of theorem/rule keys is
   the XOR of the theory hashes of the proposition's constituent theories: the
   defining theories of all constants and type constructors occurring in
   Thm.prop_of (the same term Term_Digest.thm128 digests).  The key is thus
   computable from the thm alone, identical along whatever path the thm is
   reached, and changes whenever any constituent theory's content changes
   (automatic invalidation of derived records).

   LSB convention: hashes are XORed in full and the result's byte-0 LSB is then
   OR'd with the constituents' LSBs, so a key is WIP iff any constituent theory
   is WIP.  (The final OR dominates the LSB's XOR parity, so masking byte 0
   before XOR would be redundant — see the fold in compute_constituents.)  A
   proposition with no constituents yields the all-zero hash (the empty XOR).

   The key prefix is therefore an XOR pseudo-theory, not a real theory hash:
   theory membership (deletion, hash-change migration) is decided from the
   constituent list stored in the record, never from the prefix.  See the
   signature header's "XOR scheme" section. *)

type constituent = theory_long_name * Theory_Hash.hash

val constituents_lock = Synchronized.var "Universal_Key.constituents" ()

structure Digest_Tab = Hash_Table(struct
  type key = Term_Digest.digest128
  val hash = Term_Digest.digest128_hasher
  val eq = op = : Term_Digest.digest128 * Term_Digest.digest128 -> bool
end)

(* thm128 digest -> (XOR theory hash, sorted constituent list) *)
val constituents_cache : (Theory_Hash.hash * constituent list) Digest_Tab.table =
  Digest_Tab.empty 1024

(* theorem/rule universal key -> sorted constituent list, for record writers *)
val constituents_registry : constituent list UK_Table.table = UK_Table.empty 1024

(* The defining theory of a constant or type constructor is the leading
   qualifier of its fully qualified name (HOL.conj -> HOL,
   Groups.plus_class.plus -> Groups).  Pure's primitive types (fun, prop,
   itself, idt, ...) carry no qualifier; they belong to Pure. *)
fun theory_short_of name =
  case Long_Name.explode name of
    seg :: _ :: _ => seg
  | _ => "Pure"

fun compute_constituents (context : Context.generic) (prop : term)
    : Theory_Hash.hash * constituent list =
  let
    (* constituent theories, keyed by short name (unique within a runtime);
       short-name resolution + hashing is memoized inside Theory_Hash. *)
    val thys : constituent Strhashtab.table = Strhashtab.empty 16

    fun add name =
      let val short = theory_short_of name
      in if Strhashtab.defined thys short then ()
         else Strhashtab.update thys (short, Theory_Hash.hash_of_short context short)
      end

    (* NB: Term.Type qualified — the bare constructor name is shadowed by
       this structure's entity datatype. *)
    fun walk_typ (Term.Type (c, Ts)) = (add c; List.app walk_typ Ts)
      | walk_typ _ = ()
    fun walk (Const (c, T)) = (add c; walk_typ T)
      | walk (Free (_, T)) = walk_typ T
      | walk (Var (_, T)) = walk_typ T
      | walk (Abs (_, T, t)) = (walk_typ T; walk t)
      | walk (t $ u) = (walk t; walk u)
      | walk (Bound _) = ()
    val _ = walk prop

    (* XOR all 16 bytes uniformly; the final `acc[0] |= wip` below forces the
       LSB to the OR of constituents' LSBs, which dominates the LSB's XOR
       parity (parity = 1 implies some LSB = 1 implies wip = 1), so masking
       byte 0's LSB before XORing would be redundant. *)
    val acc = Word8Array.array (16, 0w0)
    val wip = Strhashtab.fold (fn (_, (_, h)) => fn wip =>
        let
          fun loop i = if i >= 16 then ()
            else (Word8Array.update (acc, i,
                    Word8.xorb (Word8Array.sub (acc, i), Word8Vector.sub (h, i)));
                  loop (i + 1))
        in loop 0; Word8.orb (wip, Word8.andb (Word8Vector.sub (h, 0), 0w1)) end)
      thys (0w0 : Word8.word)
    val _ = Word8Array.update (acc, 0, Word8.orb (Word8Array.sub (acc, 0), wip))
    val provenance =
      Strhashtab.fold (fn (_, c) => fn cs => c :: cs) thys []
      |> sort (string_ord o apply2 #1)
  in (Word8Array.vector acc, provenance) end

fun thm_constituents (context : Context.generic) (thm : thm)
    : Theory_Hash.hash * constituent list =
  let val d = Term_Digest.thm128 thm
  in
    case Synchronized.change_result constituents_lock
           (fn () => (Digest_Tab.lookup constituents_cache d, ())) of
      SOME r => r
    | NONE =>
        let
          val r = compute_constituents context (Thm.prop_of thm)
          val _ = Synchronized.change_result constituents_lock
                    (fn () => (Digest_Tab.update constituents_cache (d, r), ()))
        in r end
  end

fun constituents_of (uk : universal_key) : constituent list option =
  Synchronized.change_result constituents_lock
    (fn () => (UK_Table.lookup constituents_registry uk, ()))

(* Unified key builder for theorem/rule keys: all tags, named or anonymous. *)
fun build_thm_key (cache : thm_uk_cache option) (context : Context.generic)
                  (tag : Word8.word) (thm : thm) : universal_key =
  cached_thm_key cache tag thm (fn () =>
    let
      val (thy_hash, prov) = thm_constituents context thm
      val uk = build_key thy_hash tag (ent_digest128_15 (Term_Digest.thm128 thm))
      val _ = Synchronized.change_result constituents_lock
                (fn () => (UK_Table.update constituents_registry (uk, prov), ()))
    in uk end)

(* --- Namespace-based entities (constant, type, class, locale) --- *)

fun key_of_ns_entity tag make_ck space context xname =
  let
    val fq_name = Name_Space.intern space xname
    val ns_entry = Name_Space.the_entry space fq_name
    val thy_long_name = default_thy_long_name context (#theory_long_name ns_entry)
    val ck = (make_ck fq_name, thy_long_name)
    val uk =
      cached_key ck (fn () =>
        build_key (Theory_Hash.hash_of (resolve_theory context thy_long_name))
                  tag (ent_string fq_name))
  in (uk, fq_name) end

fun key_of_theory' thy = Theory_Hash.hash_of thy

fun key_of_theory context xname =
  let val thy = resolve_theory context xname
  in (key_of_theory' thy, Context.theory_long_name thy) end

fun key_of_constant context xname =
  let val space = Consts.space_of (Context.cases Sign.consts_of Proof_Context.consts_of context)
  in
    if Name_Space.declared space (Name_Space.intern space xname) then
      key_of_ns_entity 0wx01 Constant space context xname
    else
      Context.cases
        (fn _ => error ("Undefined constant: " ^ quote xname))
        (fn ctxt =>
          case Variable.lookup_fixed ctxt xname of
            SOME fq_name =>
              let val thy = Proof_Context.theory_of ctxt
              in (build_key (Theory_Hash.hash_of thy) 0wx01 (ent_string fq_name),
                  fq_name) end
          | NONE => error ("Undefined constant: " ^ quote xname))
        context
  end

fun key_of_type context =
  key_of_ns_entity 0wx03 Type
    (Context.cases Sign.type_space Proof_Context.type_space context)
    context

fun key_of_class context =
  key_of_ns_entity 0wx04 Class
    (Context.cases Sign.class_space Proof_Context.class_space context)
    context

fun key_of_locale context =
  key_of_ns_entity 0wx05 Locale
    (Locale.locale_space (Context.theory_of context))
    context

(* Theorem_Collection collections live in the fact name space (registered as a
   dynamic fact via Local_Theory.add_thms_dynamic). *)
fun key_of_theorem_collection context =
  key_of_ns_entity 0wx06 Theorem_Collection
    (Facts.space_of (Context.cases Global_Theory.facts_of Proof_Context.facts_of context))
    context

fun key_of_method context =
  key_of_ns_entity 0wx07 Method
    (Method.method_space context)
    context

(* --- Theorems --- *)

local
  fun parse_thm_xname xname =
    let val len = size xname
    in
      if len > 2 andalso String.sub (xname, len - 1) = #")"
      then case Substring.fields (fn c => c = #"(")
                  (Substring.full xname) of
          [base, idx_paren] =>
            let val idx_str = Substring.string
                  (Substring.trimr 1 idx_paren)
            in case Int.fromString idx_str of
                SOME i => (Substring.string base, SOME i)
              | NONE => (xname, NONE)
            end
        | _ => (xname, NONE)
      else (xname, NONE)
    end
in

fun key_of_theorem cache context =
  let
    val thy = Context.theory_of context
    val ctxt = Context.cases Proof_Context.init_global I context
    val facts = Proof_Context.facts_of ctxt
    val fact_space = Facts.space_of facts
    val global_facts = Global_Theory.facts_of thy
  in fn xname =>
    let
      val (base_name, idx_opt) = parse_thm_xname xname
      val full_name = Name_Space.intern fact_space base_name
      (* lookup doubles as the existence check *)
      val {thms, ...} =
        case Facts.lookup context facts full_name of
          SOME r => r
        | NONE => error ("Undefined fact: " ^ quote full_name)
      val thm = case (thms, idx_opt) of
          ([thm], NONE) => thm
        | ([thm], SOME _) => thm
        | (_ :: _, SOME i) =>
            if i >= 1 andalso i <= length thms
            then nth thms (i - 1)
            else error ("Theorem index " ^ Int.toString i ^
                        " out of range for " ^ full_name ^
                        " (has " ^ Int.toString (length thms) ^ " theorems)")
        | (_ :: _ :: _, NONE) =>
            error ("Fact " ^ full_name ^ " has " ^
                   Int.toString (length thms) ^
                   " theorems; specify an index like " ^
                   full_name ^ "(1)")
        | ([], _) => error ("No theorems in fact " ^ full_name)
      val thm = Thm.transfer thy thm
      val uk = build_thm_key cache context 0wx02 thm
      val is_global = Facts.defined global_facts full_name
    in (uk, thm, is_global, full_name) end
  end

end (* local parse_thm_xname *)

fun key_of_theorem' cache context thm = build_thm_key cache context 0wx02 thm

(* --- Introduction / Elimination rules --- *)
(* Same key layout as theorems (32 bytes) but with different tags. *)

local
fun key_of_rule tag cache context thm = build_thm_key cache context tag thm
in
val key_of_introduction_rule' = key_of_rule 0wx12
val key_of_elimination_rule'  = key_of_rule 0wx22
val key_of_induction_rule'    = key_of_rule 0wx32
val key_of_case_split_rule'   = key_of_rule 0wx42
end

fun key_of_introduction_rule cache context xname =
  let val (_, thm, _, full_name) = key_of_theorem cache context xname
  in (key_of_introduction_rule' cache context thm, full_name) end

fun key_of_elimination_rule cache context xname =
  let val (_, thm, _, full_name) = key_of_theorem cache context xname
  in (key_of_elimination_rule' cache context thm, full_name) end

fun key_of_induction_rule cache context xname =
  let val (_, thm, _, full_name) = key_of_theorem cache context xname
  in (key_of_induction_rule' cache context thm, full_name) end

fun key_of_case_split_rule cache context xname =
  let val (_, thm, _, full_name) = key_of_theorem cache context xname
  in (key_of_case_split_rule' cache context thm, full_name) end

fun key_of _     context (Constant name) = #1 (key_of_constant context name)
  | key_of cache context (Theorem thm) = key_of_theorem' cache context thm
  | key_of cache context (Named_Theorem name) = #1 (key_of_theorem cache context name)
  | key_of _     context (Type name) = #1 (key_of_type context name)
  | key_of _     context (Class name) = #1 (key_of_class context name)
  | key_of _     context (Locale name) = #1 (key_of_locale context name)
  | key_of _     context (Theorem_Collection name) = #1 (key_of_theorem_collection context name)
  | key_of _     context (Method name) = #1 (key_of_method context name)
  | key_of cache context (Introduction_Rule thm) = key_of_introduction_rule' cache context thm
  | key_of cache context (Named_Introduction_Rule name) = #1 (key_of_introduction_rule cache context name)
  | key_of cache context (Elimination_Rule thm) = key_of_elimination_rule' cache context thm
  | key_of cache context (Named_Elimination_Rule name) = #1 (key_of_elimination_rule cache context name)
  | key_of cache context (Induction_Rule thm) = key_of_induction_rule' cache context thm
  | key_of cache context (Named_Induction_Rule name) = #1 (key_of_induction_rule cache context name)
  | key_of cache context (Case_Split_Rule thm) = key_of_case_split_rule' cache context thm
  | key_of cache context (Named_Case_Split_Rule name) = #1 (key_of_case_split_rule cache context name)

fun key_of'' cache context =
  let
    val const_key  = key_of_constant context
    val thm_key    = key_of_theorem cache context
    val type_key   = key_of_type context
    val class_key  = key_of_class context
    val locale_key = key_of_locale context
    val theorem_collection_key = key_of_theorem_collection context
    val method_key = key_of_method context
  in fn (Constant name)      => #1 (const_key name)
      | (Theorem thm)        => key_of_theorem' cache context thm
      | (Named_Theorem name) => #1 (thm_key name)
      | (Type name)          => #1 (type_key name)
      | (Class name)         => #1 (class_key name)
      | (Locale name)        => #1 (locale_key name)
      | (Theorem_Collection name) => #1 (theorem_collection_key name)
      | (Method name)        => #1 (method_key name)
      | (Introduction_Rule thm) => key_of_introduction_rule' cache context thm
      | (Named_Introduction_Rule name) =>
          key_of_introduction_rule' cache context (#2 (thm_key name))
      | (Elimination_Rule thm) => key_of_elimination_rule' cache context thm
      | (Named_Elimination_Rule name) =>
          key_of_elimination_rule' cache context (#2 (thm_key name))
      | (Induction_Rule thm) => key_of_induction_rule' cache context thm
      | (Named_Induction_Rule name) =>
          key_of_induction_rule' cache context (#2 (thm_key name))
      | (Case_Split_Rule thm) => key_of_case_split_rule' cache context thm
      | (Named_Case_Split_Rule name) =>
          key_of_case_split_rule' cache context (#2 (thm_key name))
  end

val pack_universal_key = MessagePackBinIO.Pack.packBytes
val unpack_universal_key = MessagePackBinIO.Unpack.unpackBytes

(* --- Callback for Python --- *)

fun make_universal_key_callback' (cache : thm_uk_cache option)
    (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "universal_key_of",
    arg_schema = MessagePackBinIO.Unpack.unpackPair
                   (ctxt_unpack,
                    MessagePackBinIO.Unpack.unpackPair
                      (MessagePackBinIO.Unpack.unpackInt,
                       MessagePackBinIO.Unpack.unpackString)),
    ret_schema = MessagePackBinIO.Pack.packPair
                   (MessagePackBinIO.Pack.packBytes,
                    MessagePackBinIO.Pack.packString),
    function = fn (context, (kind, name)) =>
      case kind of
        0 => key_of_theory context name
      | 1 => key_of_constant context name
      | 2 => let val (uk, _, _, full_name) = key_of_theorem cache context name
             in (uk, full_name) end
      | 3 => key_of_type context name
      | 4 => key_of_class context name
      | 5 => key_of_locale context name
      | 6 => key_of_theorem_collection context name
      | 7 => key_of_method context name
      | 18 (* 0x12 *) => key_of_introduction_rule cache context name
      | 34 (* 0x22 *) => key_of_elimination_rule cache context name
      | 50 (* 0x32 *) => key_of_induction_rule cache context name
      | 66 (* 0x42 *) => key_of_case_split_rule cache context name
      | _ => error ("Unknown entity kind: " ^ Int.toString kind),
    timeout = NONE
  }

fun make_universal_key_callback ctxt_unpack = make_universal_key_callback' NONE ctxt_unpack

(* --- Entity serialization --- *)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*  1 = Constant, 2 = Theorem/Named_Theorem,
    3 = Type, 4 = Class, 5 = Locale, 6 = Theorem_Collection, 7 = Method,
    0x12 = Introduction_Rule, 0x22 = Elimination_Rule  *)
fun pack_entity_kind (Constant _)               = packInt 1
  | pack_entity_kind (Theorem _)                = packInt 2
  | pack_entity_kind (Named_Theorem _)          = packInt 2
  | pack_entity_kind (Type _)                   = packInt 3
  | pack_entity_kind (Class _)                  = packInt 4
  | pack_entity_kind (Locale _)                 = packInt 5
  | pack_entity_kind (Theorem_Collection _)         = packInt 6
  | pack_entity_kind (Method _)                 = packInt 7
  | pack_entity_kind (Introduction_Rule _)      = packInt 0x12
  | pack_entity_kind (Named_Introduction_Rule _) = packInt 0x12
  | pack_entity_kind (Elimination_Rule _)       = packInt 0x22
  | pack_entity_kind (Named_Elimination_Rule _) = packInt 0x22
  | pack_entity_kind (Induction_Rule _)        = packInt 0x32
  | pack_entity_kind (Named_Induction_Rule _)  = packInt 0x32
  | pack_entity_kind (Case_Split_Rule _)       = packInt 0x42
  | pack_entity_kind (Named_Case_Split_Rule _) = packInt 0x42

fun pack_entity_kind' ConstantK         = packInt 1
  | pack_entity_kind' TheoremK          = packInt 2
  | pack_entity_kind' TypeK             = packInt 3
  | pack_entity_kind' ClassK            = packInt 4
  | pack_entity_kind' LocaleK           = packInt 5
  | pack_entity_kind' Theorem_CollectionK    = packInt 6
  | pack_entity_kind' MethodK           = packInt 7
  | pack_entity_kind' IntroductionRuleK = packInt 0x12
  | pack_entity_kind' EliminationRuleK  = packInt 0x22
  | pack_entity_kind' InductionRuleK    = packInt 0x32
  | pack_entity_kind' CaseSplitRuleK    = packInt 0x42

val unpack_entity_kind : entity_kind unpacker = fn ins =>
  let val (k, ins') = unpackInt ins
  in (case k of
        1 => ConstantK | 2 => TheoremK | 3 => TypeK
      | 4 => ClassK | 5 => LocaleK
      | 6 => Theorem_CollectionK | 7 => MethodK
      | 0x12 => IntroductionRuleK | 0x22 => EliminationRuleK
      | 0x32 => InductionRuleK | 0x42 => CaseSplitRuleK
      | _ => raise Unpack, ins')
  end

fun pack_thm_entity tag thm =
  if Thm.has_name_hint thm
  then packPair (packInt, packString) (tag, Thm_Name.print (Thm.get_name_hint thm))
  else error "Cannot pack anonymous thm (no name hint)"

fun pack_entity (Constant name)      = packPair (packInt, packString) (1, name)
  | pack_entity (Theorem thm)        = pack_thm_entity 2 thm
  | pack_entity (Named_Theorem name) = packPair (packInt, packString) (2, name)
  | pack_entity (Type name)          = packPair (packInt, packString) (3, name)
  | pack_entity (Class name)         = packPair (packInt, packString) (4, name)
  | pack_entity (Locale name)        = packPair (packInt, packString) (5, name)
  | pack_entity (Theorem_Collection name) = packPair (packInt, packString) (6, name)
  | pack_entity (Method name)        = packPair (packInt, packString) (7, name)
  | pack_entity (Introduction_Rule thm)      = pack_thm_entity 0x12 thm
  | pack_entity (Named_Introduction_Rule name) = packPair (packInt, packString) (0x12, name)
  | pack_entity (Elimination_Rule thm)       = pack_thm_entity 0x22 thm
  | pack_entity (Named_Elimination_Rule name) = packPair (packInt, packString) (0x22, name)
  | pack_entity (Induction_Rule thm)        = pack_thm_entity 0x32 thm
  | pack_entity (Named_Induction_Rule name)  = packPair (packInt, packString) (0x32, name)
  | pack_entity (Case_Split_Rule thm)       = pack_thm_entity 0x42 thm
  | pack_entity (Named_Case_Split_Rule name) = packPair (packInt, packString) (0x42, name)

val unpack_entity : entity unpacker =
  unpackPair_dep' unpack_entity_kind (fn kind => case kind of
      ConstantK         => unpackString >> Constant
    | TheoremK          => unpackString >> Named_Theorem
    | TypeK             => unpackString >> Type
    | ClassK            => unpackString >> Class
    | LocaleK           => unpackString >> Locale
    | Theorem_CollectionK    => unpackString >> Theorem_Collection
    | MethodK           => unpackString >> Method
    | IntroductionRuleK => unpackString >> Named_Introduction_Rule
    | EliminationRuleK  => unpackString >> Named_Elimination_Rule
    | InductionRuleK    => unpackString >> Named_Induction_Rule
    | CaseSplitRuleK    => unpackString >> Named_Case_Split_Rule)

end (* local MessagePackBinIO *)

end
