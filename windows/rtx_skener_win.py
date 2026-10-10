#!/usr/bin/env python3
"""
RTX skener za Windows.

Spremlja Bolho in Njuškalo ter z Windows obvestilom opozori na RTX kartico (serija 30/40/50),
ki je vsaj X % pod tržno ceno in prinese vsaj Y € zaslužka pri preprodaji.
Tržna cena = povprečje oglasov za isti model (in VRAM) v zadnjih 60 dneh.
"""

import json
import os
import random
import re
import sqlite3
import statistics
import sys
import threading
import webbrowser
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

APP = "RTX skener"
MAPA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP)
os.makedirs(MAPA, exist_ok=True)
DB_POT = os.path.join(MAPA, "rtx_skener.db")
NAST_POT = os.path.join(MAPA, "nastavitve.json")

PRIVZETO = {"popust": 25, "min_zasluzek": 40, "interval": 4, "ob_zagonu": False, "obvestila": True}

VIRI = {
    "Bolha": "https://www.bolha.com/?ctl=search_ads&keywords={q}&sort=new&page={p}",
    "Njuškalo": "https://www.njuskalo.hr/?ctl=search_ads&keywords={q}&sort=new&page={p}",
}
STROSKI = {"Bolha": 5, "Njuškalo": 25}
# Ločena iskanja za vsako različico, da se za vsak model nabere dovolj oglasov.
ISKALNI_NIZI = ["rtx 3060", "rtx 3060 ti", "rtx 3070", "rtx 3070 ti", "rtx 3080", "rtx 3080 ti",
                "rtx 3090", "rtx 4060", "rtx 4060 ti", "rtx 4070", "rtx 4070 super",
                "rtx 4070 ti", "rtx 4070 ti super", "rtx 4080", "rtx 4080 super", "rtx 4090",
                "rtx 5060", "rtx 5060 ti", "rtx 5070", "rtx 5070 ti", "rtx 5080", "rtx 5090"]
IZLOCI = ["kupim", "iščem", "iscem", "menjam", "zamenjam", "okvar", "defekt", "ne dela",
          "za dele", "pokvar", "prenosnik", "laptop", "notebook", "računalnik", "racunalnik",
          "gaming pc", "desktop", "komplet pc", "neispravn", "ne radi", "otkup", "kupujem",
          "računalo", "racunalo", "kućište", "blok", "hladilnik", "backplate",
          "rezervirano", "prodano", "prodana", "prodan ", "rezervirana", "artefakt",
          "mining", "rudar", "brez ventilator", "samo škatla", "kutija", "škatla",
          # kompleti s še čim (niso primerljivi s samo kartico)
          "ryzen", "intel", "i5 ", "i7 ", "i9 ", "procesor", "matična", "maticna", "monitor",
          "ps5", "konzol", "paket", "+ ", "riser", "nosilec",
          "kabel", "adapter", "vodno", "waterblock", "ventilator za"]
PLUS = ["garancij", "račun", "jamstv", "nova", "novo", "zapakiran", "neodprt"]

MIN_CENA = 40
MIN_VZORCEV = 100        # tržna cena šele iz vsaj 100 primerljivih oglasov
MAX_STRANI = 15          # največ strani na iskanje, dokler model nima 100 oglasov
DNI_ZGODOVINE = 60
REZERVA = 0.05

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "sl-SI,sl;q=0.9,hr;q=0.8,en;q=0.7",
}
MODEL_RE = re.compile(
    r"(?:rtx|geforce)?\s*-?\s*(30[5-9]0|40[6-9]0|50[6-9]0)\s*-?\s*(ti\s*super|ti|super)?\b", re.I)
VRAM_RE = re.compile(r"\b(6|8|10|12|16|20|24|32)\s*gb?\b", re.I)
CENA_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,(\d{1,2}))?\s*(?:€|eur)", re.I)
VRAM_POMEMBEN = {"RTX 3060": {8, 12}, "RTX 4060 Ti": {8, 16}, "RTX 3080": {10, 12},
                 "RTX 5060 Ti": {8, 16}}


# ----------------------------------------------------------------- nastavitve
def nalozi_nastavitve():
    n = dict(PRIVZETO)
    try:
        with open(NAST_POT, encoding="utf-8") as f:
            n.update(json.load(f))
    except Exception:
        pass
    return n


def shrani_nastavitve(n):
    with open(NAST_POT, "w", encoding="utf-8") as f:
        json.dump(n, f)


def zagon_ob_windows(vklop):
    """Doda/odstrani bližnjico v mapo Startup, da se skener zažene ob vklopu računalnika."""
    mapa = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    pot = os.path.join(mapa, "RTX skener.bat")
    if not os.path.isdir(mapa):
        return
    if vklop:
        if getattr(sys, "frozen", False):
            ukaz = f'start "" "{sys.executable}" --zazeni'
        else:
            ukaz = f'start "" "{sys.executable.replace("python.exe", "pythonw.exe")}" "{os.path.abspath(__file__)}" --zazeni'
        with open(pot, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n" + ukaz + "\r\n")
    elif os.path.exists(pot):
        os.remove(pot)


# ----------------------------------------------------------------- razčlenjevanje
def zaznaj_model(naslov):
    t = naslov.lower().replace("-", " ")
    t = re.sub(r"(\d{4})(ti|super)", r"\1 \2", t)
    if "rtx" not in t and "geforce" not in t:
        return None
    m = MODEL_RE.search(t)
    if not m:
        return None
    dodatek = re.sub(r"\s+", " ", (m.group(2) or "").strip()).title()
    model = f"RTX {m.group(1)}" + (f" {dodatek}" if dodatek else "")
    if model in VRAM_POMEMBEN:
        v = VRAM_RE.search(t)
        model += f" {v.group(1)}GB" if v and int(v.group(1)) in VRAM_POMEMBEN[model] else " ?GB"
    return model


def razcleni_ceno(besedilo):
    m = CENA_RE.search(besedilo.replace("\xa0", " "))
    if not m:
        return None
    return int(re.sub(r"[.\s]", "", m.group(1))) + (float("0." + m.group(2)) if m.group(2) else 0)


def izlocen(naslov):
    t = naslov.lower()
    return any(b in t for b in IZLOCI)


def razcleni_stran(html, osnova):
    soup = BeautifulSoup(html, "html.parser")
    oglasi, videni = [], set()
    for el in soup.select(".entity-title a, h3 a[href*='oglas'], h3 a[href$='.html']"):
        naslov, href = el.get_text(" ", strip=True), el.get("href", "")
        if not naslov or not href:
            continue
        url = (href if href.startswith("http") else osnova + "/" + href.lstrip("/")).split("?")[0]
        if url in videni:
            continue
        videni.add(url)
        kartica = el.find_parent(["article", "li"]) or el.parent
        cena_el = kartica.select_one(".price, .entity-prices, [class*='price']")
        cena = razcleni_ceno(cena_el.get_text(" ", strip=True)) if cena_el else None
        if cena is None:
            cena = razcleni_ceno(kartica.get_text(" ", strip=True))
        oglasi.append({"naslov": naslov, "url": url, "cena": cena,
                       "opis": kartica.get_text(" ", strip=True)})
    return oglasi


# ----------------------------------------------------------------- baza
def baza():
    db = sqlite3.connect(DB_POT, timeout=30)
    db.execute("""CREATE TABLE IF NOT EXISTS oglasi (
        url TEXT PRIMARY KEY, vir TEXT, model TEXT, naslov TEXT, cena REAL,
        prvic_viden TEXT, opozorjeno INTEGER DEFAULT 0, ponovitev INTEGER DEFAULT 0,
        trg REAL, zasluzek REAL)""")
    return db


def primerljive_cene(db, model):
    """Cene primerljivih oglasov: isti model (in VRAM), zadnjih 60 dni, brez ponovitev
    in brez skrajnosti (pod 50 % ali nad 160 % mediane - dodatki, kompleti, napačne cene)."""
    od = (datetime.now() - timedelta(days=DNI_ZGODOVINE)).isoformat()
    cene = sorted(r[0] for r in db.execute(
        "SELECT cena FROM oglasi WHERE model=? AND prvic_viden>=? AND cena>=? AND ponovitev=0",
        (model, od, MIN_CENA)))
    if not cene:
        return []
    med = statistics.median(cene)
    return [c for c in cene if 0.5 * med <= c <= 1.6 * med]


def trzna_cena(db, model):
    """Povprečje vsaj MIN_VZORCEV primerljivih oglasov (odrezanih 10 % najnižjih in najvišjih)."""
    cene = primerljive_cene(db, model)
    if len(cene) < MIN_VZORCEV:
        return None, len(cene)
    rez = len(cene) // 10
    sred = cene[rez:len(cene) - rez]
    return statistics.mean(sred), len(cene)


def potrebuje_vec(db, q):
    """Ali ima kateri model, ki ga pokrije iskanje q, še manj kot MIN_VZORCEV oglasov?"""
    osnova = "RTX " + q.split()[1]
    dodatek = " ".join(w.title() for w in q.split()[2:])
    vzorec = osnova + (" " + dodatek if dodatek else "")
    modeli = [r[0] for r in db.execute("SELECT DISTINCT model FROM oglasi WHERE model LIKE ?",
                                       (vzorec + "%",))]
    if dodatek == "":   # 'rtx 4070' ne sme šteti 4070 Super/Ti
        modeli = [m for m in modeli if m == osnova or m.startswith(osnova + " ") and m.endswith("GB")
                  and not any(x in m for x in ("Ti", "Super"))]
    if not modeli:
        return True
    return any(len(primerljive_cene(db, m)) < MIN_VZORCEV for m in modeli)


def zadnji_posli(db, n=50):
    return db.execute("SELECT model, cena, zasluzek, vir, naslov, url, prvic_viden FROM oglasi "
                      "WHERE opozorjeno=1 ORDER BY prvic_viden DESC LIMIT ?", (n,)).fetchall()


def tabela_cen(db, popust):
    vrstice = []
    for (model,) in db.execute("SELECT DISTINCT model FROM oglasi ORDER BY model").fetchall():
        trg, n = trzna_cena(db, model)
        if trg:
            vrstice.append((model, f"{trg:.0f} €", f"{trg * (1 - popust / 100):.0f} €", n))
        else:
            vrstice.append((model, f"zbiram ({n}/{MIN_VZORCEV})", "–", n))
    return vrstice


# ----------------------------------------------------------------- obvestila
def toast(naslov, besedilo, url):
    try:
        from winotify import Notification, audio
        n = Notification(app_id=APP, title=naslov, msg=besedilo, launch=url, duration="long")
        n.set_audio(audio.Default, loop=False)
        n.add_actions(label="Odpri oglas", launch=url)
        n.show()
    except Exception as e:
        print("obvestilo:", e, naslov)


# ----------------------------------------------------------------- skener
class Skener:
    def __init__(self, nastavitve, ob_poslu=None):
        self.nast = nastavitve
        self.ob_poslu = ob_poslu
        self.stop = threading.Event()
        self.nit = None
        self.stanje = "Skener še ni bil zagnan."
        self.cakajoci = []   # posli iz tega pregleda -> eno skupno obvestilo

    def tece(self):
        return self.nit is not None and self.nit.is_alive() and not self.stop.is_set()

    def zazeni(self):
        if self.tece():
            return
        self.stop.clear()
        self.nit = threading.Thread(target=self._zanka, daemon=True)
        self.nit.start()

    def ustavi(self):
        self.stop.set()
        self.stanje = "Ustavljen."

    def _zanka(self):
        db = baza()
        while not self.stop.is_set():
            ura = datetime.now().strftime("%H:%M")
            try:
                self.cakajoci = []
                novi, posli, dnevnik = self._pregled(db)
                self._obvesti()
                if not self.stop.is_set():
                    self.stanje = f"Zadnji pregled ob {ura} · novih oglasov: {novi} · poslov: {posli}\n{dnevnik}"
            except Exception as e:
                self.stanje = f"Napaka ob {ura}: {e}"
            self.stop.wait(self.nast["interval"] * 60 + random.uniform(0, 45))
        db.close()

    def _posel(self, db, o, model, vir, trg, n, znizano_od=None):
        if not trg:
            return False
        z = trg * (1 - REZERVA) - o["cena"] - STROSKI.get(vir, 0)
        if o["cena"] > trg * (1 - self.nast["popust"] / 100) or z < self.nast["min_zasluzek"]:
            return False
        # isti oglas že javljen (ponovno objavljen ali hkrati na Bolhi in Njuškalu) -> brez obvestila
        teden = (datetime.now() - timedelta(days=7)).isoformat()
        if db.execute("SELECT 1 FROM oglasi WHERE opozorjeno=1 AND lower(naslov)=? AND url<>? "
                      "AND prvic_viden>=?", (o["naslov"].lower(), o["url"], teden)).fetchone():
            db.execute("UPDATE oglasi SET opozorjeno=2 WHERE url=?", (o["url"],))
            db.commit()
            return False
        pod = (1 - o["cena"] / trg) * 100
        plus = sorted({b for b in PLUS if b in o["opis"].lower()})
        naslov = f"{model} {o['cena']:.0f} € → zaslužek ~{z:.0f} €"
        vrstice = [o["naslov"], f"{vir} · {pod:.0f} % pod trgom (povprečje {trg:.0f} € iz {n} oglasov)"]
        if znizano_od:
            vrstice.append(f"ZNIŽANO s {znizano_od:.0f} €")
        if plus:
            vrstice.append("✓ " + ", ".join(plus))
        db.execute("UPDATE oglasi SET opozorjeno=1, trg=?, zasluzek=? WHERE url=?", (trg, z, o["url"]))
        db.commit()
        self.cakajoci.append((z, naslov, "\n".join(vrstice), o["url"]))
        if self.ob_poslu:
            self.ob_poslu()
        return True

    def _obvesti(self):
        """Največ ENO obvestilo na pregled: en posel -> podrobno, več poslov -> povzetek."""
        if not self.cakajoci or not self.nast.get("obvestila", True):
            return
        self.cakajoci.sort(reverse=True)
        if len(self.cakajoci) == 1:
            _, naslov, besedilo, url = self.cakajoci[0]
            toast(naslov, besedilo, url)
        else:
            vrstice = [n for _, n, _, _ in self.cakajoci[:4]]
            if len(self.cakajoci) > 4:
                vrstice.append(f"... in še {len(self.cakajoci) - 4}")
            toast(f"{len(self.cakajoci)} ugodnih oglasov", "\n".join(vrstice), self.cakajoci[0][3])

    def _pregled(self, db):
        novi = posli = 0
        dnevnik = []
        for vir, predloga in VIRI.items():
            osnova = re.match(r"https?://[^/]+", predloga).group(0)
            skupaj, napaka = 0, None
            for q in ISKALNI_NIZI:
                # Dokler model nima 100 primerljivih oglasov, bere več strani (tudi starejše oglase).
                strani = MAX_STRANI if potrebuje_vec(db, q) else 1
                if strani > 1:
                    self.stanje = f"Zbiram oglase za tržno ceno: {vir} · {q.upper()} ..."
                for p in range(1, strani + 1):
                    if self.stop.is_set():
                        return novi, posli, "\n".join(dnevnik)
                    url = predloga.format(q=requests.utils.quote(q), p=p)
                    try:
                        r = requests.get(url, headers=HEADERS, timeout=20)
                        r.raise_for_status()
                    except Exception as e:
                        napaka = str(e)[:90]
                        break
                    oglasi = razcleni_stran(r.text, osnova)
                    skupaj += len(oglasi)
                    znanih = 0
                    for o in oglasi:
                        model = zaznaj_model(o["naslov"])
                        if (not model or o["cena"] is None or o["cena"] < MIN_CENA
                                or izlocen(o["naslov"])):
                            continue
                        star = db.execute("SELECT cena, opozorjeno FROM oglasi WHERE url=?",
                                          (o["url"],)).fetchone()
                        if star:
                            znanih += 1
                            if o["cena"] < star[0] - 1:
                                db.execute("UPDATE oglasi SET cena=? WHERE url=?", (o["cena"], o["url"]))
                                if not star[1]:
                                    trg, n = trzna_cena(db, model)
                                    posli += self._posel(db, o, model, vir, trg, n, star[0])
                            continue
                        ponovitev = db.execute(
                            "SELECT 1 FROM oglasi WHERE naslov=? AND cena=? AND vir=?",
                            (o["naslov"], o["cena"], vir)).fetchone() is not None
                        trg, n = trzna_cena(db, model)
                        db.execute("INSERT INTO oglasi (url, vir, model, naslov, cena, prvic_viden, "
                                   "ponovitev) VALUES (?,?,?,?,?,?,?)",
                                   (o["url"], vir, model, o["naslov"], o["cena"],
                                    datetime.now().isoformat(), int(ponovitev)))
                        novi += 1
                        if not ponovitev:
                            posli += self._posel(db, o, model, vir, trg, n)
                    db.commit()
                    self.stop.wait(random.uniform(2, 5))
                    # konec rezultatov ali (pri rednem pregledu) same že znane oglase
                    if not oglasi or (p > 1 and znanih == len(oglasi)):
                        break
            vrstica = f"{vir}: prebranih {skupaj} oglasov"
            if napaka:
                vrstica += f" (napaka: {napaka})"
            dnevnik.append(vrstica)
        return novi, posli, "\n".join(dnevnik)


# ----------------------------------------------------------------- okno
def main():
    import tkinter as tk
    from tkinter import ttk, messagebox

    nast = nalozi_nastavitve()
    root = tk.Tk()
    root.title(APP)
    root.geometry("820x660")
    root.minsize(600, 500)
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72)
    except Exception:
        pass

    ZELENA, RDECA = "#2E7D32", "#C62828"
    stil = ttk.Style()
    if "vista" in stil.theme_names():
        stil.theme_use("vista")
    stil.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
    stil.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    osvezi_zdaj = threading.Event()
    skener = Skener(nast, ob_poslu=osvezi_zdaj.set)
    db_ui = baza()

    okvir = ttk.Frame(root, padding=16)
    okvir.pack(fill="both", expand=True)

    ttk.Label(okvir, text="RTX skener", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    ttk.Label(okvir, text="Bolha + Njuškalo · RTX 30/40/50 · obvestilo, ko je kartica pod tržno ceno",
              foreground="#666", font=("Segoe UI", 10)).pack(anchor="w")

    def preklopi():
        if skener.tece():
            skener.ustavi()
        else:
            skener.zazeni()
        osvezi()

    gumb = tk.Button(okvir, font=("Segoe UI", 18, "bold"), fg="white", relief="flat",
                     activeforeground="white", cursor="hand2", command=preklopi, height=1, pady=10)
    gumb.pack(fill="x", pady=(16, 8))

    lbl_stanje = ttk.Label(okvir, font=("Segoe UI", 10), justify="left", wraplength=760)
    lbl_stanje.pack(anchor="w", fill="x")
    okvir.bind("<Configure>", lambda e: lbl_stanje.configure(wraplength=max(300, e.width - 20)))

    zavihki = ttk.Notebook(okvir)
    zavihki.pack(fill="both", expand=True, pady=(12, 0))

    # -- zavihek: ugodni oglasi
    z1 = ttk.Frame(zavihki, padding=8)
    zavihki.add(z1, text="  Ugodni oglasi  ")
    stolpci = ("model", "cena", "zasluzek", "vir", "naslov")
    tabela = ttk.Treeview(z1, columns=stolpci, show="headings")
    for s, ime, w, sidro in [("model", "Model", 140, "w"), ("cena", "Cena", 70, "e"),
                             ("zasluzek", "Zaslužek", 80, "e"), ("vir", "Vir", 80, "w"),
                             ("naslov", "Naslov", 380, "w")]:
        tabela.heading(s, text=ime)
        tabela.column(s, width=w, anchor=sidro, stretch=(s == "naslov"))
    drsnik = ttk.Scrollbar(z1, orient="vertical", command=tabela.yview)
    tabela.configure(yscrollcommand=drsnik.set)
    tabela.pack(side="left", fill="both", expand=True)
    drsnik.pack(side="right", fill="y")
    povezave = {}

    def odpri(_=None):
        for iid in tabela.selection():
            if iid in povezave:
                webbrowser.open(povezave[iid])
    tabela.bind("<Double-1>", odpri)
    tabela.bind("<Return>", odpri)
    lbl_prazno = ttk.Label(z1, text="Še ni ugodnih oglasov. Ko se pojavi, dobiš Windows obvestilo.\n"
                                    "Dvoklik na vrstico odpre oglas.", foreground="#666")

    # -- zavihek: tržne cene
    z2 = ttk.Frame(zavihki, padding=8)
    zavihki.add(z2, text="  Tržne cene  ")
    cene = ttk.Treeview(z2, columns=("model", "trg", "meja", "n"), show="headings")
    for s, ime, w, sidro in [("model", "Model", 180, "w"), ("trg", "Povprečna cena", 140, "e"),
                             ("meja", "Posel pod", 120, "e"), ("n", "Št. oglasov", 100, "e")]:
        cene.heading(s, text=ime)
        cene.column(s, width=w, anchor=sidro)
    cene.pack(fill="both", expand=True)

    # -- zavihek: nastavitve
    z3 = ttk.Frame(zavihki, padding=16)
    zavihki.add(z3, text="  Nastavitve  ")
    v_popust = tk.IntVar(value=nast["popust"])
    v_zasl = tk.IntVar(value=nast["min_zasluzek"])
    v_int = tk.IntVar(value=nast["interval"])
    v_zagon = tk.BooleanVar(value=nast["ob_zagonu"])
    v_obv = tk.BooleanVar(value=nast.get("obvestila", True))
    for i, (oznaka, var, od, do) in enumerate([
            ("Popust pod tržno ceno (%)", v_popust, 5, 80),
            ("Najmanjši zaslužek (€)", v_zasl, 0, 1000),
            ("Pregled vsakih (minut)", v_int, 2, 120)]):
        ttk.Label(z3, text=oznaka).grid(row=i, column=0, sticky="w", pady=6, padx=(0, 16))
        ttk.Spinbox(z3, from_=od, to=do, textvariable=var, width=8).grid(row=i, column=1, sticky="w")
    ttk.Checkbutton(z3, text="Zaženi skener ob vklopu računalnika", variable=v_zagon) \
        .grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 2))
    ttk.Checkbutton(z3, text="Pošiljaj Windows obvestila (posli se vedno vidijo v zavihku)",
                    variable=v_obv).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 6))

    def shrani():
        try:
            nast["popust"] = max(5, min(80, int(v_popust.get())))
            nast["min_zasluzek"] = max(0, int(v_zasl.get()))
            nast["interval"] = max(2, int(v_int.get()))
        except (tk.TclError, ValueError):
            messagebox.showerror(APP, "Vpiši cela števila.")
            return
        nast["ob_zagonu"] = bool(v_zagon.get())
        nast["obvestila"] = bool(v_obv.get())
        shrani_nastavitve(nast)
        try:
            zagon_ob_windows(nast["ob_zagonu"])
        except Exception as e:
            messagebox.showwarning(APP, f"Samodejnega zagona ni bilo mogoče nastaviti:\n{e}")
        messagebox.showinfo(APP, "Nastavitve shranjene.")
        osvezi()
    ttk.Button(z3, text="Shrani nastavitve", command=shrani).grid(row=7, column=0, sticky="w", pady=12)
    ttk.Label(z3, text=f"Podatki: {MAPA}", foreground="#888").grid(row=8, column=0, columnspan=2, sticky="w")

    # -- osveževanje
    zadnji_kljuc = [None]

    def osvezi():
        t = skener.tece()
        barva = RDECA if t else ZELENA
        gumb.configure(text="■   USTAVI" if t else "▶   ZAŽENI", bg=barva, activebackground=barva)
        lbl_stanje.configure(text=("● Teče — " if t else "○ Ne teče — ") + skener.stanje)
        posli = zadnji_posli(db_ui)
        kljuc = tuple(p[5] for p in posli)
        if kljuc != zadnji_kljuc[0]:
            zadnji_kljuc[0] = kljuc
            tabela.delete(*tabela.get_children())
            povezave.clear()
            for model, cena, zasl, vir, naslov, url, _ in posli:
                iid = tabela.insert("", "end", values=(model, f"{cena:.0f} €", f"~{(zasl or 0):.0f} €", vir, naslov))
                povezave[iid] = url
            if posli:
                lbl_prazno.place_forget()
            else:
                lbl_prazno.place(relx=0.5, rely=0.4, anchor="center")
        cene.delete(*cene.get_children())
        for vrstica in tabela_cen(db_ui, nast["popust"]):
            cene.insert("", "end", values=vrstica)

    def zanka_ui():
        osvezi()
        root.after(3000, zanka_ui)

    def zapri():
        if skener.tece() and not messagebox.askyesno(APP, "Skener teče. Ga ustavim in zaprem program?"):
            return
        skener.ustavi()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", zapri)

    zanka_ui()
    if "--zazeni" in sys.argv:
        skener.zazeni()
        root.iconify()
    if "--test" in sys.argv:          # samo za samodejni preizkus pri gradnji
        def posnetek():
            try:
                from PIL import ImageGrab
                root.update()
                x, y = root.winfo_rootx(), root.winfo_rooty()
                ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save("posnetek.png")
            except Exception as e:
                print("posnetek:", e)
            root.destroy()
        root.after(2500, posnetek)
    root.mainloop()


if __name__ == "__main__":
    main()
