package si.jakob.rtxskener

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import android.net.Uri

object Obvestila {
    const val KANAL_STANJE = "stanje"
    const val KANAL_POSLI = "posli"
    const val ID_STANJE = 1

    fun pripravi(c: Context) {
        val nm = c.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(KANAL_STANJE, "Stanje skenerja", NotificationManager.IMPORTANCE_LOW)
        )
        val posli = NotificationChannel(KANAL_POSLI, "Ugodni oglasi", NotificationManager.IMPORTANCE_HIGH)
        posli.enableVibration(true)
        posli.vibrationPattern = longArrayOf(0, 300, 150, 300)
        nm.createNotificationChannel(posli)
    }

    fun stanje(c: Context, besedilo: String): Notification {
        val odpri = PendingIntent.getActivity(
            c, 0, Intent(c, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        val ustavi = PendingIntent.getService(
            c, 1, Intent(c, SkenerService::class.java).setAction(SkenerService.USTAVI),
            PendingIntent.FLAG_IMMUTABLE
        )
        val akcija = Notification.Action.Builder(null as Icon?, "Ustavi", ustavi).build()
        return Notification.Builder(c, KANAL_STANJE)
            .setSmallIcon(R.drawable.ic_obvestilo)
            .setContentTitle("RTX skener teče")
            .setContentText(besedilo)
            .setOngoing(true)
            .setContentIntent(odpri)
            .addAction(akcija)
            .build()
    }

    fun posel(c: Context, naslov: String, besedilo: String, url: String) {
        val pi = PendingIntent.getActivity(
            c, url.hashCode(), Intent(Intent.ACTION_VIEW, Uri.parse(url)),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n = Notification.Builder(c, KANAL_POSLI)
            .setSmallIcon(R.drawable.ic_obvestilo)
            .setContentTitle(naslov)
            .setContentText(besedilo.lineSequence().first())
            .setStyle(Notification.BigTextStyle().bigText(besedilo))
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        var id = url.hashCode()
        if (id == ID_STANJE) id = 2
        c.getSystemService(NotificationManager::class.java).notify(id, n)
    }
}
