(*
  Universal Keys
  ==============

  A universal key is a Word8Vector.vector that uniquely identifies an Isabelle
  entity (theory, constant, theorem, type, class, or locale) across sessions.
  Keys are used as persistent identifiers in external stores (e.g. embedding
  databases) so that entries survive Isabelle restarts.

  Key format
  ----------

  Every key has the layout:

    <theory_hash (16 bytes)> <tag (1 byte)> <entity (variable)>

  - theory_hash: 16-byte hash from Theory_Hash.hash_of, identifying the
    theory that defines the entity.  Works for both heap and non-heap theories.
  - tag: 1-byte entity kind discriminator:
      0x00 = Theory, 0x01 = Constant, 0x02 = Theorem,
      0x03 = Type, 0x04 = Class, 0x05 = Locale
  - entity: variable-length payload identifying the entity within its theory.

  Key sizes
  ---------

  - Theory keys:           17 bytes  (16 + 1 + 0, empty entity)
  - Namespace entity keys: 17 + |name| bytes  (constant, type, class, locale)
  - Theorem keys:          32 bytes  (16 + 1 + 15, always)

  Theorem keys use the first 15 bytes of the 128-bit term digest
  (Term_Digest.thm128) as entity payload, guaranteeing a fixed 32-byte key.
*)
signature UNIVERSAL_KEY = sig

eqtype universal_key
type fully_quantified_name = string
type theory_long_name = string

datatype entity =
      Constant of fully_quantified_name
    | Theorem  of thm
    | Theorem_ID of serial  (* #serial of Proofterm.thm_id, from Thm.derivation_id *)
    | Named_Theorem of fully_quantified_name
    | Type     of fully_quantified_name
    | Class    of fully_quantified_name
    | Locale   of fully_quantified_name

val key_of_theory'  : theory -> universal_key
val key_of_theory   : Context.generic -> xstring -> universal_key
val key_of_constant : Context.generic -> xstring -> universal_key
val key_of_theorem  : Context.generic -> xstring -> universal_key
val key_of_theorem' : Context.generic -> thm -> universal_key
val key_of_type     : Context.generic -> xstring -> universal_key
val key_of_class    : Context.generic -> xstring -> universal_key
val key_of_locale   : Context.generic -> xstring -> universal_key
val key_of          : Context.generic -> entity -> universal_key

val make_universal_key_callback : Context.generic -> Remote_Procedure_Calling.callback'

val hasher : universal_key -> word

val pack_entity_kind : entity MessagePackBinIO.Pack.packer
val pack_entity : entity MessagePackBinIO.Pack.packer
val unpack_entity : entity MessagePackBinIO.Unpack.unpacker

end

structure Universal_Key : UNIVERSAL_KEY = struct

type fully_quantified_name = string
type theory_long_name = string
datatype entity =
      Constant of fully_quantified_name
    | Theorem  of thm
    | Theorem_ID of serial  (* #serial of Proofterm.thm_id, from Thm.derivation_id *)
    | Named_Theorem of fully_quantified_name
    | Type     of fully_quantified_name
    | Class    of fully_quantified_name
    | Locale   of fully_quantified_name
type caching_key = entity * theory_long_name
type universal_key = Word8Vector.vector
val hasher = Hashers.bitvec

fun resolve_theory (context : Context.generic) (name : string) : theory =
  let
    val thy = Context.theory_of context
    val long = String.isSubstring "." name
    val thy_name = if long then Context.theory_long_name thy
                   else Context.theory_base_name thy
  in
    if name = thy_name then thy
    else Theory.check {long = long} (Context.proof_of context) (name, Position.none)
  end

(* --- Cache --- *)

structure CacheTab = Hash_Table(struct
  type key = caching_key
  fun hash (Constant name, thy) =
        Word.xorb (0w1, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Theorem thm, thy) =
        Word.xorb (Term_Digest.digest128_hasher (Term_Digest.thm128 thm),
                   Hashers.string thy)
    | hash (Theorem_ID serial, thy) =
        Word.xorb (0w2, Word.xorb (Hashers.int serial, Hashers.string thy))
    | hash (Named_Theorem name, thy) =
        Word.xorb (0w3, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Type name, thy) =
        Word.xorb (0w4, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Class name, thy) =
        Word.xorb (0w5, Word.xorb (Hashers.string name, Hashers.string thy))
    | hash (Locale name, thy) =
        Word.xorb (0w6, Word.xorb (Hashers.string name, Hashers.string thy))
  fun eq ((Constant n1, t1), (Constant n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Theorem thm1, t1), (Theorem thm2, t2)) =
        Thm.eq_thm (thm1, thm2) andalso t1 = t2
    | eq ((Theorem_ID s1, t1), (Theorem_ID s2, t2)) = s1 = s2 andalso t1 = t2
    | eq ((Named_Theorem n1, t1), (Named_Theorem n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Type n1, t1), (Type n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Class n1, t1), (Class n2, t2)) = n1 = n2 andalso t1 = t2
    | eq ((Locale n1, t1), (Locale n2, t2)) = n1 = n2 andalso t1 = t2
    | eq _ = false
end)

val cache : universal_key CacheTab.table = CacheTab.empty 1024
val cache_lock = Synchronized.var "Universal_Key.cache" ()

fun cached_key ck compute =
  Synchronized.change_result cache_lock (fn () =>
    case CacheTab.lookup cache ck of
      SOME k => (k, ())
    | NONE => let val k = compute ()
              in CacheTab.update cache (ck, k); (k, ()) end)

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

(* --- Namespace-based entities (constant, type, class, locale) --- *)

fun key_of_ns_entity tag make_ck space context xname =
  let
    val fq_name = Name_Space.intern space xname
    val ns_entry = Name_Space.the_entry space fq_name
    val thy_long_name = #theory_long_name ns_entry
    val ck = (make_ck fq_name, thy_long_name)
  in
    cached_key ck (fn () =>
      build_key (Theory_Hash.hash_of (resolve_theory context thy_long_name))
                tag (ent_string fq_name))
  end

fun key_of_theory' thy =
  build_key (Theory_Hash.hash_of thy) 0wx00 (0, fn _ => fn _ => ())

fun key_of_theory context xname = key_of_theory' (resolve_theory context xname)

fun key_of_constant context =
  key_of_ns_entity 0wx01 Constant
    (Consts.space_of (Context.cases Sign.consts_of Proof_Context.consts_of context))
    context

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

fun key_of_theorem context xname =
  let
    val (base_name, idx_opt) = parse_thm_xname xname
    val ctxt = Context.cases Proof_Context.init_global I context
    val facts = Proof_Context.facts_of ctxt
    val fact_space = Facts.space_of facts
    val full_name = Name_Space.intern fact_space base_name
    val ns_entry = Name_Space.the_entry fact_space full_name
    val thy_long_name = #theory_long_name ns_entry
    val {thms, ...} = the (Facts.lookup context facts full_name)
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
    val thm = Thm.transfer (Context.theory_of context) thm
    fun compute () =
      build_key (Theory_Hash.hash_of (resolve_theory context thy_long_name))
                0wx02 (ent_digest128_15 (Term_Digest.thm128 thm))
  in
    case Thm.derivation_id thm of
      SOME thm_id => cached_key (Theorem_ID (#serial thm_id), thy_long_name) compute
    | NONE => compute ()
  end

end (* local parse_thm_xname *)

fun key_of_theorem' context thm =
  let
    val thm_id_opt = Thm.derivation_id thm
    val thy_long_name = case thm_id_opt of
        SOME {theory_name, ...} =>
          if theory_name = "" then Context.theory_long_name (Context.theory_of context)
          else theory_name
      | NONE => Context.theory_long_name (Context.theory_of context)
    fun compute () =
      build_key (Theory_Hash.hash_of (resolve_theory context thy_long_name))
                0wx02 (ent_digest128_15 (Term_Digest.thm128 thm))
  in
    case thm_id_opt of
      SOME thm_id => cached_key (Theorem_ID (#serial thm_id), thy_long_name) compute
    | NONE => compute ()
  end

fun key_of context (Constant name) = key_of_constant context name
  | key_of context (Theorem thm) = key_of_theorem' context thm
  | key_of context (Theorem_ID _) = error "Cannot compute key from Theorem_ID alone"
  | key_of context (Named_Theorem name) = key_of_theorem context name
  | key_of context (Type name) = key_of_type context name
  | key_of context (Class name) = key_of_class context name
  | key_of context (Locale name) = key_of_locale context name

(* --- Callback for Python --- *)

fun make_universal_key_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "universal_key_of",
    arg_schema = MessagePackBinIO.Unpack.unpackPair
                   (MessagePackBinIO.Unpack.unpackInt,
                    MessagePackBinIO.Unpack.unpackString),
    ret_schema = MessagePackBinIO.Pack.packBytes,
    function = fn (kind, name) =>
      case kind of
        0 => key_of_theory context name
      | 1 => key_of_constant context name
      | 2 => key_of_theorem context name
      | 3 => key_of_type context name
      | 4 => key_of_class context name
      | 5 => key_of_locale context name
      | _ => error ("Unknown entity kind: " ^ Int.toString kind),
    timeout = NONE
  }

(* --- Entity serialization --- *)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*  1 = Constant, 2 = Theorem/Theorem_ID/Named_Theorem,
    3 = Type, 4 = Class, 5 = Locale  *)
fun pack_entity_kind (Constant _)      = packInt 1
  | pack_entity_kind (Theorem _)       = packInt 2
  | pack_entity_kind (Theorem_ID _)    = packInt 2
  | pack_entity_kind (Named_Theorem _) = packInt 2
  | pack_entity_kind (Type _)          = packInt 3
  | pack_entity_kind (Class _)         = packInt 4
  | pack_entity_kind (Locale _)        = packInt 5

fun pack_entity (Constant name)      = packPair (packInt, packString) (1, name)
  | pack_entity (Theorem _)          = error "Cannot pack Theorem (contains live thm value)"
  | pack_entity (Theorem_ID serial)  = packPair (packInt, packInt) (2, serial)
  | pack_entity (Named_Theorem name) = packPair (packInt, packString) (2, name)
  | pack_entity (Type name)          = packPair (packInt, packString) (3, name)
  | pack_entity (Class name)         = packPair (packInt, packString) (4, name)
  | pack_entity (Locale name)        = packPair (packInt, packString) (5, name)

val unpack_entity : entity unpacker = fn ins =>
  let val (kind, ins') = unpackInt ins
  in case kind of
      1 => (unpackString >> Constant) ins'
    | 2 => ((unpackInt >> Theorem_ID) || (unpackString >> Named_Theorem)) ins'
    | 3 => (unpackString >> Type) ins'
    | 4 => (unpackString >> Class) ins'
    | 5 => (unpackString >> Locale) ins'
    | _ => raise Unpack
  end

end (* local MessagePackBinIO *)

end
