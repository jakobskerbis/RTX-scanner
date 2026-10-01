package si.jakob.rtxskener

import android.content.ContentValues
import android.content.Context
import android.database.DatabaseUtils
import android.database.sqlite.SQLiteDatabase
import org.jsoup.Jsoup
import java.net.URLEncoder
import kotlin.random.Random

data class Oglas(val naslov: String, val url: String, val cena: Double?, val opis: String)
data class Posel(
    val model: String, val naslov: String, val url: String, val vir: String,
    val cena: Double, val zasluzek: Double
)
data class Rezultat(val novi: Int, val posli: Int, val dnevnik: String)

object Skener {
    private val VIRI = linkedMapOf(
        "Bolha" to "https://www.bolha.com/?ctl=search_ads&keywords=%s&sort=new&page=%d",
        "Njuškalo" to "https://www.njuskalo.hr/?ctl=search_ads&keywords=%s&sort=new&page=%d"
    )
    private val STROSKI = mapOf("Bolha" to 5.0, "Njuškalo" to 25.0)
    private val NIZI = listOf(
        "rtx 3060", "rtx 3070", "rtx 3080", "rtx 3090",
        "rtx 4060", "rtx 4070", "rtx 4080", "rtx 4090",
        "rtx 5060", "rtx 5070", "rtx 5080", "rtx 5090"
    )
    private val IZLOCI = listOf(
        "kupim", "iščem", "iscem", "menjam", "zamenjam", "okvar", "defekt", "ne dela",
        "za dele", "pokvar", "prenosnik", "laptop", "notebook", "računalnik", "racunalnik",
        "gaming pc", "desktop", "komplet pc", "neispravn", "ne radi", "otkup", "kupujem",
        "računalo", "racunalo", "kućište", "blok", "hladilnik", "backplate",
        "rezervirano", "prodano", "prodana", "prodan ", "rezervirana", "artefakt",
        "mining", "rudar", "brez ventilator", "samo škatla", "kutija", "škatla"
    )
    private val PLUS = listOf("garancij", "račun", "jamstv", "nova", "novo", "zapakiran", "neodprt")

    private const val MIN_CENA = 40.0
    private const val MIN_VZORCEV = 5
    private const val DNI = 60L
    private const val REZERVA = 0.05
    private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36"

    private val MODEL_RE =
        Regex("""(?:rtx|geforce)?\s*-?\s*(30[5-9]0|40[6-9]0|50[6-9]0)\s*-?\s*(ti\s*super|ti|super)?\b""")
    private val VRAM_RE = Regex("""\b(6|8|10|12|16|20|24|32)\s*gb?\b""")
    private val CENA_RE =
        Regex("""(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,(\d{1,2}))?\s*(?:€|eur)""", RegexOption.IGNORE_CASE)
    private val VRAM_POMEMBEN = mapOf(
        "RTX 3060" to setOf(8, 12), "RTX 4060 Ti" to setOf(8, 16),
        "RTX 3080" to setOf(10, 12), "RTX 5060 Ti" to setOf(8, 16)
    )

    fun zaznajModel(naslov: String): String? {
        var t = naslov.lowercase().replace("-", " ")
        t = Regex("""(\d{4})(ti|super)""").replace(t, "\$1 \$2")
        if (!t.contains("rtx") && !t.contains("geforce")) return null
        val m = MODEL_RE.find(t) ?: return null
        val dodatek = m.groupValues[2].trim().split(Regex("""\s+"""))
            .filter { it.isNotEmpty() }
            .joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } }
        var model = "RTX " + m.groupValues[1] + (if (dodatek.isNotEmpty()) " $dodatek" else "")
        val mozni = VRAM_POMEMBEN[model]
        if (mozni != null) {
            val v = VRAM_RE.find(t)
            model += if (v != null && v.groupValues[1].toInt() in mozni) " ${v.groupValues[1]}GB" else " ?GB"
        }
        return model
    }

    fun razcleniCeno(s: String): Double? {
        val m = CENA_RE.find(s.replace(' ', ' ')) ?: return null
        val cela = m.groupValues[1].replace(Regex("""[.\s]"""), "").toDoubleOrNull() ?: return null
        val dec = m.groupValues[2]
        return cela + (if (dec.isNotEmpty()) ("0.$dec").toDouble() else 0.0)
    }

    private fun izlocen(naslov: String): Boolean {
        val t = naslov.lowercase()
        return IZLOCI.any { t.contains(it) }
    }

    private fun prenesi(url: String): List<Oglas> {
        val doc = Jsoup.connect(url)
            .userAgent(UA)
            .header("Accept-Language", "sl-SI,sl;q=0.9,hr;q=0.8,en;q=0.7")
            .timeout(20000)
            .get()
        val videni = HashSet<String>()
        val out = ArrayList<Oglas>()
        for (el in doc.select(".entity-title a, h3 a[href*=oglas], h3 a[href$=.html]")) {
            val naslov = el.text().trim()
            val u = el.attr("abs:href").substringBefore('?')
            if (naslov.isEmpty() || u.isEmpty() || !videni.add(u)) continue
            val kartica = el.closest("article, li") ?: el.parent() ?: continue
            val cenaEl = kartica.selectFirst(".price, .entity-prices, [class*=price]")
            val cena = cenaEl?.let { razcleniCeno(it.text()) } ?: razcleniCeno(kartica.text())
            out.add(Oglas(naslov, u, cena, kartica.text()))
        }
        return out
    }

    private fun trznaCena(db: SQLiteDatabase, model: String): Pair<Double?, Int> {
        val od = System.currentTimeMillis() - DNI * 24 * 3600 * 1000
        val cene = ArrayList<Double>()
        db.rawQuery(
            "SELECT cena FROM oglasi WHERE model=? AND prvic>=? AND cena>=? AND ponovitev=0",
            arrayOf(model, od.toString(), MIN_CENA.toString())
        ).use { while (it.moveToNext()) cene.add(it.getDouble(0)) }
        if (cene.size < MIN_VZORCEV) return Pair(null, cene.size)
        cene.sort()
        val rez = if (cene.size >= 10) cene.size / 10 else 0
        val sred = cene.subList(rez, cene.size - rez)
        return Pair(sred.average(), sred.size)
    }

    private fun preveriPosel(
        ctx: Context, db: SQLiteDatabase, o: Oglas, cena: Double, model: String, vir: String,
        trg: Double?, n: Int, znizanoOd: Double?
    ): Boolean {
        if (trg == null) return false
        val popust = Nastavitve.popust(ctx) / 100.0
        val z = trg * (1 - REZERVA) - cena - (STROSKI[vir] ?: 0.0)
        if (cena > trg * (1 - popust) || z < Nastavitve.minZasluzek(ctx)) return false
        val pod = (1 - cena / trg) * 100
        val opis = o.opis.lowercase()
        val plus = PLUS.filter { opis.contains(it) }
        val naslov = "$model ${cena.toInt()} € → zaslužek ~${z.toInt()} €"
        val vrstice = mutableListOf(
            o.naslov,
            "$vir · ${pod.toInt()} % pod trgom (povprečje ${trg.toInt()} € iz $n oglasov)"
        )
        if (znizanoOd != null) vrstice.add("ZNIŽANO s ${znizanoOd.toInt()} €")
        if (plus.isNotEmpty()) vrstice.add("✓ " + plus.joinToString(", "))
        Obvestila.posel(ctx, naslov, vrstice.joinToString("\n"), o.url)
        db.execSQL(
            "UPDATE oglasi SET opozorjeno=1, trg=?, zasluzek=? WHERE url=?",
            arrayOf<Any>(trg, z, o.url)
        )
        return true
    }

    fun pregled(ctx: Context, strani: Int): Rezultat {
        val db = Db.get(ctx).writableDatabase
        var novi = 0
        var posli = 0
        val dnevnik = StringBuilder()
        for ((vir, predloga) in VIRI) {
            var skupaj = 0
            var napaka: String? = null
            for (q in NIZI) {
                for (p in 1..strani) {
                    val url = String.format(predloga, URLEncoder.encode(q, "UTF-8"), p)
                    val oglasi: List<Oglas>
                    try {
                        oglasi = prenesi(url)
                    } catch (e: InterruptedException) {
                        throw e
                    } catch (e: Exception) {
                        napaka = e.javaClass.simpleName + " " + (e.message ?: "")
                        break
                    }
                    skupaj += oglasi.size
                    for (o in oglasi) {
                        val model = zaznajModel(o.naslov) ?: continue
                        val cena = o.cena ?: continue
                        if (cena < MIN_CENA || izlocen(o.naslov)) continue
                        val star: Pair<Double, Int>? = db.rawQuery(
                            "SELECT cena, opozorjeno FROM oglasi WHERE url=?", arrayOf(o.url)
                        ).use { if (it.moveToFirst()) Pair(it.getDouble(0), it.getInt(1)) else null }
                        if (star != null) {
                            if (cena < star.first - 1) {
                                db.execSQL("UPDATE oglasi SET cena=? WHERE url=?", arrayOf<Any>(cena, o.url))
                                if (star.second == 0) {
                                    val (trg, n) = trznaCena(db, model)
                                    if (preveriPosel(ctx, db, o, cena, model, vir, trg, n, star.first)) posli++
                                }
                            }
                            continue
                        }
                        val ponovitev = db.rawQuery(
                            "SELECT 1 FROM oglasi WHERE naslov=? AND cena=? AND vir=?",
                            arrayOf(o.naslov, cena.toString(), vir)
                        ).use { it.moveToFirst() }
                        val (trg, n) = trznaCena(db, model)
                        val cv = ContentValues()
                        cv.put("url", o.url)
                        cv.put("vir", vir)
                        cv.put("model", model)
                        cv.put("naslov", o.naslov)
                        cv.put("cena", cena)
                        cv.put("prvic", System.currentTimeMillis())
                        cv.put("ponovitev", if (ponovitev) 1 else 0)
                        db.insert("oglasi", null, cv)
                        novi++
                        if (!ponovitev && preveriPosel(ctx, db, o, cena, model, vir, trg, n, null)) posli++
                    }
                    Thread.sleep(2000L + Random.nextLong(0, 3000))
                    if (oglasi.isEmpty()) break
                }
            }
            dnevnik.append("$vir: prebranih $skupaj oglasov")
            if (napaka != null) dnevnik.append(" (napaka: ${napaka.take(80)})")
            dnevnik.append('\n')
        }
        return Rezultat(novi, posli, dnevnik.toString().trim())
    }

    fun steviloOglasov(ctx: Context): Long =
        DatabaseUtils.queryNumEntries(Db.get(ctx).readableDatabase, "oglasi")

    fun zadnjiPosli(ctx: Context, n: Int): List<Posel> {
        val out = ArrayList<Posel>()
        Db.get(ctx).readableDatabase.rawQuery(
            "SELECT model, naslov, url, vir, cena, zasluzek FROM oglasi WHERE opozorjeno=1 " +
                "ORDER BY prvic DESC LIMIT $n", null
        ).use {
            while (it.moveToNext()) {
                out.add(
                    Posel(
                        it.getString(0), it.getString(1), it.getString(2), it.getString(3),
                        it.getDouble(4), it.getDouble(5)
                    )
                )
            }
        }
        return out
    }

    fun tabelaCen(ctx: Context): String {
        val db = Db.get(ctx).readableDatabase
        val modeli = ArrayList<String>()
        db.rawQuery("SELECT DISTINCT model FROM oglasi ORDER BY model", null)
            .use { while (it.moveToNext()) modeli.add(it.getString(0)) }
        if (modeli.isEmpty()) return "Še ni podatkov – zaženi skener."
        val popust = Nastavitve.popust(ctx) / 100.0
        return modeli.joinToString("\n") { m ->
            val (t, n) = trznaCena(db, m)
            if (t == null) String.format("%-17s (premalo oglasov: %d)", m, n)
            else String.format("%-17s ~%4d €  posel pod %4d €", m, t.toInt(), (t * (1 - popust)).toInt())
        }
    }
}
