package si.jakob.rtxskener

import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.random.Random

class SkenerService : Service() {

    companion object {
        const val USTAVI = "si.jakob.rtxskener.USTAVI"

        @Volatile
        var tece = false
    }

    private var nit: Thread? = null
    private var wl: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == USTAVI) {
            stopSelf()
            return START_NOT_STICKY
        }
        Obvestila.pripravi(this)
        val n = Obvestila.stanje(this, "Zaganjam ...")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(Obvestila.ID_STANJE, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(Obvestila.ID_STANJE, n)
        }
        if (nit == null) {
            tece = true
            val pm = getSystemService(PowerManager::class.java)
            wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "rtxskener:skener").also { it.acquire() }
            nit = Thread { zanka() }.also { it.start() }
        }
        return START_STICKY
    }

    private fun zanka() {
        while (tece) {
            val ura = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
            try {
                val prvi = Skener.steviloOglasov(this) == 0L
                if (prvi) posodobi("Prvi zagon: berem oglase in gradim tržne cene (nekaj minut) ...")
                val r = Skener.pregled(this, if (prvi) 5 else 1)
                posodobi("Zadnji pregled $ura · novih: ${r.novi} · poslov: ${r.posli}\n${r.dnevnik}")
            } catch (e: InterruptedException) {
                break
            } catch (e: Exception) {
                posodobi("Napaka ob $ura: ${e.message}")
            }
            if (!tece) break
            try {
                Thread.sleep(Nastavitve.interval(this) * 60_000L + Random.nextLong(0, 45_000))
            } catch (e: InterruptedException) {
                break
            }
        }
    }

    private fun posodobi(s: String) {
        Nastavitve.nastaviStanje(this, s)
        if (tece) {
            getSystemService(NotificationManager::class.java)
                .notify(Obvestila.ID_STANJE, Obvestila.stanje(this, s.lineSequence().first()))
        }
    }

    override fun onDestroy() {
        tece = false
        nit?.interrupt()
        nit = null
        wl?.let { if (it.isHeld) it.release() }
        Nastavitve.nastaviStanje(this, "Ustavljen.")
        super.onDestroy()
    }
}
