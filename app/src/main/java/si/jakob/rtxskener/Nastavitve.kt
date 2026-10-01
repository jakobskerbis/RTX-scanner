package si.jakob.rtxskener

import android.content.Context

object Nastavitve {
    private fun p(c: Context) = c.getSharedPreferences("nastavitve", Context.MODE_PRIVATE)

    fun popust(c: Context): Int = p(c).getInt("popust", 25)
    fun minZasluzek(c: Context): Int = p(c).getInt("min_zasluzek", 40)
    fun interval(c: Context): Int = p(c).getInt("interval", 4)

    fun shrani(c: Context, popust: Int, minZasluzek: Int, interval: Int) {
        p(c).edit()
            .putInt("popust", popust.coerceIn(5, 80))
            .putInt("min_zasluzek", minZasluzek.coerceAtLeast(0))
            .putInt("interval", interval.coerceAtLeast(2))
            .apply()
    }

    fun stanje(c: Context): String = p(c).getString("stanje", "Skener še ni bil zagnan.") ?: ""
    fun nastaviStanje(c: Context, s: String) {
        p(c).edit().putString("stanje", s).apply()
    }
}
