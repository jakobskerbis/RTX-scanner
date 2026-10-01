package si.jakob.rtxskener

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var gumb: Button
    private lateinit var stanje: TextView
    private lateinit var posli: LinearLayout
    private lateinit var cene: TextView
    private lateinit var vPopust: EditText
    private lateinit var vZasluzek: EditText
    private lateinit var vInterval: EditText

    private val h = Handler(Looper.getMainLooper())
    private val osvezi = object : Runnable {
        override fun run() {
            posodobi()
            h.postDelayed(this, 3000)
        }
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun naslov(t: String) = TextView(this).apply {
        text = t
        textSize = 18f
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, dp(24), 0, dp(6))
    }

    private fun polje(koren: LinearLayout, oznaka: String, vrednost: Int): EditText {
        koren.addView(TextView(this).apply { text = oznaka; textSize = 13f })
        val e = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText(vrednost.toString())
        }
        koren.addView(e)
        return e
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val koren = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(32), dp(16), dp(32))
        }
        koren.addView(TextView(this).apply {
            text = "RTX skener"
            textSize = 28f
            setTypeface(typeface, Typeface.BOLD)
        })
        koren.addView(TextView(this).apply {
            text = "Bolha + Njuškalo · RTX 30/40/50 · opozori na oglase pod tržno ceno"
            textSize = 13f
            setTextColor(Color.GRAY)
        })

        gumb = Button(this).apply {
            textSize = 22f
            setTextColor(Color.WHITE)
            setOnClickListener { preklopi() }
        }
        koren.addView(gumb, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(80)).apply {
            topMargin = dp(20)
        })

        stanje = TextView(this).apply { textSize = 14f; setPadding(0, dp(12), 0, 0) }
        koren.addView(stanje)

        koren.addView(naslov("Ugodni oglasi"))
        posli = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        koren.addView(posli)

        koren.addView(naslov("Nastavitve"))
        vPopust = polje(koren, "Popust pod tržno ceno (%)", Nastavitve.popust(this))
        vZasluzek = polje(koren, "Najmanjši zaslužek (€)", Nastavitve.minZasluzek(this))
        vInterval = polje(koren, "Pregled vsakih (minut)", Nastavitve.interval(this))
        koren.addView(Button(this).apply {
            text = "Shrani nastavitve"
            setOnClickListener {
                Nastavitve.shrani(
                    this@MainActivity,
                    vPopust.text.toString().toIntOrNull() ?: 25,
                    vZasluzek.text.toString().toIntOrNull() ?: 40,
                    vInterval.text.toString().toIntOrNull() ?: 4
                )
                Toast.makeText(this@MainActivity, "Shranjeno", Toast.LENGTH_SHORT).show()
            }
        })

        koren.addView(naslov("Tržne cene"))
        cene = TextView(this).apply { typeface = Typeface.MONOSPACE; textSize = 12f }
        koren.addView(cene)

        setContentView(ScrollView(this).apply { addView(koren) })

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
    }

    override fun onResume() {
        super.onResume()
        h.post(osvezi)
    }

    override fun onPause() {
        super.onPause()
        h.removeCallbacks(osvezi)
    }

    private fun preklopi() {
        val i = Intent(this, SkenerService::class.java)
        if (SkenerService.tece) {
            stopService(i)
        } else {
            val pm = getSystemService(PowerManager::class.java)
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                try {
                    startActivity(
                        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName"))
                    )
                } catch (e: Exception) {
                }
            }
            startForegroundService(i)
        }
        h.postDelayed({ posodobi() }, 400)
    }

    private fun posodobi() {
        val t = SkenerService.tece
        gumb.text = if (t) "■  USTAVI" else "▶  ZAŽENI"
        gumb.setBackgroundColor(if (t) Color.rgb(198, 40, 40) else Color.rgb(46, 125, 50))
        stanje.text = (if (t) "● Teče\n" else "○ Ne teče\n") + Nastavitve.stanje(this)

        posli.removeAllViews()
        val seznam = Skener.zadnjiPosli(this, 20)
        if (seznam.isEmpty()) {
            posli.addView(TextView(this).apply {
                text = "Še ni ugodnih oglasov. Ko se pojavi, dobiš obvestilo."
                setTextColor(Color.GRAY)
            })
        }
        for (p in seznam) {
            posli.addView(TextView(this).apply {
                text = "${p.model} · ${p.cena.toInt()} € → zaslužek ~${p.zasluzek.toInt()} €\n${p.naslov} · ${p.vir}"
                textSize = 14f
                setPadding(0, dp(8), 0, dp(8))
                setTextColor(Color.rgb(21, 101, 192))
                setOnClickListener { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(p.url))) }
            })
        }
        cene.text = Skener.tabelaCen(this)
    }
}
