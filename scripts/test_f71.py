"""Testes F71 — contract de FORMA do registry, por entrada (roadmap v5).

O ``test_registry_consistency`` valida a classificacao de tenant declarado x
runtime (consistent/drift/dynamic/multi/not_found/no_data). Ele NAO valida a
FORMA de cada entrada. Este contract fecha essa lacuna, 100% OFFLINE (zero
rede, ``data/`` intocada), afirmando por entrada do SEED atual:

1. **ATS conhecido** — o ``ats`` declarado tem forma documentada na tabela
   F71 (derivada do registry + modulos), OU e explicitamente ``None``
   (dynamic total: a base decide). ATS novo no seed SEM forma na tabela =
   violador listado (force a derivacao consciente da forma antes do merge);
2. **slug na forma do ATS** — o ``tenant`` (``ats:slug``) tem exatamente um
   ``:``, prefixo igual ao ``ats`` declarado e o slug casa a forma do ATS
   (successfactors: tenant-token; workday: empresa/pagina; moka:
   empresa/ID numerico; phenom/cornerstone: token OU URL completa https;
   demais: empresa-token). ``tenant=None`` e LEGAL (dynamic: Trumpf/DATEV);
3. **URL com shape valido p/ tenants compartilhados** — slug no formato URL
   precisa ser https bem-formada (host com ponto, sem espacos); e um tenant
   COMPARTILHADO (mesmo ``ats:slug`` em N>1 empresas) nunca pode ter slug-URL:
   a URL desambigua POR empresa no runtime (``URL_SLUG_ATS`` de
   ``collectors/ats_scraper.py``) — URL compartilhada colidiria empresas;
4. **company nao-vazio** — nome canonico non-empty e UNICO (o
   ``CompanyRegistry`` indexa por nome: duplicata silenciosamente sobrescreve
   e encolhe o registro);
5. **contagem == 127 == soma das ondas** — total do SEED == 127 ==
   soma das ondas documentadas nos marcadores ``# --- N da ...`` do proprio
   seed, com a contagem REAL de cada onda == N documentado (onda que diz 17
   e traz 16 = violador).

Falha de contract = lista COMPLETA de violadores (o validador coleta TODAS
as violacoes de TODAS as entradas — nunca para na primeira). Controles
negativos (fixtures sinteticas) exercitam o MESMO validador e provam que
cada regra apanha violador + que a lista devolvida e completa.

Uso:  .venv/bin/python scripts/test_f71.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.registry import SEED, RegistryEntry  # noqa: E402

FAILURES: list[str] = []

# Contrato de contagem da especificacao F71 (127 empresas, roadmap v5).
REGISTRY_TOTAL = 127


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Tabela de formas por ATS (passo 0 da F71 — derivada do registry.py atual +
# modulos). Token = [A-Za-z0-9] inicial + [A-Za-z0-9_-]* (sem '/', ':', espaco).
# URL = https://host.ponto/... (sem espacos). ATS fora da tabela = desconhecido.
# ---------------------------------------------------------------------------

def _token_ok(s: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", s) is not None


def _is_https_url(s: str) -> bool:
    if any(c.isspace() for c in s):
        return False
    p = urlparse(s)
    return p.scheme == "https" and p.netloc != "" and "." in p.netloc


def _workday_ok(s: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_-]*", s) is not None


def _moka_ok(s: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*/[0-9]+", s) is not None


def _token_or_url(s: str) -> bool:
    return _token_ok(s) or _is_https_url(s)


# ats -> (forma humana, predicado do slug). Mantida EXATA em relacao aos ATS
# presentes no seed: entry de ATS novo sem forma aqui = violador (secao 1);
# forma sem nenhuma entry = linha morta (a mesma secao 1 exige remocao).
ATS_SLUG_SHAPES: dict[str, tuple[str, Callable[[str], bool]]] = {
    "successfactors": ("tenant (1 token; empresas compartilham o tenant — o runtime desambigua por URL, URL_SLUG_ATS)", _token_ok),
    "workday": ("empresa/pagina (2 segmentos, sem '/' extra)", _workday_ok),
    "smartrecruiters": ("empresa (1 token)", _token_ok),
    "phenom": ("empresa (token; 'nan' = artefato do manifest upstream) OU URL completa https de careers", _token_or_url),
    "eightfold": ("empresa (1 token)", _token_ok),
    "cornerstone": ("empresa (token) OU URL completa https (csod careersite)", _token_or_url),
    "greenhouse": ("empresa (1 token)", _token_ok),
    "bamboohr": ("empresa (1 token)", _token_ok),
    "softgarden": ("empresa (1 token)", _token_ok),
    "recruitee": ("empresa (1 token)", _token_ok),
    "teamtailor": ("empresa (1 token)", _token_ok),
    "ashby": ("empresa (1 token)", _token_ok),
    "personio": ("empresa (1 token)", _token_ok),
    "moka": ("empresa/ID (2 segmentos, ID numerico)", _moka_ok),
}


# ---------------------------------------------------------------------------
# Validadores — coletam TODAS as violacoes (lista completa, nunca a primeira).
# ---------------------------------------------------------------------------

def _slug_of(tenant: str) -> str:
    return tenant.split(":", 1)[1]


def entry_violations(e: RegistryEntry) -> list[str]:
    """TODAS as violacoes de forma de UMA entrada (lista vazia = conforme)."""
    out: list[str] = []
    name = (e.name or "").strip() or "<company vazio>"
    if not (e.name or "").strip():
        out.append(f"{name!r}: company vazio")
    # ATS conhecido ou explicitamente dynamic (ats=None -> a base decide).
    if e.ats is None:
        if e.tenant is not None:
            out.append(f"{name}: ats=None (dynamic total) exige tenant=None — declarado {e.tenant!r}")
        return out
    if e.ats not in ATS_SLUG_SHAPES:
        out.append(
            f"{name}: ATS {e.ats!r} sem forma documentada na tabela F71 — "
            f"derive a forma (registry + modulos) e adicione ANTES de merge a onda"
        )
        return out
    if e.tenant is None:
        return out  # dynamic deliberado (ex.: Trumpf/DATEV): a base decide
    tenant = e.tenant
    if ":" not in tenant:
        out.append(f"{name}: tenant {tenant!r} sem o ':' separador (ats:slug)")
        return out
    prefix, slug = tenant.split(":", 1)
    if prefix != e.ats:
        out.append(f"{name}: tenant {tenant!r} com prefixo {prefix!r} != ats declarado {e.ats!r}")
    if not slug.strip():
        out.append(f"{name}: slug vazio no tenant {tenant!r}")
        return out
    if not slug.startswith("http") and ":" in slug:
        # ':' extra so e legal dentro de slug-URL (https://...); slug-token
        # com ':' quebra a identidade ats:slug consumida pelo pipeline.
        out.append(f"{name}: tenant {tenant!r} com ':' extra no slug (token nao pode conter ':')")
        return out
    shape_label, shape_ok = ATS_SLUG_SHAPES[e.ats]
    if not shape_ok(slug):
        out.append(f"{name}: slug {slug!r} fora da forma do ATS {e.ats!r} — esperado: {shape_label}")
    if slug.startswith("http") and not _is_https_url(slug):
        out.append(f"{name}: slug-URL {slug!r} invalida (esperado https + host com ponto, sem espacos)")
    return out


def _is_url_slug(e: RegistryEntry) -> bool:
    return e.tenant is not None and ":" in e.tenant and _slug_of(e.tenant).startswith("http")


def seed_form_violations(entries: list[RegistryEntry]) -> list[str]:
    """TODAS as violacoes de forma do conjunto (por entrada + coletivas)."""
    out: list[str] = []
    for e in entries:
        out.extend(entry_violations(e))
    # company unico: o CompanyRegistry indexa por nome — duplicata sobrescreve
    # silenciosamente e encolhe o registro.
    for cname, n in Counter(e.name for e in entries).items():
        if n > 1:
            out.append(f"company duplicado {cname!r} (x{n}) — CompanyRegistry descartaria entradas")
    # tenants compartilhados (mesmo ats:slug em N>1 empresas): slug nunca pode
    # ser URL — a URL desambigua POR empresa no runtime (URL_SLUG_ATS).
    shared: Counter = Counter((e.ats, _slug_of(e.tenant)) for e in entries if e.tenant and ":" in e.tenant)
    for (ats, slug), n in shared.items():
        if n > 1 and slug.startswith("http"):
            out.append(
                f"tenant compartilhado {ats}:{slug!r} (x{n} empresas) com slug-URL — "
                f"URL e POR empresa (URL_SLUG_ATS); tenant compartilhado tem que ser token"
            )
    return out


# ---------------------------------------------------------------------------
# Ondas documentadas no fonte do registry (contrato de contagem).
# ---------------------------------------------------------------------------

_WAVE_RE = re.compile(r"^    # --- (\d+) da ", re.M)
_ENTRY_RE = re.compile(r"^    RegistryEntry\(", re.M)


def seed_block(src: str) -> str:
    """Bloco ``SEED = [ ... ]`` do fonte do registry."""
    m = re.search(r"^SEED = \[", src, re.M)
    if not m:
        return ""
    end = src.find("\n]", m.end())
    return src[m.start():end] if end != -1 else src[m.start():]


def parse_waves(block: str) -> list[tuple[int, int, str]]:
    """[(N documentado, entradas reais, rotulo)] por onda, na ordem do fonte."""
    marks = list(_WAVE_RE.finditer(block))
    waves: list[tuple[int, int, str]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
        seg = block[m.start():end]
        label = block[m.start():block.find("\n", m.start())].strip()
        waves.append((int(m.group(1)), len(_ENTRY_RE.findall(seg)), label))
    return waves


def wave_violations(block: str) -> list[str]:
    """TODAS as divergencias onda-documentada x contagem real (lista completa)."""
    out: list[str] = []
    if not block:
        return ["bloco SEED = [ nao encontrado no fonte do registry"]
    waves = parse_waves(block)
    if not waves:
        out.append("nenhuma onda documentada (marcador '    # --- N da ...') dentro do SEED")
    for n_doc, n_real, label in waves:
        if n_real != n_doc:
            out.append(f"onda documentada {n_doc} mas com {n_real} entradas :: {label}")
    n_src = len(_ENTRY_RE.findall(block))
    if waves and n_src != sum(n for n, _, _ in waves):
        out.append(
            f"{n_src} RegistryEntry no fonte mas soma das ondas documentadas = "
            f"{sum(n for n, _, _ in waves)} — entrada fora de onda documentada"
        )
    return out


# ---------------------------------------------------------------------------
# [1] Tabela de formas: cobertura exata (nem faltando, nem sobrando)
# ---------------------------------------------------------------------------

def test_shape_table_coverage() -> None:
    print("== [1] tabela de formas F71 x ATS do seed (cobertura exata) ==")
    seed_ats = {e.ats for e in SEED if e.ats is not None}
    table_ats = set(ATS_SLUG_SHAPES)
    missing = sorted(seed_ats - table_ats)
    dead = sorted(table_ats - seed_ats)
    for a in missing:
        print(f"    VIOLADOR: ATS {a!r} no seed SEM forma na tabela F71")
    for a in dead:
        print(f"    VIOLADOR: forma de {a!r} na tabela F71 sem nenhuma entry no seed (linha morta)")
    check("1a. todo ATS do seed tem forma documentada (tabela F71)", not missing,
          f"sem forma: {missing}" if missing else f"{len(seed_ats)} ATS cobertos")
    check("1b. nenhuma forma na tabela sem entry no seed", not dead,
          f"linhas mortas: {dead}" if dead else "")
    check("1c. predicados da tabela sao callables com rotulo",
          all(callable(pred) and isinstance(lbl, str) and lbl
              for lbl, pred in ATS_SLUG_SHAPES.values()))


# ---------------------------------------------------------------------------
# [2] Contract de forma por entrada — seed atual: zero violadores
# ---------------------------------------------------------------------------

def test_seed_form_contract() -> None:
    print("== [2] forma por entrada no SEED (127) — zero violadores ==")
    viol = seed_form_violations(list(SEED))
    for v in viol:
        print(f"    VIOLADOR: {v}")
    check("2a. zero violadores de forma no seed atual", not viol,
          f"{len(viol)} violadores" if viol else "127 entradas conformes")
    # Visibilidade dos tenants compartilhados (regra da secao [3] e informativo):
    shared = Counter(
        (e.ats, _slug_of(e.tenant)) for e in SEED if e.tenant and ":" in e.tenant
    )
    multi = {f"{a}:{s}": n for (a, s), n in shared.items() if n > 1}
    print(f"    tenants compartilhados (informativo): {multi}")
    # dynamic (tenant=None, ats conhecido) e legal e visivel:
    dynamic = [e.name for e in SEED if e.ats in ATS_SLUG_SHAPES and e.tenant is None]
    print(f"    entries dynamic (tenant=None, base decide): {dynamic}")
    check("2b. dynamic (tenant=None) tem ATS conhecido",
          all(e.ats in ATS_SLUG_SHAPES for e in SEED if e.tenant is None),
          f"{dynamic}")


# ---------------------------------------------------------------------------
# [3] URL com shape valido p/ tenants compartilhados
# ---------------------------------------------------------------------------

def test_url_shapes() -> None:
    print("== [3] slug-URL valida + tenant compartilhado nunca e URL ==")
    url_slugs = [(e.name, e.tenant) for e in SEED if _is_url_slug(e)]
    for name, tenant in url_slugs:
        slug = _slug_of(tenant)
        check(f"3. slug-URL de {name} bem-formada (https + host com ponto)",
              _is_https_url(slug), f"{slug}")
    bad_url = [(e.name, _slug_of(e.tenant)) for e in SEED if _is_url_slug(e) and not _is_https_url(_slug_of(e.tenant))]
    check("3a. toda slug-URL do seed e https bem-formada", not bad_url, f"{bad_url}")
    # tenant compartilhado -> slug token (nunca URL: a URL e POR empresa)
    shared_url = seed_form_violations(list(SEED))
    shared_url = [v for v in shared_url if "tenant compartilhado" in v]
    for v in shared_url:
        print(f"    VIOLADOR: {v}")
    check("3b. nenhum tenant compartilhado com slug-URL", not shared_url,
          f"{len(shared_url)} violadores" if shared_url else "")
    # slug-URL e especifica de UMA empresa (dupla garantia da regra acima):
    url_counter = Counter(e.tenant for e in SEED if _is_url_slug(e))
    dup = {t: n for t, n in url_counter.items() if n > 1}
    check("3c. cada slug-URL pertence a exatamente 1 empresa", not dup, f"{dup}" if dup else f"{len(url_counter)} slug-URL ok")


# ---------------------------------------------------------------------------
# [4] company nao-vazio + unico
# ---------------------------------------------------------------------------

def test_company_names() -> None:
    print("== [4] company nao-vazio e unico (127 nomes) ==")
    empty = [e for e in SEED if not (e.name or "").strip()]
    for e in empty:
        print(f"    VIOLADOR: company vazio em ats={e.ats!r} tenant={e.tenant!r}")
    check("4a. nenhum company vazio", not empty, f"{len(empty)} violadores" if empty else "")
    dups = {n: c for n, c in Counter(e.name for e in SEED).items() if c > 1}
    for n, c in dups.items():
        print(f"    VIOLADOR: company duplicado {n!r} (x{c})")
    check("4b. nenhum company duplicado", not dups, f"{dups}" if dups else "127 unicos")
    check("4c. CompanyRegistry indexa o seed inteiro (dict por nome nao colide)",
          len({e.name for e in SEED}) == len(SEED),
          f"{len(SEED)} entradas -> {len({e.name for e in SEED})} chaves")


# ---------------------------------------------------------------------------
# [5] contagem == 127 == soma das ondas documentadas
# ---------------------------------------------------------------------------

def test_counts_and_waves() -> None:
    print("== [5] contagem == 127 == soma das ondas documentadas ==")
    check("5a. total do SEED == 127 (contrato F71)", len(SEED) == REGISTRY_TOTAL,
          f"len(SEED)={len(SEED)}")
    src = (Path(__file__).resolve().parent.parent / "src" / "internship_finder" / "registry.py").read_text(encoding="utf-8")
    block = seed_block(src)
    waves = parse_waves(block)
    print(f"    ondas documentadas: {[(n, real) for n, real, _ in waves]}")
    check("5b. bloco SEED = [ encontrado no fonte", bool(block))
    wv = wave_violations(block)
    for v in wv:
        print(f"    VIOLADOR: {v}")
    check("5c. cada onda: entradas reais == N documentado (lista completa)", not wv,
          f"{len(wv)} violadores" if wv else f"{len(waves)} ondas conformes")
    s = sum(n for n, _, _ in waves)
    check("5d. soma das ondas documentadas == 127 == len(SEED)",
          s == REGISTRY_TOTAL == len(SEED),
          f"soma={s} vs total={len(SEED)}")
    n_src = len(_ENTRY_RE.findall(block))
    check("5e. RegistryEntry no fonte == len(SEED) (nenhuma entry fora do bloco)",
          n_src == len(SEED), f"fonte={n_src} vs SEED={len(SEED)}")


# ---------------------------------------------------------------------------
# [6] ATS conhecido: scraper registrado no pacote upstream
# ---------------------------------------------------------------------------

def test_known_ats_scrapers() -> None:
    print("== [6] todo ATS da tabela tem scraper registrado (upstream) ==")
    from ats_scrapers.scrapers import ScraperRegistry

    for ats in sorted(ATS_SLUG_SHAPES):
        check(f"6. has_scraper({ats!r}) e True", ScraperRegistry.has_scraper(ats))
    # URL_SLUG_ATS do modulo: ATS cujo slug efetivo pode ser a URL completa.
    from internship_finder.collectors.ats_scraper import URL_SLUG_ATS

    seed_ats = {e.ats for e in SEED if e.ats is not None}
    url_ats = sorted(seed_ats & set(URL_SLUG_ATS))
    print(f"    ATS do seed em URL_SLUG_ATS (runtime desambigua por URL): {url_ats}")
    check("6a. seed nao declara ATS de URL_SLUG_ATS fora da tabela F71",
          set(URL_SLUG_ATS) & seed_ats <= set(ATS_SLUG_SHAPES))


# ---------------------------------------------------------------------------
# [7] Controles negativos: o validador apanha TODOS os violadores (fixtures)
# ---------------------------------------------------------------------------

def _e(name: str, ats: str | None, tenant: str | None) -> RegistryEntry:
    return RegistryEntry(name=name, ats=ats, tenant=tenant)


def test_negative_controls() -> None:
    print("== [7] controles negativos — MESMO validador apanha todos os violadores ==")
    violators = [
        (_e("X", "icims", "icims:acme"), "sem forma documentada"),          # ATS desconhecido
        (_e("Y", "workday", "greenhouse:y/y"), "prefixo"),                   # prefixo != ats
        (_e("Z", "workday", "workday:zalando"), "empresa/pagina"),           # 1 segmento
        (_e("W", "successfactors", "successfactors:jobs/2"), "forma do ATS"),  # '/' no token
        (_e("V", "phenom", "phenom:http://x.y"), "invalida"),                # http, nao https
        (_e("U", "workday", "workday:a:b"), "':' extra"),                   # colon no slug-token
        (_e("T", "moka", "moka:adidas/abc"), "ID numerico"),                 # ID nao numerico
        (_e("S", None, "workday:s/s"), "dynamic total"),                    # ats=None c/ tenant
        (_e("  ", "ashby", "ashby:statista"), "company vazio"),             # nome vazio
        (_e("R", "phenom", "phenom:https://a b.com"), "invalida"),          # espaco na URL
    ]
    for entry, expect in violators:
        vs = entry_violations(entry)
        hit = any(expect in v for v in vs)
        if not hit:
            print(f"    VIOLADOR NAO APANHADO: {entry.name!r} esperava {expect!r}, got {vs}")
        check(f"7. {entry.name.strip() or '<vazio>'!r} apanhado ({expect})", hit, f"{vs}")

    # validos sinteticos -> zero violacoes (falsos positivos = contract quebrado)
    valids = [
        _e("A", "workday", "workday:a/b"),
        _e("B", "successfactors", "successfactors:jobs"),
        _e("C", "phenom", "phenom:nan"),
        _e("D", "phenom", "phenom:https://careers.exemplo.com"),
        _e("E", "cornerstone", "cornerstone:https://x.csod.com/ux/ats/careersite/4/home?c=x"),
        _e("F", "moka", "moka:adidas/140456"),
        _e("G", "personio", "personio:sungrow-emea"),
        _e("H", "workday", None),        # dynamic (Trumpf/DATEV)
        _e("I", None, None),             # dynamic total
    ]
    for entry in valids:
        vs = entry_violations(entry)
        check(f"7. {entry.name!r} valido -> zero violacoes", not vs, f"{vs}" if vs else "")

    # lista COMPLETA: 3 violadores de especies diferentes -> as 3 violacoes
    trio = [
        _e("P1", "icims", "icims:x"),        # ATS desconhecido
        _e("P2", "workday", "workday:a"),    # forma workday
        _e("", "ashby", "ashby:statista"),   # company vazio
        _e("P4", "workday", "workday:ok/ok"),  # conforme
    ]
    got = seed_form_violations(trio)
    check("7a. lista COMPLETA: 3 violadores -> >=3 violacoes listadas (nao para na 1a)",
          len(got) >= 3 and any("P1" in v for v in got) and any("P2" in v for v in got)
          and any("P3" in v or "company vazio" in v for v in got) and not any("P4" in v for v in got),
          f"{got}")

    # duplicata de nome -> violacao coletiva (CompanyRegistry sobrescreveria)
    dup = [_e("D1", "ashby", "ashby:a"), _e("D1", "ashby", "ashby:b")]
    got = seed_form_violations(dup)
    check("7b. company duplicado apanhado", any("duplicado" in v for v in got), f"{got}")

    # tenant compartilhado com slug-URL -> violacao (URL e POR empresa)
    shared_url = [
        _e("S1", "phenom", "phenom:https://careers.empresa.com"),
        _e("S2", "phenom", "phenom:https://careers.empresa.com"),
    ]
    got = seed_form_violations(shared_url)
    check("7c. tenant compartilhado com slug-URL apanhado",
          any("tenant compartilhado" in v for v in got), f"{got}")

    # ondas: documento 12, trago 3 -> divergencia listada com a onda exata
    fake = (
        "SEED = [\n"
        "    # --- 12 da onda sintetica (fixture F71) ---\n"
        "    RegistryEntry(name=\"a\", ats=\"ashby\", tenant=\"ashby:a\"),\n"
        "    RegistryEntry(name=\"b\", ats=\"ashby\", tenant=\"ashby:b\"),\n"
        "    RegistryEntry(name=\"c\", ats=\"ashby\", tenant=\"ashby:c\"),\n"
    )
    fake_block = fake + "]\n"
    wv = wave_violations(seed_block(fake) or fake_block)
    check("7d. onda documentada 12 com 3 entradas apanhada",
          any("documentada 12" in v for v in wv), f"{wv}")
    # entrada fora de onda documentada (soma das ondas < total do fonte)
    fake2 = fake + "    RegistryEntry(name=\"d\", ats=\"ashby\", tenant=\"ashby:d\"),\n" + "]\n"
    wv2 = wave_violations(seed_block(fake2) or fake2)
    check("7e. entry fora de onda documentada apanhada (soma != fonte)",
          any("soma das ondas" in v for v in wv2), f"{wv2}")
    # onda consistente -> zero violacoes
    fake3 = (
        "SEED = [\n"
        "    # --- 2 da onda sintetica ok (fixture F71) ---\n"
        "    RegistryEntry(name=\"a\", ats=\"ashby\", tenant=\"ashby:a\"),\n"
        "    RegistryEntry(name=\"b\", ats=\"ashby\", tenant=\"ashby:b\"),\n"
        "]\n"
    )
    wv3 = wave_violations(seed_block(fake3) or fake3)
    check("7f. onda consistente -> zero violacoes de onda", not wv3, f"{wv3}")
    # sem marcador de onda nenhum -> violacao explicita
    fake4 = "SEED = [\n    RegistryEntry(name=\"a\", ats=\"ashby\", tenant=\"ashby:a\"),\n]\n"
    wv4 = wave_violations(seed_block(fake4) or fake4)
    check("7g. seed sem onda documentada apanhado",
          any("nenhuma onda documentada" in v for v in wv4), f"{wv4}")


def main() -> int:
    test_shape_table_coverage()
    print()
    test_seed_form_contract()
    print()
    test_url_shapes()
    print()
    test_company_names()
    print()
    test_counts_and_waves()
    print()
    test_known_ats_scrapers()
    print()
    test_negative_controls()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
